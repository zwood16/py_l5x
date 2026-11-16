"""Tests for adding, replacing, renaming, removing and scheduling programs."""

import re
from pathlib import Path

import pytest
from test_layout import first_difference

from py_l5x import (
    ProgramSpec,
    Project,
    RoutineSpec,
    RungSpec,
    TagSpec,
    build_program,
    load,
    loads,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _example() -> Project:
    """Load the main example project.

    Returns:
        The parsed project.
    """
    return load(str(FIXTURES / "example.L5X"))


def _spec(name: str = "Fresh", **changes) -> ProgramSpec:
    """Create a small program spec.

    Args:
        name: The program name.
        **changes: Fields to override.

    Returns:
        A program with a few tags and a main routine.
    """
    spec = ProgramSpec(
        name,
        tags=[
            TagSpec("count", "DINT", value=5),
            TagSpec("timer", "TIMER", value={"PRE": 100}),
            TagSpec("label", "STRING", value="hi"),
        ],
        routines=[RoutineSpec("Main", rungs=[RungSpec("XIC(a)OTE(b);")])],
        main_routine="Main",
    )
    for key, value in changes.items():
        setattr(spec, key, value)
    return spec


def _scheduled(project: Project, task: str) -> list[str]:
    """List the programs scheduled in a task.

    Args:
        project: The project.
        task: The task name.

    Returns:
        The ``ScheduledProgram`` names.
    """
    element = project.tasks[task]._element
    return [
        e.get("Name") for e in element.findall("ScheduledPrograms/ScheduledProgram")
    ]


class TestAdd:
    """ProgramsCollection.add."""

    def test_sorted_position(self) -> None:
        """New programs are inserted in case-insensitive name order."""
        project = _example()
        for name in ("alpha", "Zulu", "mainprogram2", "_first"):
            project.programs.add(_spec(name))
        names = list(project.programs)
        assert names == sorted(names, key=str.lower)
        assert names.index("alpha") < names.index("AnotherProgram")

    def test_unscheduled_by_default(self) -> None:
        """Without a task the program is not scheduled anywhere."""
        project = _example()
        project.programs.add(_spec())
        assert all("Fresh" not in _scheduled(project, t) for t in project.tasks)

    def test_scheduling(self) -> None:
        """With a task the program is appended to its ScheduledPrograms."""
        project = _example()
        project.programs.add(_spec(), task="MainTask")
        assert _scheduled(project, "MainTask")[-1] == "Fresh"
        assert list(project.tasks["MainTask"].programs)[-1] == "Fresh"
        again = loads(project.to_string())
        assert "Fresh" in list(again.tasks["MainTask"].programs)

    def test_creates_scheduled_programs_container(self) -> None:
        """A task without ScheduledPrograms gets one."""
        project = _example()
        element = project.tasks["MainTask"]._element
        element.remove(element.find("ScheduledPrograms"))
        project.programs.add(_spec(), task="MainTask")
        assert _scheduled(project, "MainTask") == ["Fresh"]

    def test_unknown_task(self) -> None:
        """An unknown task raises KeyError and changes nothing."""
        project = _example()
        before = project.to_string()
        with pytest.raises(KeyError):
            project.programs.add(_spec(), task="NoTask")
        assert project.to_string() == before

    def test_unknown_type(self) -> None:
        """An unknown tag type is rejected."""
        project = _example()
        before = project.to_string()
        spec = _spec()
        spec.tags.append(TagSpec("bad", "Missing"))
        with pytest.raises(ValueError, match="unknown data type"):
            project.programs.add(spec)
        assert project.to_string() == before

    @pytest.mark.parametrize("name", ["MainProgram", "mainprogram", "MAINPROGRAM"])
    def test_name_collision(self, name: str) -> None:
        """Names matching an existing program fail, ignoring case."""
        project = _example()
        with pytest.raises(ValueError, match="already exists"):
            project.programs.add(_spec(name))

    @pytest.mark.parametrize("name", ["1a", "a__b", "a_", "x" * 41, "a b"])
    def test_invalid_name(self, name: str) -> None:
        """Invalid names are rejected."""
        with pytest.raises(ValueError):
            _example().programs.add(_spec(name))

    def test_calls_are_not_checked(self) -> None:
        """Calls to unknown instructions are accepted (documented limit)."""
        project = _example()
        routine = RoutineSpec("Main", rungs=[RungSpec("NoSuchAoi(x);")])
        project.programs.add(_spec(routines=[routine]))
        assert "Fresh" in project.programs

    def test_creates_programs_container(self) -> None:
        """A controller without programs gets the container, before Tasks."""
        project = loads(
            '<RSLogix5000Content><Controller Name="C"><Tasks/></Controller>'
            "</RSLogix5000Content>"
        )
        project.programs.add(_spec())
        assert [c.tag for c in project.controller_element] == ["Programs", "Tasks"]

    def test_element_matches_builder(self) -> None:
        """The inserted element equals build_program's output."""
        project = _example()
        spec = _spec()
        built = build_program(spec, project._type_registry)
        added = project.programs.add(spec)
        assert first_difference(built, added._element) is None

    def test_reads_back(self) -> None:
        """Tags and routines of the new program read back."""
        project = _example()
        program = project.programs.add(_spec(), task="MainTask")
        assert program.tags["count"].value == 5
        assert program.tags["timer"].to_python()["PRE"] == 100
        assert program.routines["Main"].rungs[0].text == "XIC(a)OTE(b);"
        assert program.main_routine_name == "Main"


class TestReplace:
    """ProgramsCollection.replace."""

    def test_keeps_values_for_unchanged_tags(self) -> None:
        """Tags with value=None and an unchanged type keep their data."""
        project = _example()
        program = project.programs["MainProgram"]
        program.tags["a_dint"].value = 42
        program.tags["a_timer"].members["PRE"].value = 1234
        l5k_before = program.tags["a_udt_instance"]._element.find("Data[@Format='L5K']")
        assert l5k_before is not None
        spec = program.to_spec()
        for tag in spec.tags:
            tag.value = None
        project.programs.replace(spec)
        program = project.programs["MainProgram"]
        assert program.tags["a_dint"].value == 42
        assert program.tags["a_timer"].members["PRE"].value == 1234
        # The old data (including L5K) is carried over untouched.
        kept = program.tags["a_udt_instance"]._element.find("Data[@Format='L5K']")
        assert kept is not None

    def test_type_change_rebuilds(self) -> None:
        """A changed type or dimension comes from the spec."""
        project = _example()
        program = project.programs["MainProgram"]
        program.tags["a_dint"].value = 42
        spec = program.to_spec()
        for tag in spec.tags:
            tag.value = None
        by_name = {t.name: t for t in spec.tags}
        by_name["a_dint"].data_type = "REAL"
        by_name["a_dint"].radix = "Float"
        by_name["a_sint"].dimensions = 3
        project.programs.replace(spec)
        program = project.programs["MainProgram"]
        assert program.tags["a_dint"].data_type == "REAL"
        assert program.tags["a_dint"].value_element is None
        assert program.tags["a_sint"].dimensions == (3,)
        assert program.tags["a_sint"].value_element is None

    def test_value_in_spec_wins(self) -> None:
        """A spec value replaces the current data."""
        project = _example()
        program = project.programs["MainProgram"]
        program.tags["a_dint"].value = 42
        spec = program.to_spec()
        next(t for t in spec.tags if t.name == "a_dint").value = 7
        project.programs.replace(spec)
        assert project.programs["MainProgram"].tags["a_dint"].value == 7

    def test_new_and_removed_tags_and_routines(self) -> None:
        """Added tags, dropped tags and changed routines come from the spec."""
        project = _example()
        spec = project.programs["MainProgram"].to_spec()
        spec.tags = [t for t in spec.tags if t.name != "a_dint"]
        spec.tags.append(TagSpec("brand_new", "DINT", value=9))
        spec.routines[0].rungs.append(RungSpec("NOP();"))
        project.programs.replace(spec)
        program = project.programs["MainProgram"]
        assert "a_dint" not in program.tags
        assert program.tags["brand_new"].value == 9
        assert program.routines[spec.routines[0].name].rungs[-1].text == "NOP();"

    def test_position_and_schedule_untouched(self) -> None:
        """The program stays in place and scheduled."""
        project = _example()
        names = list(project.programs)
        schedule = {t: _scheduled(project, t) for t in project.tasks}
        project.programs.replace(project.programs["MainProgram"].to_spec())
        assert list(project.programs) == names
        assert {t: _scheduled(project, t) for t in project.tasks} == schedule

    def test_round_trip_every_program(self) -> None:
        """replace(to_spec()) leaves each program identical (minus L5K)."""
        reference = _example()
        for name in list(reference.programs):
            project = _example()
            before = project.programs[name]._element
            expected = re.sub(
                r'<Data Format="L5K">.*?</Data>\r\n',
                "",
                _serialize(before),
                flags=re.DOTALL,
            )
            project.programs.replace(project.programs[name].to_spec())
            assert _serialize(project.programs[name]._element) == expected, name

    def test_atomic_on_failure(self) -> None:
        """A bad spec leaves the document byte-identical."""
        project = _example()
        before = project.to_string()
        spec = project.programs["MainProgram"].to_spec()
        spec.tags.append(TagSpec("bad", "Missing"))
        with pytest.raises(ValueError, match="unknown data type"):
            project.programs.replace(spec)
        spec = project.programs["MainProgram"].to_spec()
        spec.tags.append(TagSpec("bad2", "DINT", value="oops"))
        with pytest.raises(TypeError):
            project.programs.replace(spec)
        spec = project.programs["MainProgram"].to_spec()
        spec.main_routine = "NoSuchRoutine"
        with pytest.raises(ValueError):
            project.programs.replace(spec)
        assert project.to_string() == before

    def test_missing(self) -> None:
        """A missing program raises KeyError."""
        with pytest.raises(KeyError):
            _example().programs.replace(_spec("Nope"))


def _serialize(element) -> str:
    """Serialize an element with the writer's formatting rules.

    Args:
        element: Any element.

    Returns:
        Text using CRLF and restored CDATA.
    """
    from py_l5x.writer import to_string

    return to_string(element)


class TestRemoveRename:
    """remove and rename update the schedule."""

    def test_remove(self) -> None:
        """Removing a scheduled program removes its entry."""
        project = _example()
        project.programs.remove("AnotherProgram")
        assert "AnotherProgram" not in project.programs
        assert "AnotherProgram" not in _scheduled(project, "MainTask")
        assert _scheduled(project, "MainTask") == ["MainProgram", "Robot"]
        assert "AnotherProgram" not in loads(project.to_string()).programs

    def test_remove_unscheduled_and_missing(self) -> None:
        """An unscheduled program is removed; a missing one raises."""
        project = _example()
        project.programs.remove("Unscheduled")
        assert "Unscheduled" not in project.programs
        with pytest.raises(KeyError):
            project.programs.remove("nope")

    def test_rename(self) -> None:
        """Renaming updates the ScheduledProgram entry in place."""
        project = _example()
        renamed = project.programs.rename("Robot", "RobotCell")
        assert renamed.name == "RobotCell"
        assert _scheduled(project, "MainTask") == [
            "MainProgram",
            "AnotherProgram",
            "RobotCell",
        ]
        assert list(project.tasks["MainTask"].programs)[-1] == "RobotCell"
        assert loads(project.to_string()).programs["RobotCell"].name == "RobotCell"

    def test_rename_case_only(self) -> None:
        """A case-only rename of the program itself works."""
        project = _example()
        project.programs.rename("Robot", "ROBOT")
        assert "ROBOT" in _scheduled(project, "MainTask")

    @pytest.mark.parametrize("new", ["maINprogram", "1x", "a__b"])
    def test_rename_errors(self, new: str) -> None:
        """Taken and invalid names are rejected; nothing changes."""
        project = _example()
        before = project.to_string()
        with pytest.raises(ValueError):
            project.programs.rename("Robot", new)
        with pytest.raises(KeyError):
            project.programs.rename("nope", "x")
        assert project.to_string() == before


class TestSchedule:
    """schedule and unschedule."""

    def test_schedule_and_unschedule(self) -> None:
        """An unscheduled program can be scheduled and unscheduled again."""
        project = _example()
        project.programs.schedule("Unscheduled", "PeriodicTask")
        assert _scheduled(project, "PeriodicTask") == ["PeriodicProgram", "Unscheduled"]
        assert project.programs.unschedule("Unscheduled") == "PeriodicTask"
        assert _scheduled(project, "PeriodicTask") == ["PeriodicProgram"]

    def test_already_scheduled(self) -> None:
        """A program can be scheduled in at most one task."""
        project = _example()
        before = project.to_string()
        with pytest.raises(ValueError, match="already scheduled"):
            project.programs.schedule("Robot", "PeriodicTask")
        assert project.to_string() == before

    def test_unschedule_when_not_scheduled(self) -> None:
        """Unscheduling an unscheduled program returns None."""
        project = _example()
        before = project.to_string()
        assert project.programs.unschedule("Unscheduled") is None
        assert project.to_string() == before

    def test_unknown_names(self) -> None:
        """Unknown programs and tasks raise KeyError."""
        project = _example()
        with pytest.raises(KeyError):
            project.programs.schedule("nope", "MainTask")
        with pytest.raises(KeyError):
            project.programs.schedule("Unscheduled", "NoTask")
        with pytest.raises(KeyError):
            project.programs.unschedule("nope")

    def test_reschedule_after_unschedule(self) -> None:
        """Moving a program between tasks works via unschedule + schedule."""
        project = _example()
        project.programs.unschedule("Robot")
        project.programs.schedule("Robot", "SafetyTask")
        assert _scheduled(project, "SafetyTask") == ["SafetyProgram", "Robot"]
        assert _scheduled(project, "MainTask") == ["MainProgram", "AnotherProgram"]

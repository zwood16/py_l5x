"""Tests for py_l5x.parsers.task."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.aoi import AOIDataTypesCollection
from py_l5x.parsers.datatype import DataTypesCollection
from py_l5x.parsers.tag import TypeRegistry
from py_l5x.parsers.task import EventInfo, Task, TasksCollection

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLE_L5X = FIXTURES_DIR / "example.L5X"


@pytest.fixture
def example_tree() -> ET.ElementTree:
    """Load the example L5X file."""
    return ET.parse(str(EXAMPLE_L5X))


@pytest.fixture
def controller_element(example_tree: ET.ElementTree) -> ET.Element:
    """Extract the <Controller> element from the example L5X."""
    controller = example_tree.getroot().find("Controller")
    assert controller is not None, "Controller element not found in example.L5X"
    return controller


@pytest.fixture
def type_registry(controller_element: ET.Element) -> TypeRegistry:
    """Build a TypeRegistry from the example L5X's UDT and AOI collections."""
    return TypeRegistry(
        DataTypesCollection(controller_element),
        AOIDataTypesCollection(controller_element),
    )


@pytest.fixture
def tasks(
    controller_element: ET.Element, type_registry: TypeRegistry
) -> TasksCollection:
    """Tasks collection."""
    return TasksCollection(controller_element, type_registry)


# ---------------------------------------------------------------------------
# TasksCollection
# ---------------------------------------------------------------------------


class TestTasksCollection:
    """Tests for TasksCollection mapping behavior."""

    def test_collection_has_three_tasks(self, tasks: TasksCollection) -> None:
        """Tasks collection contains the four example tasks."""
        assert len(tasks) == 4
        assert "MainTask" in tasks
        assert "EventTask" in tasks
        assert "PeriodicTask" in tasks
        assert "SafetyTask" in tasks

    def test_iteration_order(self, tasks: TasksCollection) -> None:
        """list(tasks) preserves XML order."""
        names = list(tasks)
        assert names == ["EventTask", "MainTask", "PeriodicTask", "SafetyTask"]

    def test_getitem_returns_task(self, tasks: TasksCollection) -> None:
        """tasks["MainTask"] returns a Task instance."""
        task = tasks["MainTask"]
        assert isinstance(task, Task)

    def test_missing_key_raises_keyerror(self, tasks: TasksCollection) -> None:
        """Accessing a non-existent task raises KeyError."""
        with pytest.raises(KeyError, match="NoSuchTask"):
            _ = tasks["NoSuchTask"]


# ---------------------------------------------------------------------------
# MainTask (CONTINUOUS)
# ---------------------------------------------------------------------------


class TestMainTask:
    """Tests for the CONTINUOUS MainTask."""

    @pytest.fixture
    def main_task(self, tasks: TasksCollection) -> Task:
        """The MainTask from the example L5X."""
        return tasks["MainTask"]

    def test_name(self, main_task: Task) -> None:
        """Task name matches."""
        assert main_task.name == "MainTask"

    def test_type(self, main_task: Task) -> None:
        """MainTask type is CONTINUOUS."""
        assert main_task.type_ == "CONTINUOUS"

    def test_priority(self, main_task: Task) -> None:
        """Priority is parsed as int."""
        assert main_task.priority == 10

    def test_watchdog(self, main_task: Task) -> None:
        """Watchdog is parsed as int."""
        assert main_task.watchdog == 500

    def test_disable_update_outputs(self, main_task: Task) -> None:
        """DisableUpdateOutputs is False."""
        assert main_task.disable_update_outputs is False

    def test_inhibit_task(self, main_task: Task) -> None:
        """InhibitTask is False."""
        assert main_task.inhibit_task is False

    def test_event_info_is_none(self, main_task: Task) -> None:
        """CONTINUOUS tasks have no EventInfo."""
        assert main_task.event_info is None

    def test_description_is_empty(self, main_task: Task) -> None:
        """MainTask has no description child."""
        assert main_task.description == ""

    def test_scheduled_program_names(self, main_task: Task) -> None:
        """Scheduled programs are in XML order."""
        assert main_task.scheduled_program_names == (
            "MainProgram",
            "AnotherProgram",
            "Robot",
        )

    def test_programs_mapping(self, main_task: Task) -> None:
        """task.programs is a Mapping keyed by program name."""
        programs = main_task.programs
        assert len(programs) == 3
        assert list(programs) == ["MainProgram", "AnotherProgram", "Robot"]

    def test_programs_returns_program_instances(self, main_task: Task) -> None:
        """task.programs["MainProgram"] is a Program instance."""
        from py_l5x.parsers.program import Program

        prog = main_task.programs["MainProgram"]
        assert isinstance(prog, Program)
        assert prog.name == "MainProgram"

    def test_programs_cross_wires_to_routines(self, main_task: Task) -> None:
        """task.programs["MainProgram"].routines["MainRoutine"] is present."""
        main_prog = main_task.programs["MainProgram"]
        assert "MainRoutine" in main_prog.routines
        assert main_prog.routines["MainRoutine"].type_ == "RLL"

    def test_missing_scheduled_program_raises_keyerror(self, main_task: Task) -> None:
        """Accessing an unscheduled program raises KeyError."""
        with pytest.raises(KeyError, match="NoSuchProgram"):
            _ = main_task.programs["NoSuchProgram"]


# ---------------------------------------------------------------------------
# PeriodicTask
# ---------------------------------------------------------------------------


class TestPeriodicTask:
    """Tests for the PERIODIC PeriodicTask."""

    @pytest.fixture
    def periodic_task(self, tasks: TasksCollection) -> Task:
        """The PeriodicTask from the example L5X."""
        return tasks["PeriodicTask"]

    def test_name(self, periodic_task: Task) -> None:
        """Task name matches."""
        assert periodic_task.name == "PeriodicTask"

    def test_type(self, periodic_task: Task) -> None:
        """PeriodicTask type is PERIODIC."""
        assert periodic_task.type_ == "PERIODIC"

    def test_rate(self, periodic_task: Task) -> None:
        """Rate is parsed as float."""
        assert periodic_task.rate == 10.0

    def test_priority(self, periodic_task: Task) -> None:
        """Priority is parsed as int."""
        assert periodic_task.priority == 10

    def test_watchdog(self, periodic_task: Task) -> None:
        """Watchdog is parsed as int."""
        assert periodic_task.watchdog == 500

    def test_disable_update_outputs(self, periodic_task: Task) -> None:
        """DisableUpdateOutputs is False."""
        assert periodic_task.disable_update_outputs is False

    def test_inhibit_task(self, periodic_task: Task) -> None:
        """InhibitTask is False."""
        assert periodic_task.inhibit_task is False

    def test_event_info_is_none(self, periodic_task: Task) -> None:
        """PERIODIC tasks have no EventInfo."""
        assert periodic_task.event_info is None

    def test_description(self, periodic_task: Task) -> None:
        """Description text is extracted from CDATA."""
        assert periodic_task.description == "Periodic type task with a 10ms rate"

    def test_scheduled_program_names(self, periodic_task: Task) -> None:
        """Single scheduled program."""
        assert periodic_task.scheduled_program_names == ("PeriodicProgram",)

    def test_programs_mapping(self, periodic_task: Task) -> None:
        """task.programs contains the single scheduled program."""
        programs = periodic_task.programs
        assert len(programs) == 1
        assert "PeriodicProgram" in programs


# ---------------------------------------------------------------------------
# EventTask
# ---------------------------------------------------------------------------


class TestEventTask:
    """Tests for the EVENT EventTask."""

    @pytest.fixture
    def event_task(self, tasks: TasksCollection) -> Task:
        """The EventTask from the example L5X."""
        return tasks["EventTask"]

    def test_name(self, event_task: Task) -> None:
        """Task name matches."""
        assert event_task.name == "EventTask"

    def test_type(self, event_task: Task) -> None:
        """EventTask type is EVENT."""
        assert event_task.type_ == "EVENT"

    def test_priority(self, event_task: Task) -> None:
        """Priority is parsed as int."""
        assert event_task.priority == 15

    def test_watchdog(self, event_task: Task) -> None:
        """Watchdog is parsed as int."""
        assert event_task.watchdog == 500

    def test_disable_update_outputs(self, event_task: Task) -> None:
        """DisableUpdateOutputs is True."""
        assert event_task.disable_update_outputs is True

    def test_inhibit_task(self, event_task: Task) -> None:
        """InhibitTask is True."""
        assert event_task.inhibit_task is True

    def test_event_info_exists(self, event_task: Task) -> None:
        """EVENT tasks have an EventInfo."""
        assert event_task.event_info is not None
        assert isinstance(event_task.event_info, EventInfo)

    def test_event_info_event_trigger(self, event_task: Task) -> None:
        """EventInfo event_trigger matches."""
        assert event_task.event_info.event_trigger == "EVENT Instruction Only"

    def test_event_info_enable_timeout(self, event_task: Task) -> None:
        """EventInfo enable_timeout is True."""
        assert event_task.event_info.enable_timeout is True

    def test_description(self, event_task: Task) -> None:
        """Description text is extracted from CDATA."""
        assert event_task.description == "An example of an event taks"

    def test_scheduled_program_names(self, event_task: Task) -> None:
        """Single scheduled program."""
        assert event_task.scheduled_program_names == ("EventProgram",)

    def test_programs_mapping(self, event_task: Task) -> None:
        """task.programs contains the single scheduled program."""
        programs = event_task.programs
        assert len(programs) == 1
        assert "EventProgram" in programs

    def test_programs_returns_program_instance(self, event_task: Task) -> None:
        """task.programs["EventProgram"] is a Program instance."""
        from py_l5x.parsers.program import Program

        prog = event_task.programs["EventProgram"]
        assert isinstance(prog, Program)
        assert prog.name == "EventProgram"


# ---------------------------------------------------------------------------
# Task repr
# ---------------------------------------------------------------------------


class TestTaskRepr:
    """Tests for Task.__repr__."""

    def test_main_task_repr(self, tasks: TasksCollection) -> None:
        """Task repr includes the name."""
        assert repr(tasks["MainTask"]) == "Task('MainTask')"

    def test_event_task_repr(self, tasks: TasksCollection) -> None:
        """EventTask repr includes the name."""
        assert repr(tasks["EventTask"]) == "Task('EventTask')"

    def test_periodic_task_repr(self, tasks: TasksCollection) -> None:
        """PeriodicTask repr includes the name."""
        assert repr(tasks["PeriodicTask"]) == "Task('PeriodicTask')"


# ---------------------------------------------------------------------------
# SafetyTask
# ---------------------------------------------------------------------------


class TestSafetyTask:
    """Tests for the PERIODIC SafetyTask (Class="Safety")."""

    @pytest.fixture
    def safety_task(self, tasks: TasksCollection) -> Task:
        """The SafetyTask from the example L5X."""
        return tasks["SafetyTask"]

    def test_name(self, safety_task: Task) -> None:
        """Task name matches."""
        assert safety_task.name == "SafetyTask"

    def test_type(self, safety_task: Task) -> None:
        """SafetyTask type is PERIODIC."""
        assert safety_task.type_ == "PERIODIC"

    def test_rate(self, safety_task: Task) -> None:
        """Rate is parsed as float."""
        assert safety_task.rate == 20.0

    def test_watchdog(self, safety_task: Task) -> None:
        """Watchdog is parsed as int."""
        assert safety_task.watchdog == 20

    def test_class(self, safety_task: Task) -> None:
        """class_ reports the safety partition class."""
        assert safety_task.class_ == "Safety"

    def test_is_safety(self, safety_task: Task) -> None:
        """is_safety is True for a safety task."""
        assert safety_task.is_safety is True

    def test_scheduled_program_names(self, safety_task: Task) -> None:
        """Single scheduled safety program."""
        assert safety_task.scheduled_program_names == ("SafetyProgram",)

    def test_programs_returns_safety_program(self, safety_task: Task) -> None:
        """task.programs["SafetyProgram"] is a safety-class Program."""
        from py_l5x.parsers.program import Program

        prog = safety_task.programs["SafetyProgram"]
        assert isinstance(prog, Program)
        assert prog.name == "SafetyProgram"
        assert prog.is_safety is True

    def test_repr(self, safety_task: Task) -> None:
        """SafetyTask repr includes the name."""
        assert repr(safety_task) == "Task('SafetyTask')"


class TestNonSafetyTasksAreNotSafety:
    """Standard tasks should not be misreported as safety tasks."""

    @pytest.mark.parametrize("name", ["MainTask", "PeriodicTask", "EventTask"])
    def test_class_and_is_safety(self, tasks: TasksCollection, name: str) -> None:
        """Standard tasks report Class="Standard" and is_safety=False."""
        task = tasks[name]
        assert task.class_ == "Standard"
        assert task.is_safety is False

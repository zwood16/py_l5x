"""Tests for component export (``py_l5x.build.export``)."""

import copy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_layout import first_difference

from py_l5x import (
    AOISpec,
    DataTypeSpec,
    MemberSpec,
    ParameterSpec,
    ProgramSpec,
    Project,
    RoutineSpec,
    RungSpec,
    TagSpec,
    export_component,
    load,
    loads,
)
from py_l5x.build.export import referenced_names

FIXTURES = Path(__file__).parent / "fixtures"


def _example() -> Project:
    """Load the main example project.

    Returns:
        The parsed project.
    """
    return load(str(FIXTURES / "example.L5X"))


def _summary(project: Project) -> dict:
    """List the names (and ``Use``) in each container of an export.

    Args:
        project: An exported (or fixture) project.

    Returns:
        ``{container: [(name, use), ...] or None}`` plus the context program's
        tag names under ``"ProgTags"``.
    """
    controller = project.controller_element
    out: dict = {}
    for container in (
        "DataTypes",
        "Modules",
        "AddOnInstructionDefinitions",
        "Tags",
        "Programs",
    ):
        element = controller.find(container)
        out[container] = (
            None
            if element is None
            else [(e.get("Name"), e.get("Use")) for e in element]
        )
    program = controller.find("Programs/Program")
    if program is not None and program.get("Use") == "Context":
        tags = program.find("Tags")
        out["ProgTags"] = None if tags is None else [t.get("Name") for t in tags]
    return out


def _comparable(element: ET.Element, remove: tuple[str, ...] = ()) -> ET.Element:
    """Strip what a comparison with Studio's own export must ignore.

    Removes L5K data, the ``Class`` attribute (Studio's GUI exports omit
    ``Class="Standard"`` that the full-project export writes) and any element
    matching an XPath in *remove*.

    Args:
        element: The ``<Controller>`` element.
        remove: XPaths (relative to *element*) to delete.

    Returns:
        A stripped copy.
    """
    copy_ = copy.deepcopy(element)
    for parent in copy_.iter():
        for child in list(parent):
            if child.tag in ("Data", "DefaultData") and child.get("Format") == "L5K":
                parent.remove(child)
    for node in copy_.iter():
        if node.tag in ("AddOnInstructionDefinition", "Program", "Tag"):
            node.attrib.pop("Class", None)
    for path in remove:
        parent_path, _, tag = path.rpartition("/")
        for parent in copy_.findall(parent_path) if parent_path else [copy_]:
            for child in parent.findall(tag):
                parent.remove(child)
    return copy_


def _root_attributes(project: Project) -> dict[str, str]:
    """Return the root attributes without Studio-only extras.

    Args:
        project: An exported (or fixture) project.

    Returns:
        The attributes minus ``ExportDate``, ``ExportOptions`` and ``Owner``,
        with whitespace stripped.
    """
    return {
        k: v.strip()
        for k, v in project.root.attrib.items()
        if k not in ("ExportDate", "ExportOptions", "Owner")
    }


def _golden_cases(project: Project):
    """List the fixture exports with their targets in the example project.

    Args:
        project: The example project.

    Returns:
        ``(fixture, target, XPaths to ignore in the tree comparison)``.
    """
    routine = project.programs["MainProgram"].routines["SequenceRoutine"]
    return [
        ("A_UDT_DataType", project.data_types["A_UDT"], ()),
        ("Debounce_AOI", project.aois["Debounce"], ()),
        ("robotAlarmCode_DataType_String", project.data_types["robotAlarmCode"], ()),
        ("SequenceRoutine_Routine_RLL", routine, ()),
        # The fixture was exported from an older project: MainProgram had 30
        # tags and different routines, so only its attributes are compared.
        (
            "MainProgram_Program",
            project.programs["MainProgram"],
            ("Programs/Program/Tags", "Programs/Program/Routines"),
        ),
        # The fixture was exported with the RoutineLabels option, so its SeqCtrl
        # context routine has a <Labels> element that example.L5X lacks.
        (
            "Rung2_from_SequenceRoutine",
            routine.rungs[2],
            (
                "AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines/"
                "Routine/RLLContent/Labels",
            ),
        ),
    ]


class TestGolden:
    """Exports from example.L5X match Studio's own component exports."""

    @pytest.mark.parametrize("index", range(6))
    def test_context_sets_and_order(self, index: int) -> None:
        """The same objects, in the same order, in every container."""
        project = _example()
        fixture, target, _ = _golden_cases(project)[index]
        mine = project.export(target)
        gold = load(str(FIXTURES / f"{fixture}.L5X"))
        assert _summary(mine) == _summary(gold), fixture

    @pytest.mark.parametrize("index", range(6))
    def test_tree(self, index: int) -> None:
        """The controller tree is identical apart from the listed exclusions."""
        project = _example()
        fixture, target, remove = _golden_cases(project)[index]
        mine = project.export(target)
        gold = load(str(FIXTURES / f"{fixture}.L5X"))
        left = _comparable(mine.controller_element, remove)
        right = _comparable(gold.controller_element, remove)
        assert first_difference(left, right) is None, fixture

    @pytest.mark.parametrize("index", range(6))
    def test_root_attributes(self, index: int) -> None:
        """The root attributes equal Studio's (minus ExportDate/ExportOptions)."""
        project = _example()
        fixture, target, _ = _golden_cases(project)[index]
        mine = project.export(target)
        gold = load(str(FIXTURES / f"{fixture}.L5X"))
        assert _root_attributes(mine) == _root_attributes(gold)
        assert "ExportDate" not in mine.root.attrib

    def test_exclusions_are_explained(self) -> None:
        """The fixture differences listed above really are version differences."""
        project = _example()
        gold = load(str(FIXTURES / "MainProgram_Program.L5X"))
        old = set(gold.programs["MainProgram"].tags)
        assert len(old) == 30
        assert old < set(project.programs["MainProgram"].tags)
        gold = load(str(FIXTURES / "Rung2_from_SequenceRoutine.L5X"))
        content = gold.controller_element.find(
            "AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines/"
            "Routine/RLLContent"
        )
        assert content.find("Labels") is not None
        assert "RoutineLabels" in gold.root.get("ExportOptions")
        assert (
            _example()
            .aois["SeqCtrl"]
            .routines["Logic"]
            ._element.find("RLLContent/Labels")
            is None
        )

    def test_shape_details(self) -> None:
        """Use markers and empty containers follow Studio's exports."""
        project = _example()
        rung = project.export(
            project.programs["MainProgram"].routines["SequenceRoutine"].rungs[2]
        )
        controller = rung.controller_element
        assert controller.get("Use") == "Context"
        assert controller.find("DataTypes").text == "\n"
        program = controller.find("Programs/Program")
        assert program.get("Use") == "Context"
        routine = program.find("Routines/Routine")
        assert list(routine.attrib.items()) == [
            ("Use", "Context"),
            ("Name", "SequenceRoutine"),
        ]
        assert routine.find("RLLContent").get("Use") == "Context"
        target = routine.find("RLLContent/Rung")
        assert list(target.attrib)[:2] == ["Use", "Number"]
        assert target.get("Number") == "2"
        assert controller.find("Tags") is None
        assert controller.find("Modules") is None

    def test_program_export_has_empty_tags_container(self) -> None:
        """A Program export always has a controller-level Tags container."""
        project = _example()
        exported = project.export(project.programs["MainProgram"])
        tags = exported.controller_element.find("Tags")
        assert tags is not None
        assert tags.get("Use") == "Context"
        assert len(tags) == 0

    def test_dependencies_on_every_type(self) -> None:
        """Every UDT and AOI with user types in the file has Dependencies."""
        project = _example()
        exported = project.export(project.programs["MainProgram"])
        controller = exported.controller_element
        udt = controller.find("DataTypes/DataType[@Name='A_UDT']")
        deps = [
            (d.get("Type"), d.get("Name"))
            for d in udt.findall("Dependencies/Dependency")
        ]
        assert deps == [
            ("DataType", "simple_udt"),
            ("AddOnInstructionDefinition", "GenericInput"),
        ]
        aoi = controller.find(
            "AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name='GenericInput']"
        )
        assert [d.get("Name") for d in aoi.findall("Dependencies/Dependency")] == [
            "Debounce"
        ]


def _consistent(project: Project) -> None:
    """Check an export's types all resolve inside the file.

    Args:
        project: An exported project, re-read through the reader.
    """
    defined = set(project.data_types) | set(project.aois)
    for dependency in project.root.iter("Dependency"):
        assert dependency.get("Name") in defined, dependency.get("Name")
    for member in project.root.iter("Member"):
        type_name = member.get("DataType")
        if type_name in ("BIT", "SINT", "INT", "DINT", "LINT", "BOOL", "REAL", "LREAL"):
            continue
        if type_name in ("TIMER", "STRING", "COUNTER"):
            continue
        assert type_name in defined, type_name


class TestSpecTargets:
    """Exports of specs."""

    def test_udt_spec_with_project(self) -> None:
        """A new UDT using simple_udt brings simple_udt and its Dependencies."""
        project = _example()
        spec = DataTypeSpec(
            "NewUdt", [MemberSpec("a", "BOOL"), MemberSpec("u", "simple_udt")]
        )
        exported = project.export(spec)
        summary = _summary(exported)
        assert summary["DataTypes"] == [("NewUdt", "Target"), ("simple_udt", None)]
        assert summary["AddOnInstructionDefinitions"] is None
        target = exported.controller_element.find("DataTypes/DataType")
        deps = target.findall("Dependencies/Dependency")
        assert [d.get("Name") for d in deps] == ["simple_udt"]
        again = loads(exported.to_string())
        assert again.target.name == "NewUdt"
        _consistent(again)

    def test_aoi_spec_calls_debounce(self) -> None:
        """A new AOI calling Debounce in logic brings Debounce as context."""
        project = _example()
        spec = AOISpec(
            "Caller",
            [ParameterSpec("In1", "BOOL"), ParameterSpec("Out1", "BOOL", "Output")],
            routines=[RoutineSpec("Logic", rungs=[RungSpec("Debounce(local);")])],
        )
        exported = project.export(spec)
        summary = _summary(exported)
        assert summary["AddOnInstructionDefinitions"] == [
            ("Debounce", None),
            ("Caller", "Target"),
        ]
        assert summary["DataTypes"] == []
        assert exported.root.get("TargetRevision") == "1.0"
        again = loads(exported.to_string())
        assert again.target.name == "Caller"
        _consistent(again)

    def test_aoi_spec_with_udt_parameter(self) -> None:
        """An InOut UDT parameter brings the UDT; its AOI local brings the AOI."""
        project = _example()
        spec = AOISpec(
            "UsesTypes",
            [ParameterSpec("u", "simple_udt", "InOut")],
            [],
            [RoutineSpec("Logic", rungs=[RungSpec("NOP();")])],
        )
        spec.local_tags = []
        exported = project.export(spec)
        assert _summary(exported)["DataTypes"] == [("simple_udt", None)]

    def test_program_spec_references_controller_tags(self) -> None:
        """Controller tags used in logic become context, with their types."""
        project = _example()
        spec = ProgramSpec(
            "Uses",
            tags=[TagSpec("local_count", "DINT", value=3)],
            routines=[
                RoutineSpec(
                    "Main",
                    rungs=[
                        RungSpec("XIC(ALLOWABLE_ALARMS[0].LEN)OTE(local_count);"),
                        RungSpec("XIC(Local:1:I.Pt00.Data)OTE(local_count);"),
                    ],
                )
            ],
            main_routine="Main",
        )
        exported = project.export(spec)
        summary = _summary(exported)
        assert summary["Tags"] == [("ALLOWABLE_ALARMS", None)]
        assert summary["DataTypes"] == [("robotAlarmCode", None)]
        assert summary["Modules"] == [
            ("Local", "Reference"),
            ("Test_Input_Module", "Reference"),
        ]
        assert summary["Programs"] == [("Uses", "Target")]
        again = loads(exported.to_string())
        assert again.target.name == "Uses"
        assert again.programs["Uses"].tags["local_count"].value == 3
        _consistent(again)

    def test_program_spec_own_tags_are_not_context(self) -> None:
        """Names of the program's own tags are not exported as controller tags."""
        project = _example()
        spec = ProgramSpec(
            "Own",
            tags=[TagSpec("ALLOWABLE_ALARMS", "DINT")],
            routines=[
                RoutineSpec("Main", rungs=[RungSpec("XIC(ALLOWABLE_ALARMS)NOP();")])
            ],
        )
        assert _summary(project.export(spec))["Tags"] == []

    def test_tag_spec_and_alias(self) -> None:
        """A controller TagSpec is a controller target; types come along."""
        project = _example()
        exported = project.export(TagSpec("newtag", "A_UDT", value={"a_dint": 4}))
        summary = _summary(exported)
        assert summary["Tags"] == [("newtag", "Target")]
        assert summary["DataTypes"] == [("A_UDT", None), ("simple_udt", None)]
        assert [n for n, _ in summary["AddOnInstructionDefinitions"]] == [
            "Debounce",
            "GenericInput",
        ]
        assert exported.root.get("TargetType") == "Tag"
        again = loads(exported.to_string())
        assert again.controller_tags["newtag"].to_python()["a_dint"] == 4

    def test_without_project_atomic_only(self) -> None:
        """Without a project only atomic and built-in types are allowed."""
        exported = export_component(TagSpec("n", "DINT", value=5))
        assert exported.controller.name == "Exported"
        assert exported.controller_tags["n"].value == 5
        exported = export_component(
            DataTypeSpec("T", [MemberSpec("t", "TIMER"), MemberSpec("d", "DINT")])
        )
        assert _summary(exported)["DataTypes"] == [("T", "Target")]
        with pytest.raises(ValueError, match="unresolvable data type"):
            export_component(DataTypeSpec("T", [MemberSpec("u", "simple_udt")]))
        with pytest.raises(ValueError):
            export_component(TagSpec("t", "simple_udt"))

    def test_loaded_objects_need_a_project(self) -> None:
        """Loaded objects without a project are refused."""
        with pytest.raises(ValueError, match="need the project"):
            export_component(_example().data_types["A_UDT"])

    def test_unresolvable_types(self) -> None:
        """Unknown member and tag types raise ValueError."""
        project = _example()
        with pytest.raises(ValueError, match="unresolvable data type 'Missing'"):
            project.export(DataTypeSpec("T", [MemberSpec("m", "Missing")]))
        with pytest.raises(ValueError, match="unresolvable data type 'Missing'"):
            project.export(
                ProgramSpec("P", tags=[TagSpec("t", "Missing")], routines=[])
            )

    def test_controller_name(self) -> None:
        """The controller name comes from the argument, else the project."""
        project = _example()
        spec = TagSpec("n", "DINT")
        assert project.export(spec).controller.name == project.controller.name
        assert project.export(spec, controller_name="Plant").controller.name == "Plant"


class TestMultipleTargets:
    """Several targets of one kind."""

    def test_two_udts(self) -> None:
        """Targets come first, then context; TargetName is the first."""
        project = _example()
        exported = project.export(
            [project.data_types["robotAlarmCode"], project.data_types["A_UDT"]]
        )
        summary = _summary(exported)
        assert summary["DataTypes"] == [
            ("robotAlarmCode", "Target"),
            ("A_UDT", "Target"),
            ("simple_udt", None),
        ]
        assert exported.root.get("TargetName") == "robotAlarmCode"
        assert exported.root.get("TargetCount") == "2"
        assert len(list(exported.root.iter("DataType"))) == 3
        assert len(exported.controller_element.findall(".//*[@Use='Target']")) == 2

    def test_two_aois_in_project_order(self) -> None:
        """AOI targets and context are in project order."""
        project = _example()
        exported = project.export(
            [project.aois["GenericInput"], project.aois["Debounce"]]
        )
        assert _summary(exported)["AddOnInstructionDefinitions"] == [
            ("Debounce", "Target"),
            ("GenericInput", "Target"),
        ]

    def test_two_rungs(self) -> None:
        """Rungs of one routine export together."""
        project = _example()
        routine = project.programs["MainProgram"].routines["SequenceRoutine"]
        exported = project.export([routine.rungs[0], routine.rungs[2]])
        rungs = exported.controller_element.findall(
            "Programs/Program/Routines/Routine/RLLContent/Rung"
        )
        assert [r.get("Number") for r in rungs] == ["0", "2"]
        assert exported.root.get("TargetCount") == "2"

    def test_mixed_kinds_raise(self) -> None:
        """Mixed kinds are refused."""
        project = _example()
        with pytest.raises(ValueError, match="one kind"):
            project.export([project.data_types["A_UDT"], project.aois["Debounce"]])
        with pytest.raises(ValueError, match="one kind"):
            project.export([project.data_types["A_UDT"], TagSpec("t", "DINT")])
        with pytest.raises(ValueError, match="no targets"):
            project.export([])
        with pytest.raises(TypeError):
            project.export(42)

    def test_rungs_of_different_routines_raise(self) -> None:
        """Rungs must share a routine; routines must share a program."""
        project = _example()
        main = project.programs["MainProgram"].routines["MainRoutine"]
        seq = project.programs["MainProgram"].routines["SequenceRoutine"]
        with pytest.raises(ValueError, match="one routine"):
            project.export([main.rungs[0], seq.rungs[0]])
        other = project.programs["AnotherProgram"].routines["Main"]
        with pytest.raises(ValueError, match="one program"):
            project.export([main, other])

    def test_programs_one_at_a_time(self) -> None:
        """Only one Program target is accepted."""
        project = _example()
        with pytest.raises(ValueError, match="one at a time"):
            project.export([project.programs["MainProgram"], project.programs["Robot"]])


class TestTagTargets:
    """Tag targets, scope and aliases."""

    def test_program_tag_alias(self) -> None:
        """A program alias tag exports under its program; modules follow."""
        project = _example()
        tag = project.programs["MainProgram"].tags["an_alias_tag"]
        exported = project.export(tag)
        summary = _summary(exported)
        assert summary["Programs"] == [("MainProgram", "Context")]
        assert summary["ProgTags"] == ["an_alias_tag"]
        assert summary["Modules"] == [
            ("Local", "Reference"),
            ("Test_Input_Module", "Reference"),
        ]
        target = exported.controller_element.find("Programs/Program/Tags/Tag")
        assert target.get("Use") == "Target"
        again = loads(exported.to_string())
        assert again.target.name == "an_alias_tag"

    def test_alias_target_comes_along(self) -> None:
        """An alias to another program tag brings that tag as context."""
        project = _example()
        project.programs["MainProgram"].tags.add_alias("pointer", "a_dint")
        exported = project.export(project.programs["MainProgram"].tags["pointer"])
        tags = exported.controller_element.find("Programs/Program/Tags")
        assert [(t.get("Name"), t.get("Use")) for t in tags] == [
            ("a_dint", None),
            ("pointer", "Target"),
        ]

    def test_controller_alias_target(self) -> None:
        """A controller alias brings its controller target."""
        project = _example()
        project.controller_tags.add_alias("ctl_alias", "ALLOWABLE_ALARMS")
        exported = project.export(project.controller_tags["ctl_alias"])
        summary = _summary(exported)
        assert summary["Tags"] == [("ALLOWABLE_ALARMS", None), ("ctl_alias", "Target")]
        assert summary["DataTypes"] == [("robotAlarmCode", None)]

    def test_mixed_scopes_raise(self) -> None:
        """Controller and program tags cannot be exported together."""
        project = _example()
        with pytest.raises(ValueError, match="controller tags or in one program"):
            project.export(
                [
                    project.controller_tags["ALLOWABLE_ALARMS"],
                    project.programs["MainProgram"].tags["a_dint"],
                ]
            )

    def test_foreign_objects_raise(self) -> None:
        """Objects from another project are refused."""
        project = _example()
        other = _example()
        with pytest.raises(ValueError, match="not part of the given project"):
            project.export(other.data_types["A_UDT"])

    def test_aoi_routine_refused(self) -> None:
        """AOI routines are exported with the AOI."""
        project = _example()
        with pytest.raises(ValueError, match="exported with the AOI"):
            project.export(project.aois["Debounce"].routines["Logic"])


class TestReferencedNames:
    """Logic tokenizing."""

    def test_operands(self) -> None:
        """Base names are the first identifier of each operand."""
        names = referenced_names(
            "XIC(a.b)MOV(c[idx].d,e)ADD(1,2.5,f)GRT(16#ff,g)CMP(h>=5);"
        )
        assert names == ["a", "c", "idx", "e", "f", "g", "h"]

    def test_instructions_and_literals_skipped(self) -> None:
        """Instructions (followed by '('), numbers and radix digits are skipped."""
        names = referenced_names("TON(t,?,?)MOV(T#5s,x)XIC(1.5e3)OTE(y);")
        assert names == ["t", "x", "y"]

    def test_strings_and_comments_ignored(self) -> None:
        """String literals and ST comments never contribute names."""
        assert referenced_names("MSG('some_tag other');") == []
        st = "x := y; // hidden\n(* gone\nalso_gone *)\ns := 'text_tag'; z := w;"
        assert referenced_names(st, st=True) == ["x", "y", "s", "z", "w"]

    def test_cross_program_references_ignored(self) -> None:
        """``\\Program.Tag`` references are ignored."""
        assert referenced_names("XIC(\\Other.Tag)OTE(mine);") == ["mine"]
        assert referenced_names("XIC(\\Other.Tag.member)OTE(mine);") == ["mine"]

    def test_module_names(self) -> None:
        """Module-style names keep their colons."""
        names = referenced_names("XIC(Local:1:I.Pt00.Data)OTE(ValveBank:I.Data);")
        assert names == ["Local:1:I", "ValveBank:I"]

    def test_lookalikes_do_not_become_context(self) -> None:
        """End to end: strings, comments and cross-program refs add no tags."""
        project = _example()
        spec = ProgramSpec(
            "Looks",
            routines=[
                RoutineSpec(
                    "Main",
                    rungs=[
                        RungSpec("MSG('ALLOWABLE_ALARMS');"),
                        RungSpec("XIC(\\Other.ALLOWABLE_ALARMS)OTE(x);"),
                    ],
                ),
                RoutineSpec(
                    "Calc",
                    "ST",
                    lines=[
                        "x := 1; // ALLOWABLE_ALARMS",
                        "(* ALLOWABLE_ALARMS *)",
                        "s := 'ALLOWABLE_ALARMS';",
                    ],
                ),
            ],
        )
        assert _summary(project.export(spec))["Tags"] == []


class TestRoundTripAndWrite:
    """Exports re-read cleanly and write to files."""

    @pytest.mark.parametrize(
        "name", ["MainProgram", "AnotherProgram", "Robot", "SafetyProgram"]
    )
    def test_every_program_export_is_consistent(self, name: str) -> None:
        """Re-reading a program export resolves every context type."""
        project = _example()
        exported = project.export(project.programs[name])
        again = loads(exported.to_string())
        assert again.target.name == name
        _consistent(again)
        for tag in again.programs[name].tags.values():
            if hasattr(tag, "to_python"):
                tag.to_python()

    def test_all_aoi_and_udt_exports(self) -> None:
        """Every UDT and AOI exports and re-reads consistently."""
        project = _example()
        for data_type in project.data_types.values():
            if data_type.class_ == "User":
                _consistent(loads(project.export(data_type).to_string()))
        for aoi in project.aois.values():
            _consistent(loads(project.export(aoi).to_string()))

    def test_write_and_load(self, tmp_path: Path) -> None:
        """An export can be written with a BOM and CRLF and loaded again."""
        project = _example()
        exported = project.export(
            project.programs["MainProgram"].routines["SequenceRoutine"]
        )
        path = tmp_path / "routine.L5X"
        exported.write(path)
        assert path.read_bytes().startswith(b"\xef\xbb\xbf<?xml")
        again = load(str(path))
        assert again.target_type == "Routine"
        assert again.target.name == "SequenceRoutine"
        assert again.root.get("ContainsContext") == "true"

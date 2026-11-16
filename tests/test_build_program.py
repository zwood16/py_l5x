"""Tests for tag and program specs, builders and ``to_spec``."""

import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_layout import first_difference

from py_l5x import (
    ProgramSpec,
    RoutineSpec,
    RungSpec,
    TagSpec,
    build_program,
    build_tag,
    load,
    loads,
)
from py_l5x.parsers.layout import LayoutError

FIXTURES = Path(__file__).parent / "fixtures"


def _comparable(element: ET.Element) -> ET.Element:
    """Strip what the builders deliberately do not emit.

    Removes L5K ``Data``/``DefaultData`` (never written) and the component
    export's ``Use`` attribute from the root.

    Args:
        element: An exported ``<Tag>`` or ``<Program>``.

    Returns:
        A stripped copy.
    """
    copy_ = copy.deepcopy(element)
    for parent in copy_.iter():
        for child in list(parent):
            if child.tag in ("Data", "DefaultData") and child.get("Format") == "L5K":
                parent.remove(child)
    copy_.attrib.pop("Use", None)
    return copy_


def _program_names(file: str) -> list[str]:
    """List the program names of a fixture.

    Args:
        file: Fixture file name.

    Returns:
        The names.
    """
    return list(load(str(FIXTURES / file)).programs)


class TestGoldenPrograms:
    """Programs rebuild exactly from their own specs."""

    @pytest.mark.parametrize("name", _program_names("example.L5X"))
    def test_example(self, name: str) -> None:
        """Every program of example.L5X rebuilds identically (minus L5K)."""
        project = load(str(FIXTURES / "example.L5X"))
        program = project.programs[name]
        built = build_program(program.to_spec(), project._type_registry)
        assert first_difference(built, _comparable(program._element)) is None

    def test_component_export(self) -> None:
        """MainProgram_Program.L5X (a component export) rebuilds identically."""
        project = load(str(FIXTURES / "MainProgram_Program.L5X"))
        program = project.programs["MainProgram"]
        assert program.use == "Target"
        built = build_program(program.to_spec(), project._type_registry)
        assert first_difference(built, _comparable(program._element)) is None

    @pytest.mark.parametrize("name", _program_names("simple_example.L5X"))
    def test_simple_example(self, name: str) -> None:
        """Every program of simple_example.L5X rebuilds identically."""
        project = load(str(FIXTURES / "simple_example.L5X"))
        program = project.programs[name]
        built = build_program(program.to_spec(), project._type_registry)
        assert first_difference(built, _comparable(program._element)) is None

    def test_exclusions_are_only_l5k_and_use(self) -> None:
        """Without the L5K strip the rebuild differs; with it, nothing does."""
        project = load(str(FIXTURES / "example.L5X"))
        program = project.programs["MainProgram"]
        built = build_program(program.to_spec(), project._type_registry)
        assert first_difference(built, program._element) is not None
        assert first_difference(built, _comparable(program._element)) is None


class TestGoldenTags:
    """Controller tags rebuild exactly, or are rejected clearly."""

    _UNSUPPORTED = {
        "consumed_tag",
        "produced_tag",
        "message_tag",
        "ServosMotionGroup",
        "testServo",
    }

    def test_example_controller_tags(self) -> None:
        """Supported tags are identical; the rest raise ValueError."""
        project = load(str(FIXTURES / "example.L5X"))
        rejected = set()
        for name, tag in project.controller_tags.items():
            try:
                spec = tag.to_spec()
            except ValueError:
                rejected.add(name)
                continue
            built = build_tag(spec, project._type_registry)
            assert first_difference(built, _comparable(tag._element)) is None, name
        assert rejected == self._UNSUPPORTED

    def test_rejection_messages(self) -> None:
        """Produced, consumed and specialty tags give clear errors."""
        project = load(str(FIXTURES / "example.L5X"))
        tags = project.controller_tags
        with pytest.raises(ValueError, match="Produced tags are not supported"):
            tags["produced_tag"].to_spec()
        with pytest.raises(ValueError, match="Consumed tags are not supported"):
            tags["consumed_tag"].to_spec()
        with pytest.raises(ValueError, match="MESSAGE"):
            tags["message_tag"].to_spec()
        with pytest.raises(ValueError, match="AXIS_CIP_DRIVE"):
            tags["testServo"].to_spec()

    def test_radix_fixture(self) -> None:
        """All radix_values tags rebuild; only LREAL 1e-10 differs in text."""
        project = load(str(FIXTURES / "radix_values_Tags.L5X"))
        differing = []
        for name, tag in project.controller_tags.items():
            built = build_tag(tag.to_spec(), project._type_registry)
            if first_difference(built, _comparable(tag._element)) is not None:
                differing.append(name)
        assert differing == ["v146_LREAL_Float"]

    def test_string_and_type_defaults_fixtures(self) -> None:
        """String escapes and type-default tags rebuild identically."""
        for file in ("string_escapes_Tags.L5X", "type_defaults_Tags.L5X"):
            project = load(str(FIXTURES / file))
            for name, tag in project.controller_tags.items():
                built = build_tag(tag.to_spec(), project._type_registry)
                assert first_difference(built, _comparable(tag._element)) is None, name

    def test_program_with_unsupported_tag(self) -> None:
        """A program holding a specialty tag cannot be converted."""
        project = load(str(FIXTURES / "example.L5X"))
        tag = project.programs["MainProgram"].tags["a_dint"]
        tag._element.set("TagType", "Produced")
        with pytest.raises(ValueError, match="Produced"):
            project.programs["MainProgram"].to_spec()


class TestBuildTag:
    """build_tag details."""

    @pytest.fixture
    def registry(self):
        """The example project's type registry."""
        return load(str(FIXTURES / "example.L5X"))._type_registry

    def test_attribute_order_and_children(self, registry) -> None:
        """Attributes and children follow Studio's order."""
        spec = TagSpec(
            "t",
            "DINT",
            dimensions=(2, 3),
            description="d",
            value=[[1, 2, 3], [4, 5, 6]],
            radix="Hex",
            external_access="Read Only",
            constant=False,
            operand_comments={".0": "zero"},
            operand_metadata={"": {"engineering_unit": "mm"}, ".1": {"max": "5"}},
            metadata={"OpcUaAccess": "None", "Usage": "Public", "Class": "Standard"},
        )
        element = build_tag(spec, registry)
        assert list(element.attrib) == [
            "Name", "Class", "TagType", "DataType", "Dimensions", "Radix", "Usage",
            "Constant", "ExternalAccess", "OpcUaAccess",
        ]  # fmt: skip
        assert element.get("Dimensions") == "2 3"
        assert [c.tag for c in element] == [
            "Description",
            "Comments",
            "EngineeringUnits",
            "Maxes",
            "Data",
        ]
        units = element.find("EngineeringUnits/EngineeringUnit")
        assert "Operand" not in units.attrib
        assert element.find("Data/Array").get("Radix") == "Hex"

    def test_alias(self, registry) -> None:
        """An alias tag has TagType Alias and AliasFor."""
        element = build_tag(
            TagSpec("a", alias_for="other.x", description="d"), registry
        )
        assert list(element.attrib.items()) == [
            ("Name", "a"),
            ("TagType", "Alias"),
            ("AliasFor", "other.x"),
        ]
        assert [c.tag for c in element] == ["Description"]

    def test_shares_the_add_code_path(self) -> None:
        """TagsCollection.add produces exactly what build_tag returns."""
        project = load(str(FIXTURES / "example.L5X"))
        spec = TagSpec(
            "shared",
            "TIMER",
            description="x",
            value={"PRE": 5},
            external_access="Read/Write",
            constant=False,
        )
        built = build_tag(spec, project._type_registry)
        added = project.controller_tags.add(
            "shared",
            "TIMER",
            description="x",
            value={"PRE": 5},
            external_access="Read/Write",
            constant=False,
        )
        assert first_difference(built, added._element) is None

    def test_bool_array_rounding(self, registry) -> None:
        """BOOL arrays round up to 32; multi-dimensional BOOL is refused."""
        element = build_tag(TagSpec("b", "BOOL", dimensions=40), registry)
        assert element.get("Dimensions") == "64"
        with pytest.raises(ValueError, match="multi-dimensional BOOL"):
            build_tag(TagSpec("b", "BOOL", dimensions=(2, 3)), registry)

    def test_atomic_values_materialize(self, registry) -> None:
        """Values give Decorated data; none gives no Data."""
        assert build_tag(TagSpec("n", "DINT"), registry).find("Data") is None
        element = build_tag(TagSpec("n", "DINT", value=5, radix="Hex"), registry)
        assert element.find("Data/DataValue").get("Value") == "16#0000_0005"
        element = build_tag(TagSpec("s", "STRING", value="hi"), registry)
        assert element.find("Data").get("Length") == "2"

    @pytest.mark.parametrize(
        "spec",
        [
            TagSpec("1bad", "DINT"),
            TagSpec("a__b", "DINT"),
            TagSpec("ok"),
            TagSpec("ok", "DINT", alias_for="x"),
            TagSpec("ok", alias_for="x", value=1),
            TagSpec("ok", alias_for="x", dimensions=2),
            TagSpec("ok", "DINT", dimensions=0),
            TagSpec("ok", "DINT", dimensions=(1, 2, 3, 4)),
            TagSpec("ok", "DINT", metadata={"Radix": "Hex"}),
            TagSpec("ok", "DINT", metadata={"TagType": "Alias"}),
        ],
    )
    def test_invalid_specs(self, registry, spec: TagSpec) -> None:
        """Invalid specs raise ValueError."""
        with pytest.raises(ValueError):
            build_tag(spec, registry)

    def test_bad_values(self, registry) -> None:
        """Bad values raise before anything is returned."""
        with pytest.raises(TypeError):
            build_tag(TagSpec("n", "DINT", value="x"), registry)
        with pytest.raises(KeyError):
            build_tag(TagSpec("t", "TIMER", value={"nope": 1}), registry)
        with pytest.raises(ValueError):
            build_tag(TagSpec("n", "SINT", value=500), registry)
        with pytest.raises(LayoutError):
            build_tag(TagSpec("m", "MESSAGE", value={}), registry)

    def test_json_round_trip(self) -> None:
        """A TagSpec with tuple dimensions survives JSON."""
        spec = TagSpec(
            "t",
            "DINT",
            dimensions=(2, 3),
            value=[[1, 2, 3], [4, 5, 6]],
            operand_comments={".0": "x"},
            operand_metadata={"": {"min": "0"}},
            metadata={"Class": "Safety"},
        )
        data = json.loads(json.dumps(spec.to_dict()))
        assert TagSpec.from_dict(data) == spec


class TestBuildProgram:
    """build_program from scratch."""

    @pytest.fixture
    def registry(self):
        """The example project's type registry."""
        return load(str(FIXTURES / "example.L5X"))._type_registry

    def _spec(self) -> ProgramSpec:
        """Create a program with tags of each kind and RLL and ST routines.

        Returns:
            The spec.
        """
        return ProgramSpec(
            "Scratch",
            tags=[
                TagSpec("n", "DINT", value=7),
                TagSpec("s", "STRING", value="hello"),
                TagSpec("t", "TIMER", value={"PRE": 100}),
                TagSpec("u", "simple_udt", value={"Dint": 3}),
                TagSpec("arr", "REAL", dimensions=3, value=[1.0, 2.0, 3.0]),
                TagSpec("al", alias_for="n"),
                TagSpec("plain", "BOOL"),
            ],
            routines=[
                RoutineSpec("Main", rungs=[RungSpec("XIC(plain)OTE(plain);", "c")]),
                RoutineSpec("Fault", rungs=[RungSpec("NOP();")]),
                RoutineSpec("Calc", "ST", lines=["n := 1;", "  s := 'x';"]),
            ],
            main_routine="Main",
            fault_routine="Fault",
            description="a program",
        )

    def test_shape(self, registry) -> None:
        """Attributes, children and sorted routines."""
        element = build_program(self._spec(), registry)
        assert list(element.attrib.items()) == [
            ("Name", "Scratch"),
            ("TestEdits", "false"),
            ("MainRoutineName", "Main"),
            ("FaultRoutineName", "Fault"),
            ("Disabled", "false"),
            ("Class", "Standard"),
            ("UseAsFolder", "false"),
        ]
        assert [c.tag for c in element] == ["Description", "Tags", "Routines"]
        routines = element.findall("Routines/Routine")
        assert [r.get("Name") for r in routines] == ["Calc", "Fault", "Main"]
        assert [t.get("Name") for t in element.findall("Tags/Tag")] == [
            "n", "s", "t", "u", "arr", "al", "plain",
        ]  # fmt: skip
        assert element.tail is None

    def test_reads_back_and_round_trips(self) -> None:
        """Insert into a project; to_spec returns an equal spec."""
        project = load(str(FIXTURES / "example.L5X"))
        spec = self._spec()
        project.programs.add(spec)
        program = project.programs["Scratch"]
        assert program.tags["t"].to_python()["PRE"] == 100
        assert program.tags["u"].to_python()["Dint"] == 3
        assert program.tags["arr"].to_python() == [1.0, 2.0, 3.0]
        assert program.tags["al"].alias_for == "n"
        assert program.routines["Calc"].st_code == "n := 1;\n  s := 'x';"
        again = program.to_spec()
        assert [t.name for t in again.tags] == [t.name for t in spec.tags]
        assert again.main_routine == "Main"
        assert again.fault_routine == "Fault"
        rebuilt = build_program(again, project._type_registry)
        assert first_difference(rebuilt, program._element) is None
        reloaded = loads(project.to_string()).programs["Scratch"]
        assert first_difference(rebuilt, reloaded._element) is None

    def test_optional_attributes(self, registry) -> None:
        """No main/fault/class omits those attributes; metadata overrides."""
        spec = ProgramSpec(
            "Opt",
            class_=None,
            disabled=True,
            metadata={"TestEdits": "true", "Extra": "x"},
        )
        element = build_program(spec, registry)
        assert list(element.attrib.items()) == [
            ("Name", "Opt"),
            ("TestEdits", "true"),
            ("Disabled", "true"),
            ("UseAsFolder", "false"),
            ("Extra", "x"),
        ]
        assert element.find("Tags") is not None
        assert len(element.find("Tags")) == 0

    def test_validation(self, registry) -> None:
        """Invalid specs raise ValueError."""
        logic = RoutineSpec("Main", rungs=[RungSpec("NOP();")])
        bad = [
            ProgramSpec("1x"),
            ProgramSpec("p", main_routine="Nope", routines=[logic]),
            ProgramSpec("p", fault_routine="Nope", routines=[logic]),
            ProgramSpec("p", tags=[TagSpec("a", "DINT"), TagSpec("A", "DINT")]),
            ProgramSpec("p", routines=[logic, RoutineSpec("main")]),
            ProgramSpec("p", routines=[RoutineSpec("a__b")]),
            ProgramSpec("p", routines=[RoutineSpec("r", "FBD")]),
            ProgramSpec("p", routines=[RoutineSpec("r", rungs=[RungSpec("XIC(a")])]),
            ProgramSpec(
                "p", routines=[RoutineSpec("r", "ST", rungs=[RungSpec("A();")])]
            ),
            ProgramSpec("p", routines=[RoutineSpec("r", lines=["x"])]),
            ProgramSpec("p", tags=[TagSpec("a", "DINT", value="bad")]),
        ]
        for spec in bad:
            with pytest.raises((ValueError, TypeError)):
                build_program(spec, registry)

    def test_tags_and_routines_are_separate_namespaces(self, registry) -> None:
        """A tag and a routine may share a name."""
        spec = ProgramSpec(
            "p",
            tags=[TagSpec("same", "DINT")],
            routines=[RoutineSpec("same", rungs=[RungSpec("NOP();")])],
        )
        assert build_program(spec, registry) is not None

    def test_json_round_trip(self) -> None:
        """A ProgramSpec survives JSON."""
        spec = self._spec()
        data = json.loads(json.dumps(spec.to_dict()))
        assert ProgramSpec.from_dict(data) == spec

    def test_routine_to_spec(self) -> None:
        """Routine.to_spec keeps comments and indentation raw."""
        project = load(str(FIXTURES / "example.L5X"))
        routine = project.programs["AnotherProgram"].routines["StructuredTextRoutine"]
        spec = routine.to_spec()
        assert spec.type_ == "ST"
        assert spec.lines == [line.text for line in routine.st_lines]
        rll = project.programs["MainProgram"].routines["MainRoutine"].to_spec()
        assert rll.rungs[0].text
        fbd = (
            load(str(FIXTURES / "example.L5X"))
            .programs["MainProgram"]
            .routines["MainRoutine"]
        )
        fbd._element.set("Type", "FBD")
        with pytest.raises(ValueError, match="unsupported type"):
            fbd.to_spec()

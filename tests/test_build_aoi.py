"""Tests for AOI specs, ``build_aoi`` and ``AOIDefinition.to_spec``."""

import copy
import dataclasses
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_layout import first_difference

from py_l5x import (
    AOISpec,
    LocalTagSpec,
    ParameterSpec,
    Project,
    RoutineSpec,
    RungSpec,
    aoi_call_operands,
    build_aoi,
    load,
    loads,
)
from py_l5x.parsers.schema import insert_child_at

FIXTURES = Path(__file__).parent / "fixtures"


def _aoi_names(file: str) -> list[str]:
    """List the AOI names of a fixture.

    Args:
        file: Fixture file name.

    Returns:
        The names.
    """
    return list(load(str(FIXTURES / file)).aois)


def _comparable(element: ET.Element) -> ET.Element:
    """Strip what we deliberately do not emit from an exported AOI.

    Removes L5K ``DefaultData`` (never emitted) and the component export's
    ``Use`` attribute.

    Args:
        element: An exported ``<AddOnInstructionDefinition>``.

    Returns:
        A stripped copy.
    """
    copy_ = copy.deepcopy(element)
    for parent in copy_.iter():
        for child in list(parent):
            if child.tag == "DefaultData" and child.get("Format") == "L5K":
                parent.remove(child)
    copy_.attrib.pop("Use", None)
    return copy_


def _drop_dependencies(element: ET.Element) -> ET.Element | None:
    """Remove ``<Dependencies>`` from an element, keeping tails right.

    Args:
        element: The AOI element, modified in place.

    Returns:
        The removed element, or ``None`` if there was none.
    """
    dependencies = element.find("Dependencies")
    if dependencies is not None:
        element.remove(dependencies)
        element[-1].tail = "\n"
    return dependencies


class TestGoldenRebuild:
    """Specs from loaded AOIs rebuild Studio's elements exactly."""

    @pytest.mark.parametrize("name", _aoi_names("type_defaults_Tags.L5X"))
    def test_type_defaults(self, name: str) -> None:
        """Every AOI of the type_defaults export rebuilds identically.

        The one exception is FanucRobot, whose Dependencies Studio orders by a
        rule that is not recoverable from the definition; there the entries
        must be the same set and everything else identical.
        """
        project = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        aoi = project.aois[name]
        built = build_aoi(aoi.to_spec(), project._type_registry)
        original = _comparable(aoi._element)
        if name == "FanucRobot":
            ours = _drop_dependencies(built)
            theirs = _drop_dependencies(original)
            assert sorted((d.get("Type"), d.get("Name")) for d in ours) == sorted(
                (d.get("Type"), d.get("Name")) for d in theirs
            )
        assert first_difference(built, original) is None

    @pytest.mark.parametrize("name", _aoi_names("example.L5X"))
    def test_example(self, name: str) -> None:
        """Every AOI of example.L5X rebuilds identically.

        The export has no ``<Dependencies>``; the ones we add are checked
        against the type_defaults export of the same AOI.
        """
        project = load(str(FIXTURES / "example.L5X"))
        aoi = project.aois[name]
        built = build_aoi(aoi.to_spec(), project._type_registry)
        ours = _drop_dependencies(built)
        original = _comparable(aoi._element)
        assert original.find("Dependencies") is None
        assert first_difference(built, original) is None
        golden = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        studio = golden.aois[name]._element.find("Dependencies")
        if studio is None:
            assert ours is None
        elif name == "FanucRobot":
            assert sorted((d.get("Type"), d.get("Name")) for d in ours) == sorted(
                (d.get("Type"), d.get("Name")) for d in studio
            )
        else:
            assert first_difference(ours, studio) is None

    def test_debounce_component_export(self) -> None:
        """Debounce_AOI.L5X (a component export) rebuilds identically."""
        project = load(str(FIXTURES / "Debounce_AOI.L5X"))
        aoi = project.aois["Debounce"]
        built = build_aoi(aoi.to_spec(), project._type_registry)
        assert first_difference(built, _comparable(aoi._element)) is None

    def test_fanuc_robot_dependencies_present(self) -> None:
        """FanucRobot lists each used type once."""
        project = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        built = build_aoi(project.aois["FanucRobot"].to_spec(), project._type_registry)
        names = [d.get("Name") for d in built.findall("Dependencies/Dependency")]
        assert len(names) == len(set(names)) == 7


def _minimal() -> AOISpec:
    """Create a minimal AOI spec.

    Returns:
        One Input, one Output and a Logic rung.
    """
    return AOISpec(
        "Mini",
        [ParameterSpec("In1", "BOOL"), ParameterSpec("Out1", "BOOL", "Output")],
        routines=[RoutineSpec("Logic", rungs=[RungSpec("XIC(In1)OTE(Out1);")])],
    )


def _insert(project: Project, spec: AOISpec) -> ET.Element:
    """Build an AOI and insert it into a loaded project by hand.

    Args:
        project: The project (it must have an AOI container).
        spec: The spec.

    Returns:
        The inserted element.
    """
    element = build_aoi(spec, project._type_registry)
    container = project.controller_element.find("AddOnInstructionDefinitions")
    insert_child_at(container, len(container), element)
    return element


@pytest.fixture
def project() -> Project:
    """The example project, for registry and insertion."""
    return load(str(FIXTURES / "example.L5X"))


def _normalized(spec: AOISpec) -> AOISpec:
    """Make a hand-written spec comparable with ``to_spec`` output.

    Args:
        spec: A hand-written spec.

    Returns:
        A copy whose ``metadata`` is ``{}`` (what a built AOI reads back as).
    """
    return dataclasses.replace(spec, metadata={})


class TestMinimal:
    """A minimal AOI."""

    def test_shape(self) -> None:
        """Attributes, children, system parameters and the empty LocalTags."""
        built = build_aoi(_minimal())
        assert list(built.attrib.items()) == [
            ("Name", "Mini"),
            ("Revision", "1.0"),
            ("ExecutePrescan", "false"),
            ("ExecutePostscan", "false"),
            ("ExecuteEnableInFalse", "false"),
        ]
        assert [c.tag for c in built] == ["Parameters", "LocalTags", "Routines"]
        parameters = built.findall("Parameters/Parameter")
        assert [p.get("Name") for p in parameters] == [
            "EnableIn",
            "EnableOut",
            "In1",
            "Out1",
        ]
        assert list(parameters[0].attrib.items()) == [
            ("Name", "EnableIn"),
            ("TagType", "Base"),
            ("DataType", "BOOL"),
            ("Usage", "Input"),
            ("Radix", "Decimal"),
            ("Required", "false"),
            ("Visible", "false"),
            ("ExternalAccess", "Read Only"),
        ]
        description = parameters[1].find("Description")
        assert description[0].text == "Enable Output - System Defined Parameter"
        in1, out1 = parameters[2:]
        assert in1.get("ExternalAccess") == "Read/Write"
        assert out1.get("ExternalAccess") == "Read Only"
        assert len(built.find("LocalTags")) == 0
        assert built.tail is None

    def test_default_data_is_decorated_only(self) -> None:
        """DefaultData is Decorated, with no L5K."""
        built = build_aoi(_minimal())
        defaults = built.findall("Parameters/Parameter/DefaultData")
        assert [d.get("Format") for d in defaults] == ["Decorated", "Decorated"]
        assert defaults[0][0].attrib == {
            "DataType": "BOOL",
            "Radix": "Decimal",
            "Value": "0",
        }

    def test_reads_back_and_round_trips(self, project: Project) -> None:
        """The reader sees it, and to_spec returns the spec."""
        _insert(project, _minimal())
        aoi = project.aois["Mini"]
        assert list(aoi.parameters) == ["EnableIn", "EnableOut", "In1", "Out1"]
        assert aoi.parameters["Out1"].usage == "Output"
        assert aoi.routines["Logic"].rungs[0].text == "XIC(In1)OTE(Out1);"
        assert aoi.to_spec() == _normalized(_minimal())
        text = project.to_string()
        assert "<LocalTags/>" in text
        assert loads(text).aois["Mini"].to_spec() == _normalized(_minimal())


class TestRoutines:
    """Routines and execute flags."""

    def test_st_logic(self, project: Project) -> None:
        """An ST Logic routine keeps its indentation."""
        spec = AOISpec(
            "StAoi",
            [ParameterSpec("Out1", "DINT", "Output")],
            routines=[
                RoutineSpec(
                    "Logic",
                    "ST",
                    lines=["IF a THEN", "    Out1 := 1;", "", "END_IF;"],
                    description="st",
                )
            ],
        )
        _insert(project, spec)
        routine = project.aois["StAoi"].routines["Logic"]
        assert routine.type_ == "ST"
        assert routine.st_code == "IF a THEN\n    Out1 := 1;\n\nEND_IF;"
        assert routine.description == "st"
        assert project.aois["StAoi"].to_spec() == _normalized(spec)

    def test_all_routines_and_flags(self, project: Project) -> None:
        """Four routines are sorted by name; flags default to present."""
        names = ["Prescan", "Logic", "EnableInFalse", "Postscan"]
        spec = AOISpec(
            "Four",
            [ParameterSpec("Out1", "BOOL", "Output")],
            routines=[
                RoutineSpec(
                    n, rungs=[RungSpec("OTU(Out1);", "c" if n == "Logic" else "")]
                )
                for n in names
            ],
        )
        built = build_aoi(spec)
        assert [r.get("Name") for r in built.findall("Routines/Routine")] == sorted(
            names
        )
        assert built.get("ExecutePrescan") == "true"
        assert built.get("ExecutePostscan") == "true"
        assert built.get("ExecuteEnableInFalse") == "true"
        _insert(project, spec)
        expected = dataclasses.replace(
            _normalized(spec), routines=sorted(spec.routines, key=lambda r: r.name)
        )
        assert project.aois["Four"].to_spec() == expected
        assert project.aois["Four"].routines["Logic"].rungs[0].comment == "c"

    def test_explicit_flags_override(self, project: Project) -> None:
        """Explicit flags win; to_spec keeps non-default ones."""
        spec = AOISpec(
            "Flags",
            [ParameterSpec("Out1", "BOOL", "Output")],
            routines=[
                RoutineSpec("Logic", rungs=[RungSpec("NOP();")]),
                RoutineSpec("Prescan", rungs=[RungSpec("NOP();")]),
            ],
            execute_prescan=False,
            execute_postscan=True,
            execute_enable_in_false=True,
        )
        built = build_aoi(spec)
        assert built.get("ExecutePrescan") == "false"
        assert built.get("ExecutePostscan") == "true"
        assert built.get("ExecuteEnableInFalse") == "true"
        _insert(project, spec)
        assert project.aois["Flags"].to_spec() == _normalized(spec)

    def test_rung_numbers_and_comments(self) -> None:
        """Rungs are numbered from 0 with optional comments."""
        spec = AOISpec(
            "Num",
            [],
            routines=[
                RoutineSpec(
                    "Logic", rungs=[RungSpec("A();", "first"), RungSpec("B();")]
                )
            ],
        )
        rungs = build_aoi(spec).findall("Routines/Routine/RLLContent/Rung")
        assert [r.get("Number") for r in rungs] == ["0", "1"]
        assert [c.tag for c in rungs[0]] == ["Comment", "Text"]
        assert [c.tag for c in rungs[1]] == ["Text"]


class TestDefinitionsAndDefaults:
    """Parameters, local tags, defaults and dependencies."""

    def _spec(self) -> AOISpec:
        """Create an AOI with UDT, AOI and TIMER members and defaults.

        Returns:
            The spec.
        """
        return AOISpec(
            "Rich",
            [
                ParameterSpec("u", "simple_udt", "InOut"),
                ParameterSpec("arr", "DINT", "InOut", dimension=4),
                ParameterSpec("delay", "DINT", default=100, radix="Hex"),
                ParameterSpec("gain", "REAL", "Output", default=1.5),
                ParameterSpec("flag", "BOOL", default=True),
            ],
            [
                LocalTagSpec("t", "TIMER", default={"PRE": 777}),
                LocalTagSpec("deb", "Debounce"),
                LocalTagSpec("n", "DINT", default=5, external_access="None"),
                LocalTagSpec("s", "STRING", default="hi"),
                LocalTagSpec("sv", "simple_udt", default={"Dint": 3}),
            ],
            [RoutineSpec("Logic", rungs=[RungSpec("NOP();")])],
        )

    def test_reads_back(self, project: Project) -> None:
        """Defaults, InOut rules and dependencies read back correctly."""
        spec = self._spec()
        element = _insert(project, spec)
        aoi = project.aois["Rich"]
        assert aoi.local_tags["t"].to_python()["PRE"] == 777
        assert aoi.local_tags["s"].to_python() == "hi"
        assert aoi.local_tags["sv"].to_python()["Dint"] == 3
        assert aoi.local_tags["n"].to_python() == 5
        assert aoi.parameters["delay"].value == 100
        assert aoi.parameters["gain"].value == 1.5
        assert aoi.parameters["flag"].value is True
        inout = element.find("Parameters/Parameter[@Name='u']")
        assert list(inout.attrib.items()) == [
            ("Name", "u"),
            ("TagType", "Base"),
            ("DataType", "simple_udt"),
            ("Usage", "InOut"),
            ("Required", "true"),
            ("Visible", "true"),
            ("Constant", "false"),
        ]
        assert inout.find("DefaultData") is None
        array = element.find("Parameters/Parameter[@Name='arr']")
        assert list(array.attrib)[:5] == [
            "Name",
            "TagType",
            "DataType",
            "Dimensions",
            "Usage",
        ]
        delay = element.find("Parameters/Parameter[@Name='delay']")
        assert delay.find("DefaultData/DataValue").get("Value") == "16#0000_0064"
        deps = element.findall("Dependencies/Dependency")
        assert [(d.get("Type"), d.get("Name")) for d in deps] == [
            ("DataType", "simple_udt"),
            ("AddOnInstructionDefinition", "Debounce"),
        ]
        local_n = element.find("LocalTags/LocalTag[@Name='n']")
        assert list(local_n.attrib.items()) == [
            ("Name", "n"),
            ("DataType", "DINT"),
            ("Radix", "Decimal"),
            ("ExternalAccess", "None"),
        ]
        local_t = element.find("LocalTags/LocalTag[@Name='t']")
        assert "Radix" not in local_t.attrib

    def test_to_spec_round_trip(self, project: Project) -> None:
        """to_spec returns the same spec (defaults equal to the type's are None)."""
        spec = self._spec()
        built = _insert(project, spec)
        read = project.aois["Rich"].to_spec()
        # Dict defaults read back complete (every member), so compare those
        # separately and the rest of the spec directly.
        timer = read.local_tags[0].default
        assert timer == {"PRE": 777, "ACC": 0, "EN": False, "TT": False, "DN": False}
        assert read.local_tags[4].default["Dint"] == 3
        expected = _normalized(spec)
        pairs = zip(expected.local_tags, read.local_tags, strict=True)
        for spec_tag, read_tag in pairs:
            if isinstance(spec_tag.default, dict):
                spec_tag.default = read_tag.default
        assert read == expected
        again = loads(project.to_string())
        assert again.aois["Rich"].to_spec() == read
        rebuilt = build_aoi(read, project._type_registry)
        assert first_difference(rebuilt, built) is None

    def test_default_equal_to_type_default_becomes_none(self, project: Project) -> None:
        """An explicit default equal to the type default reads back as None."""
        spec = AOISpec(
            "Eq",
            [ParameterSpec("p", "DINT", default=0)],
            routines=[RoutineSpec("Logic", rungs=[RungSpec("NOP();")])],
        )
        _insert(project, spec)
        assert project.aois["Eq"].to_spec().parameters[0].default is None

    def test_local_array(self) -> None:
        """A local array builds an Array default."""
        spec = AOISpec(
            "Arr",
            [],
            [LocalTagSpec("a", "DINT", dimension=3, default=[1, 2, 3])],
            [RoutineSpec("Logic", rungs=[RungSpec("NOP();")])],
        )
        local = build_aoi(spec).find("LocalTags/LocalTag")
        assert local.get("Dimensions") == "3"
        values = [e.get("Value") for e in local.findall("DefaultData/Array/Element")]
        assert values == ["1", "2", "3"]

    def test_extended_properties(self, project: Project) -> None:
        """Description, units, limits, states, comments and flags round trip."""
        spec = AOISpec(
            "Ext",
            [
                ParameterSpec(
                    "temp",
                    "REAL",
                    required=True,
                    visible=True,
                    description="temperature",
                    engineering_unit="degC",
                    min=0,
                    max=1800,
                    external_access="Read Only",
                    operand_comments={},
                ),
                ParameterSpec(
                    "bits",
                    "DINT",
                    "Output",
                    visible=True,
                    operand_comments={".1": "one", ".0": "zero"},
                ),
                ParameterSpec(
                    "on",
                    "BOOL",
                    description="on state",
                    state0="off",
                    state1="on",
                    required=True,
                ),
            ],
            routines=[RoutineSpec("Logic", rungs=[RungSpec("NOP();")])],
            description="aoi",
            revision="2.1",
            revision_note="note",
            vendor="AIC",
            additional_help_text="help",
        )
        element = _insert(project, spec)
        temp = element.find("Parameters/Parameter[@Name='temp']")
        assert list(temp.attrib)[-3:] == ["ExternalAccess", "Max", "Min"]
        assert temp.get("Max") == "1800.0"
        assert temp.get("Min") == "0.0"
        assert [c.tag for c in temp] == [
            "Description",
            "EngineeringUnits",
            "DefaultData",
        ]
        bits = element.find("Parameters/Parameter[@Name='bits']")
        assert [c.get("Operand") for c in bits.findall("Comments/Comment")] == [
            ".0",
            ".1",
        ]
        on = element.find("Parameters/Parameter[@Name='on']")
        assert [c.tag for c in on] == [
            "Description",
            "State0s",
            "State1s",
            "DefaultData",
        ]
        assert [c.tag for c in element] == [
            "Description",
            "RevisionNote",
            "AdditionalHelpText",
            "Parameters",
            "LocalTags",
            "Routines",
        ]
        assert list(element.attrib)[:3] == ["Name", "Revision", "Vendor"]
        aoi = project.aois["Ext"]
        assert aoi.parameters["temp"].description == "temperature"
        assert aoi.parameters["temp"].engineering_unit == "degC"
        assert aoi.parameters["bits"].operand_comments == {".0": "zero", ".1": "one"}
        assert aoi.parameters["on"].state1 == "on"
        assert aoi.revision == "2.1"
        round_tripped = aoi.to_spec()
        assert round_tripped.parameters[0].min == "0.0"
        assert round_tripped.vendor == "AIC"
        assert round_tripped.additional_help_text == "help"
        assert round_tripped.parameters[1].operand_comments == {
            ".0": "zero",
            ".1": "one",
        }

    @pytest.mark.parametrize(
        ("required", "visible"), [(False, False), (False, True), (True, True)]
    )
    def test_required_visible(self, required: bool, visible: bool) -> None:
        """Valid explicit Input combinations are written as true/false."""
        spec = AOISpec(
            "RV",
            [ParameterSpec("p", "DINT", required=required, visible=visible)],
            routines=[RoutineSpec("Logic", rungs=[RungSpec("NOP();")])],
        )
        param = build_aoi(spec).find("Parameters/Parameter[@Name='p']")
        assert param.get("Required") == str(required).lower()
        assert param.get("Visible") == str(visible).lower()

    @staticmethod
    def _flags(usage: str, **flags) -> tuple[str, str]:
        """Build a one-parameter AOI and return its Required/Visible text.

        Args:
            usage: The parameter usage.
            **flags: ``required`` and/or ``visible``.

        Returns:
            The ``Required`` and ``Visible`` attributes.
        """
        data_type = "simple_udt" if usage == "InOut" else "DINT"
        spec = AOISpec(
            "RV",
            [ParameterSpec("p", data_type, usage, **flags)],
            routines=[RoutineSpec("Logic", rungs=[RungSpec("NOP();")])],
        )
        project = load(str(FIXTURES / "example.L5X"))
        param = build_aoi(spec, project._type_registry).find(
            "Parameters/Parameter[@Name='p']"
        )
        return param.get("Required"), param.get("Visible")

    def test_derived_defaults(self) -> None:
        """None derives the flags from the usage."""
        assert self._flags("InOut") == ("true", "true")
        assert self._flags("Input") == ("false", "false")
        assert self._flags("Output") == ("false", "false")
        assert self._flags("Input", required=True) == ("true", "true")
        assert self._flags("Output", required=True) == ("true", "true")
        assert self._flags("Input", visible=True) == ("false", "true")
        assert self._flags("InOut", required=True, visible=True) == ("true", "true")

    @pytest.mark.parametrize(
        "flags",
        [
            {"required": False},
            {"visible": False},
            {"required": False, "visible": False},
            {"required": True, "visible": False},
            {"required": False, "visible": True},
        ],
    )
    def test_inout_must_be_required_and_visible(self, flags: dict) -> None:
        """Any explicit False on an InOut raises, citing Studio's error."""
        with pytest.raises(ValueError, match="RxE_INVALID_TAG_USAGE_TYPE"):
            self._flags("InOut", **flags)

    @pytest.mark.parametrize("usage", ["Input", "Output"])
    def test_required_needs_visible(self, usage: str) -> None:
        """Required but not visible raises, citing Studio's error."""
        with pytest.raises(ValueError, match="RxE_ILLEGAL_OPERATIONS"):
            self._flags(usage, required=True, visible=False)

    def test_structured_input_cites_studio_errors(self) -> None:
        """Structured or array Input/Output parameters name Studio's errors."""
        spec = AOISpec(
            "S",
            [ParameterSpec("a", "DINT", dimension=2)],
            routines=[RoutineSpec("Logic")],
        )
        with pytest.raises(ValueError, match="RxE_ARRAY_INVALID_FOR_PARAMETER"):
            build_aoi(spec)

    def test_to_spec_stores_none_for_derived_values(self, project: Project) -> None:
        """to_spec leaves derived flags None and keeps the others explicit."""
        spec = AOISpec(
            "Flags2",
            [
                ParameterSpec("io", "simple_udt", "InOut"),
                ParameterSpec("a", "DINT"),
                ParameterSpec("b", "DINT", required=True),
                ParameterSpec("c", "DINT", visible=True),
                ParameterSpec("d", "DINT", "Output", required=True),
            ],
            routines=[RoutineSpec("Logic", rungs=[RungSpec("NOP();")])],
        )
        _insert(project, spec)
        read = project.aois["Flags2"].to_spec()
        assert [(p.required, p.visible) for p in read.parameters] == [
            (None, None),
            (None, None),
            (True, None),
            (None, True),
            (True, None),
        ]
        assert aoi_call_operands(read) == ["io", "b", "d"]
        assert aoi_call_operands(spec) == ["io", "b", "d"]

    def test_metadata_written_verbatim(self) -> None:
        """Metadata attributes follow Studio's order."""
        spec = _minimal()
        spec.metadata = {
            "EditedBy": "me",
            "CreatedDate": "2020-01-01T00:00:00.000Z",
            "Class": "Standard",
            "SoftwareRevision": "v37.00",
        }
        assert list(build_aoi(spec).attrib) == [
            "Name",
            "Class",
            "Revision",
            "ExecutePrescan",
            "ExecutePostscan",
            "ExecuteEnableInFalse",
            "CreatedDate",
            "EditedBy",
            "SoftwareRevision",
        ]


class TestValidation:
    """Spec validation errors."""

    @staticmethod
    def _spec(**changes) -> AOISpec:
        """Create a valid spec with changes.

        Args:
            **changes: Fields to replace.

        Returns:
            The spec.
        """
        return dataclasses.replace(_minimal(), **changes)

    def test_bad_aoi_name(self) -> None:
        """Invalid AOI names are rejected."""
        for name in ("1a", "a__b", "a_", "x" * 41, "a b", ""):
            with pytest.raises(ValueError):
                build_aoi(self._spec(name=name))

    @pytest.mark.parametrize("name", ["EnableIn", "EnableOut", "enablein", "ENABLEOUT"])
    def test_reserved_names(self, name: str) -> None:
        """EnableIn/EnableOut may not be listed (in parameters or locals)."""
        with pytest.raises(ValueError, match="reserved"):
            build_aoi(self._spec(parameters=[ParameterSpec(name, "BOOL")]))
        with pytest.raises(ValueError, match="reserved"):
            build_aoi(self._spec(local_tags=[LocalTagSpec(name, "BOOL")]))

    def test_duplicates_across_parameters_and_locals(self) -> None:
        """One namespace, case-insensitive."""
        with pytest.raises(ValueError, match="already exists"):
            build_aoi(
                self._spec(
                    parameters=[ParameterSpec("a", "DINT")],
                    local_tags=[LocalTagSpec("A", "DINT")],
                )
            )
        with pytest.raises(ValueError, match="already exists"):
            build_aoi(
                self._spec(
                    parameters=[ParameterSpec("a", "DINT"), ParameterSpec("a", "INT")]
                )
            )

    def test_bad_parameter_name(self) -> None:
        """Bad parameter names are rejected."""
        with pytest.raises(ValueError):
            build_aoi(self._spec(parameters=[ParameterSpec("a__b", "DINT")]))

    def test_missing_logic(self) -> None:
        """A Logic routine is required."""
        with pytest.raises(ValueError, match="Logic"):
            build_aoi(self._spec(routines=[RoutineSpec("Prescan")]))
        with pytest.raises(ValueError, match="Logic"):
            build_aoi(self._spec(routines=[]))

    def test_bad_routine_name_and_duplicates(self) -> None:
        """Only the four names, once each."""
        logic = RoutineSpec("Logic", rungs=[RungSpec("NOP();")])
        with pytest.raises(ValueError, match="routine name"):
            build_aoi(self._spec(routines=[logic, RoutineSpec("Extra")]))
        with pytest.raises(ValueError, match="duplicate"):
            build_aoi(self._spec(routines=[logic, logic]))

    def test_usage_and_structured_input(self) -> None:
        """Usage must be valid; only InOut may be structured or an array."""
        with pytest.raises(ValueError, match="usage"):
            build_aoi(self._spec(parameters=[ParameterSpec("a", "DINT", "Bogus")]))
        with pytest.raises(ValueError, match="only InOut"):
            build_aoi(self._spec(parameters=[ParameterSpec("a", "TIMER", "Input")]))
        with pytest.raises(ValueError, match="only InOut"):
            build_aoi(
                self._spec(
                    parameters=[ParameterSpec("a", "DINT", "Output", dimension=2)]
                )
            )

    def test_inout_has_no_default_or_limits(self) -> None:
        """InOut parameters take no default and no min/max."""
        with pytest.raises(ValueError, match="no default"):
            build_aoi(
                self._spec(parameters=[ParameterSpec("a", "DINT", "InOut", default=1)])
            )
        with pytest.raises(ValueError, match="min/max"):
            build_aoi(
                self._spec(parameters=[ParameterSpec("a", "DINT", "InOut", min=0)])
            )

    def test_access_and_dimension(self) -> None:
        """External access and dimension are checked."""
        with pytest.raises(ValueError, match="external access"):
            build_aoi(
                self._spec(parameters=[ParameterSpec("a", "DINT", external_access="x")])
            )
        with pytest.raises(ValueError, match="dimension"):
            build_aoi(self._spec(local_tags=[LocalTagSpec("a", "DINT", dimension=-1)]))

    @pytest.mark.parametrize("text", ["", "XIC(a)", "XIC(a;", "XIC(a));", "[XIC(a);"])
    def test_bad_rung_text(self, text: str) -> None:
        """Rung text gets the light check."""
        routine = RoutineSpec("Logic", rungs=[RungSpec(text)])
        with pytest.raises(ValueError):
            build_aoi(self._spec(routines=[routine]))

    def test_rungs_and_lines_mismatch(self) -> None:
        """ST routines have no rungs; RLL routines no lines."""
        with pytest.raises(ValueError, match="cannot have rungs"):
            build_aoi(
                self._spec(
                    routines=[RoutineSpec("Logic", "ST", rungs=[RungSpec("A();")])]
                )
            )
        with pytest.raises(ValueError, match="cannot have ST lines"):
            build_aoi(self._spec(routines=[RoutineSpec("Logic", lines=["a"])]))
        with pytest.raises(ValueError, match="single line"):
            build_aoi(self._spec(routines=[RoutineSpec("Logic", "ST", lines=["a\nb"])]))

    def test_bad_default(self) -> None:
        """A bad default value is rejected."""
        spec = self._spec(local_tags=[LocalTagSpec("t", "TIMER", default={"nope": 1})])
        with pytest.raises(KeyError):
            build_aoi(spec)

    def test_unknown_type_without_registry(self) -> None:
        """A project type needs a registry."""
        spec = self._spec(local_tags=[LocalTagSpec("t", "simple_udt")])
        with pytest.raises(ValueError, match="unknown data type"):
            build_aoi(spec)


class TestCallOperands:
    """aoi_call_operands."""

    def test_spec(self) -> None:
        """Required parameters come in definition order, InOut included."""
        spec = AOISpec(
            "C",
            [
                ParameterSpec("a", "DINT", required=True),
                ParameterSpec("b", "DINT"),
                ParameterSpec("u", "simple_udt", "InOut", required=True),
                ParameterSpec("o", "DINT", "Output", required=True),
            ],
            routines=[RoutineSpec("Logic")],
        )
        assert aoi_call_operands(spec) == ["a", "u", "o"]
        assert aoi_call_operands(_minimal()) == []

    @pytest.mark.parametrize(
        "name", ["Debounce", "GenericInput", "FanucRobot", "FanucPNS", "SeqCtrl"]
    )
    def test_definition_matches_spec_and_xml(self, name: str) -> None:
        """Definitions and their specs agree and match the Required attributes."""
        project = load(str(FIXTURES / "example.L5X"))
        aoi = project.aois[name]
        expected = [
            p.get("Name")
            for p in aoi._element.findall("Parameters/Parameter")
            if p.get("Required") == "true"
            and p.get("Name") not in ("EnableIn", "EnableOut")
        ]
        assert aoi_call_operands(aoi) == expected
        assert aoi_call_operands(aoi.to_spec()) == expected

    def test_known_values(self) -> None:
        """GenericInput requires physicalInput."""
        project = load(str(FIXTURES / "example.L5X"))
        assert aoi_call_operands(project.aois["GenericInput"]) == ["physicalInput"]


class TestSerialization:
    """JSON round trips and to_spec limits."""

    def test_json_round_trip_of_definition(self) -> None:
        """A spec from a definition survives JSON and rebuilds the same."""
        project = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        spec = project.aois["FanucRobot"].to_spec()
        loaded = AOISpec.from_dict(json.loads(json.dumps(spec.to_dict())))
        assert loaded == spec
        assert (
            first_difference(
                build_aoi(loaded, project._type_registry),
                build_aoi(spec, project._type_registry),
            )
            is None
        )

    def test_json_round_trip_of_scratch_spec(self) -> None:
        """A hand-written spec with defaults survives JSON."""
        spec = TestDefinitionsAndDefaults()._spec()
        assert AOISpec.from_dict(json.loads(json.dumps(spec.to_dict()))) == spec

    def test_spec_fields_are_plain(self) -> None:
        """to_dict output is pure JSON data."""
        project = load(str(FIXTURES / "example.L5X"))
        data = project.aois["GenericInput"].to_spec().to_dict()
        assert json.loads(json.dumps(data)) == data

    def test_protected_aoi_refused(self) -> None:
        """A protected AOI cannot be converted."""
        project = load(str(FIXTURES / "example.L5X"))
        aoi = project.aois["Debounce"]
        ET.SubElement(aoi._element, "EncodedData")
        with pytest.raises(ValueError, match="protected"):
            aoi.to_spec()

    def test_unsupported_child_and_routine_type(self) -> None:
        """Unknown children and non-RLL/ST routines are refused."""
        project = load(str(FIXTURES / "example.L5X"))
        aoi = project.aois["Debounce"]
        ET.SubElement(aoi._element, "Mystery")
        with pytest.raises(ValueError, match="unsupported element"):
            aoi.to_spec()
        project = load(str(FIXTURES / "example.L5X"))
        aoi = project.aois["Debounce"]
        aoi._element.find("Routines/Routine").set("Type", "FBD")
        with pytest.raises(ValueError, match="unsupported type"):
            aoi.to_spec()

    def test_built_aoi_survives_serialization(self, project: Project) -> None:
        """Insert, serialize, reload, rebuild: identical elements."""
        spec = TestDefinitionsAndDefaults()._spec()
        built = _insert(project, spec)
        reloaded = loads(project.to_string())
        element = reloaded.aois["Rich"]._element
        assert first_difference(built, element) is None

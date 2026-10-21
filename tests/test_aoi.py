"""Tests for py_l5x.parsers.aoi."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x import (
    AOILocalArrayTag,
    AOILocalAtomicTag,
    AOILocalBoolTag,
    AOILocalDateTimeTag,
    AOILocalFloatTag,
    AOILocalIntegerTag,
    AOILocalStringTag,
    AOILocalStructTag,
    AOILocalTimeTag,
)
from py_l5x.parsers.aoi import (
    _AOI_LOCAL_TAG_CLASSES,
    AOICollection,
    AOIDataTypesCollection,
    AOIDefinition,
    AOILocalTag,
    AOIParameter,
    AOIParametersCollection,
    _AOIDefinitionTag,
)
from py_l5x.parsers.datatype import DataTypesCollection
from py_l5x.parsers.routine import Routine
from py_l5x.parsers.tag import (
    ArrayNode,
    AtomicNode,
    BoolNode,
    DateTimeNode,
    FloatNode,
    IntegerNode,
    StringNode,
    StructNode,
    TimeNode,
    TypeRegistry,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLE_L5X = FIXTURES_DIR / "example.L5X"


@pytest.fixture
def example_tree() -> ET.ElementTree:
    """Load the example L5X file."""
    return ET.parse(str(EXAMPLE_L5X))


@pytest.fixture
def controller_element(example_tree: ET.ElementTree) -> ET.Element:
    """Extract the <Controller> element from the example L5X."""
    el = example_tree.getroot().find("Controller")
    assert el is not None, "Controller element not found in example.L5X"
    return el


@pytest.fixture
def type_registry(controller_element: ET.Element) -> TypeRegistry:
    """Build a TypeRegistry from the example L5X's UDT and AOI collections."""
    return TypeRegistry(
        DataTypesCollection(controller_element),
        AOIDataTypesCollection(controller_element),
    )


@pytest.fixture
def aoi_definitions(
    controller_element: ET.Element, type_registry: TypeRegistry
) -> AOICollection:
    """AOI definitions collection."""
    return AOICollection(controller_element, type_registry)


@pytest.fixture
def aoi_xml_elements(example_tree: ET.ElementTree) -> list[ET.Element]:
    """Extract all <AddOnInstructionDefinition> elements from the example L5X."""
    root = example_tree.getroot()
    defs = root.findall(".//AddOnInstructionDefinition")
    assert len(defs) > 0, "No AddOnInstructionDefinition elements found in example.L5X"
    return defs


@pytest.fixture
def debounce_aoi(aoi_xml_elements: list[ET.Element]) -> ET.Element:
    """The Debounce AOI definition."""
    for el in aoi_xml_elements:
        if el.get("Name") == "Debounce":
            return el
    pytest.fail("Debounce AOI not found in example.L5X")


@pytest.fixture
def generic_input_aoi(aoi_xml_elements: list[ET.Element]) -> ET.Element:
    """The GenericInput AOI definition."""
    for el in aoi_xml_elements:
        if el.get("Name") == "GenericInput":
            return el
    pytest.fail("GenericInput AOI not found in example.L5X")


@pytest.fixture
def fanuc_robot_aoi(aoi_xml_elements: list[ET.Element]) -> ET.Element:
    """The FanucRobot AOI definition."""
    for el in aoi_xml_elements:
        if el.get("Name") == "FanucRobot":
            return el
    pytest.fail("FanucRobot AOI not found in example.L5X")


@pytest.fixture
def aoi_types(controller_element: ET.Element) -> AOIDataTypesCollection:
    """Create an AOIDataTypesCollection instance from the example L5X."""
    return AOIDataTypesCollection(controller_element)


@pytest.fixture
def debounce(aoi_types: AOIDataTypesCollection) -> AOIParametersCollection:
    """The Debounce AOI's parameters."""
    return aoi_types["Debounce"]


@pytest.fixture
def generic_input(aoi_types: AOIDataTypesCollection) -> AOIParametersCollection:
    """The GenericInput AOI's parameters."""
    return aoi_types["GenericInput"]


class TestAoiCollection:
    """Tests for AOI collection mapping behavior."""

    def test_contains_known_aois(self, aoi_definitions: AOICollection) -> None:
        """Debounce and FanucRobot are present."""
        assert "Debounce" in aoi_definitions
        assert "FanucRobot" in aoi_definitions

    def test_getitem_returns_definition(self, aoi_definitions: AOICollection) -> None:
        """Indexing returns an AOI definition wrapper."""
        assert isinstance(aoi_definitions["Debounce"], AOIDefinition)


class TestAoiIdentity:
    """Tests for AOI identity metadata."""

    def test_identity_fields(self, aoi_definitions: AOICollection) -> None:
        """Key AOI attributes are exposed as typed properties."""
        debounce = aoi_definitions["Debounce"]
        assert debounce.name == "Debounce"
        assert debounce.revision == "1.2"
        assert debounce.execute_enable_in_false is True
        assert debounce.execute_prescan is False
        assert debounce.execute_postscan is False
        assert debounce.software_revision == "v37.00"


class TestAoiParametersAndRoutines:
    """Tests for reused parameter and routine parser surfaces."""

    def test_parameters_property_reuses_aoi_parameters_collection(
        self, aoi_definitions: AOICollection
    ) -> None:
        """AOI.parameters returns AOIParametersCollection."""
        debounce = aoi_definitions["Debounce"]
        assert isinstance(debounce.parameters, AOIParametersCollection)
        assert debounce.parameters["onDelay"].data_type == "DINT"

    def test_routines_property_reuses_shared_routine_parser(
        self, aoi_definitions: AOICollection
    ) -> None:
        """AOI.routines returns Routine wrappers."""
        debounce = aoi_definitions["Debounce"]
        assert "Logic" in debounce.routines
        assert isinstance(debounce.routines["Logic"], Routine)
        assert debounce.routines["Logic"].type_ == "RLL"

    def test_st_routine_is_exposed(self, aoi_definitions: AOICollection) -> None:
        """FanucAlarmLookup has an ST logic routine."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        logic = lookup.routines["Logic"]
        assert logic.type_ == "ST"
        assert "recoverableAlarm := 0;" in logic.st_code


class TestAoiLocalTags:
    """Tests for AOI LocalTag metadata and value parsing."""

    def test_local_tags_collection(self, aoi_definitions: AOICollection) -> None:
        """AOI.local_tags maps local tag names to AOILocalTag wrappers."""
        debounce = aoi_definitions["Debounce"]
        assert "debounceOnTimer" in debounce.local_tags
        assert isinstance(debounce.local_tags["debounceOnTimer"], AOILocalTag)

    def test_local_tag_structure_drilldown(
        self, aoi_definitions: AOICollection
    ) -> None:
        """Structured local tags expose member drill-down."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        assert isinstance(timer, StructNode)
        assert timer.members["PRE"].value == 0
        assert timer.members["DN"].value == 0

    def test_local_tag_aoi_datatype_drilldown_uses_registry(
        self, aoi_definitions: AOICollection
    ) -> None:
        """AOI-typed local tags resolve nested members from AOI parameter defs."""
        generic_input = aoi_definitions["GenericInput"]
        nested = generic_input.local_tags["debounce"]
        assert isinstance(nested, StructNode)
        assert nested.members["EnableIn"].value == 1
        assert nested.members["state"].data_type == "BOOL"

    def test_local_tag_string_fallback(self, aoi_definitions: AOICollection) -> None:
        """String-format local tags fall back to DefaultData Format=String."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        robot_alarm_code = lookup.local_tags["robotAlarmCode"]
        assert robot_alarm_code.value == ""


class TestAOILocalTagTyping:
    """Tests for AOI local tag node typing and static class selection."""

    def test_struct_local_tag_isinstance_node(
        self, aoi_definitions: AOICollection
    ) -> None:
        """A TIMER local tag is both an AOILocalTag and a StructNode."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        assert isinstance(timer, AOILocalTag)
        assert isinstance(timer, StructNode)
        assert type(timer) is AOILocalStructTag

    def test_struct_local_tag_class_shared(
        self, aoi_definitions: AOICollection
    ) -> None:
        """Multiple TIMER locals share the same static class object."""
        debounce = aoi_definitions["Debounce"]
        timer1 = debounce.local_tags["debounceOnTimer"]
        generic_input = aoi_definitions["GenericInput"]
        timer2 = generic_input.local_tags["debounce"]
        # Both are StructNode-based local tags, so should have the same type
        assert type(timer1) is type(timer2)

    def test_integer_local_tag_with_properties(
        self, aoi_definitions: AOICollection
    ) -> None:
        """An integer local tag exposes its value, radix, and constraints."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        length = lookup.local_tags["length"]
        assert isinstance(length, IntegerNode)
        assert type(length) is AOILocalIntegerTag
        assert length.value == 0
        assert length.radix == "Decimal"
        assert length.min is None
        assert length.max is None
        assert length.bit_width == 32

    def test_integer_local_tag_describe(self, aoi_definitions: AOICollection) -> None:
        """describe() of integer local tag includes value and radix."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        length = lookup.local_tags["length"]
        desc = length.describe()
        assert "value: 0" in desc
        assert "radix: 'Decimal'" in desc

    def test_bool_local_tag(self, aoi_definitions: AOICollection) -> None:
        """A BOOL local tag is a BoolNode."""
        generic_input = aoi_definitions["GenericInput"]
        rising_ons = generic_input.local_tags["risingOns"]
        assert isinstance(rising_ons, BoolNode)
        assert rising_ons.data_type == "BOOL"
        assert rising_ons.value is False
        assert not hasattr(rising_ons, "min")

    def test_string_local_tag(self, aoi_definitions: AOICollection) -> None:
        """A STRING local tag is a StringNode."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        robot_alarm_code = lookup.local_tags["robotAlarmCode"]
        assert isinstance(robot_alarm_code, StringNode)
        assert robot_alarm_code.value == ""

    def test_local_tag_has_no_data_attribute(
        self, aoi_definitions: AOICollection
    ) -> None:
        """Typed local tags do not have a .data property (they ARE the node)."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        assert not hasattr(timer, "data")

    def test_local_tag_extra_attributes_excludes_radix_etc(
        self, aoi_definitions: AOICollection
    ) -> None:
        """Local tag.extra_attributes excludes Radix/Dimensions/Min/Max/etc."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        length = lookup.local_tags["length"]
        assert length.element.get("Radix") == "Decimal"
        assert "Radix" not in length.extra_attributes

    def test_local_tag_element_property(self, aoi_definitions: AOICollection) -> None:
        """Local tag.element returns the raw <LocalTag> element."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        assert timer.element is not None
        assert timer.element.tag == "LocalTag"

    def test_local_tag_value_element_differs(
        self, aoi_definitions: AOICollection
    ) -> None:
        """For typed local tags, value_element is not the same as element."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        # The typed local tag IS a StructNode, so it has a value_element
        assert timer.value_element is not timer.element


class TestAOILocalTagClasses:
    """Static AOI local tag classes are exported and selected per node type."""

    @pytest.mark.parametrize(
        ("aoi_name", "local_name", "expected_cls"),
        [
            ("Debounce", "debounceOnTimer", AOILocalStructTag),
            ("GenericInput", "risingOns", AOILocalBoolTag),
            ("GenericInput", "debounce", AOILocalStructTag),
            ("FanucAlarmLookup", "length", AOILocalIntegerTag),
            ("FanucAlarmLookup", "robotAlarmCode", AOILocalStringTag),
            ("FanucRobot", "startRobot", AOILocalBoolTag),
            ("FanucRobot", "alarmLookup", AOILocalStructTag),
        ],
    )
    def test_fixture_local_tag_class(
        self,
        aoi_definitions: AOICollection,
        aoi_name: str,
        local_name: str,
        expected_cls: type[AOILocalTag],
    ) -> None:
        """Each fixture local tag is an instance of its expected exported class."""
        local = aoi_definitions[aoi_name].local_tags[local_name]
        assert type(local) is expected_cls
        assert isinstance(local, AOILocalTag)

    def test_mapping_covers_node_classes(self) -> None:
        """Every node class maps to its static AOI local tag class."""
        assert {
            BoolNode: AOILocalBoolTag,
            IntegerNode: AOILocalIntegerTag,
            FloatNode: AOILocalFloatTag,
            TimeNode: AOILocalTimeTag,
            DateTimeNode: AOILocalDateTimeTag,
            AtomicNode: AOILocalAtomicTag,
            StringNode: AOILocalStringTag,
            StructNode: AOILocalStructTag,
            ArrayNode: AOILocalArrayTag,
        } == _AOI_LOCAL_TAG_CLASSES

    @pytest.mark.parametrize(
        ("cls", "node"),
        [
            (AOILocalBoolTag, BoolNode),
            (AOILocalIntegerTag, IntegerNode),
            (AOILocalFloatTag, FloatNode),
            (AOILocalTimeTag, TimeNode),
            (AOILocalDateTimeTag, DateTimeNode),
            (AOILocalAtomicTag, AtomicNode),
            (AOILocalStringTag, StringNode),
            (AOILocalStructTag, StructNode),
            (AOILocalArrayTag, ArrayNode),
        ],
    )
    def test_class_is_local_tag_and_node(self, cls: type, node: type) -> None:
        """Each static class combines AOILocalTag with its node class."""
        assert issubclass(cls, AOILocalTag)
        assert issubclass(cls, node)
        assert cls.__name__.startswith("AOILocal")

    def test_classes_exported_from_package(self) -> None:
        """All nine AOI local tag classes are listed in py_l5x.__all__."""
        import py_l5x

        for cls in (
            AOILocalArrayTag,
            AOILocalAtomicTag,
            AOILocalBoolTag,
            AOILocalDateTimeTag,
            AOILocalFloatTag,
            AOILocalIntegerTag,
            AOILocalStringTag,
            AOILocalStructTag,
            AOILocalTimeTag,
        ):
            assert cls.__name__ in py_l5x.__all__
            assert getattr(py_l5x, cls.__name__) is cls


class TestAoiLogicText:
    """Tests for AOI-level logic rendering helpers."""

    def test_logic_text_contains_headers_and_code(
        self, aoi_definitions: AOICollection
    ) -> None:
        """AOI.logic_text emits AOI/routine headers and routine text."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        text = lookup.logic_text()
        assert text.startswith("AOI: FanucAlarmLookup")
        assert "Routine: Logic (ST)" in text
        assert "recoverableAlarm := 0;" in text

    def test_print_logic_text_prints_and_returns(
        self,
        aoi_definitions: AOICollection,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """AOI.print_logic_text prints and returns the same content."""
        debounce = aoi_definitions["Debounce"]
        returned = debounce.print_logic_text()
        out = capsys.readouterr().out
        assert returned in out


# ---------------------------------------------------------------------------
# AOI parameters
# ---------------------------------------------------------------------------


class TestAOIParameterParsing:
    """Tests for AOIParameter and AOIParametersCollection parsing."""

    def test_parameter_identity(self, debounce_aoi: ET.Element) -> None:
        """Basic parameter properties are correctly extracted."""
        params = AOIParametersCollection(debounce_aoi)
        param = params["onDelay"]
        assert param.name == "onDelay"
        assert param.data_type == "DINT"
        assert param.usage == "Input"
        assert param.radix == "Decimal"
        assert param.required is False
        assert param.visible is True

    def test_parameter_description(self, debounce_aoi: ET.Element) -> None:
        """Parameter description is extracted from CDATA."""
        params = AOIParametersCollection(debounce_aoi)
        assert (
            "milliseconds before output bit turns ON" in params["onDelay"].description
        )

    def test_parameter_inout_detection(self, fanuc_robot_aoi: ET.Element) -> None:
        """InOut usage is correctly identified."""
        params = AOIParametersCollection(fanuc_robot_aoi)
        # allowableAlarms is InOut in FanucRobot
        assert params["allowableAlarms"].is_inout is True
        # robotUI is InOut in FanucRobot
        assert params["robotUI"].is_inout is True

    def test_filtered_parameters(self, fanuc_robot_aoi: ET.Element) -> None:
        """datatype_members excludes InOut parameters."""
        params = AOIParametersCollection(fanuc_robot_aoi)
        filtered = params.datatype_members
        assert "allowableAlarms" not in filtered
        assert "robotUI" not in filtered
        assert "robotUO" not in filtered

    def test_fanuc_robot_constant_is_declared_field(
        self, fanuc_robot_aoi: ET.Element
    ) -> None:
        """Constant is a declared field on parameters, not an extra attribute."""
        params = AOIParametersCollection(fanuc_robot_aoi)
        param = params["allowableAlarms"]
        assert param.constant is False
        assert "Constant" not in param.extra_attributes


# ---------------------------------------------------------------------------
# AOIDataTypesCollection mapping protocol
# ---------------------------------------------------------------------------


class TestAOIDataTypesCollection:
    """Tests for the AOIDataTypesCollection mapping protocol."""

    def test_contains_debounce(self, aoi_types: AOIDataTypesCollection) -> None:
        """Debounce is present in the collection."""
        assert "Debounce" in aoi_types

    def test_contains_fanuc_robot(self, aoi_types: AOIDataTypesCollection) -> None:
        """FanucRobot is present in the collection."""
        assert "FanucRobot" in aoi_types

    def test_getitem_returns_parameters(
        self, aoi_types: AOIDataTypesCollection
    ) -> None:
        """Indexing returns an AOIParametersCollection instance."""
        assert isinstance(aoi_types["Debounce"], AOIParametersCollection)

    def test_missing_key_raises(self, aoi_types: AOIDataTypesCollection) -> None:
        """Missing AOI name raises KeyError."""
        with pytest.raises(KeyError):
            aoi_types["NoSuchAOI"]


# ---------------------------------------------------------------------------
# AOIParametersCollection mapping protocol / datatype_members filtering
# ---------------------------------------------------------------------------


class TestAOIParametersCollection:
    """Tests for the AOIParametersCollection mapping and InOut filtering."""

    def test_contains_state_param(self, debounce: AOIParametersCollection) -> None:
        """The state parameter is present."""
        assert "state" in debounce

    def test_getitem_returns_parameter(self, debounce: AOIParametersCollection) -> None:
        """Indexing returns an AOIParameter instance."""
        assert isinstance(debounce["state"], AOIParameter)

    def test_datatype_members_excludes_inout(
        self, aoi_types: AOIDataTypesCollection
    ) -> None:
        """datatype_members excludes InOut params (FanucAlarmLookup allowableAlarms)."""
        alarm_lookup = aoi_types["FanucAlarmLookup"]
        assert "allowableAlarms" in alarm_lookup
        assert "allowableAlarms" not in alarm_lookup.datatype_members

    def test_datatype_members_includes_input_output(
        self, generic_input: AOIParametersCollection
    ) -> None:
        """datatype_members includes Input/Output parameters."""
        assert "state" in generic_input.datatype_members
        assert "onDelay" in generic_input.datatype_members


# ---------------------------------------------------------------------------
# AOIParameter identity / metadata
# ---------------------------------------------------------------------------


class TestAOIParameterIdentity:
    """Tests for AOIParameter identity properties."""

    def test_name(self, debounce: AOIParametersCollection) -> None:
        """Name matches the Name attribute."""
        assert debounce["state"].name == "state"

    def test_data_type(self, debounce: AOIParametersCollection) -> None:
        """Data type matches the DataType attribute."""
        assert debounce["onDelay"].data_type == "DINT"

    def test_usage_input(self, debounce: AOIParametersCollection) -> None:
        """onDelay is an Input parameter."""
        assert debounce["onDelay"].usage == "Input"

    def test_usage_output(self, debounce: AOIParametersCollection) -> None:
        """state is an Output parameter."""
        assert debounce["state"].usage == "Output"

    def test_is_inout(self, aoi_types: AOIDataTypesCollection) -> None:
        """allowableAlarms uses InOut usage."""
        assert aoi_types["FanucAlarmLookup"]["allowableAlarms"].is_inout is True

    def test_description(self, debounce: AOIParametersCollection) -> None:
        """Description text matches the Description CDATA."""
        assert (
            debounce["onDelay"].description == "milliseconds before output bit turns ON"
        )


class TestAOIParameterMetadata:
    """Tests for AOIParameter min/max/engineering_unit/state0/state1."""

    def test_min(self, debounce: AOIParametersCollection) -> None:
        """Min matches the Min attribute, converted to int."""
        assert debounce["onDelay"].min == 0

    def test_max(self, debounce: AOIParametersCollection) -> None:
        """Max matches the Max attribute, converted to int."""
        assert debounce["onDelay"].max == 2147483647

    def test_engineering_unit(self, debounce: AOIParametersCollection) -> None:
        """Engineering unit matches the nested EngineeringUnits CDATA."""
        assert debounce["onDelay"].engineering_unit == "ms"

    def test_state0(self, debounce: AOIParametersCollection) -> None:
        """State0 matches the nested State0s/State0 CDATA."""
        assert debounce["state"].state0 == "off"

    def test_state1(self, debounce: AOIParametersCollection) -> None:
        """State1 matches the nested State1s/State1 CDATA."""
        assert debounce["state"].state1 == "on"

    def test_min_max_absent_returns_none(
        self, generic_input: AOIParametersCollection
    ) -> None:
        """Min/max are None when not specified."""
        assert generic_input["state"].min is None
        assert generic_input["state"].max is None

    def test_engineering_unit_absent_returns_empty(
        self, generic_input: AOIParametersCollection
    ) -> None:
        """Engineering unit is empty string when not specified."""
        assert generic_input["state"].engineering_unit == ""


# ---------------------------------------------------------------------------
# AOIParameter shares its identity base with AOILocalTag
# ---------------------------------------------------------------------------

_PARAM_XML = (
    '<Parameter Name="p" TagType="Base" DataType="REAL" Usage="Input" '
    'Radix="Float" Required="false" Visible="true" ExternalAccess="Read/Write" '
    'Description="from attr" Min="0.5" Max="9.5" ExternalLogging="true" '
    'Foo="1">'
    '<DefaultData Format="Decorated">'
    '<DataValue DataType="REAL" Radix="Float" Value="1.0"/>'
    "</DefaultData></Parameter>"
)


class TestAOIParameterSharedBase:
    """Parameters and local tags share the _AOIDefinitionTag identity base."""

    def test_parameter_and_local_tag_share_base(self) -> None:
        """Both AOI parameters and AOI local tags derive from _AOIDefinitionTag."""
        assert issubclass(AOIParameter, _AOIDefinitionTag)
        assert issubclass(AOILocalTag, _AOIDefinitionTag)

    def test_description_attr_fallback(self) -> None:
        """A bare Description attribute is read for parameters, as for tags."""
        param = AOIParameter(ET.fromstring(_PARAM_XML))
        assert param.description == "from attr"
        assert "Description" not in param.extra_attributes

    def test_extra_attributes_exclude_known_keys(self) -> None:
        """Min/Max/ExternalLogging/Radix are not reported as extra attributes."""
        param = AOIParameter(ET.fromstring(_PARAM_XML))
        assert param.extra_attributes == {"TagType": "Base", "Foo": "1"}

    def test_repr_is_describe_with_header(self) -> None:
        """repr matches describe(); the header includes name and data type."""
        param = AOIParameter(ET.fromstring(_PARAM_XML))
        assert repr(param) == param.describe()
        assert param.describe().splitlines()[0] == "AOIParameter('p', 'REAL')"

    def test_describe_lists_metadata_once(self) -> None:
        """Min/Max appear once each in describe(); declared fields are not repeated."""
        param = AOIParameter(ET.fromstring(_PARAM_XML))
        lines = param.describe().splitlines()
        assert lines.count("  min: 0.5") == 1
        assert lines.count("  max: 9.5") == 1
        assert sum(line.strip().startswith("external_logging") for line in lines) == 1
        assert sum(line.strip().startswith("description") for line in lines) == 1

    def test_constant_is_declared(self) -> None:
        """Constant on a parameter is a declared field read as a bool."""
        param = AOIParameter(ET.fromstring(_PARAM_XML))
        assert param.constant is False
        const = AOIParameter(
            ET.fromstring(_PARAM_XML.replace('Foo="1"', 'Constant="true"'))
        )
        assert const.constant is True
        assert "  constant = True" in const.describe().splitlines()

    def test_describe_uses_debounce_metadata(
        self, debounce: AOIParametersCollection
    ) -> None:
        """Debounce's state parameter describes its description and states."""
        text = debounce["state"].describe()
        assert "  description = 'debounced output'" in text
        assert "  state0: 'off'" in text
        assert "  state1: 'on'" in text
        assert "engineering_unit" not in text

    def test_describe_uses_debounce_units_and_limits(
        self, debounce: AOIParametersCollection
    ) -> None:
        """Debounce's onDelay describes its engineering unit and min/max."""
        text = debounce["onDelay"].describe()
        assert "  min: 0" in text.splitlines()
        assert "  max: 2147483647" in text.splitlines()
        assert "  engineering_unit: 'ms'" in text.splitlines()


class TestAOIParameterOverrides:
    """Operand-qualified parameter metadata is kept as overrides."""

    def test_seqctrl_state_overrides_contain_running(
        self, aoi_types: AOIDataTypesCollection
    ) -> None:
        """SeqCtrl's state parameter has a '.0' comment override of 'running'."""
        state = aoi_types["SeqCtrl"]["state"]
        assert state._overrides.get(".0") == {"comment": "running"}

    def test_parameter_gets_registry_from_definition(
        self, aoi_definitions: AOICollection, type_registry: TypeRegistry
    ) -> None:
        """AOIDefinition.parameters passes its type registry to each parameter."""
        params = aoi_definitions["Debounce"].parameters
        assert params["onDelay"]._type_registry is type_registry

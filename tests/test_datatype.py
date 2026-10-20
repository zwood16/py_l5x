"""Tests for py_l5x.parsers.datatype (UDT DataTypes and AOI parameters)."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.datatype import (
    AddOnDataTypeCollection,
    AddOnParameter,
    AddOnParameters,
    DataType,
    DataTypesCollection,
)
from py_l5x.parsers.utils import convert_numeric

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
def data_types(controller_element: ET.Element) -> DataTypesCollection:
    """Create a DataTypesCollection instance from the example L5X."""
    return DataTypesCollection(controller_element)


@pytest.fixture
def aoi_definitions(example_tree: ET.ElementTree) -> list[ET.Element]:
    """Extract all <AddOn InstructionDefinition> elements from the example L5X."""
    root = example_tree.getroot()
    defs = root.findall(".//AddOnInstructionDefinition")
    assert len(defs) > 0, "No AddOnInstructionDefinition elements found in example.L5X"
    return defs


@pytest.fixture
def debounce_aoi(aoi_definitions: list[ET.Element]) -> ET.Element:
    """The Debounce AOI definition."""
    for el in aoi_definitions:
        if el.get("Name") == "Debounce":
            return el
    pytest.fail("Debounce AOI not found in example.L5X")


@pytest.fixture
def generic_input_aoi(aoi_definitions: list[ET.Element]) -> ET.Element:
    """The GenericInput AOI definition."""
    for el in aoi_definitions:
        if el.get("Name") == "GenericInput":
            return el
    pytest.fail("GenericInput AOI not found in example.L5X")


@pytest.fixture
def fanuc_robot_aoi(aoi_definitions: list[ET.Element]) -> ET.Element:
    """The FanucRobot AOI definition."""
    for el in aoi_definitions:
        if el.get("Name") == "FanucRobot":
            return el
    pytest.fail("FanucRobot AOI not found in example.L5X")


@pytest.fixture
def a_udt(data_types: DataTypesCollection) -> DataType:
    """The A_UDT data type."""
    return data_types["A_UDT"]


@pytest.fixture
def aoi_types(controller_element: ET.Element) -> AddOnDataTypeCollection:
    """Create an AddOnDataTypeCollection instance from the example L5X."""
    return AddOnDataTypeCollection(controller_element)


@pytest.fixture
def debounce(aoi_types: AddOnDataTypeCollection) -> AddOnParameters:
    """The Debounce AOI's parameters."""
    return aoi_types["Debounce"]


@pytest.fixture
def generic_input(aoi_types: AddOnDataTypeCollection) -> AddOnParameters:
    """The GenericInput AOI's parameters."""
    return aoi_types["GenericInput"]


# ---------------------------------------------------------------------------
# DataTypesCollection mapping protocol
# ---------------------------------------------------------------------------


class TestDataTypesCollection:
    """Tests for the DataTypesCollection mapping protocol."""

    def test_contains_a_udt(self, data_types: DataTypesCollection) -> None:
        """A_UDT is present in the collection."""
        assert "A_UDT" in data_types

    def test_contains_string_family_type(self, data_types: DataTypesCollection) -> None:
        """robotString is present in the collection."""
        assert "robotString" in data_types

    def test_len(self, data_types: DataTypesCollection) -> None:
        """Collection length matches the number of <DataType> elements."""
        assert len(data_types) == len(
            list(data_types._parent.findall("DataTypes/DataType"))
        )

    def test_iteration_yields_names(self, data_types: DataTypesCollection) -> None:
        """Iterating yields DataType names."""
        assert "A_UDT" in list(data_types)

    def test_getitem_returns_data_type(self, data_types: DataTypesCollection) -> None:
        """Indexing returns a DataType instance."""
        assert isinstance(data_types["A_UDT"], DataType)

    def test_missing_key_raises(self, data_types: DataTypesCollection) -> None:
        """Missing data type name raises KeyError."""
        with pytest.raises(KeyError):
            data_types["NoSuchType"]


# ---------------------------------------------------------------------------
# DataType identity
# ---------------------------------------------------------------------------


class TestDataTypeIdentity:
    """Tests for DataType identity properties."""

    def test_name(self, a_udt: DataType) -> None:
        """Name matches the Name attribute."""
        assert a_udt.name == "A_UDT"

    def test_family(self, a_udt: DataType) -> None:
        """Family matches the Family attribute."""
        assert a_udt.family == "NoFamily"

    def test_class(self, a_udt: DataType) -> None:
        """Class matches the Class attribute."""
        assert a_udt.class_ == "User"

    def test_is_string_false(self, a_udt: DataType) -> None:
        """A_UDT is not a string family type."""
        assert a_udt.is_string is False


# ---------------------------------------------------------------------------
# String family types
# ---------------------------------------------------------------------------


class TestStringFamily:
    """Tests for STRING-family data types."""

    def test_robot_string_is_string(self, data_types: DataTypesCollection) -> None:
        """robotString is flagged as a string family type."""
        assert data_types["robotString"].is_string is True

    def test_robot_string_max_length(self, data_types: DataTypesCollection) -> None:
        """robotString max_length matches the DATA member dimension."""
        assert data_types["robotString"].max_length == 100

    def test_robot_alarm_code_max_length(self, data_types: DataTypesCollection) -> None:
        """robotAlarmCode max_length matches the DATA member dimension."""
        assert data_types["robotAlarmCode"].max_length == 8

    def test_non_string_max_length_is_none(self, a_udt: DataType) -> None:
        """Non-string data types have no max_length."""
        assert a_udt.max_length is None


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


class TestDataTypeMembers:
    """Tests for DataTypeMember properties via A_UDT."""

    def test_bit_member_target(self, a_udt: DataType) -> None:
        """Bit member target references the hidden host member."""
        member = a_udt.members["a_Bool"]
        assert member.is_bit_member is True
        assert member.target == "ZZZZZZZZZZA_UDT0"
        assert member.bit_number == 0

    def test_bit_member_hidden_is_false(self, a_udt: DataType) -> None:
        """Bit members themselves are not hidden."""
        assert a_udt.members["a_Bool"].hidden is False

    def test_host_member_is_hidden(self, a_udt: DataType) -> None:
        """The host SINT member is hidden."""
        assert a_udt.members["ZZZZZZZZZZA_UDT0"].hidden is True

    def test_non_bit_member_bit_number_is_none(self, a_udt: DataType) -> None:
        """Non-bit members have no bit_number."""
        assert a_udt.members["a_sint"].bit_number is None

    def test_second_bit_member_number(self, a_udt: DataType) -> None:
        """Second bit member in the host has bit_number 1."""
        assert a_udt.members["on_off_bool"].bit_number == 1

    def test_min_max_are_typed_ints(self, a_udt: DataType) -> None:
        """Min/Max on a SINT member convert to int."""
        member = a_udt.members["a_sint_with_props"]
        assert member.min == 0
        assert member.max == 25
        assert isinstance(member.min, int)
        assert isinstance(member.max, int)

    def test_min_max_absent_is_none(self, a_udt: DataType) -> None:
        """Members without Min/Max return None."""
        member = a_udt.members["a_sint"]
        assert member.min is None
        assert member.max is None

    def test_array_member(self, a_udt: DataType) -> None:
        """Array member has correct dimension and is_array."""
        member = a_udt.members["an_array"]
        assert member.dimension == 4
        assert member.is_array is True

    def test_non_array_member(self, a_udt: DataType) -> None:
        """Non-array member has dimension 0 and is_array False."""
        member = a_udt.members["a_sint"]
        assert member.dimension == 0
        assert member.is_array is False

    def test_nested_udt_member(self, a_udt: DataType) -> None:
        """Nested UDT member's data_type is the referenced UDT name."""
        assert a_udt.members["a_nested_UDT"].data_type == "simple_udt"

    def test_nested_aoi_member(self, a_udt: DataType) -> None:
        """Nested AOI member's data_type is the referenced AOI name."""
        assert a_udt.members["an_aoi"].data_type == "GenericInput"

    def test_description(self, a_udt: DataType) -> None:
        """Member description text is extracted from CDATA."""
        assert a_udt.members["a_Bool"].description == "This is a bool"

    def test_engineering_unit(self, a_udt: DataType) -> None:
        """Member engineering unit text is extracted from CDATA."""
        assert a_udt.members["on_off_bool"].engineering_unit == "Boolean"

    def test_state0_state1(self, a_udt: DataType) -> None:
        """Boolean member State0/State1 text is extracted from CDATA."""
        member = a_udt.members["on_off_bool"]
        assert member.state0 == "Off"
        assert member.state1 == "On"

    def test_external_logging_present(self, a_udt: DataType) -> None:
        """ExternalLogging attribute converts to bool when present."""
        assert a_udt.members["on_off_bool"].external_logging is True
        assert a_udt.members["a_sint_with_props"].external_logging is False

    def test_external_logging_absent_is_none(self, a_udt: DataType) -> None:
        """ExternalLogging is None when the attribute is absent."""
        assert a_udt.members["a_sint"].external_logging is None

    def test_external_access(self, a_udt: DataType) -> None:
        """External access matches the ExternalAccess attribute."""
        assert a_udt.members["a_sint"].external_access == "Read/Write"


# ---------------------------------------------------------------------------
# visible_members / bit_groups
# ---------------------------------------------------------------------------


class TestVisibleMembersAndBitGroups:
    """Tests for the packed-boolean convenience helpers."""

    def test_visible_members_excludes_hidden_hosts(self, a_udt: DataType) -> None:
        """visible_members excludes the hidden host bytes."""
        visible = a_udt.visible_members
        assert "ZZZZZZZZZZA_UDT0" not in visible
        assert "ZZZZZZZZZZA_UDT6" not in visible

    def test_visible_members_includes_regular_members(self, a_udt: DataType) -> None:
        """visible_members still includes non-hidden members."""
        visible = a_udt.visible_members
        assert "a_Bool" in visible
        assert "a_sint" in visible

    def test_visible_members_count(self, a_udt: DataType) -> None:
        """visible_members length excludes exactly the two hidden hosts."""
        assert len(a_udt.visible_members) == len(a_udt.members) - 2

    def test_bit_groups_keys(self, a_udt: DataType) -> None:
        """bit_groups is keyed by the hidden host member names."""
        groups = a_udt.bit_groups
        assert set(groups) == {"ZZZZZZZZZZA_UDT0", "ZZZZZZZZZZA_UDT6"}

    def test_bit_groups_members(self, a_udt: DataType) -> None:
        """bit_groups lists the correct bit members for each host."""
        groups = a_udt.bit_groups
        assert [m.name for m in groups["ZZZZZZZZZZA_UDT0"]] == [
            "a_Bool",
            "on_off_bool",
        ]
        assert [m.name for m in groups["ZZZZZZZZZZA_UDT6"]] == ["another_bool"]


# ---------------------------------------------------------------------------
# Extra / all attributes
# ---------------------------------------------------------------------------


class TestDataTypeAttributes:
    """Tests for DataType extra_attributes/attributes."""

    def test_extra_attributes_empty_for_a_udt(self, a_udt: DataType) -> None:
        """A_UDT has no attributes beyond Name/Family/Class."""
        assert a_udt.extra_attributes == {}

    def test_attributes_contains_known_keys(self, a_udt: DataType) -> None:
        """attributes includes Name/Family/Class."""
        attrs = a_udt.attributes
        assert attrs["Name"] == "A_UDT"
        assert attrs["Family"] == "NoFamily"
        assert attrs["Class"] == "User"


class TestDataTypeMemberAttributes:
    """Tests for DataTypeMember extra_attributes/attributes."""

    def test_extra_attributes_excludes_known_keys(self, a_udt: DataType) -> None:
        """Known keys are excluded from extra_attributes."""
        extras = a_udt.members["a_sint_with_props"].extra_attributes
        for key in ("Name", "DataType", "Max", "Min"):
            assert key not in extras

    def test_attributes_is_superset(self, a_udt: DataType) -> None:
        """attributes contains everything in extra_attributes plus known keys."""
        member = a_udt.members["a_sint_with_props"]
        attrs = member.attributes
        for k, v in member.extra_attributes.items():
            assert attrs[k] == v


# ---------------------------------------------------------------------------
# __repr__ / describe()
# ---------------------------------------------------------------------------


class TestDataTypeRepr:
    """Tests for DataType.__repr__/describe()."""

    def test_header(self, a_udt: DataType) -> None:
        """First line is the DataType('Name') header."""
        assert repr(a_udt).splitlines()[0] == "DataType('A_UDT')"

    def test_repr_equals_describe(self, a_udt: DataType) -> None:
        """__repr__ returns describe()."""
        assert repr(a_udt) == a_udt.describe()

    def test_key_lines(self, a_udt: DataType) -> None:
        """Identity lines and the members block are present."""
        lines = repr(a_udt).splitlines()
        assert "  family = 'NoFamily'" in lines
        assert "  class_ = 'User'" in lines
        assert "  members:" in lines
        assert "    a_sint: SINT" in lines
        assert "    a_nested_UDT: simple_udt" in lines

    def test_hidden_host_members_omitted(self, a_udt: DataType) -> None:
        """Hidden packed-boolean host bytes are not listed."""
        assert "ZZZZZZZZZZA_UDT0" not in repr(a_udt)

    def test_no_max_length_for_non_string(self, a_udt: DataType) -> None:
        """max_length is only shown for STRING-family types."""
        assert "max_length" not in repr(a_udt)

    def test_string_family_shows_max_length(
        self, data_types: DataTypesCollection
    ) -> None:
        """STRING-family types include max_length."""
        text = repr(data_types["robotString"])
        assert "  max_length: 100" in text.splitlines()
        assert "    DATA: SINT" in text.splitlines()

    def test_no_duplicate_lines(self, a_udt: DataType) -> None:
        """Each describe line appears once."""
        lines = repr(a_udt).splitlines()
        assert len(lines) == len(set(lines))


class TestDataTypeMemberRepr:
    """Tests for DataTypeMember.__repr__/describe()."""

    def test_header(self, a_udt: DataType) -> None:
        """First line is the DataTypeMember('name', 'data_type') header."""
        member = a_udt.members["a_sint"]
        assert repr(member).splitlines()[0] == "DataTypeMember('a_sint', 'SINT')"

    def test_repr_equals_describe(self, a_udt: DataType) -> None:
        """__repr__ returns describe()."""
        member = a_udt.members["a_sint"]
        assert repr(member) == member.describe()

    def test_min_max_lines_when_set(self, a_udt: DataType) -> None:
        """Min/Max are listed when present."""
        lines = repr(a_udt.members["a_sint_with_props"]).splitlines()
        assert "  min: 0" in lines
        assert "  max: 25" in lines

    def test_min_max_omitted_when_absent(self, a_udt: DataType) -> None:
        """Min/Max lines are omitted when the attributes are absent."""
        text = repr(a_udt.members["a_sint"])
        assert "min:" not in text
        assert "max:" not in text

    def test_no_duplicate_lines(self, a_udt: DataType) -> None:
        """Each describe line appears once."""
        lines = repr(a_udt.members["a_sint_with_props"]).splitlines()
        assert len(lines) == len(set(lines))


# ---------------------------------------------------------------------------
# convert_numeric
# ---------------------------------------------------------------------------


class TestConvertNumeric:
    """Unit tests for the convert_numeric helper."""

    def test_int_type(self) -> None:
        """Integer atomic types convert to int."""
        assert convert_numeric("25", "SINT") == 25
        assert isinstance(convert_numeric("25", "DINT"), int)

    def test_real_type(self) -> None:
        """Real atomic types convert to float."""
        assert convert_numeric("3.14", "REAL") == pytest.approx(3.14)
        assert isinstance(convert_numeric("1", "LREAL"), float)

    def test_unknown_type_falls_back_to_str(self) -> None:
        """Unknown data types are returned unchanged."""
        assert convert_numeric("some_value", "simple_udt") == "some_value"

    def test_unparseable_int_falls_back_to_str(self) -> None:
        """Values that don't parse cleanly are returned unchanged."""
        assert convert_numeric("not_a_number", "SINT") == "not_a_number"


# ---------------------------------------------------------------------------
# Add-On Instruction Parameters
# ---------------------------------------------------------------------------


class TestAddOnInstructionParameters:
    """Tests for AddOnInstructionParameter and AddOnInstructionParameters."""

    def test_parameter_identity(self, debounce_aoi: ET.Element) -> None:
        """Basic parameter properties are correctly extracted."""
        params = AddOnParameters(debounce_aoi)
        param = params["onDelay"]
        assert param.name == "onDelay"
        assert param.data_type == "DINT"
        assert param.usage == "Input"
        assert param.radix == "Decimal"
        assert param.required is False
        assert param.visible is True

    def test_parameter_description(self, debounce_aoi: ET.Element) -> None:
        """Parameter description is extracted from CDATA."""
        params = AddOnParameters(debounce_aoi)
        assert (
            "milliseconds before output bit turns ON" in params["onDelay"].description
        )

    def test_parameter_inout_detection(self, fanuc_robot_aoi: ET.Element) -> None:
        """InOut usage is correctly identified."""
        params = AddOnParameters(fanuc_robot_aoi)
        # allowableAlarms is InOut in FanucRobot
        assert params["allowableAlarms"].is_inout is True
        # robotUI is InOut in FanucRobot
        assert params["robotUI"].is_inout is True

    def test_filtered_parameters(self, fanuc_robot_aoi: ET.Element) -> None:
        """datatype_members excludes InOut parameters."""
        params = AddOnParameters(fanuc_robot_aoi)
        filtered = params.datatype_members
        assert "allowableAlarms" not in filtered
        assert "robotUI" not in filtered
        assert "robotUO" not in filtered

    def test_fanuc_robot_extra_attributes(self, fanuc_robot_aoi: ET.Element) -> None:
        """Verify extra attributes like 'Constant' are captured."""
        params = AddOnParameters(fanuc_robot_aoi)
        param = params["allowableAlarms"]
        assert param.extra_attributes.get("Constant") == "false"


# ---------------------------------------------------------------------------
# AddOnDataTypeCollection mapping protocol
# ---------------------------------------------------------------------------


class TestAddOnDataTypeCollection:
    """Tests for the AddOnDataTypeCollection mapping protocol."""

    def test_contains_debounce(self, aoi_types: AddOnDataTypeCollection) -> None:
        """Debounce is present in the collection."""
        assert "Debounce" in aoi_types

    def test_contains_fanuc_robot(self, aoi_types: AddOnDataTypeCollection) -> None:
        """FanucRobot is present in the collection."""
        assert "FanucRobot" in aoi_types

    def test_getitem_returns_parameters(
        self, aoi_types: AddOnDataTypeCollection
    ) -> None:
        """Indexing returns an AddOnParameters instance."""
        assert isinstance(aoi_types["Debounce"], AddOnParameters)

    def test_missing_key_raises(self, aoi_types: AddOnDataTypeCollection) -> None:
        """Missing AOI name raises KeyError."""
        with pytest.raises(KeyError):
            aoi_types["NoSuchAOI"]


# ---------------------------------------------------------------------------
# AddOnParameters mapping protocol / datatype_members filtering
# ---------------------------------------------------------------------------


class TestAddOnParameters:
    """Tests for the AddOnParameters mapping and InOut filtering."""

    def test_contains_state_param(self, debounce: AddOnParameters) -> None:
        """The state parameter is present."""
        assert "state" in debounce

    def test_getitem_returns_parameter(self, debounce: AddOnParameters) -> None:
        """Indexing returns an AddOnParameter instance."""
        assert isinstance(debounce["state"], AddOnParameter)

    def test_datatype_members_excludes_inout(
        self, aoi_types: AddOnDataTypeCollection
    ) -> None:
        """datatype_members excludes InOut params (FanucAlarmLookup allowableAlarms)."""
        alarm_lookup = aoi_types["FanucAlarmLookup"]
        assert "allowableAlarms" in alarm_lookup
        assert "allowableAlarms" not in alarm_lookup.datatype_members

    def test_datatype_members_includes_input_output(
        self, generic_input: AddOnParameters
    ) -> None:
        """datatype_members includes Input/Output parameters."""
        assert "state" in generic_input.datatype_members
        assert "onDelay" in generic_input.datatype_members


# ---------------------------------------------------------------------------
# AddOnParameter identity / metadata
# ---------------------------------------------------------------------------


class TestAddOnParameterIdentity:
    """Tests for AddOnParameter identity properties."""

    def test_name(self, debounce: AddOnParameters) -> None:
        """Name matches the Name attribute."""
        assert debounce["state"].name == "state"

    def test_data_type(self, debounce: AddOnParameters) -> None:
        """Data type matches the DataType attribute."""
        assert debounce["onDelay"].data_type == "DINT"

    def test_usage_input(self, debounce: AddOnParameters) -> None:
        """onDelay is an Input parameter."""
        assert debounce["onDelay"].usage == "Input"

    def test_usage_output(self, debounce: AddOnParameters) -> None:
        """state is an Output parameter."""
        assert debounce["state"].usage == "Output"

    def test_is_inout(self, aoi_types: AddOnDataTypeCollection) -> None:
        """allowableAlarms uses InOut usage."""
        assert aoi_types["FanucAlarmLookup"]["allowableAlarms"].is_inout is True

    def test_description(self, debounce: AddOnParameters) -> None:
        """Description text matches the Description CDATA."""
        assert (
            debounce["onDelay"].description == "milliseconds before output bit turns ON"
        )


class TestAddOnParameterMetadata:
    """Tests for AddOnParameter min/max/engineering_unit/state0/state1."""

    def test_min(self, debounce: AddOnParameters) -> None:
        """Min matches the Min attribute, converted to int."""
        assert debounce["onDelay"].min == 0

    def test_max(self, debounce: AddOnParameters) -> None:
        """Max matches the Max attribute, converted to int."""
        assert debounce["onDelay"].max == 2147483647

    def test_engineering_unit(self, debounce: AddOnParameters) -> None:
        """Engineering unit matches the nested EngineeringUnits CDATA."""
        assert debounce["onDelay"].engineering_unit == "ms"

    def test_state0(self, debounce: AddOnParameters) -> None:
        """State0 matches the nested State0s/State0 CDATA."""
        assert debounce["state"].state0 == "off"

    def test_state1(self, debounce: AddOnParameters) -> None:
        """State1 matches the nested State1s/State1 CDATA."""
        assert debounce["state"].state1 == "on"

    def test_min_max_absent_returns_none(self, generic_input: AddOnParameters) -> None:
        """Min/max are None when not specified."""
        assert generic_input["state"].min is None
        assert generic_input["state"].max is None

    def test_engineering_unit_absent_returns_empty(
        self, generic_input: AddOnParameters
    ) -> None:
        """Engineering unit is empty string when not specified."""
        assert generic_input["state"].engineering_unit == ""

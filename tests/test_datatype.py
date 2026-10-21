"""Tests for py_l5x.parsers.datatype (UDT DataTypes)."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.datatype import (
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
def a_udt(data_types: DataTypesCollection) -> DataType:
    """The A_UDT data type."""
    return data_types["A_UDT"]


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

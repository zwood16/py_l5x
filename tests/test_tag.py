"""Tests for py_l5x.parsers.tag and py_l5x.parsers.program."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.program import Program, ProgramsCollection
from py_l5x.parsers.tag import (
    Tag,
    TagsCollection,
    TagValueArray,
    TagValueScalar,
    TagValueStructure,
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
        AddOnDataTypeCollection(controller_element),
    )


@pytest.fixture
def controller_tags(
    controller_element: ET.Element, type_registry: TypeRegistry
) -> TagsCollection:
    """Controller-scoped tags collection."""
    return TagsCollection(controller_element, type_registry)


@pytest.fixture
def programs(
    controller_element: ET.Element, type_registry: TypeRegistry
) -> ProgramsCollection:
    """Programs collection."""
    return ProgramsCollection(controller_element, type_registry)


@pytest.fixture
def main_program_tags(programs: ProgramsCollection) -> TagsCollection:
    """MainProgram's tags collection."""
    return programs["MainProgram"].tags


# ---------------------------------------------------------------------------
# TagsCollection / ProgramsCollection mapping protocol
# ---------------------------------------------------------------------------


class TestTagsCollection:
    """Tests for the TagsCollection mapping protocol."""

    def test_contains_controller_tag(self, controller_tags: TagsCollection) -> None:
        """Controller-scoped tag is present."""
        assert "ALLOWABLE_ALARMS" in controller_tags

    def test_getitem_returns_tag(self, controller_tags: TagsCollection) -> None:
        """Indexing returns a Tag instance."""
        assert isinstance(controller_tags["ALLOWABLE_ALARMS"], Tag)

    def test_missing_key_raises(self, controller_tags: TagsCollection) -> None:
        """Missing tag name raises KeyError."""
        with pytest.raises(KeyError):
            controller_tags["NoSuchTag"]


class TestProgramsCollection:
    """Tests for the ProgramsCollection mapping protocol and Program identity."""

    def test_contains_main_program(self, programs: ProgramsCollection) -> None:
        """MainProgram is present."""
        assert "MainProgram" in programs

    def test_getitem_returns_program(self, programs: ProgramsCollection) -> None:
        """Indexing returns a Program instance."""
        assert isinstance(programs["MainProgram"], Program)

    def test_main_routine_name(self, programs: ProgramsCollection) -> None:
        """Main routine name matches the MainRoutineName attribute."""
        assert programs["MainProgram"].main_routine_name == "MainRoutine"

    def test_program_tags_returns_tags_collection(
        self, programs: ProgramsCollection
    ) -> None:
        """Program.tags returns a TagsCollection scoped to that program."""
        assert isinstance(programs["MainProgram"].tags, TagsCollection)
        assert "a_dint" in programs["MainProgram"].tags


# ---------------------------------------------------------------------------
# Atomic leaf tags
# ---------------------------------------------------------------------------


class TestAtomicTags:
    """Tests for plain atomic tag values."""

    def test_a_dint_value(self, main_program_tags: TagsCollection) -> None:
        """a_dint value is an int."""
        value_node = main_program_tags["a_dint"].value
        assert isinstance(value_node, TagValueScalar)
        assert value_node.value == 0

    def test_a_dint_description(self, main_program_tags: TagsCollection) -> None:
        """a_dint tag-level description is exposed via Tag.description."""
        assert main_program_tags["a_dint"].description == "a standard double integer"

    def test_a_bool_value(self, main_program_tags: TagsCollection) -> None:
        """a_bool value parses as an int (BOOL uses 0/1)."""
        assert main_program_tags["a_bool"].value.value == 0

    def test_a_real_value(self, main_program_tags: TagsCollection) -> None:
        """a_real value parses as a float."""
        assert main_program_tags["a_real"].value.value == 0.0

    def test_an_unsigned_dint_value(self, main_program_tags: TagsCollection) -> None:
        """an_unsigned_dint value parses as an int."""
        assert main_program_tags["an_unsigned_dint"].value.value == 0

    def test_datetime_value_passthrough(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Non-numeric radix values (DT#...) pass through as raw strings."""
        assert (
            main_program_tags["datetime"].value.value
            == "DT#1970-01-01-00:00:00.000_000Z"
        )


# ---------------------------------------------------------------------------
# STRING-family top-level tags (Format="String" fallback)
# ---------------------------------------------------------------------------


class TestStringTags:
    """Tests for top-level STRING-family tags using the String data fallback."""

    def test_a_string_value(self, main_program_tags: TagsCollection) -> None:
        """a_string (STRING type) resolves to an empty string."""
        value_node = main_program_tags["a_string"].value
        assert isinstance(value_node, TagValueScalar)
        assert value_node.value == ""

    def test_a_custom_string_value(self, main_program_tags: TagsCollection) -> None:
        """a_custom_string (custom StringFamily UDT) resolves via the String fallback."""
        assert main_program_tags["a_custom_string"].value.value == ""


# ---------------------------------------------------------------------------
# Nested UDT / AOI / array drill-down
# ---------------------------------------------------------------------------


class TestNestedUdtDrillDown:
    """Tests for nested UDT/array/AOI member drill-down."""

    def test_root_is_structure(self, main_program_tags: TagsCollection) -> None:
        """a_udt_instance's value root is a TagValueStructure."""
        assert isinstance(main_program_tags["a_udt_instance"].value, TagValueStructure)

    def test_nested_udt_member(self, main_program_tags: TagsCollection) -> None:
        """Drilling into a nested UDT member (a_nested_UDT.Dint) works."""
        udt = main_program_tags["a_udt_instance"].value
        assert udt["a_nested_UDT"]["Dint"].value == 0

    def test_array_of_atomics(self, main_program_tags: TagsCollection) -> None:
        """Drilling into an array-of-atomics member (an_array[0]) works."""
        udt = main_program_tags["a_udt_instance"].value
        array_node = udt["an_array"]
        assert isinstance(array_node, TagValueArray)
        assert array_node[0].value == 0.0
        assert len(array_node) == 4

    def test_nested_aoi_member(self, main_program_tags: TagsCollection) -> None:
        """Drilling into a nested AOI-instance member (an_aoi.state) cross-refs AOI defs."""
        udt = main_program_tags["a_udt_instance"].value
        state_node = udt["an_aoi"]["state"]
        assert state_node.value == 0
        assert state_node.description == "Debounced device value"


class TestArrayOfStructures:
    """Tests for top-level arrays of structures (ALLOWABLE_ALARMS)."""

    def test_element_is_structure(self, controller_tags: TagsCollection) -> None:
        """Each array element is a TagValueStructure."""
        alarms = controller_tags["ALLOWABLE_ALARMS"].value
        assert isinstance(alarms, TagValueArray)
        assert isinstance(alarms[1], TagValueStructure)

    def test_element_data_value(self, controller_tags: TagsCollection) -> None:
        """Element 1's DATA member matches the expected alarm code."""
        alarms = controller_tags["ALLOWABLE_ALARMS"].value
        assert alarms[1]["DATA"].value == "SRVO-003"

    def test_element_len_value(self, controller_tags: TagsCollection) -> None:
        """Element 1's LEN member matches the expected string length."""
        alarms = controller_tags["ALLOWABLE_ALARMS"].value
        assert alarms[1]["LEN"].value == 8

    def test_array_length(self, controller_tags: TagsCollection) -> None:
        """The array reports its full dimension."""
        alarms = controller_tags["ALLOWABLE_ALARMS"].value
        assert len(alarms) == 20


# ---------------------------------------------------------------------------
# AOI instance tags (top-level)
# ---------------------------------------------------------------------------


class TestAoiInstanceTags:
    """Tests for top-level AOI-instance tags."""

    def test_fanuc_robot_param_value_and_description(
        self, programs: ProgramsCollection
    ) -> None:
        """ShopRobotCtrl's progNumber parameter cross-refs the FanucRobot AOI def."""
        robot_tags = programs["Robot"].tags
        ctrl = robot_tags["ShopRobotCtrl"].value
        prog_number = ctrl["progNumber"]
        assert prog_number.value == 1
        assert prog_number.data_type == "SINT"

    def test_seq_ctrl_param_description(
        self, main_program_tags: TagsCollection
    ) -> None:
        """sequence's currentStep parameter cross-refs the SeqCtrl AOI def."""
        seq = main_program_tags["sequence"].value
        current_step = seq["currentStep"]
        assert current_step.value == 7000
        assert current_step.description == "Active Step Number"


# ---------------------------------------------------------------------------
# Override layering
# ---------------------------------------------------------------------------


class TestOverrideLayering:
    """Tests for tag-instance operand overrides layered over type-def metadata."""

    def test_bit_override_description(self, main_program_tags: TagsCollection) -> None:
        """Bit 1 of a_commented_dint has a description from the Comments override."""
        commented = main_program_tags["a_commented_dint"].value
        bit1 = commented[1]
        assert bit1.description == "this is bit 1"

    def test_bit_override_engineering_unit(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Bit 1 has an engineering unit from the EngineeringUnits override."""
        commented = main_program_tags["a_commented_dint"].value
        assert commented[1].engineering_unit == "mm"

    def test_bit_override_states(self, main_program_tags: TagsCollection) -> None:
        """Bit 1 has state0/state1 text from the State0s/State1s overrides."""
        commented = main_program_tags["a_commented_dint"].value
        bit1 = commented[1]
        assert bit1.state0 == "off"
        assert bit1.state1 == "on"

    def test_bit_override_external_logging(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Bit 1 has external_logging False, bit 10 has it True, per the overrides."""
        commented = main_program_tags["a_commented_dint"].value
        assert commented[1].external_logging is False
        assert commented[10].external_logging is True

    def test_bit_override_computed_value(
        self, main_program_tags: TagsCollection
    ) -> None:
        """A bit's boolean value is computed from the parent scalar's int value."""
        commented = main_program_tags["a_commented_dint"].value
        assert commented[1].value is False

    def test_bit_without_override_has_no_metadata(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Bit 0 has a comment but no engineering unit/state overrides."""
        commented = main_program_tags["a_commented_dint"].value
        bit0 = commented[0]
        assert bit0.description == "this is bit 0"
        assert bit0.engineering_unit == ""

    def test_udt_member_max_override(self, main_program_tags: TagsCollection) -> None:
        """a_udt_instance's a_sint_with_props Max override resolves via the operand path."""
        udt = main_program_tags["a_udt_instance"].value
        member = udt["a_sint_with_props"]
        assert member.max == 25
        assert member.min == 0


# ---------------------------------------------------------------------------
# Program-scoped tags
# ---------------------------------------------------------------------------


class TestProgramScopedTags:
    """Tests for tags scoped to individual programs."""

    def test_another_program_aoi_tag(self, programs: ProgramsCollection) -> None:
        """AnotherProgram's TestInput (GenericInput AOI instance) cross-refs correctly."""
        another_tags = programs["AnotherProgram"].tags
        test_input = another_tags["TestInput"].value
        on_delay = test_input["onDelay"]
        assert on_delay.value == 25
        assert on_delay.description == "Debounce On Delay (ms)"

    def test_robot_program_deep_nesting(self, programs: ProgramsCollection) -> None:
        """ShopRobot resolves 3+ levels deep (IN.UO.cmdEnable)."""
        robot_tags = programs["Robot"].tags
        shop_robot = robot_tags["ShopRobot"].value
        assert shop_robot["IN"]["UO"]["cmdEnable"].value == 1

    def test_robot_program_string_member(self, programs: ProgramsCollection) -> None:
        """ShopRobot's lastAlarm (robotString member) exposes LEN/DATA."""
        robot_tags = programs["Robot"].tags
        shop_robot = robot_tags["ShopRobot"].value
        last_alarm = shop_robot["lastAlarm"]
        assert last_alarm["DATA"].value == "SYST-034 HOLD signal from SOP/UOP is lost"
        assert last_alarm["LEN"].value == 41


# ---------------------------------------------------------------------------
# Edge cases: alias, message, produced/consumed
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for alias, message, and produced/consumed tags."""

    def test_alias_tag_value_is_none(self, main_program_tags: TagsCollection) -> None:
        """Alias tags have no value data."""
        assert main_program_tags["an_alias_tag"].value is None

    def test_alias_tag_alias_for(self, main_program_tags: TagsCollection) -> None:
        """Alias tags expose their AliasFor target string."""
        assert main_program_tags["an_alias_tag"].alias_for == "Local:1:I.Pt01.Data"

    def test_message_tag_value_is_none(self, controller_tags: TagsCollection) -> None:
        """MESSAGE-type tags have no parsed value tree."""
        assert controller_tags["message_tag"].value is None

    def test_message_tag_parameters(self, controller_tags: TagsCollection) -> None:
        """MESSAGE-type tags expose their MessageParameters attributes."""
        params = controller_tags["message_tag"].message_parameters
        assert params is not None
        assert params["MessageType"] == "CIP Data Table Write"

    def test_consumed_tag_value_and_info(self, controller_tags: TagsCollection) -> None:
        """Consumed tags parse their atomic value and expose ConsumeInfo."""
        tag = controller_tags["consumed_tag"]
        assert tag.value.value == 0
        assert tag.consume_info == {
            "Producer": "AnotherPLC",
            "RemoteTag": "fake_other_tag",
            "RemoteInstance": "0",
            "RPI": "20",
            "Unicast": "true",
        }

    def test_produced_tag_value_and_info(self, controller_tags: TagsCollection) -> None:
        """Produced tags parse their atomic value and expose ProduceInfo."""
        tag = controller_tags["produced_tag"]
        assert tag.value.value == 0
        assert tag.produce_info is not None
        assert tag.produce_info["ProduceCount"] == "1"

"""Tests for py_l5x.parsers.tag and py_l5x.parsers.program."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import py_l5x
from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.program import Program, ProgramsCollection
from py_l5x.parsers.specialty_tags import AxisParameters, MotionGroupParameters
from py_l5x.parsers.tag import (
    AliasTag,
    ArrayNode,
    ArrayTag,
    AtomicNode,
    AtomicTag,
    AxisTag,
    BoolTag,
    DateTimeTag,
    FloatTag,
    IntegerNode,
    IntegerTag,
    MessageTag,
    MotionGroupTag,
    StringNode,
    StringTag,
    StructNode,
    StructTag,
    Tag,
    TagNode,
    TagsCollection,
    TimeTag,
    TypeRegistry,
    UnknownTag,
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
        tag = main_program_tags["a_dint"]
        assert isinstance(tag, IntegerNode)
        assert tag.value == 0
        assert main_program_tags["a_dint"].value == 0

    def test_a_dint_description(self, main_program_tags: TagsCollection) -> None:
        """a_dint tag-level description is exposed via Tag.description."""
        assert main_program_tags["a_dint"].description == "a standard double integer"

    def test_a_bool_value(self, main_program_tags: TagsCollection) -> None:
        """a_bool value parses as an int (BOOL uses 0/1)."""
        assert main_program_tags["a_bool"].value == 0

    def test_a_real_value(self, main_program_tags: TagsCollection) -> None:
        """a_real value parses as a float."""
        assert main_program_tags["a_real"].value == 0.0

    def test_an_unsigned_dint_value(self, main_program_tags: TagsCollection) -> None:
        """an_unsigned_dint value parses as an int."""
        assert main_program_tags["an_unsigned_dint"].value == 0

    def test_datetime_value_passthrough(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Non-numeric radix values (DT#...) pass through as raw strings."""
        assert main_program_tags["datetime"].value == "DT#1970-01-01-00:00:00.000_000Z"


# ---------------------------------------------------------------------------
# Root-level tag metadata (min/max/engineering unit/state text/ext logging)
# ---------------------------------------------------------------------------


class TestRootTagMetadata:
    """Tests for metadata set directly on the ``<Tag>`` element itself."""

    def test_engineering_unit(self, main_program_tags: TagsCollection) -> None:
        """a_real_with_properties's tag-level EngineeringUnits is exposed."""
        tag = main_program_tags["a_real_with_properties"]
        assert tag.engineering_unit == "mm"

    def test_engineering_unit_absent(self, main_program_tags: TagsCollection) -> None:
        """a_dint has no EngineeringUnits container, so engineering_unit is empty."""
        assert main_program_tags["a_dint"].engineering_unit == ""

    def test_state0_and_state1(self, main_program_tags: TagsCollection) -> None:
        """a_bool_with_properties's tag-level State0s/State1s are exposed."""
        tag = main_program_tags["a_bool_with_properties"]
        assert tag.state0 == "Off"
        assert tag.state1 == "On"

    def test_external_logging(self, main_program_tags: TagsCollection) -> None:
        """a_bool_with_properties's tag-level ExternalLogging is exposed."""
        tag = main_program_tags["a_bool_with_properties"]
        assert tag.external_logging is True

    def test_external_logging_false(self, main_program_tags: TagsCollection) -> None:
        """a_real_with_properties's tag-level ExternalLogging is exposed."""
        tag = main_program_tags["a_real_with_properties"]
        assert tag.external_logging is False

    def test_external_logging_absent(self, main_program_tags: TagsCollection) -> None:
        """a_dint has no ExternalLoggings container, so external_logging is None."""
        assert main_program_tags["a_dint"].external_logging is None

    def test_flat_metadata_properties_work(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Tag metadata properties provide direct access."""
        tag = main_program_tags["a_bool_with_properties"]
        # a_bool_with_properties has tag-level state0/state1 but no engineering_unit at tag level
        # (engineering_unit "boolean" comes from the BOOL data type definition, not the tag)
        assert tag.state0 == "Off"
        assert tag.state1 == "On"
        assert tag.external_logging is True

    def test_flat_metadata_safe_when_absent(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Metadata properties return appropriate defaults when not set on tag.

        For value tags (IntegerTag, BoolTag, etc.), metadata properties come from
        the node classes via MRO (min/max from IntegerNode, state0/state1 from BoolNode,
        engineering_unit/external_logging from TagNode).
        """
        # IntegerTag a_dint: no min/max declared on the tag
        tag = main_program_tags["a_dint"]
        assert tag.min is None
        assert tag.max is None
        assert tag.engineering_unit == ""  # from TagNode, no override
        assert tag.external_logging is None  # from TagNode, no override
        # But no state0/state1 since IntegerTag inherits from IntegerNode, not BoolNode
        assert not hasattr(tag, "state0")
        assert not hasattr(tag, "state1")

    def test_root_scalar_data_has_no_metadata(
        self, main_program_tags: TagsCollection
    ) -> None:
        """The root value-tree node does not surface Tag-level metadata.

        min/max/engineering_unit/etc. belong on the ``Tag`` object itself,
        not on its ``.data`` value-tree node (which only carries operand
        overrides and type-def metadata for nested members/bits).
        """
        node = main_program_tags["a_real"]
        assert isinstance(node, TagNode)
        assert node.engineering_unit == ""


# ---------------------------------------------------------------------------
# STRING-family top-level tags (Format="String" fallback)
# ---------------------------------------------------------------------------


class TestStringTags:
    """Tests for top-level STRING-family tags using the String data fallback."""

    def test_a_string_value(self, main_program_tags: TagsCollection) -> None:
        """a_string (STRING type) resolves to an empty string."""
        node = main_program_tags["a_string"]
        assert isinstance(node, StringNode)
        assert node.value == ""

    def test_a_custom_string_value(self, main_program_tags: TagsCollection) -> None:
        """a_custom_string (custom StringFamily UDT) resolves via the String fallback."""
        assert main_program_tags["a_custom_string"].value == ""


# ---------------------------------------------------------------------------
# Nested UDT / AOI / array drill-down
# ---------------------------------------------------------------------------


class TestNestedUdtDrillDown:
    """Tests for nested UDT/array/AOI member drill-down."""

    def test_root_is_structure(self, main_program_tags: TagsCollection) -> None:
        """a_udt_instance's value root is a structure-kind TagNode."""
        node = main_program_tags["a_udt_instance"]
        assert isinstance(node, StructNode)

    def test_nested_udt_member(self, main_program_tags: TagsCollection) -> None:
        """Drilling into a nested UDT member (a_nested_UDT.Dint) works."""
        udt = main_program_tags["a_udt_instance"]
        assert udt.members["a_nested_UDT"].members["Dint"].value == 0

    def test_array_of_atomics(self, main_program_tags: TagsCollection) -> None:
        """Drilling into an array-of-atomics member (an_array[0]) works."""
        udt = main_program_tags["a_udt_instance"]
        array_node = udt.members["an_array"]
        assert isinstance(array_node, ArrayNode)
        assert array_node.elements[0].value == 0.0
        assert len(array_node.elements) == 4

    def test_nested_aoi_member(self, main_program_tags: TagsCollection) -> None:
        """Drilling into a nested AOI-instance member (an_aoi.state) cross-refs AOI defs."""
        udt = main_program_tags["a_udt_instance"]
        state_node = udt.members["an_aoi"].members["state"]
        assert state_node.value == 0
        assert state_node.description == "Debounced device value"


class TestArrayOfStructures:
    """Tests for top-level arrays of structures (ALLOWABLE_ALARMS)."""

    def test_element_is_structure(self, controller_tags: TagsCollection) -> None:
        """Each array element is a structure-kind TagNode."""
        alarms = controller_tags["ALLOWABLE_ALARMS"]
        assert isinstance(alarms, ArrayNode)
        assert isinstance(alarms.elements[1], StringNode)

    def test_element_data_value(self, controller_tags: TagsCollection) -> None:
        """Element 1's DATA member matches the expected alarm code."""
        alarms = controller_tags["ALLOWABLE_ALARMS"]
        assert alarms.elements[1].members["DATA"].value == "SRVO-003"

    def test_element_len_value(self, controller_tags: TagsCollection) -> None:
        """Element 1's LEN member matches the expected string length."""
        alarms = controller_tags["ALLOWABLE_ALARMS"]
        assert alarms.elements[1].members["LEN"].value == 8

    def test_array_length(self, controller_tags: TagsCollection) -> None:
        """The array reports its full dimension."""
        alarms = controller_tags["ALLOWABLE_ALARMS"]
        assert len(alarms.elements) == 20
        assert len(controller_tags["ALLOWABLE_ALARMS"].elements) == 20


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
        ctrl = robot_tags["ShopRobotCtrl"]
        prog_number = ctrl.members["progNumber"]
        assert prog_number.value == 1
        assert prog_number.data_type == "SINT"

    def test_seq_ctrl_param_description(
        self, main_program_tags: TagsCollection
    ) -> None:
        """sequence's currentStep parameter cross-refs the SeqCtrl AOI def."""
        seq = main_program_tags["sequence"]
        current_step = seq.members["currentStep"]
        assert current_step.value == 7000
        assert current_step.description == "Active Step Number"


# ---------------------------------------------------------------------------
# Override layering
# ---------------------------------------------------------------------------


class TestOverrideLayering:
    """Tests for tag-instance operand overrides layered over type-def metadata."""

    def test_bit_override_description(self, main_program_tags: TagsCollection) -> None:
        """Bit 1 of a_commented_dint has a description from the Comments override."""
        commented = main_program_tags["a_commented_dint"]
        bit1 = commented.bit(1)
        assert bit1.description == "this is bit 1"

    def test_bit_override_engineering_unit(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Bit 1 has an engineering unit from the EngineeringUnits override."""
        commented = main_program_tags["a_commented_dint"]
        assert commented.bit(1).engineering_unit == "mm"

    def test_bit_override_states(self, main_program_tags: TagsCollection) -> None:
        """Bit 1 has state0/state1 text from the State0s/State1s overrides."""
        commented = main_program_tags["a_commented_dint"]
        bit1 = commented.bit(1)
        assert bit1.state0 == "off"
        assert bit1.state1 == "on"

    def test_bit_override_external_logging(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Bit 1 has external_logging False, bit 10 has it True, per the overrides."""
        commented = main_program_tags["a_commented_dint"]
        assert commented.bit(1).external_logging is False
        assert commented.bit(10).external_logging is True

    def test_bit_override_computed_value(
        self, main_program_tags: TagsCollection
    ) -> None:
        """A bit's boolean value is computed from the parent scalar's int value."""
        commented = main_program_tags["a_commented_dint"]
        assert commented.bit(1).value is False

    def test_bit_without_override_has_no_metadata(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Bit 0 has a comment but no engineering unit/state overrides."""
        commented = main_program_tags["a_commented_dint"]
        bit0 = commented.bit(0)
        assert bit0.description == "this is bit 0"
        assert bit0.engineering_unit == ""

    def test_udt_member_max_override(self, main_program_tags: TagsCollection) -> None:
        """a_udt_instance's a_sint_with_props Max override resolves via the operand path."""
        udt = main_program_tags["a_udt_instance"]
        member = udt.members["a_sint_with_props"]
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
        test_input = another_tags["TestInput"]
        on_delay = test_input.members["onDelay"]
        assert on_delay.value == 25
        assert on_delay.description == "Debounce On Delay (ms)"

    def test_robot_program_deep_nesting(self, programs: ProgramsCollection) -> None:
        """ShopRobot resolves 3+ levels deep (IN.UO.cmdEnable)."""
        robot_tags = programs["Robot"].tags
        shop_robot = robot_tags["ShopRobot"]
        assert shop_robot.members["IN"].members["UO"].members["cmdEnable"].value == 1

    def test_robot_program_string_member(self, programs: ProgramsCollection) -> None:
        """ShopRobot's lastAlarm (robotString member) exposes LEN/DATA."""
        robot_tags = programs["Robot"].tags
        shop_robot = robot_tags["ShopRobot"]
        last_alarm = shop_robot.members["lastAlarm"]
        assert (
            last_alarm.members["DATA"].value
            == "SYST-034 HOLD signal from SOP/UOP is lost"
        )
        assert last_alarm.members["LEN"].value == 41


# ---------------------------------------------------------------------------
# Edge cases: alias, message, produced/consumed
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for alias, message, and produced/consumed tags."""

    def test_alias_tag_value_is_none(self, main_program_tags: TagsCollection) -> None:
        """Alias tags have no value data."""
        tag = main_program_tags["an_alias_tag"]
        assert isinstance(tag, AliasTag)
        assert not hasattr(tag, "value")

    def test_alias_tag_alias_for(self, main_program_tags: TagsCollection) -> None:
        """Alias tags expose their AliasFor target string."""
        assert main_program_tags["an_alias_tag"].alias_for == "Local:1:I.Pt01.Data"

    def test_message_tag_value_is_none(self, controller_tags: TagsCollection) -> None:
        """MESSAGE-type tags have no parsed value tree."""
        tag = controller_tags["message_tag"]
        assert isinstance(tag, MessageTag)
        assert not hasattr(tag, "value")

    def test_message_tag_parameters(self, controller_tags: TagsCollection) -> None:
        """MESSAGE-type tags expose a typed MessageParameters wrapper."""
        params = controller_tags["message_tag"].message_parameters
        assert params is not None
        assert params.message_type == "CIP Data Table Write"
        assert params.local_element == "message_data"
        assert params.connected is True
        assert params.cache_connections is True


# ---------------------------------------------------------------------------
# Specialty tag data: MOTION_GROUP / AXIS_CIP_DRIVE / generic Data fallback
# ---------------------------------------------------------------------------


class TestSpecialtyTagData:
    """Tests for MOTION_GROUP/AXIS_CIP_DRIVE typed wrappers and the fallback."""

    def test_motion_group_parameters(self, controller_tags: TagsCollection) -> None:
        """MOTION_GROUP tags expose a typed MotionGroupParameters wrapper."""
        params = controller_tags["ServosMotionGroup"].motion_group_parameters
        assert isinstance(params, MotionGroupParameters)
        assert params.coarse_update_period == 2000
        assert params.phase_shift == 0
        assert params.general_fault_type == "Non Major Fault"
        assert params.auto_tag_update == "Enabled"
        assert params.alternate1_update_multiplier == 1
        assert params.alternate2_update_multiplier == 1

    def test_motion_group_value_is_none(self, controller_tags: TagsCollection) -> None:
        """MOTION_GROUP tags have no parsed Decorated value tree."""
        tag = controller_tags["ServosMotionGroup"]
        assert isinstance(tag, MotionGroupTag)
        assert not hasattr(tag, "value")

    def test_axis_parameters(self, controller_tags: TagsCollection) -> None:
        """AXIS_CIP_DRIVE tags expose a typed AxisParameters wrapper."""
        params = controller_tags["testServo"].axis_parameters
        assert isinstance(params, AxisParameters)
        assert params.motion_group == "ServosMotionGroup"
        assert params.motion_module == "Test_Servo_Drive:Ch1"
        assert params.axis_configuration == "Position Loop"
        assert params.motor_catalog_number == "VPL-B0631T-C"
        assert params.conversion_constant == 10000.0
        assert params.position_units == "mm"
        assert params.maximum_speed == 226.66667
        assert params.home_mode == "Active"
        assert params.soft_travel_limit_checking is True
        assert params.feedback1_type == "Hiperface DSL"
        assert params.axis_id == 1598518072

    def test_axis_parameters_scaling(self, controller_tags: TagsCollection) -> None:
        """AXIS_CIP_DRIVE tags expose typed scaling/actuator properties."""
        params = controller_tags["testServo"].axis_parameters
        assert isinstance(params, AxisParameters)
        assert params.scaling_source == "From Calculator"
        assert params.load_type == "Linear Actuator"
        assert params.actuator_type == "Screw"
        assert params.travel_mode == "Limited"
        assert params.travel_range == 1000.0
        assert params.position_scaling_numerator == 1.0
        assert params.position_scaling_denominator == 1.0
        assert params.position_unwind_numerator == 1.0
        assert params.position_unwind_denominator == 1.0
        assert params.actuator_lead == 10.0
        assert params.actuator_lead_unit == "Millimeter/Rev"
        assert params.actuator_diameter == 1.0
        assert params.actuator_diameter_unit == "Millimeter"
        assert params.transmission_ratio_input == 5.0
        assert params.transmission_ratio_output == 1.0

    def test_axis_parameters_motor_nameplate(
        self, controller_tags: TagsCollection
    ) -> None:
        """AXIS_CIP_DRIVE tags expose typed motor nameplate properties."""
        params = controller_tags["testServo"].axis_parameters
        assert isinstance(params, AxisParameters)
        assert params.motor_unit == "Rev"
        assert params.motor_polarity == "Normal"
        assert params.motor_rated_voltage == 480.0
        assert params.motor_rated_continuous_current == 0.85
        assert params.motor_rated_peak_current == 2.97
        assert params.motor_rated_output_power == 0.31
        assert params.motor_overload_limit == 100.0
        assert params.rotary_motor_poles == 8
        assert params.rotary_motor_inertia == 0.000011
        assert params.rotary_motor_rated_speed == 8000.0
        assert params.rotary_motor_max_speed == 8000.0
        assert params.pm_motor_rated_torque == 0.46
        assert params.pm_motor_torque_constant == 0.58
        assert params.pm_motor_rotary_voltage_constant == 35.05671

    def test_axis_parameters_extra_attributes(
        self, controller_tags: TagsCollection
    ) -> None:
        """Attributes without a dedicated property are in extra_attributes."""
        params = controller_tags["testServo"].axis_parameters
        assert isinstance(params, AxisParameters)
        assert params.extra_attributes["TorqueLoopBandwidth"] == "1000.0"

    def test_non_specialty_tag_has_no_specialty_data(
        self, controller_tags: TagsCollection
    ) -> None:
        """Ordinary tags have no message/motion-group/axis parameters."""
        tag = controller_tags["toSafety_reset"]
        # This is a regular IntegerTag, not a specialty tag
        assert not hasattr(tag, "message_parameters")
        assert not hasattr(tag, "motion_group_parameters")
        assert not hasattr(tag, "axis_parameters")
        assert not hasattr(tag, "special_data_format")
        assert not hasattr(tag, "special_data_attributes")

    def test_special_data_format(self, controller_tags: TagsCollection) -> None:
        """special_data_format reports the non-value Data section's Format."""
        assert controller_tags["message_tag"].special_data_format == "Message"
        assert controller_tags["ServosMotionGroup"].special_data_format == "MotionGroup"
        assert controller_tags["testServo"].special_data_format == "Axis"

    def test_special_data_attributes_fallback(
        self, controller_tags: TagsCollection
    ) -> None:
        """special_data_attributes returns the root Data element's attributes."""
        assert controller_tags["ServosMotionGroup"].special_data_attributes == {
            "Format": "MotionGroup"
        }

    def test_consumed_tag_value_and_info(self, controller_tags: TagsCollection) -> None:
        """Consumed tags parse their atomic value and expose a ConsumeInfo facet."""
        tag = controller_tags["consumed_tag"]
        assert tag.value == 0
        consumed = tag.consumed
        assert consumed is not None
        assert consumed.producer == "AnotherPLC"
        assert consumed.remote_tag == "fake_other_tag"
        assert consumed.remote_instance == 0
        assert consumed.rpi == 20
        assert consumed.unicast is True

    def test_produced_tag_value_and_info(self, controller_tags: TagsCollection) -> None:
        """Produced tags parse their atomic value and expose a ProduceInfo facet."""
        tag = controller_tags["produced_tag"]
        assert tag.value == 0
        produced = tag.produced
        assert produced is not None
        assert produced.produce_count == 1


# ---------------------------------------------------------------------------
# Safety program / tags
# ---------------------------------------------------------------------------


class TestSafetyProgram:
    """Tests for the SafetyProgram (Class="Safety") and its safety tags."""

    def test_program_class(self, programs: ProgramsCollection) -> None:
        """SafetyProgram reports Class="Safety"."""
        assert programs["SafetyProgram"].class_ == "Safety"

    def test_program_is_safety(self, programs: ProgramsCollection) -> None:
        """SafetyProgram.is_safety is True."""
        assert programs["SafetyProgram"].is_safety is True

    def test_standard_programs_are_not_safety(
        self, programs: ProgramsCollection
    ) -> None:
        """Standard programs report Class="Standard" and is_safety=False."""
        for name in ("MainProgram", "AnotherProgram", "Robot"):
            assert programs[name].class_ == "Standard"
            assert programs[name].is_safety is False

    def test_program_routines(self, programs: ProgramsCollection) -> None:
        """SafetyProgram's routines are parsed normally."""
        routines = programs["SafetyProgram"].routines
        assert set(routines) == {"Main", "Inputs", "Outputs"}

    def test_safety_tag_class(self, controller_tags: TagsCollection) -> None:
        """Controller-scoped safety tag reports Class="Safety"."""
        tag = controller_tags["fromNormal_reset"]
        assert tag.class_ == "Safety"
        assert tag.is_safety is True

    def test_standard_tag_is_not_safety(self, controller_tags: TagsCollection) -> None:
        """A Standard-class controller tag is not flagged as safety."""
        tag = controller_tags["toSafety_reset"]
        assert tag.class_ == "Standard"
        assert tag.is_safety is False

    def test_safety_program_local_tags(self, programs: ProgramsCollection) -> None:
        """SafetyProgram's local safety I/O tags are present and readable."""
        safety_tags = programs["SafetyProgram"].tags
        assert "door_dcs" in safety_tags
        assert "estop_dcs" in safety_tags
        assert safety_tags["input_ok"].value == 0

    def test_safety_program_alias_tag(self, programs: ProgramsCollection) -> None:
        """reset_signal aliases the controller-scoped safety tag."""
        alias = programs["SafetyProgram"].tags["reset_signal"]
        assert alias.alias_for == "fromNormal_reset"
        assert isinstance(alias, AliasTag)
        assert not hasattr(alias, "value")


# ---------------------------------------------------------------------------
# Tag dispatch and type dispatch tests
# ---------------------------------------------------------------------------


class TestMakeTagDispatch:
    """Tests for correct tag type dispatch in _make_tag factory.

    Verifies that the factory creates the correct Tag subclass based on
    the tag's data type, structure, and metadata.
    """

    def test_bool_tag_dispatch(self, main_program_tags: TagsCollection) -> None:
        """A BOOL tag is dispatched to BoolTag."""
        tag = main_program_tags["a_bool"]
        assert type(tag) is BoolTag
        assert hasattr(tag, "value")
        assert hasattr(tag, "state0")
        assert hasattr(tag, "state1")
        assert not hasattr(tag, "min")
        assert not hasattr(tag, "max")

    def test_integer_tag_dispatch(self, main_program_tags: TagsCollection) -> None:
        """A DINT tag is dispatched to IntegerTag."""
        tag = main_program_tags["a_dint"]
        assert type(tag) is IntegerTag
        assert hasattr(tag, "value")
        assert hasattr(tag, "min")
        assert hasattr(tag, "max")
        assert not hasattr(tag, "state0")
        assert not hasattr(tag, "state1")

    def test_float_tag_dispatch(self, main_program_tags: TagsCollection) -> None:
        """A REAL tag is dispatched to FloatTag."""
        tag = main_program_tags["a_real"]
        assert type(tag) is FloatTag
        assert hasattr(tag, "value")
        assert hasattr(tag, "min")
        assert hasattr(tag, "max")
        assert not hasattr(tag, "state0")
        assert not hasattr(tag, "state1")

    def test_string_tag_dispatch(self, main_program_tags: TagsCollection) -> None:
        """A STRING tag is dispatched to StringTag."""
        tag = main_program_tags["a_string"]
        assert type(tag) is StringTag
        assert hasattr(tag, "value")
        assert hasattr(tag, "len")
        assert hasattr(tag, "max_length")
        assert hasattr(tag, "members")
        assert not hasattr(tag, "min")

    def test_struct_tag_dispatch(self, main_program_tags: TagsCollection) -> None:
        """A UDT instance tag is dispatched to StructTag."""
        tag = main_program_tags["a_udt_instance"]
        assert type(tag) is StructTag
        assert hasattr(tag, "members")
        assert not hasattr(tag, "value")
        assert not hasattr(tag, "min")

    def test_array_tag_dispatch(self, main_program_tags: TagsCollection) -> None:
        """An array tag is dispatched to ArrayTag."""
        tag = main_program_tags["a_2d_array"]
        assert type(tag) is ArrayTag
        assert hasattr(tag, "elements")
        assert hasattr(tag, "dimensions")
        assert not hasattr(tag, "min")
        assert not hasattr(tag, "value")

    def test_time_tag_dispatch(self, main_program_tags: TagsCollection) -> None:
        """A TIME tag is dispatched to TimeTag."""
        tag = main_program_tags["duration"]
        assert type(tag) is TimeTag
        assert hasattr(tag, "value")
        assert hasattr(tag, "unit")
        assert not hasattr(tag, "min")

    def test_datetime_tag_dispatch(self, main_program_tags: TagsCollection) -> None:
        """A DT tag is dispatched to DateTimeTag."""
        tag = main_program_tags["datetime"]
        assert type(tag) is DateTimeTag
        assert hasattr(tag, "value")
        assert hasattr(tag, "unit")
        assert not hasattr(tag, "min")

    def test_alias_tag_dispatch(self, main_program_tags: TagsCollection) -> None:
        """An alias tag is dispatched to AliasTag."""
        tag = main_program_tags["an_alias_tag"]
        assert type(tag) is AliasTag
        assert hasattr(tag, "alias_for")
        assert not hasattr(tag, "value")
        assert not hasattr(tag, "min")

    def test_motion_group_tag_dispatch(self, controller_tags: TagsCollection) -> None:
        """A MOTION_GROUP tag is dispatched to MotionGroupTag."""
        tag = controller_tags["ServosMotionGroup"]
        assert type(tag) is MotionGroupTag
        assert hasattr(tag, "motion_group_parameters")
        assert hasattr(tag, "special_data_format")
        assert tag.special_data_format == "MotionGroup"
        assert not hasattr(tag, "value")

    def test_axis_tag_dispatch(self, controller_tags: TagsCollection) -> None:
        """An AXIS_CIP_DRIVE tag is dispatched to AxisTag."""
        tag = controller_tags["testServo"]
        assert type(tag) is AxisTag
        assert hasattr(tag, "axis_parameters")
        assert hasattr(tag, "special_data_format")
        assert tag.special_data_format == "Axis"
        assert not hasattr(tag, "value")

    def test_message_tag_dispatch(self, controller_tags: TagsCollection) -> None:
        """A MESSAGE tag is dispatched to MessageTag."""
        tag = controller_tags["message_tag"]
        assert type(tag) is MessageTag
        assert hasattr(tag, "message_parameters")
        assert hasattr(tag, "special_data_format")
        assert tag.special_data_format == "Message"
        assert not hasattr(tag, "value")

    def test_tag_element_reference(self, main_program_tags: TagsCollection) -> None:
        """Tag.element returns the raw <Tag> XML element."""
        tag = main_program_tags["a_dint"]
        elem = tag.element
        assert elem.tag == "Tag"
        assert elem.get("Name") == "a_dint"
        assert elem.get("DataType") == "DINT"

    def test_tag_value_element_differs_from_element(
        self, main_program_tags: TagsCollection
    ) -> None:
        """For value tags, value_element is not the same as element."""
        tag = main_program_tags["a_dint"]
        assert tag.value_element is not tag.element
        # value_element is the child (DataValue/Structure/Array/etc.) inside Decorated
        assert tag.value_element.tag in ("DataValue", "Structure", "Array")

    def test_all_collection_items_are_typed_tags(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Every tag in a collection is an instance of a Tag subclass, not plain Tag."""
        for name, tag in main_program_tags.items():
            # Verify it's a Tag
            assert isinstance(tag, Tag)
            # Verify it's NOT the base Tag class (it's a subclass)
            assert type(tag) is not Tag, f"Tag {name!r} is plain Tag, not a subclass"

    def test_integer_tag_no_range_without_override(
        self, main_program_tags: TagsCollection
    ) -> None:
        """A root IntegerTag with no Min/Max attributes reports no bounds."""
        tag = main_program_tags["a_dint"]
        assert isinstance(tag, IntegerTag)
        # a_dint has no Min/Max attributes on the <Tag> element
        assert tag.min is None
        assert tag.max is None

    def test_float_tag_with_properties(self, main_program_tags: TagsCollection) -> None:
        """A FloatTag with Min/Max attributes returns them with correct type."""
        tag = main_program_tags["a_real_with_properties"]
        assert isinstance(tag, FloatTag)
        # a_real_with_properties has Min="-10.0" Max="400.0" on the <Tag>
        assert tag.min == -10.0
        assert tag.max == 400.0
        assert isinstance(tag.min, (int, float))
        assert isinstance(tag.max, (int, float))

    def test_struct_tag_no_elements_property(
        self, main_program_tags: TagsCollection
    ) -> None:
        """StructTag has members but not elements."""
        tag = main_program_tags["a_udt_instance"]
        assert isinstance(tag, StructTag)
        assert hasattr(tag, "members")
        assert not hasattr(tag, "elements")

    def test_array_tag_no_value_property(
        self, main_program_tags: TagsCollection
    ) -> None:
        """ArrayTag has elements but not a single value."""
        tag = main_program_tags["a_2d_array"]
        assert isinstance(tag, ArrayTag)
        assert hasattr(tag, "elements")
        assert not hasattr(tag, "value")

    def test_radix_not_in_extra_attributes(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Radix is surfaced via radix property and not in extra_attributes."""
        tag = main_program_tags["a_dint"]
        assert isinstance(tag, IntegerNode)
        # a_dint has a Radix attribute from its value element
        assert tag.radix is not None
        # Radix should not appear in extra_attributes
        assert "Radix" not in tag.extra_attributes

    def test_dimensions_not_in_extra_attributes(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Dimensions is surfaced via dimensions property and not in extra_attributes."""
        tag = main_program_tags["a_2d_array"]
        assert isinstance(tag, ArrayTag)
        # a_2d_array has a Dimensions attribute on its value element
        assert tag.dimensions == (2, 3)
        # Dimensions should not appear in extra_attributes
        assert "Dimensions" not in tag.extra_attributes

    def test_alias_tag_no_value_property(
        self, main_program_tags: TagsCollection
    ) -> None:
        """AliasTag has no value property."""
        tag = main_program_tags["an_alias_tag"]
        assert isinstance(tag, AliasTag)
        assert hasattr(tag, "alias_for")
        assert not hasattr(tag, "value")


# ---------------------------------------------------------------------------
# Integer type tests: bit_width, min/max, bit(), bits accessor
# ---------------------------------------------------------------------------


class TestIntegerBitWidth:
    """Test bit_width property for all integer types present as tags."""

    @pytest.mark.parametrize(
        "tag_name,expected_width",
        [
            ("a_sint", 8),
            ("an_unsigned_sint", 8),
            ("an_int", 16),
            ("an_unsigned_int", 16),
            ("a_dint", 32),
            ("an_unsigned_dint", 32),
            ("a_lint", 64),
            ("an_unsigned_lint", 64),
        ],
    )
    def test_integer_bit_width(
        self, main_program_tags: TagsCollection, tag_name: str, expected_width: int
    ) -> None:
        """Integer tags report correct bit_width."""
        tag = main_program_tags[tag_name]
        assert isinstance(tag, IntegerTag)
        assert tag.bit_width == expected_width

    def test_bits_length_equals_bit_width(
        self, main_program_tags: TagsCollection
    ) -> None:
        """len(tag.bits) equals bit_width for integer tags."""
        for tag_name in ["a_sint", "a_dint", "a_lint"]:
            tag = main_program_tags[tag_name]
            assert len(tag.bits) == tag.bit_width


class TestIntegerMinMax:
    """Test min/max for integer types (no Tag-level override)."""

    @pytest.mark.parametrize(
        "tag_name",
        [
            "a_sint",
            "an_unsigned_sint",
            "an_int",
            "an_unsigned_int",
            "a_dint",
            "an_unsigned_dint",
            "a_lint",
            "an_unsigned_lint",
        ],
    )
    def test_integer_undeclared_min_max(
        self,
        main_program_tags: TagsCollection,
        tag_name: str,
    ) -> None:
        """Integer tags without declared bounds report no min/max."""
        tag = main_program_tags[tag_name]
        assert isinstance(tag, IntegerTag)
        assert tag.min is None
        assert tag.max is None


class TestIntegerBitAccessor:
    """Test bit(n) accessor and bits property."""

    def test_bit_accessor_returns_bool_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """bit(n) returns a BoolNode."""
        tag = main_program_tags["a_dint"]
        bit_node = tag.bit(0)
        assert isinstance(bit_node, TagNode)  # BoolNode
        assert hasattr(bit_node, "value")

    def test_bit_operand_path(self, main_program_tags: TagsCollection) -> None:
        """bit(n) node has operand path ending with .n."""
        tag = main_program_tags["a_dint"]
        bit5 = tag.bit(5)
        assert bit5.operand_path.endswith(".5")

    def test_bit_out_of_range_raises_index_error(
        self, main_program_tags: TagsCollection
    ) -> None:
        """bit(n) raises IndexError when n >= bit_width."""
        tag = main_program_tags["a_dint"]
        with pytest.raises(IndexError):
            tag.bit(32)  # DINT has bit_width=32

    def test_bits_property(self, main_program_tags: TagsCollection) -> None:
        """bits property returns list of BoolNode for each bit."""
        tag = main_program_tags["a_sint"]
        bits = tag.bits
        assert len(bits) == 8  # SINT is 8 bits
        for i, bit in enumerate(bits):
            assert isinstance(bit, TagNode)  # BoolNode
            assert bit.operand_path.endswith(f".{i}")


# ---------------------------------------------------------------------------
# Irrelevant accessor AttributeError tests
# ---------------------------------------------------------------------------


class TestIrrelevantAccessorsRaiseAttributeError:
    """Test AttributeError on irrelevant accessors for various tag types."""

    def test_bool_tag_no_bit_accessor(self, main_program_tags: TagsCollection) -> None:
        """BoolTag has no bit/bits accessors (only IntegerNode has these)."""
        tag = main_program_tags["a_bool"]
        with pytest.raises(AttributeError):
            tag.bit(0)
        with pytest.raises(AttributeError):
            tag.bits

    def test_float_tag_no_bits(self, main_program_tags: TagsCollection) -> None:
        """FloatTag has no bit/bits accessors."""
        tag = main_program_tags["a_real"]
        with pytest.raises(AttributeError):
            tag.bit(0)
        with pytest.raises(AttributeError):
            tag.bits

    def test_string_tag_no_elements(self, main_program_tags: TagsCollection) -> None:
        """StringTag has no elements accessor."""
        tag = main_program_tags["a_string"]
        with pytest.raises(AttributeError):
            tag.elements

    def test_string_tag_no_bit(self, main_program_tags: TagsCollection) -> None:
        """StringTag has no bit accessor."""
        tag = main_program_tags["a_string"]
        with pytest.raises(AttributeError):
            tag.bit(0)

    def test_struct_tag_no_elements(self, main_program_tags: TagsCollection) -> None:
        """StructTag has no elements accessor."""
        tag = main_program_tags["a_udt_instance"]
        with pytest.raises(AttributeError):
            tag.elements

    def test_struct_tag_no_value(self, main_program_tags: TagsCollection) -> None:
        """StructTag has no value accessor."""
        tag = main_program_tags["a_udt_instance"]
        with pytest.raises(AttributeError):
            tag.value

    def test_array_tag_no_members(self, main_program_tags: TagsCollection) -> None:
        """ArrayTag has no members accessor."""
        tag = main_program_tags["a_2d_array"]
        with pytest.raises(AttributeError):
            tag.members

    def test_array_tag_no_value(self, main_program_tags: TagsCollection) -> None:
        """ArrayTag has no value accessor."""
        tag = main_program_tags["a_2d_array"]
        with pytest.raises(AttributeError):
            tag.value

    def test_alias_tag_no_value(self, main_program_tags: TagsCollection) -> None:
        """AliasTag has no value accessor."""
        tag = main_program_tags["an_alias_tag"]
        with pytest.raises(AttributeError):
            tag.value

    def test_message_tag_no_members(self, controller_tags: TagsCollection) -> None:
        """MessageTag has no members accessor."""
        tag = controller_tags["message_tag"]
        with pytest.raises(AttributeError):
            tag.members


# ---------------------------------------------------------------------------
# STRING tag tests: value, len, max_length, members structure
# ---------------------------------------------------------------------------


class TestStringRootTag:
    """Test root-level STRING tags and their members structure."""

    def test_string_root_value(self, main_program_tags: TagsCollection) -> None:
        """a_string root tag has value, len, max_length, and members."""
        tag = main_program_tags["a_string"]
        assert isinstance(tag, StringTag)
        assert tag.value == ""
        assert tag.len == 0
        assert tag.max_length == 82

    def test_string_members_has_len_and_data(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_string members has exactly LEN and DATA keys."""
        tag = main_program_tags["a_string"]
        members = tag.members
        assert set(members.keys()) == {"LEN", "DATA"}

    def test_string_len_member_is_integer_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_string.members["LEN"] is an IntegerNode."""
        tag = main_program_tags["a_string"]
        len_member = tag.members["LEN"]
        assert isinstance(len_member, IntegerNode)

    def test_string_data_member_is_atomic_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_string.members["DATA"] is an AtomicNode (string value)."""
        tag = main_program_tags["a_string"]
        data_member = tag.members["DATA"]
        assert isinstance(data_member, AtomicNode)

    def test_custom_string_type_root_tag_value(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_custom_string (custom StringFamily UDT) accesses via String fallback."""
        custom_str = main_program_tags["a_custom_string"]
        assert isinstance(custom_str, StringNode)
        # Custom string type should have value, len, max_length
        assert hasattr(custom_str, "value")
        assert hasattr(custom_str, "len")
        assert hasattr(custom_str, "max_length")

    def test_allowable_alarms_element_is_string(
        self, controller_tags: TagsCollection
    ) -> None:
        """ALLOWABLE_ALARMS elements are StringNode (custom string UDT)."""
        alarms = controller_tags["ALLOWABLE_ALARMS"]
        element = alarms.elements[0]
        assert isinstance(element, StringNode)
        assert hasattr(element, "value")
        assert hasattr(element, "len")
        assert hasattr(element, "members")
        members = element.members
        assert "LEN" in members
        assert "DATA" in members


# ---------------------------------------------------------------------------
# Time/DateTime tags: exact classes, values, units, radix
# ---------------------------------------------------------------------------


class TestTimeDateTagsExactValues:
    """Test Time and DateTime tags from MainProgram with exact fixture values."""

    def test_short_duration_is_time_tag(
        self, main_program_tags: TagsCollection
    ) -> None:
        """short_duration (TIME32) is a TimeTag."""
        tag = main_program_tags["short_duration"]
        assert isinstance(tag, TimeTag)

    def test_short_duration_value(self, main_program_tags: TagsCollection) -> None:
        """short_duration value is the literal 'T32#0us'."""
        tag = main_program_tags["short_duration"]
        assert tag.value == "T32#0us"

    def test_short_duration_unit(self, main_program_tags: TagsCollection) -> None:
        """short_duration unit is 'us' (microsecond)."""
        tag = main_program_tags["short_duration"]
        assert tag.unit == "us"

    def test_short_duration_radix(self, main_program_tags: TagsCollection) -> None:
        """short_duration radix includes 'Time32'."""
        tag = main_program_tags["short_duration"]
        assert "Time32" in tag.radix

    def test_duration_is_time_tag(self, main_program_tags: TagsCollection) -> None:
        """duration (TIME) is a TimeTag."""
        tag = main_program_tags["duration"]
        assert isinstance(tag, TimeTag)

    def test_duration_value(self, main_program_tags: TagsCollection) -> None:
        """duration value is the literal 'T#0us'."""
        tag = main_program_tags["duration"]
        assert tag.value == "T#0us"

    def test_duration_unit(self, main_program_tags: TagsCollection) -> None:
        """duration unit is 'us'."""
        tag = main_program_tags["duration"]
        assert tag.unit == "us"

    def test_duration_radix(self, main_program_tags: TagsCollection) -> None:
        """duration radix is 'Time (us)'."""
        tag = main_program_tags["duration"]
        assert tag.radix == "Time (us)"

    def test_long_duration_is_time_tag(self, main_program_tags: TagsCollection) -> None:
        """long_duration (LTIME) is a TimeTag."""
        tag = main_program_tags["long_duration"]
        assert isinstance(tag, TimeTag)

    def test_long_duration_value(self, main_program_tags: TagsCollection) -> None:
        """long_duration value is the literal 'LT#0ns'."""
        tag = main_program_tags["long_duration"]
        assert tag.value == "LT#0ns"

    def test_long_duration_unit(self, main_program_tags: TagsCollection) -> None:
        """long_duration unit is 'ns' (nanosecond)."""
        tag = main_program_tags["long_duration"]
        assert tag.unit == "ns"

    def test_long_duration_radix(self, main_program_tags: TagsCollection) -> None:
        """long_duration radix is 'LTime (ns)'."""
        tag = main_program_tags["long_duration"]
        assert tag.radix == "LTime (ns)"

    def test_datetime_is_datetime_tag(self, main_program_tags: TagsCollection) -> None:
        """datetime (DT) is a DateTimeTag."""
        tag = main_program_tags["datetime"]
        assert isinstance(tag, DateTimeTag)

    def test_datetime_value(self, main_program_tags: TagsCollection) -> None:
        """datetime value is the literal 'DT#1970-01-01-00:00:00.000_000Z'."""
        tag = main_program_tags["datetime"]
        assert tag.value == "DT#1970-01-01-00:00:00.000_000Z"

    def test_datetime_unit(self, main_program_tags: TagsCollection) -> None:
        """datetime unit is 'us'."""
        tag = main_program_tags["datetime"]
        assert tag.unit == "us"

    def test_datetime_radix(self, main_program_tags: TagsCollection) -> None:
        """datetime radix is 'Date/Time'."""
        tag = main_program_tags["datetime"]
        assert tag.radix == "Date/Time"

    def test_long_datetime_is_datetime_tag(
        self, main_program_tags: TagsCollection
    ) -> None:
        """long_datetime (LDT) is a DateTimeTag."""
        tag = main_program_tags["long_datetime"]
        assert isinstance(tag, DateTimeTag)

    def test_long_datetime_value(self, main_program_tags: TagsCollection) -> None:
        """long_datetime value is the literal 'LDT#1970-01-01-00:00:00.000_000_000Z'."""
        tag = main_program_tags["long_datetime"]
        assert tag.value == "LDT#1970-01-01-00:00:00.000_000_000Z"

    def test_long_datetime_unit(self, main_program_tags: TagsCollection) -> None:
        """long_datetime unit is 'ns'."""
        tag = main_program_tags["long_datetime"]
        assert tag.unit == "ns"

    def test_long_datetime_radix(self, main_program_tags: TagsCollection) -> None:
        """long_datetime radix is 'Date/Time (ns)'."""
        tag = main_program_tags["long_datetime"]
        assert tag.radix == "Date/Time (ns)"


# ---------------------------------------------------------------------------
# Fallback tag types: AtomicTag for unknown atomic, UnknownTag
# ---------------------------------------------------------------------------


class TestFallbackAtomicTag:
    """Test AtomicTag fallback for unknown atomic type names."""

    def test_unknown_atomic_creates_atomic_tag(
        self, type_registry: TypeRegistry
    ) -> None:
        """An unknown atomic type name falls back to AtomicTag."""
        # Construct minimal XML for an unknown atomic type
        tag_xml = """<Tag Name="test_unknown" DataType="UNKNOWN_ATOMIC_TYPE" TagType="Base">
            <Data Format="Decorated">
                <DataValue DataType="UNKNOWN_ATOMIC_TYPE" Value="42"/>
            </Data>
        </Tag>"""
        tag_el = ET.fromstring(tag_xml)
        from py_l5x.parsers.tag import _make_tag

        tag = _make_tag(tag_el, type_registry)
        assert isinstance(tag, AtomicTag)


class TestFallbackUnknownTag:
    """Test UnknownTag fallback for tags with no value data or unrecognized special format."""

    def test_unknown_tag_no_value_data(self, type_registry: TypeRegistry) -> None:
        """A tag with no value data falls back to UnknownTag."""
        tag_xml = """<Tag Name="test_empty" TagType="Base" DataType="DINT">
        </Tag>"""
        tag_el = ET.fromstring(tag_xml)
        from py_l5x.parsers.tag import _make_tag

        tag = _make_tag(tag_el, type_registry)
        assert isinstance(tag, UnknownTag)

    def test_unknown_tag_unrecognized_special_format(
        self, type_registry: TypeRegistry
    ) -> None:
        """A tag with unrecognized special Data Format falls back to UnknownTag."""
        tag_xml = """<Tag Name="test_special" TagType="Base">
            <Data Format="UnknownFormat" X="1"/>
        </Tag>"""
        tag_el = ET.fromstring(tag_xml)
        from py_l5x.parsers.tag import _make_tag

        tag = _make_tag(tag_el, type_registry)
        assert isinstance(tag, UnknownTag)
        assert tag.special_data_format == "UnknownFormat"
        assert tag.special_data_attributes == {"Format": "UnknownFormat", "X": "1"}


# ---------------------------------------------------------------------------
# Root metadata: Min/Max as typed values, State0/State1
# ---------------------------------------------------------------------------


class TestRootMetadataMinMax:
    """Test Min/Max attributes on Tag element with typed return values."""

    def test_integer_tag_with_min_max(self, main_program_tags: TagsCollection) -> None:
        """opcua_dint has Min/Max as integers."""
        tag = main_program_tags["opcua_dint"]
        assert isinstance(tag, IntegerTag)
        assert tag.min == -400
        assert tag.max == 200
        assert isinstance(tag.min, int)
        assert isinstance(tag.max, int)

    def test_float_tag_with_min_max(self, main_program_tags: TagsCollection) -> None:
        """a_real_with_properties has Min/Max as floats."""
        tag = main_program_tags["a_real_with_properties"]
        assert isinstance(tag, FloatTag)
        assert tag.min == -10.0
        assert tag.max == 400.0
        assert isinstance(tag.min, float)
        assert isinstance(tag.max, float)

    def test_float_tag_without_min_returns_none(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_real has no Min/Max attribute, so returns None."""
        tag = main_program_tags["a_real"]
        assert tag.min is None
        assert tag.max is None


class TestRootMetadataState:
    """Test State0/State1 attributes on BoolTag."""

    def test_bool_tag_with_state0_state1(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_bool_with_properties has tag-level State0s/State1s."""
        tag = main_program_tags["a_bool_with_properties"]
        assert isinstance(tag, BoolTag)
        assert tag.state0 == "Off"
        assert tag.state1 == "On"


class TestPublicExports:
    """Tests for public API exports in py_l5x.__all__."""

    def test_all_exports_are_module_attributes(self) -> None:
        """Every name in py_l5x.__all__ is an attribute of the py_l5x module."""
        for name in py_l5x.__all__:
            assert hasattr(py_l5x, name), (
                f"{name!r} in __all__ but not an attribute of py_l5x"
            )

    def test_tag_classes_in_all(self) -> None:
        """All 14 public tag classes are in py_l5x.__all__."""
        expected_tag_classes = {
            "BoolTag",
            "IntegerTag",
            "FloatTag",
            "TimeTag",
            "DateTimeTag",
            "AtomicTag",
            "StringTag",
            "StructTag",
            "ArrayTag",
            "AliasTag",
            "MessageTag",
            "AxisTag",
            "MotionGroupTag",
            "UnknownTag",
        }
        for cls_name in expected_tag_classes:
            assert cls_name in py_l5x.__all__, f"{cls_name!r} not in __all__"

    def test_aoi_local_tag_in_all(self) -> None:
        """AOILocalTag is in py_l5x.__all__."""
        assert "AOILocalTag" in py_l5x.__all__

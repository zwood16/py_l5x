"""Tests for py_l5x.parsers.tag and py_l5x.parsers.program."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.program import Program, ProgramsCollection
from py_l5x.parsers.specialty_tags import AxisParameters, MotionGroupParameters
from py_l5x.parsers.tag import Tag, TagNode, TagsCollection, TypeRegistry

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
        node = main_program_tags["a_dint"].data
        assert isinstance(node, TagNode)
        assert node.kind == "scalar"
        assert node.value == 0
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
        assert main_program_tags["a_real_with_properties"].engineering_unit == "mm"

    def test_engineering_unit_absent(self, main_program_tags: TagsCollection) -> None:
        """a_dint has no EngineeringUnits container at all."""
        assert main_program_tags["a_dint"].engineering_unit == ""

    def test_state0_and_state1(self, main_program_tags: TagsCollection) -> None:
        """a_bool_with_properties's tag-level State0s/State1s are exposed."""
        assert main_program_tags["a_bool_with_properties"].state0 == "Off"
        assert main_program_tags["a_bool_with_properties"].state1 == "On"

    def test_external_logging(self, main_program_tags: TagsCollection) -> None:
        """a_bool_with_properties's tag-level ExternalLogging is exposed."""
        assert main_program_tags["a_bool_with_properties"].external_logging is True

    def test_external_logging_false(self, main_program_tags: TagsCollection) -> None:
        """a_real_with_properties's tag-level ExternalLogging is exposed."""
        assert main_program_tags["a_real_with_properties"].external_logging is False

    def test_external_logging_absent(self, main_program_tags: TagsCollection) -> None:
        """a_dint has no ExternalLoggings container at all."""
        assert main_program_tags["a_dint"].external_logging is None

    def test_root_scalar_data_has_no_metadata(
        self, main_program_tags: TagsCollection
    ) -> None:
        """The root value-tree node does not surface Tag-level metadata.

        min/max/engineering_unit/etc. belong on the ``Tag`` object itself,
        not on its ``.data`` value-tree node (which only carries operand
        overrides and type-def metadata for nested members/bits).
        """
        node = main_program_tags["a_real"].data
        assert isinstance(node, TagNode)
        assert node.engineering_unit == ""


# ---------------------------------------------------------------------------
# STRING-family top-level tags (Format="String" fallback)
# ---------------------------------------------------------------------------


class TestStringTags:
    """Tests for top-level STRING-family tags using the String data fallback."""

    def test_a_string_value(self, main_program_tags: TagsCollection) -> None:
        """a_string (STRING type) resolves to an empty string."""
        node = main_program_tags["a_string"].data
        assert isinstance(node, TagNode)
        assert node.kind == "scalar"
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
        node = main_program_tags["a_udt_instance"].data
        assert isinstance(node, TagNode)
        assert node.kind == "structure"

    def test_nested_udt_member(self, main_program_tags: TagsCollection) -> None:
        """Drilling into a nested UDT member (a_nested_UDT.Dint) works."""
        udt = main_program_tags["a_udt_instance"].data
        assert udt.members["a_nested_UDT"].members["Dint"].value == 0

    def test_array_of_atomics(self, main_program_tags: TagsCollection) -> None:
        """Drilling into an array-of-atomics member (an_array[0]) works."""
        udt = main_program_tags["a_udt_instance"].data
        array_node = udt.members["an_array"]
        assert isinstance(array_node, TagNode)
        assert array_node.kind == "array"
        assert array_node.elements[0].value == 0.0
        assert len(array_node.elements) == 4

    def test_nested_aoi_member(self, main_program_tags: TagsCollection) -> None:
        """Drilling into a nested AOI-instance member (an_aoi.state) cross-refs AOI defs."""
        udt = main_program_tags["a_udt_instance"].data
        state_node = udt.members["an_aoi"].members["state"]
        assert state_node.value == 0
        assert state_node.description == "Debounced device value"


class TestArrayOfStructures:
    """Tests for top-level arrays of structures (ALLOWABLE_ALARMS)."""

    def test_element_is_structure(self, controller_tags: TagsCollection) -> None:
        """Each array element is a structure-kind TagNode."""
        alarms = controller_tags["ALLOWABLE_ALARMS"].data
        assert isinstance(alarms, TagNode)
        assert alarms.kind == "array"
        assert isinstance(alarms.elements[1], TagNode)
        assert alarms.elements[1].kind == "structure"

    def test_element_data_value(self, controller_tags: TagsCollection) -> None:
        """Element 1's DATA member matches the expected alarm code."""
        alarms = controller_tags["ALLOWABLE_ALARMS"].data
        assert alarms.elements[1].members["DATA"].value == "SRVO-003"

    def test_element_len_value(self, controller_tags: TagsCollection) -> None:
        """Element 1's LEN member matches the expected string length."""
        alarms = controller_tags["ALLOWABLE_ALARMS"].data
        assert alarms.elements[1].members["LEN"].value == 8

    def test_array_length(self, controller_tags: TagsCollection) -> None:
        """The array reports its full dimension."""
        alarms = controller_tags["ALLOWABLE_ALARMS"].data
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
        ctrl = robot_tags["ShopRobotCtrl"].data
        prog_number = ctrl.members["progNumber"]
        assert prog_number.value == 1
        assert prog_number.data_type == "SINT"

    def test_seq_ctrl_param_description(
        self, main_program_tags: TagsCollection
    ) -> None:
        """sequence's currentStep parameter cross-refs the SeqCtrl AOI def."""
        seq = main_program_tags["sequence"].data
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
        commented = main_program_tags["a_commented_dint"].data
        bit1 = commented.bit(1)
        assert bit1.description == "this is bit 1"

    def test_bit_override_engineering_unit(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Bit 1 has an engineering unit from the EngineeringUnits override."""
        commented = main_program_tags["a_commented_dint"].data
        assert commented.bit(1).engineering_unit == "mm"

    def test_bit_override_states(self, main_program_tags: TagsCollection) -> None:
        """Bit 1 has state0/state1 text from the State0s/State1s overrides."""
        commented = main_program_tags["a_commented_dint"].data
        bit1 = commented.bit(1)
        assert bit1.state0 == "off"
        assert bit1.state1 == "on"

    def test_bit_override_external_logging(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Bit 1 has external_logging False, bit 10 has it True, per the overrides."""
        commented = main_program_tags["a_commented_dint"].data
        assert commented.bit(1).external_logging is False
        assert commented.bit(10).external_logging is True

    def test_bit_override_computed_value(
        self, main_program_tags: TagsCollection
    ) -> None:
        """A bit's boolean value is computed from the parent scalar's int value."""
        commented = main_program_tags["a_commented_dint"].data
        assert commented.bit(1).value is False

    def test_bit_without_override_has_no_metadata(
        self, main_program_tags: TagsCollection
    ) -> None:
        """Bit 0 has a comment but no engineering unit/state overrides."""
        commented = main_program_tags["a_commented_dint"].data
        bit0 = commented.bit(0)
        assert bit0.description == "this is bit 0"
        assert bit0.engineering_unit == ""

    def test_udt_member_max_override(self, main_program_tags: TagsCollection) -> None:
        """a_udt_instance's a_sint_with_props Max override resolves via the operand path."""
        udt = main_program_tags["a_udt_instance"].data
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
        test_input = another_tags["TestInput"].data
        on_delay = test_input.members["onDelay"]
        assert on_delay.value == 25
        assert on_delay.description == "Debounce On Delay (ms)"

    def test_robot_program_deep_nesting(self, programs: ProgramsCollection) -> None:
        """ShopRobot resolves 3+ levels deep (IN.UO.cmdEnable)."""
        robot_tags = programs["Robot"].tags
        shop_robot = robot_tags["ShopRobot"].data
        assert shop_robot.members["IN"].members["UO"].members["cmdEnable"].value == 1

    def test_robot_program_string_member(self, programs: ProgramsCollection) -> None:
        """ShopRobot's lastAlarm (robotString member) exposes LEN/DATA."""
        robot_tags = programs["Robot"].tags
        shop_robot = robot_tags["ShopRobot"].data
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
        assert main_program_tags["an_alias_tag"].value is None

    def test_alias_tag_alias_for(self, main_program_tags: TagsCollection) -> None:
        """Alias tags expose their AliasFor target string."""
        assert main_program_tags["an_alias_tag"].alias_for == "Local:1:I.Pt01.Data"

    def test_message_tag_value_is_none(self, controller_tags: TagsCollection) -> None:
        """MESSAGE-type tags have no parsed value tree."""
        assert controller_tags["message_tag"].value is None

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
        assert controller_tags["ServosMotionGroup"].value is None

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
        assert tag.message_parameters is None
        assert tag.motion_group_parameters is None
        assert tag.axis_parameters is None
        assert tag.special_data_format is None
        assert tag.special_data_attributes is None

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
        """Consumed tags parse their atomic value and expose ConsumeInfo."""
        tag = controller_tags["consumed_tag"]
        assert tag.value == 0
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
        assert tag.value == 0
        assert tag.produce_info is not None
        assert tag.produce_info["ProduceCount"] == "1"


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
        assert alias.value is None

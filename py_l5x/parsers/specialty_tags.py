"""Typed wrappers for tag data types with non-standard ``<Data>`` sections.

``MESSAGE``, ``MOTION_GROUP``, and ``AXIS_CIP_DRIVE`` (and related CIP axis
types) tags don't export a normal ``Decorated``/``String`` value tree.
Instead, Logix exports a single ``<Data Format="...">`` element wrapping one
parameter child (``MessageParameters``, ``MotionGroupParameters``, or
``AxisParameters``) whose *attributes* carry all the configuration. These
classes wrap that child element directly.

Only the ``Decorated``-equivalent data is modeled here -- the redundant
``L5K`` mirror some of these tags also export is intentionally ignored (see
:mod:`py_l5x.parsers.tag`).

Each class declares the commonly used attributes as typed :class:`XmlField`
descriptors (readable *and* writable -- see :mod:`py_l5x.parsers.base`) and
falls back to :attr:`extra_attributes`/:attr:`attributes` for anything not
explicitly covered (e.g. ``AxisParameters`` has 150+ attributes; only the
most commonly used ones get dedicated fields).
"""

from __future__ import annotations

from py_l5x.parsers.base import (
    BaseElement,
    bool_attr,
    flag_attr,
    float_attr,
    int_attr,
    str_attr,
)


class MessageParameters(BaseElement):
    """``<MessageParameters>``, for ``MESSAGE`` type tags.

    Configures a CIP message (e.g. a Data Table Read/Write to another
    controller over EtherNet/IP).

    Args:
        element: The ``<MessageParameters>`` element from a parsed L5X tree.
    """

    message_type = str_attr(
        "MessageType", doc='Message instruction type (e.g. "CIP Data Table Write").'
    )
    remote_element = str_attr(
        "RemoteElement",
        doc="Tag/element name on the remote device being read or written.",
    )
    requested_length = int_attr(
        "RequestedLength", doc="Number of elements requested, if applicable."
    )
    connected = flag_attr(
        "ConnectedFlag",
        doc="Whether the message uses a connected (vs. unconnected) path.",
    )
    connection_path = str_attr(
        "ConnectionPath", doc="CIP path to the target device (e.g. a controller name)."
    )
    comm_type_code = str_attr("CommTypeCode", doc="Raw communication type code.")
    local_index = int_attr(
        "LocalIndex", doc="Local array index used with local_element, if applicable."
    )
    local_element = str_attr(
        "LocalElement",
        doc="Local tag/element supplying or receiving the message data.",
    )
    cache_connections = bool_attr(
        "CacheConnections",
        true_str="TRUE",
        false_str="FALSE",
        doc="Whether the underlying CIP connection is cached between messages.",
    )


class MotionGroupParameters(BaseElement):
    """``<MotionGroupParameters>``, for ``MOTION_GROUP`` type tags.

    A motion group coordinates the update scheduling of one or more CIP
    Motion axes (see :class:`AxisParameters`). At least one motion group is
    required when any ``AXIS_CIP_DRIVE`` tag is present.

    Args:
        element: The ``<MotionGroupParameters>`` element from a parsed L5X
            tree.
    """

    coarse_update_period = int_attr(
        "CoarseUpdatePeriod", doc="Coarse update period in microseconds."
    )
    phase_shift = int_attr(
        "PhaseShift",
        doc="Phase shift (in microseconds) applied to the update schedule.",
    )
    general_fault_type = str_attr(
        "GeneralFaultType",
        doc='Fault severity applied when the group faults (e.g. "Non Major Fault").',
    )
    auto_tag_update = str_attr(
        "AutoTagUpdate",
        doc='Whether axis tag data auto-updates ("Enabled"/"Disabled").',
    )
    alternate1_update_multiplier = int_attr(
        "Alternate1UpdateMultiplier",
        doc="Update rate multiplier for the first alternate update group.",
    )
    alternate2_update_multiplier = int_attr(
        "Alternate2UpdateMultiplier",
        doc="Update rate multiplier for the second alternate update group.",
    )


class AxisParameters(BaseElement):
    """``<AxisParameters>``, for ``AXIS_CIP_DRIVE`` (and related CIP axis)
    type tags.

    Represents a single EtherNet/IP servo axis. This element carries well
    over a hundred drive/motor/loop-tuning attributes; only the most
    commonly used ones get dedicated fields below. Anything else is
    available via :attr:`extra_attributes`/:attr:`attributes`.

    Args:
        element: The ``<AxisParameters>`` element from a parsed L5X tree.
    """

    # ------------------------------------------------------------------
    # Identification / configuration
    # ------------------------------------------------------------------

    motion_group = str_attr(
        "MotionGroup", doc='Name of the "MOTION_GROUP" tag this axis belongs to.'
    )
    motion_module = str_attr(
        "MotionModule",
        doc='Servo drive module and channel driving this axis (e.g. "Drive:Ch1").',
    )
    axis_configuration = str_attr(
        "AxisConfiguration",
        doc='Loop configuration (e.g. "Position Loop", "Velocity Loop").',
    )
    feedback_configuration = str_attr(
        "FeedbackConfiguration",
        doc='Feedback source configuration (e.g. "Motor Feedback").',
    )
    motor_data_source = str_attr(
        "MotorDataSource",
        doc='Where motor nameplate data comes from (e.g. "Database").',
    )
    motor_catalog_number = str_attr(
        "MotorCatalogNumber", doc='Motor catalog number (e.g. "VPL-B0631T-C").'
    )
    motor_type = str_attr(
        "MotorType", doc='Motor type (e.g. "Rotary Permanent Magnet").'
    )
    motion_scaling_configuration = str_attr(
        "MotionScalingConfiguration",
        doc='How position scaling is derived (e.g. "Control Scaling").',
    )

    # ------------------------------------------------------------------
    # Scaling / units
    # ------------------------------------------------------------------

    conversion_constant = float_attr(
        "ConversionConstant", doc="Position feedback counts per position_units."
    )
    position_units = str_attr(
        "PositionUnits", doc='Engineering unit for position (e.g. "mm").'
    )
    position_unwind = float_attr(
        "PositionUnwind",
        doc="Position value at which a rotary axis unwinds back to zero.",
    )
    motion_polarity = str_attr(
        "MotionPolarity",
        doc='Direction polarity for commanded motion ("Normal"/"Inverted").',
    )
    motion_resolution = int_attr(
        "MotionResolution", doc="Position feedback counts per motor revolution/unit."
    )
    scaling_source = str_attr(
        "ScalingSource",
        doc='Where scaling values come from (e.g. "From Calculator", "User Entered").',
    )
    load_type = str_attr(
        "LoadType", doc='Mechanical load type (e.g. "Linear Actuator", "Rotary").'
    )
    actuator_type = str_attr(
        "ActuatorType",
        doc='Actuator mechanism type (e.g. "Screw", "Belt/Pulley", "Rack & Pinion").',
    )
    travel_mode = str_attr(
        "TravelMode", doc='Travel range mode (e.g. "Limited", "Unlimited").'
    )
    travel_range = float_attr(
        "TravelRange", doc="Total travel range of the axis, in position_units."
    )
    position_scaling_numerator = float_attr(
        "PositionScalingNumerator",
        doc="Numerator of the position scaling ratio (motor units to load units).",
    )
    position_scaling_denominator = float_attr(
        "PositionScalingDenominator",
        doc="Denominator of the position scaling ratio (motor units to load units).",
    )
    position_unwind_numerator = float_attr(
        "PositionUnwindNumerator",
        doc="Numerator of the position unwind ratio, for rotary/unwind axes.",
    )
    position_unwind_denominator = float_attr(
        "PositionUnwindDenominator",
        doc="Denominator of the position unwind ratio, for rotary/unwind axes.",
    )
    actuator_lead = float_attr(
        "ActuatorLead",
        doc="Actuator lead (e.g. screw lead/pitch or pulley circumference).",
    )
    actuator_lead_unit = str_attr(
        "ActuatorLeadUnit",
        doc='Engineering unit for actuator_lead (e.g. "Millimeter/Rev").',
    )
    actuator_diameter = float_attr(
        "ActuatorDiameter", doc="Actuator diameter (e.g. pulley or drum diameter)."
    )
    actuator_diameter_unit = str_attr(
        "ActuatorDiameterUnit",
        doc='Engineering unit for actuator_diameter (e.g. "Millimeter").',
    )
    transmission_ratio_input = float_attr(
        "TransmissionRatioInput", doc="Gearbox/transmission ratio input (motor side)."
    )
    transmission_ratio_output = float_attr(
        "TransmissionRatioOutput", doc="Gearbox/transmission ratio output (load side)."
    )

    # ------------------------------------------------------------------
    # Motor nameplate
    # ------------------------------------------------------------------

    motor_unit = str_attr("MotorUnit", doc='Motor motion unit (e.g. "Rev").')
    motor_polarity = str_attr(
        "MotorPolarity", doc='Motor direction polarity ("Normal"/"Inverted").'
    )
    motor_device_code = str_attr(
        "MotorDeviceCode",
        doc="Motor device identification code reported over the network.",
    )
    motor_rated_voltage = float_attr(
        "MotorRatedVoltage", doc="Motor nameplate rated voltage."
    )
    motor_rated_continuous_current = float_attr(
        "MotorRatedContinuousCurrent", doc="Motor nameplate rated continuous current."
    )
    motor_rated_peak_current = float_attr(
        "MotorRatedPeakCurrent", doc="Motor nameplate rated peak current."
    )
    motor_rated_output_power = float_attr(
        "MotorRatedOutputPower", doc="Motor nameplate rated output power (kW)."
    )
    motor_overload_limit = float_attr(
        "MotorOverloadLimit", doc="Motor thermal overload limit (percent of rated)."
    )
    rotary_motor_poles = int_attr(
        "RotaryMotorPoles", doc="Number of motor poles, for rotary motors."
    )
    rotary_motor_inertia = float_attr(
        "RotaryMotorInertia", doc="Rotor inertia, for rotary motors."
    )
    rotary_motor_rated_speed = float_attr(
        "RotaryMotorRatedSpeed", doc="Nameplate rated speed, for rotary motors."
    )
    rotary_motor_max_speed = float_attr(
        "RotaryMotorMaxSpeed", doc="Maximum mechanical speed, for rotary motors."
    )
    pm_motor_rated_torque = float_attr(
        "PMMotorRatedTorque", doc="Rated torque, for permanent-magnet motors."
    )
    pm_motor_torque_constant = float_attr(
        "PMMotorTorqueConstant", doc="Torque constant, for permanent-magnet motors."
    )
    pm_motor_rotary_voltage_constant = float_attr(
        "PMMotorRotaryVoltageConstant",
        doc="Back-EMF voltage constant, for permanent-magnet rotary motors.",
    )

    # ------------------------------------------------------------------
    # Homing
    # ------------------------------------------------------------------

    home_mode = str_attr("HomeMode", doc='Homing mode (e.g. "Active", "Passive").')
    home_direction = str_attr(
        "HomeDirection", doc="Direction the axis travels while searching for home."
    )
    home_sequence = str_attr(
        "HomeSequence", doc='Sequence of events used to establish home (e.g. "Switch").'
    )
    home_position = float_attr(
        "HomePosition", doc="Position value assigned once homing completes."
    )
    home_offset = float_attr(
        "HomeOffset",
        doc="Offset applied from the home switch/marker to the home position.",
    )
    home_speed = float_attr(
        "HomeSpeed", doc="Speed used while searching for the home switch/marker."
    )
    home_return_speed = float_attr(
        "HomeReturnSpeed", doc="Speed used to return to the home position after homing."
    )

    # ------------------------------------------------------------------
    # Motion limits
    # ------------------------------------------------------------------

    maximum_speed = float_attr(
        "MaximumSpeed", doc="Maximum commandable speed, in position_units per second."
    )
    maximum_acceleration = float_attr(
        "MaximumAcceleration", doc="Maximum commandable acceleration."
    )
    maximum_deceleration = float_attr(
        "MaximumDeceleration", doc="Maximum commandable deceleration."
    )
    velocity_limit_positive = float_attr(
        "VelocityLimitPositive", doc="Positive-direction velocity limit."
    )
    velocity_limit_negative = float_attr(
        "VelocityLimitNegative", doc="Negative-direction velocity limit."
    )
    torque_limit_positive = float_attr(
        "TorqueLimitPositive",
        doc="Positive-direction torque limit (percent of motor rated torque).",
    )
    torque_limit_negative = float_attr(
        "TorqueLimitNegative",
        doc="Negative-direction torque limit (percent of motor rated torque).",
    )
    soft_travel_limit_positive = float_attr(
        "SoftTravelLimitPositive",
        doc="Positive-direction software travel limit position.",
    )
    soft_travel_limit_negative = float_attr(
        "SoftTravelLimitNegative",
        doc="Negative-direction software travel limit position.",
    )
    soft_travel_limit_checking = bool_attr(
        "SoftTravelLimitChecking",
        true_str="TRUE",
        false_str="FALSE",
        doc="Whether software travel limits are enforced.",
    )

    # ------------------------------------------------------------------
    # Stopping
    # ------------------------------------------------------------------

    programmed_stop_mode = str_attr(
        "ProgrammedStopMode",
        doc="Deceleration profile used for a normal (programmed) stop.",
    )
    stopping_action = str_attr(
        "StoppingAction",
        doc="Action taken to stop the axis on a fault/disable condition.",
    )
    stopping_torque = float_attr(
        "StoppingTorque", doc="Torque limit applied while stopping."
    )
    stopping_time_limit = float_attr(
        "StoppingTimeLimit",
        doc="Maximum time allowed for the axis to stop before faulting.",
    )

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    feedback1_type = str_attr(
        "Feedback1Type", doc='Primary feedback device type (e.g. "Hiperface DSL").'
    )
    feedback1_unit = str_attr(
        "Feedback1Unit", doc='Primary feedback device unit (e.g. "Rev").'
    )
    feedback1_cycle_resolution = int_attr(
        "Feedback1CycleResolution",
        doc="Primary feedback device counts per cycle/revolution.",
    )
    feedback1_turns = int_attr(
        "Feedback1Turns",
        doc="Primary feedback device number of turns (multi-turn absolute).",
    )

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    axis_id = int_attr(
        "AxisID", doc="Internal numeric identifier Logix assigns to this axis."
    )

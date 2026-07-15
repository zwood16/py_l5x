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

Each class exposes the commonly used attributes as typed properties and
falls back to :attr:`extra_attributes`/:attr:`attributes` for anything not
explicitly covered (e.g. ``AxisParameters`` has 150+ attributes; only the
most commonly used ones get dedicated properties).
"""

from __future__ import annotations

from py_l5x.parsers.base import BaseElement


def _parse_bool(value: str) -> bool | None:
    """Parse a ``"true"``/``"false"`` (case-insensitive) attribute.

    Args:
        value: The raw attribute string, or ``""`` if absent.

    Returns:
        ``True``/``False`` when *value* is non-empty, ``None`` otherwise.
    """
    if not value:
        return None
    return value.strip().upper() == "TRUE"


def _parse_int(value: str) -> int | None:
    """Parse an integer attribute; return ``None`` for empty/invalid values.

    Args:
        value: The raw attribute string, or ``""`` if absent.

    Returns:
        The parsed integer, or ``None`` if empty or not a valid integer.
    """
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: str) -> float | None:
    """Parse a floating-point attribute; return ``None`` for empty/invalid values.

    Args:
        value: The raw attribute string, or ``""`` if absent.

    Returns:
        The parsed float, or ``None`` if empty or not a valid float.
    """
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_flag(value: str) -> bool | None:
    """Parse a ``"1"``/``"0"`` flag attribute.

    Args:
        value: The raw attribute string, or ``""`` if absent.

    Returns:
        ``True``/``False`` when *value* is non-empty, ``None`` otherwise.
    """
    if not value:
        return None
    return value.strip() == "1"


def _fmt(value: object) -> str:
    """Format a property value for display in ``__repr__``.

    Args:
        value: Any property value (``str``, ``int``, ``float``, ``bool``, or
            ``None``).

    Returns:
        ``str(value)``, or ``"\u2014"`` (an em dash) for ``None`` or an empty
        string.
    """
    if value is None or value == "":
        return "\u2014"
    return str(value)


def _repr_with_extras(header_lines: list[str], extra_attributes: dict[str, str]) -> str:
    """Build a multi-line ``__repr__`` string with an Extra Attributes section.

    Args:
        header_lines: Already-formatted ``"Label: value"`` lines to show
            first.
        extra_attributes: Attributes not covered by dedicated properties;
            appended (sorted) under an ``"Extra Attributes:"`` header if
            non-empty.

    Returns:
        The joined multi-line representation string.
    """
    lines = list(header_lines)
    if extra_attributes:
        lines.append("Extra Attributes:")
        for k, v in sorted(extra_attributes.items()):
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


class MessageParameters(BaseElement):
    """``<MessageParameters>``, for ``MESSAGE`` type tags.

    Configures a CIP message (e.g. a Data Table Read/Write to another
    controller over EtherNet/IP).

    Args:
        element: The ``<MessageParameters>`` element from a parsed L5X tree.
    """

    _KNOWN_KEYS: frozenset[str] = frozenset(
        {
            "MessageType",
            "RemoteElement",
            "RequestedLength",
            "ConnectedFlag",
            "ConnectionPath",
            "CommTypeCode",
            "LocalIndex",
            "LocalElement",
            "CacheConnections",
        }
    )

    @property
    def message_type(self) -> str:
        """Message instruction type (e.g. ``"CIP Data Table Write"``)."""
        return self._get("MessageType")

    @property
    def remote_element(self) -> str:
        """Tag/element name on the remote device being read or written."""
        return self._get("RemoteElement")

    @property
    def requested_length(self) -> int | None:
        """Number of elements requested, if applicable."""
        return _parse_int(self._get("RequestedLength"))

    @property
    def connected(self) -> bool | None:
        """Whether the message uses a connected (vs. unconnected) path."""
        return _parse_flag(self._get("ConnectedFlag"))

    @property
    def connection_path(self) -> str:
        """CIP path to the target device (e.g. a controller name)."""
        return self._get("ConnectionPath")

    @property
    def comm_type_code(self) -> str:
        """Raw communication type code."""
        return self._get("CommTypeCode")

    @property
    def local_index(self) -> int | None:
        """Local array index used with :attr:`local_element`, if applicable."""
        return _parse_int(self._get("LocalIndex"))

    @property
    def local_element(self) -> str:
        """Local tag/element supplying or receiving the message data."""
        return self._get("LocalElement")

    @property
    def cache_connections(self) -> bool | None:
        """Whether the underlying CIP connection is cached between messages."""
        return _parse_bool(self._get("CacheConnections"))

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v for k, v in self._element.attrib.items() if k not in self._KNOWN_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<MessageParameters>`` element."""
        return dict(self._element.attrib)

    def __repr__(self) -> str:
        """Return a multi-line representation of the message configuration.

        Returns:
            A formatted string suitable for display in debug output.
        """
        return _repr_with_extras(
            [
                f"Message Type:      {_fmt(self.message_type)}",
                f"Connection Path:   {_fmt(self.connection_path)}",
                f"Remote Element:    {_fmt(self.remote_element)}",
                f"Local Element:     {_fmt(self.local_element)}",
                f"Requested Length:  {_fmt(self.requested_length)}",
                f"Connected:         {_fmt(self.connected)}",
                f"Cache Connections: {_fmt(self.cache_connections)}",
            ],
            self.extra_attributes,
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

    _KNOWN_KEYS: frozenset[str] = frozenset(
        {
            "CoarseUpdatePeriod",
            "PhaseShift",
            "GeneralFaultType",
            "AutoTagUpdate",
            "Alternate1UpdateMultiplier",
            "Alternate2UpdateMultiplier",
        }
    )

    @property
    def coarse_update_period(self) -> int | None:
        """Coarse update period in microseconds."""
        return _parse_int(self._get("CoarseUpdatePeriod"))

    @property
    def phase_shift(self) -> int | None:
        """Phase shift (in microseconds) applied to the update schedule."""
        return _parse_int(self._get("PhaseShift"))

    @property
    def general_fault_type(self) -> str:
        """Fault severity applied when the group faults (e.g. ``"Non Major Fault"``)."""
        return self._get("GeneralFaultType")

    @property
    def auto_tag_update(self) -> str:
        """Whether axis tag data auto-updates (``"Enabled"``/``"Disabled"``)."""
        return self._get("AutoTagUpdate")

    @property
    def alternate1_update_multiplier(self) -> int | None:
        """Update rate multiplier for the first alternate update group."""
        return _parse_int(self._get("Alternate1UpdateMultiplier"))

    @property
    def alternate2_update_multiplier(self) -> int | None:
        """Update rate multiplier for the second alternate update group."""
        return _parse_int(self._get("Alternate2UpdateMultiplier"))

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v for k, v in self._element.attrib.items() if k not in self._KNOWN_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<MotionGroupParameters>`` element."""
        return dict(self._element.attrib)

    def __repr__(self) -> str:
        """Return a multi-line representation of the motion group configuration.

        Returns:
            A formatted string suitable for display in debug output.
        """
        return _repr_with_extras(
            [
                f"Coarse Update Period: {_fmt(self.coarse_update_period)} us",
                f"Phase Shift:          {_fmt(self.phase_shift)} us",
                f"General Fault Type:   {_fmt(self.general_fault_type)}",
                f"Auto Tag Update:      {_fmt(self.auto_tag_update)}",
                f"Alt1 Update Mult:     {_fmt(self.alternate1_update_multiplier)}",
                f"Alt2 Update Mult:     {_fmt(self.alternate2_update_multiplier)}",
            ],
            self.extra_attributes,
        )


class AxisParameters(BaseElement):
    """``<AxisParameters>``, for ``AXIS_CIP_DRIVE`` (and related CIP axis)
    type tags.

    Represents a single EtherNet/IP servo axis. This element carries well
    over a hundred drive/motor/loop-tuning attributes; only the most
    commonly used ones get dedicated properties below. Anything else is
    available via :attr:`extra_attributes`/:attr:`attributes`.

    Args:
        element: The ``<AxisParameters>`` element from a parsed L5X tree.
    """

    _KNOWN_KEYS: frozenset[str] = frozenset(
        {
            "MotionGroup",
            "MotionModule",
            "AxisConfiguration",
            "FeedbackConfiguration",
            "MotorDataSource",
            "MotorCatalogNumber",
            "MotorType",
            "MotionScalingConfiguration",
            "ConversionConstant",
            "PositionUnits",
            "PositionUnwind",
            "MotionPolarity",
            "MotionResolution",
            "ScalingSource",
            "LoadType",
            "ActuatorType",
            "TravelMode",
            "TravelRange",
            "PositionScalingNumerator",
            "PositionScalingDenominator",
            "PositionUnwindNumerator",
            "PositionUnwindDenominator",
            "ActuatorLead",
            "ActuatorLeadUnit",
            "ActuatorDiameter",
            "ActuatorDiameterUnit",
            "TransmissionRatioInput",
            "TransmissionRatioOutput",
            "MotorUnit",
            "MotorPolarity",
            "MotorDeviceCode",
            "MotorRatedVoltage",
            "MotorRatedContinuousCurrent",
            "MotorRatedPeakCurrent",
            "MotorRatedOutputPower",
            "MotorOverloadLimit",
            "RotaryMotorPoles",
            "RotaryMotorInertia",
            "RotaryMotorRatedSpeed",
            "RotaryMotorMaxSpeed",
            "PMMotorRatedTorque",
            "PMMotorTorqueConstant",
            "PMMotorRotaryVoltageConstant",
            "HomeMode",
            "HomeDirection",
            "HomeSequence",
            "HomePosition",
            "HomeOffset",
            "HomeSpeed",
            "HomeReturnSpeed",
            "MaximumSpeed",
            "MaximumAcceleration",
            "MaximumDeceleration",
            "VelocityLimitPositive",
            "VelocityLimitNegative",
            "TorqueLimitPositive",
            "TorqueLimitNegative",
            "SoftTravelLimitPositive",
            "SoftTravelLimitNegative",
            "SoftTravelLimitChecking",
            "ProgrammedStopMode",
            "StoppingAction",
            "StoppingTorque",
            "StoppingTimeLimit",
            "Feedback1Type",
            "Feedback1Unit",
            "Feedback1CycleResolution",
            "Feedback1Turns",
            "AxisID",
        }
    )

    # ------------------------------------------------------------------
    # Identification / configuration
    # ------------------------------------------------------------------

    @property
    def motion_group(self) -> str:
        """Name of the ``MOTION_GROUP`` tag this axis belongs to."""
        return self._get("MotionGroup")

    @property
    def motion_module(self) -> str:
        """Servo drive module and channel driving this axis (e.g. ``"Drive:Ch1"``)."""
        return self._get("MotionModule")

    @property
    def axis_configuration(self) -> str:
        """Loop configuration (e.g. ``"Position Loop"``, ``"Velocity Loop"``)."""
        return self._get("AxisConfiguration")

    @property
    def feedback_configuration(self) -> str:
        """Feedback source configuration (e.g. ``"Motor Feedback"``)."""
        return self._get("FeedbackConfiguration")

    @property
    def motor_data_source(self) -> str:
        """Where motor nameplate data comes from (e.g. ``"Database"``)."""
        return self._get("MotorDataSource")

    @property
    def motor_catalog_number(self) -> str:
        """Motor catalog number (e.g. ``"VPL-B0631T-C"``)."""
        return self._get("MotorCatalogNumber")

    @property
    def motor_type(self) -> str:
        """Motor type (e.g. ``"Rotary Permanent Magnet"``)."""
        return self._get("MotorType")

    @property
    def motion_scaling_configuration(self) -> str:
        """How position scaling is derived (e.g. ``"Control Scaling"``)."""
        return self._get("MotionScalingConfiguration")

    # ------------------------------------------------------------------
    # Scaling / units
    # ------------------------------------------------------------------

    @property
    def conversion_constant(self) -> float | None:
        """Position feedback counts per :attr:`position_units`."""
        return _parse_float(self._get("ConversionConstant"))

    @property
    def position_units(self) -> str:
        """Engineering unit for position (e.g. ``"mm"``)."""
        return self._get("PositionUnits")

    @property
    def position_unwind(self) -> float | None:
        """Position value at which a rotary axis unwinds back to zero."""
        return _parse_float(self._get("PositionUnwind"))

    @property
    def motion_polarity(self) -> str:
        """Direction polarity for commanded motion (``"Normal"``/``"Inverted"``)."""
        return self._get("MotionPolarity")

    @property
    def motion_resolution(self) -> int | None:
        """Position feedback counts per motor revolution/unit."""
        return _parse_int(self._get("MotionResolution"))

    @property
    def scaling_source(self) -> str:
        """Where scaling values come from (e.g. ``"From Calculator"``, ``"User Entered"``)."""
        return self._get("ScalingSource")

    @property
    def load_type(self) -> str:
        """Mechanical load type (e.g. ``"Linear Actuator"``, ``"Rotary"``)."""
        return self._get("LoadType")

    @property
    def actuator_type(self) -> str:
        """Actuator mechanism type (e.g. ``"Screw"``, ``"Belt/Pulley"``, ``"Rack & Pinion"``)."""
        return self._get("ActuatorType")

    @property
    def travel_mode(self) -> str:
        """Travel range mode (e.g. ``"Limited"``, ``"Unlimited"``)."""
        return self._get("TravelMode")

    @property
    def travel_range(self) -> float | None:
        """Total travel range of the axis, in :attr:`position_units`."""
        return _parse_float(self._get("TravelRange"))

    @property
    def position_scaling_numerator(self) -> float | None:
        """Numerator of the position scaling ratio (motor units to load units)."""
        return _parse_float(self._get("PositionScalingNumerator"))

    @property
    def position_scaling_denominator(self) -> float | None:
        """Denominator of the position scaling ratio (motor units to load units)."""
        return _parse_float(self._get("PositionScalingDenominator"))

    @property
    def position_unwind_numerator(self) -> float | None:
        """Numerator of the position unwind ratio, for rotary/unwind axes."""
        return _parse_float(self._get("PositionUnwindNumerator"))

    @property
    def position_unwind_denominator(self) -> float | None:
        """Denominator of the position unwind ratio, for rotary/unwind axes."""
        return _parse_float(self._get("PositionUnwindDenominator"))

    @property
    def actuator_lead(self) -> float | None:
        """Actuator lead (e.g. screw lead/pitch or pulley circumference)."""
        return _parse_float(self._get("ActuatorLead"))

    @property
    def actuator_lead_unit(self) -> str:
        """Engineering unit for :attr:`actuator_lead` (e.g. ``"Millimeter/Rev"``)."""
        return self._get("ActuatorLeadUnit")

    @property
    def actuator_diameter(self) -> float | None:
        """Actuator diameter (e.g. pulley or drum diameter)."""
        return _parse_float(self._get("ActuatorDiameter"))

    @property
    def actuator_diameter_unit(self) -> str:
        """Engineering unit for :attr:`actuator_diameter` (e.g. ``"Millimeter"``)."""
        return self._get("ActuatorDiameterUnit")

    @property
    def transmission_ratio_input(self) -> float | None:
        """Gearbox/transmission ratio input (motor side)."""
        return _parse_float(self._get("TransmissionRatioInput"))

    @property
    def transmission_ratio_output(self) -> float | None:
        """Gearbox/transmission ratio output (load side)."""
        return _parse_float(self._get("TransmissionRatioOutput"))

    # ------------------------------------------------------------------
    # Motor nameplate
    # ------------------------------------------------------------------

    @property
    def motor_unit(self) -> str:
        """Motor motion unit (e.g. ``"Rev"``)."""
        return self._get("MotorUnit")

    @property
    def motor_polarity(self) -> str:
        """Motor direction polarity (``"Normal"``/``"Inverted"``)."""
        return self._get("MotorPolarity")

    @property
    def motor_device_code(self) -> str:
        """Motor device identification code reported over the network."""
        return self._get("MotorDeviceCode")

    @property
    def motor_rated_voltage(self) -> float | None:
        """Motor nameplate rated voltage."""
        return _parse_float(self._get("MotorRatedVoltage"))

    @property
    def motor_rated_continuous_current(self) -> float | None:
        """Motor nameplate rated continuous current."""
        return _parse_float(self._get("MotorRatedContinuousCurrent"))

    @property
    def motor_rated_peak_current(self) -> float | None:
        """Motor nameplate rated peak current."""
        return _parse_float(self._get("MotorRatedPeakCurrent"))

    @property
    def motor_rated_output_power(self) -> float | None:
        """Motor nameplate rated output power (kW)."""
        return _parse_float(self._get("MotorRatedOutputPower"))

    @property
    def motor_overload_limit(self) -> float | None:
        """Motor thermal overload limit (percent of rated)."""
        return _parse_float(self._get("MotorOverloadLimit"))

    @property
    def rotary_motor_poles(self) -> int | None:
        """Number of motor poles, for rotary motors."""
        return _parse_int(self._get("RotaryMotorPoles"))

    @property
    def rotary_motor_inertia(self) -> float | None:
        """Rotor inertia, for rotary motors."""
        return _parse_float(self._get("RotaryMotorInertia"))

    @property
    def rotary_motor_rated_speed(self) -> float | None:
        """Nameplate rated speed, for rotary motors."""
        return _parse_float(self._get("RotaryMotorRatedSpeed"))

    @property
    def rotary_motor_max_speed(self) -> float | None:
        """Maximum mechanical speed, for rotary motors."""
        return _parse_float(self._get("RotaryMotorMaxSpeed"))

    @property
    def pm_motor_rated_torque(self) -> float | None:
        """Rated torque, for permanent-magnet motors."""
        return _parse_float(self._get("PMMotorRatedTorque"))

    @property
    def pm_motor_torque_constant(self) -> float | None:
        """Torque constant, for permanent-magnet motors."""
        return _parse_float(self._get("PMMotorTorqueConstant"))

    @property
    def pm_motor_rotary_voltage_constant(self) -> float | None:
        """Back-EMF voltage constant, for permanent-magnet rotary motors."""
        return _parse_float(self._get("PMMotorRotaryVoltageConstant"))

    # ------------------------------------------------------------------
    # Homing
    # ------------------------------------------------------------------

    @property
    def home_mode(self) -> str:
        """Homing mode (e.g. ``"Active"``, ``"Passive"``)."""
        return self._get("HomeMode")

    @property
    def home_direction(self) -> str:
        """Direction the axis travels while searching for home."""
        return self._get("HomeDirection")

    @property
    def home_sequence(self) -> str:
        """Sequence of events used to establish home (e.g. ``"Switch"``)."""
        return self._get("HomeSequence")

    @property
    def home_position(self) -> float | None:
        """Position value assigned once homing completes."""
        return _parse_float(self._get("HomePosition"))

    @property
    def home_offset(self) -> float | None:
        """Offset applied from the home switch/marker to the home position."""
        return _parse_float(self._get("HomeOffset"))

    @property
    def home_speed(self) -> float | None:
        """Speed used while searching for the home switch/marker."""
        return _parse_float(self._get("HomeSpeed"))

    @property
    def home_return_speed(self) -> float | None:
        """Speed used to return to the home position after homing."""
        return _parse_float(self._get("HomeReturnSpeed"))

    # ------------------------------------------------------------------
    # Motion limits
    # ------------------------------------------------------------------

    @property
    def maximum_speed(self) -> float | None:
        """Maximum commandable speed, in :attr:`position_units` per second."""
        return _parse_float(self._get("MaximumSpeed"))

    @property
    def maximum_acceleration(self) -> float | None:
        """Maximum commandable acceleration."""
        return _parse_float(self._get("MaximumAcceleration"))

    @property
    def maximum_deceleration(self) -> float | None:
        """Maximum commandable deceleration."""
        return _parse_float(self._get("MaximumDeceleration"))

    @property
    def velocity_limit_positive(self) -> float | None:
        """Positive-direction velocity limit."""
        return _parse_float(self._get("VelocityLimitPositive"))

    @property
    def velocity_limit_negative(self) -> float | None:
        """Negative-direction velocity limit."""
        return _parse_float(self._get("VelocityLimitNegative"))

    @property
    def torque_limit_positive(self) -> float | None:
        """Positive-direction torque limit (percent of motor rated torque)."""
        return _parse_float(self._get("TorqueLimitPositive"))

    @property
    def torque_limit_negative(self) -> float | None:
        """Negative-direction torque limit (percent of motor rated torque)."""
        return _parse_float(self._get("TorqueLimitNegative"))

    @property
    def soft_travel_limit_positive(self) -> float | None:
        """Positive-direction software travel limit position."""
        return _parse_float(self._get("SoftTravelLimitPositive"))

    @property
    def soft_travel_limit_negative(self) -> float | None:
        """Negative-direction software travel limit position."""
        return _parse_float(self._get("SoftTravelLimitNegative"))

    @property
    def soft_travel_limit_checking(self) -> bool | None:
        """Whether software travel limits are enforced."""
        return _parse_bool(self._get("SoftTravelLimitChecking"))

    # ------------------------------------------------------------------
    # Stopping
    # ------------------------------------------------------------------

    @property
    def programmed_stop_mode(self) -> str:
        """Deceleration profile used for a normal (programmed) stop."""
        return self._get("ProgrammedStopMode")

    @property
    def stopping_action(self) -> str:
        """Action taken to stop the axis on a fault/disable condition."""
        return self._get("StoppingAction")

    @property
    def stopping_torque(self) -> float | None:
        """Torque limit applied while stopping."""
        return _parse_float(self._get("StoppingTorque"))

    @property
    def stopping_time_limit(self) -> float | None:
        """Maximum time allowed for the axis to stop before faulting."""
        return _parse_float(self._get("StoppingTimeLimit"))

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    @property
    def feedback1_type(self) -> str:
        """Primary feedback device type (e.g. ``"Hiperface DSL"``)."""
        return self._get("Feedback1Type")

    @property
    def feedback1_unit(self) -> str:
        """Primary feedback device unit (e.g. ``"Rev"``)."""
        return self._get("Feedback1Unit")

    @property
    def feedback1_cycle_resolution(self) -> int | None:
        """Primary feedback device counts per cycle/revolution."""
        return _parse_int(self._get("Feedback1CycleResolution"))

    @property
    def feedback1_turns(self) -> int | None:
        """Primary feedback device number of turns (multi-turn absolute)."""
        return _parse_int(self._get("Feedback1Turns"))

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    @property
    def axis_id(self) -> int | None:
        """Internal numeric identifier Logix assigns to this axis."""
        return _parse_int(self._get("AxisID"))

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        ``AxisParameters`` carries well over a hundred attributes; only a
        commonly used subset has dedicated properties above. Everything
        else (detailed tuning, exception actions, etc.) is available here,
        keyed by the original XML attribute name so it can be
        cross-referenced against the Rockwell L5X export manual.
        """
        return {
            k: v for k, v in self._element.attrib.items() if k not in self._KNOWN_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<AxisParameters>`` element."""
        return dict(self._element.attrib)

    def __repr__(self) -> str:
        """Return a multi-line representation of the axis configuration.

        Shows a curated subset of the most commonly referenced properties
        (identification, scaling, homing, motion limits, stopping, and
        feedback); the full attribute set remains available via
        :attr:`attributes`/:attr:`extra_attributes`.

        Returns:
            A formatted string suitable for display in debug output.
        """
        return _repr_with_extras(
            [
                f"Motion Group:        {_fmt(self.motion_group)}",
                f"Motion Module:       {_fmt(self.motion_module)}",
                f"Axis Configuration:  {_fmt(self.axis_configuration)}",
                f"Feedback Config:     {_fmt(self.feedback_configuration)}",
                f"Motor Catalog Number: {_fmt(self.motor_catalog_number)}",
                f"Motor Type:          {_fmt(self.motor_type)}",
                f"Motor Rated Power:   {_fmt(self.motor_rated_output_power)}",
                f"Motor Rated Voltage: {_fmt(self.motor_rated_voltage)}",
                f"Conversion Constant: {_fmt(self.conversion_constant)}",
                f"Position Units:      {_fmt(self.position_units)}",
                f"Position Scaling N/D: {_fmt(self.position_scaling_numerator)} / {_fmt(self.position_scaling_denominator)}",
                f"Motion Resolution:   {_fmt(self.motion_resolution)}",
                f"Motion Polarity:     {_fmt(self.motion_polarity)}",
                f"Load Type:           {_fmt(self.load_type)}",
                f"Actuator Type:       {_fmt(self.actuator_type)}",
                f"Actuator Lead:       {_fmt(self.actuator_lead)} {_fmt(self.actuator_lead_unit)}",
                f"Travel Range:        {_fmt(self.travel_range)}",
                f"Home Mode:           {_fmt(self.home_mode)}",
                f"Home Direction:      {_fmt(self.home_direction)}",
                f"Home Sequence:       {_fmt(self.home_sequence)}",
                f"Maximum Speed:       {_fmt(self.maximum_speed)}",
                f"Maximum Accel:       {_fmt(self.maximum_acceleration)}",
                f"Maximum Decel:       {_fmt(self.maximum_deceleration)}",
                f"Velocity Limit +/-:  {_fmt(self.velocity_limit_positive)} / {_fmt(self.velocity_limit_negative)}",
                f"Torque Limit +/-:    {_fmt(self.torque_limit_positive)} / {_fmt(self.torque_limit_negative)}",
                f"Soft Limit +/-:      {_fmt(self.soft_travel_limit_positive)} / {_fmt(self.soft_travel_limit_negative)}",
                f"Programmed Stop:     {_fmt(self.programmed_stop_mode)}",
                f"Stopping Action:     {_fmt(self.stopping_action)}",
                f"Feedback1 Type:      {_fmt(self.feedback1_type)}",
                f"Feedback1 Unit:      {_fmt(self.feedback1_unit)}",
                f"Axis ID:             {_fmt(self.axis_id)}",
            ],
            self.extra_attributes,
        )

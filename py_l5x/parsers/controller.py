"""Top-level controller data.

This module provides ``ControllerInfo``, a wrapper around the ``<Controller>``
element in L5X files.  It declares every known XML attribute as a typed
:class:`~py_l5x.parsers.base.XmlField`/:class:`~py_l5x.parsers.base.CDataField`
and collects any unrecognised attributes in ``extra_attributes`` so they can
be cross-referenced against the Rockwell L5X export manual.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import (
    BaseElement,
    CDataField,
    bool_attr,
    int_attr,
    str_attr,
)


def _parse_int(value: str | None) -> int | None:
    """Parse an integer attribute; return ``None`` for empty/missing values.

    Args:
        value: The raw attribute string, or ``None`` if absent.

    Returns:
        The parsed integer, or ``None`` if the value is empty, missing, or
        not a valid integer.
    """
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


class SafetyInfo(BaseElement):
    """The ``<SafetyInfo>`` element, present only on safety controllers.

    Args:
        element: The ``<SafetyInfo>`` element from a parsed L5X tree.
    """

    safety_locked = bool_attr(
        "SafetyLocked", default=False, doc="Whether the safety partition is locked."
    )
    signature_run_mode_protect = bool_attr(
        "SignatureRunModeProtect",
        default=False,
        doc="Whether a safety signature protects against changes in Run mode.",
    )
    configure_safety_io_always = bool_attr(
        "ConfigureSafetyIOAlways",
        default=False,
        doc="Whether safety I/O can always be configured, even when the safety "
        "partition is locked.",
    )
    safety_level = str_attr("SafetyLevel", doc='Safety level string (e.g. "SIL3/PLe").')
    safety_tag_map = CDataField(
        "SafetyTagMap",
        doc="Raw text mapping standard tags to safety-side counterparts.",
    )

    def __repr__(self) -> str:
        """Return a concise representation including the safety level."""
        return f"SafetyInfo(SafetyLevel={self.safety_level!r})"


class TimeSynchronize(BaseElement):
    """The ``<TimeSynchronize>`` element (CIP Sync / PTP configuration).

    Args:
        element: The ``<TimeSynchronize>`` element from a parsed L5X tree.
    """

    priority1 = int_attr("Priority1", doc="Grandmaster clock Priority1 value.")
    priority2 = int_attr("Priority2", doc="Grandmaster clock Priority2 value.")
    ptp_enable = bool_attr(
        "PTPEnable",
        default=False,
        doc="Whether PTP (IEEE-1588) time synchronization is enabled -- "
        "required for CIP Motion / servo drive time sync.",
    )

    def __repr__(self) -> str:
        """Return a concise representation including PTP enable state."""
        return f"TimeSynchronize(PTPEnable={self.ptp_enable})"


class EthernetPort(BaseElement):
    """One ``<EthernetPort>`` under the controller's ``<EthernetPorts>``.

    Args:
        element: The ``<EthernetPort>`` element from a parsed L5X tree.
    """

    port = int_attr("Port", doc="Integer port number.")
    label = str_attr("Label", doc='Port label (e.g. "A1").')
    port_enabled = bool_attr(
        "PortEnabled", default=False, doc="Whether the port is enabled."
    )

    def __repr__(self) -> str:
        """Return a concise representation including the port label."""
        return f"EthernetPort({self.label!r}, enabled={self.port_enabled})"


class _EthernetPortsView(Mapping[int, EthernetPort]):
    """A live ``Mapping`` of integer port number to ``EthernetPort``.

    Args:
        controller_element: The ``<Controller>`` element whose
            ``EthernetPorts/EthernetPort`` children form this view.
    """

    def __init__(self, controller_element: ET.Element) -> None:
        self._controller_element = controller_element

    def _children(self) -> list[ET.Element]:
        ports_el = self._controller_element.find("EthernetPorts")
        if ports_el is None:
            return []
        return ports_el.findall("EthernetPort")

    def __getitem__(self, port: int) -> EthernetPort:
        for el in self._children():
            if _parse_int(el.get("Port")) == port:
                return EthernetPort(el)
        raise KeyError(port)

    def __iter__(self) -> Iterator[int]:
        for el in self._children():
            parsed = _parse_int(el.get("Port"))
            if parsed is not None:
                yield parsed

    def __len__(self) -> int:
        return len(self._children())

    def __repr__(self) -> str:
        return f"EthernetPorts({list(self)!r})"


class ControllerInfo(BaseElement):
    """Top-level controller metadata from a ``<Controller>`` element.

    Wraps a ``<Controller>`` XML element and exposes its attributes as
    readable properties.  Any attributes not explicitly handled are
    available via :attr:`extra_attributes`.

    Beyond the ``<Controller>`` element's own attributes, several notable
    child elements are exposed as typed properties:

    * :attr:`safety_info` / :attr:`is_safety_controller` -- safety
      partition configuration for safety controllers.
    * :attr:`time_synchronize` -- CIP Sync / PTP configuration (used for
      time-synchronized CIP Motion servo drives).
    * :attr:`cst_master_id` / :attr:`wall_clock_time` -- clock/CST info.
    * :attr:`opc_ua_enabled` / :attr:`opc_ua_enabled_ports` -- embedded OPC
      UA server state.
    * :attr:`ethernet_ports` -- per-port enable state.

    Args:
        element: The ``<Controller>`` element from a parsed L5X tree.
            Typically obtained via ``root.find("Controller")``.

    Example:
        >>> from xml.etree import ElementTree as ET
        >>> root = ET.parse("project.L5X").getroot()
        >>> ctrl = ControllerInfo(root.find("Controller"))
        >>> print(ctrl.name)
        MyController
    """

    def __init__(self, element: ET.Element) -> None:
        """Initialise from a ``<Controller>`` XML element.

        Args:
            element: The ``<Controller>`` element from a parsed L5X tree.
                Pass ``root.find("Controller")`` when constructing directly.
        """
        super().__init__(element)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    name = str_attr("Name", doc="Controller name.")
    use = str_attr(
        "Use",
        doc='Export target role. Common values include "Target" and "Source".',
    )
    processor_type = str_attr(
        "ProcessorType",
        default=None,
        doc='Processor catalog number (e.g. "5069-L306ERM"). None for '
        "context controllers (component exports).",
    )

    @property
    def is_context(self) -> bool:
        """Whether this controller element is a context (not the target).

        Component exports wrap all dependency data inside a
        ``<Controller Use="Context">`` element.  When this is ``True``,
        firmware, processor type, dates, and serial-number attributes are
        absent from the XML and the corresponding properties return ``None``.

        Returns:
            ``True`` if ``Use`` is ``"Context"``; ``False`` otherwise.
        """
        return self.use == "Context"

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------

    major_rev = str_attr(
        "MajorRev",
        default=None,
        doc="Major firmware revision. None for context controllers.",
    )
    minor_rev = str_attr(
        "MinorRev",
        default=None,
        doc="Minor firmware revision. None for context controllers.",
    )

    # ------------------------------------------------------------------
    # Dates / identifiers
    # ------------------------------------------------------------------

    project_creation_date = str_attr(
        "ProjectCreationDate",
        default=None,
        doc="Date string when the project was first created. None for "
        "context controllers.",
    )
    last_modified_date = str_attr(
        "LastModifiedDate",
        default=None,
        doc="Date string when the project was last saved. None for context "
        "controllers.",
    )
    project_sn = str_attr(
        "ProjectSN",
        default=None,
        doc="Project serial number. None for context controllers.",
    )

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    @property
    def safety_info(self) -> SafetyInfo | None:
        """Safety configuration for a safety-capable controller.

        Returns:
            A :class:`SafetyInfo` instance if a ``<SafetyInfo>`` child is
            present, ``None`` for non-safety controllers/context exports.
        """
        el = self._element.find("SafetyInfo")
        if el is None:
            return None
        return SafetyInfo(el)

    @property
    def is_safety_controller(self) -> bool:
        """Whether this is a safety controller.

        Returns:
            ``True`` if a ``<SafetyInfo>`` element is present, ``False``
            otherwise.
        """
        return self.safety_info is not None

    # ------------------------------------------------------------------
    # Time synchronization / clock
    # ------------------------------------------------------------------

    @property
    def cst_master_id(self) -> str | None:
        """Coordinated System Time (CST) master node id.

        Returns:
            The value of ``<CST MasterID="...">``, or ``None`` if absent.
        """
        el = self._element.find("CST")
        return el.get("MasterID") if el is not None else None

    @property
    def wall_clock_time(self) -> dict[str, str] | None:
        """Controller wall-clock/time-zone configuration.

        Returns:
            A dict of ``<WallClockTime>`` attributes (``LocalTimeAdjustment``,
            ``TimeZone``), or ``None`` if the element is absent.
        """
        el = self._element.find("WallClockTime")
        return dict(el.attrib) if el is not None else None

    @property
    def time_synchronize(self) -> TimeSynchronize | None:
        """CIP Sync (PTP / IEEE-1588) time synchronization configuration.

        Required for time-synchronized devices such as servo drives using
        CIP Motion. See :attr:`TimeSynchronize.ptp_enable`.

        Returns:
            A :class:`TimeSynchronize` instance if a ``<TimeSynchronize>``
            child is present, ``None`` otherwise.
        """
        el = self._element.find("TimeSynchronize")
        if el is None:
            return None
        return TimeSynchronize(el)

    @property
    def ethernet_ports(self) -> Mapping[int, EthernetPort]:
        """Live mapping of controller Ethernet port number to ``EthernetPort``.

        Returns:
            A ``Mapping`` keyed by integer port number; empty if no
            ``<EthernetPorts>`` element is present.
        """
        return _EthernetPortsView(self._element)

    # ------------------------------------------------------------------
    # OPC UA
    # ------------------------------------------------------------------

    @property
    def opc_ua_enabled(self) -> bool:
        """Whether the controller's embedded OPC UA server is enabled.

        Studio 5000 only exports an ``<OpcUaInfo>`` element when the OPC UA
        server feature is turned on.

        Returns:
            ``True`` if an ``<OpcUaInfo>`` element is present, ``False``
            otherwise.
        """
        return self._element.find("OpcUaInfo") is not None

    @property
    def opc_ua_enabled_ports(self) -> int | None:
        """Bitmask of Ethernet ports the OPC UA server is enabled on.

        Returns:
            The integer value of ``<OpcUaInfo EnabledPorts="...">``, or
            ``None`` if OPC UA is not enabled.
        """
        el = self._element.find("OpcUaInfo")
        if el is None:
            return None
        raw = el.get("EnabledPorts")
        return int(raw) if raw and raw.lstrip("-").isdigit() else None

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a multi-line string representation of the controller.

        Includes the controller name, processor type, firmware version,
        creation and modification dates, and any extra attributes.

        Returns:
            A formatted string suitable for display in debug output.
        """
        lines = [
            f"Controller Name:  {self.name}",
            f"Processor Type:   {self.processor_type or '—'}",
            f"Firmware:         {self.major_rev or '—'}.{self.minor_rev or '—'}",
            f"Created:          {self.project_creation_date or '—'}",
            f"Last Modified:    {self.last_modified_date or '—'}",
        ]
        extras = self.extra_attributes
        if extras:
            lines.append("Extra Attributes:")
            for k, v in sorted(extras.items()):
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

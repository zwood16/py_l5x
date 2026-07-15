"""Top-level controller data.

This module provides ``ControllerInfo``, a wrapper around the ``<Controller>``
element in L5X files.  It exposes every known XML attribute as a typed property
and collects any unrecognised attributes in ``extra_attributes`` so they can be
cross-referenced against the Rockwell L5X export manual.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import BaseElement

# XML attribute names that are exposed as explicit properties.
# Everything else ends up in ``extra_attributes``.
_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {
        "Use",
        "Name",
        "ProcessorType",
        "MajorRev",
        "MinorRev",
        "ProjectCreationDate",
        "LastModifiedDate",
        "ProjectSN",
    }
)


def _parse_bool(value: str | None) -> bool | None:
    """Parse a Rockwell-style ``"true"``/``"false"`` attribute.

    Args:
        value: The raw attribute string, or ``None`` if absent.

    Returns:
        ``True``/``False`` when the attribute is present, ``None`` otherwise.
    """
    if value is None:
        return None
    return value == "true"


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

    Attributes:
        safety_locked: Whether the safety partition is locked.
        signature_run_mode_protect: Whether a safety signature protects
            against changes in Run mode.
        configure_safety_io_always: Whether safety I/O can always be
            configured, even when the safety partition is locked.
        safety_level: Safety level string (e.g. ``"SIL3/PLe"``).
        safety_tag_map: Raw text of the ``<SafetyTagMap>`` child, mapping
            standard tags to their safety-side counterparts (e.g.
            ``"toSafety_reset=fromNormal_reset"``).

    Args:
        element: The ``<SafetyInfo>`` element from a parsed L5X tree.
    """

    _KNOWN_KEYS: frozenset[str] = frozenset(
        {
            "SafetyLocked",
            "SignatureRunModeProtect",
            "ConfigureSafetyIOAlways",
            "SafetyLevel",
        }
    )

    @property
    def safety_locked(self) -> bool:
        """Whether the safety partition is locked.

        Returns:
            ``True`` if ``SafetyLocked`` is ``"true"``, ``False`` otherwise.
        """
        return self._get("SafetyLocked") == "true"

    @property
    def signature_run_mode_protect(self) -> bool:
        """Whether a safety signature protects against changes in Run mode.

        Returns:
            ``True`` if ``SignatureRunModeProtect`` is ``"true"``, ``False``
            otherwise.
        """
        return self._get("SignatureRunModeProtect") == "true"

    @property
    def configure_safety_io_always(self) -> bool:
        """Whether safety I/O can always be configured.

        Returns:
            ``True`` if ``ConfigureSafetyIOAlways`` is ``"true"``, ``False``
            otherwise.
        """
        return self._get("ConfigureSafetyIOAlways") == "true"

    @property
    def safety_level(self) -> str:
        """Safety level string.

        Returns:
            The value of the ``SafetyLevel`` XML attribute (e.g.
            ``"SIL3/PLe"``).
        """
        return self._get("SafetyLevel")

    @property
    def safety_tag_map(self) -> str:
        """Raw text mapping standard tags to safety-side counterparts.

        Returns:
            The stripped text content of ``<SafetyTagMap>``, or ``""`` if
            absent.
        """
        return self._get_cdata_child("SafetyTagMap")

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v for k, v in self._element.attrib.items() if k not in self._KNOWN_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<SafetyInfo>`` element."""
        return dict(self._element.attrib)

    def __repr__(self) -> str:
        """Return a concise representation including the safety level."""
        return f"SafetyInfo(SafetyLevel={self.safety_level!r})"


class TimeSynchronize(BaseElement):
    """The ``<TimeSynchronize>`` element (CIP Sync / PTP configuration).

    Attributes:
        priority1: Grandmaster clock Priority1 value.
        priority2: Grandmaster clock Priority2 value.
        ptp_enable: Whether PTP (IEEE-1588) time synchronization is enabled
            -- required for CIP Motion / servo drive time sync.

    Args:
        element: The ``<TimeSynchronize>`` element from a parsed L5X tree.
    """

    _KNOWN_KEYS: frozenset[str] = frozenset({"Priority1", "Priority2", "PTPEnable"})

    @property
    def priority1(self) -> int | None:
        """Grandmaster clock Priority1 value."""
        return _parse_int(self._get("Priority1"))

    @property
    def priority2(self) -> int | None:
        """Grandmaster clock Priority2 value."""
        return _parse_int(self._get("Priority2"))

    @property
    def ptp_enable(self) -> bool:
        """Whether PTP (IEEE-1588) time synchronization is enabled."""
        return self._get("PTPEnable") == "true"

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v for k, v in self._element.attrib.items() if k not in self._KNOWN_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<TimeSynchronize>`` element."""
        return dict(self._element.attrib)

    def __repr__(self) -> str:
        """Return a concise representation including PTP enable state."""
        return f"TimeSynchronize(PTPEnable={self.ptp_enable})"


class EthernetPort(BaseElement):
    """One ``<EthernetPort>`` under the controller's ``<EthernetPorts>``.

    Attributes:
        port: Integer port number.
        label: Port label (e.g. ``"A1"``).
        port_enabled: Whether the port is enabled.

    Args:
        element: The ``<EthernetPort>`` element from a parsed L5X tree.
    """

    _KNOWN_KEYS: frozenset[str] = frozenset({"Port", "Label", "PortEnabled"})

    @property
    def port(self) -> int | None:
        """Integer port number."""
        return _parse_int(self._get("Port"))

    @property
    def label(self) -> str:
        """Port label (e.g. ``"A1"``)."""
        return self._get("Label")

    @property
    def port_enabled(self) -> bool:
        """Whether the port is enabled."""
        return self._get("PortEnabled") == "true"

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v for k, v in self._element.attrib.items() if k not in self._KNOWN_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<EthernetPort>`` element."""
        return dict(self._element.attrib)

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

    @property
    def name(self) -> str:
        """Controller name.

        Returns:
            The value of the ``Name`` XML attribute.
        """
        return self._get("Name")

    @property
    def use(self) -> str:
        """Export target role.

        Common values include ``"Target"`` and ``"Source"``.

        Returns:
            The value of the ``Use`` XML attribute.
        """
        return self._get("Use")

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
        return self._get("Use") == "Context"

    @property
    def processor_type(self) -> str | None:
        """Processor catalog number.

        Returns ``None`` for context controllers (component exports) where
        this attribute is not present.

        Returns:
            The catalog number string (e.g. ``"5069-L306ERM"``), or ``None``.
        """
        return self._element.get("ProcessorType")

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------

    @property
    def major_rev(self) -> str | None:
        """Major firmware revision.

        Returns ``None`` for context controllers (component exports) where
        this attribute is not present.

        Returns:
            The value of the ``MajorRev`` XML attribute, or ``None``.
        """
        return self._element.get("MajorRev")

    @property
    def minor_rev(self) -> str | None:
        """Minor firmware revision.

        Returns ``None`` for context controllers (component exports) where
        this attribute is not present.

        Returns:
            The value of the ``MinorRev`` XML attribute, or ``None``.
        """
        return self._element.get("MinorRev")

    # ------------------------------------------------------------------
    # Dates / identifiers
    # ------------------------------------------------------------------

    @property
    def project_creation_date(self) -> str | None:
        """Date string when the project was first created.

        Returns ``None`` for context controllers (component exports) where
        this attribute is not present.

        Returns:
            The value of the ``ProjectCreationDate`` XML attribute, or ``None``.
        """
        return self._element.get("ProjectCreationDate")

    @property
    def last_modified_date(self) -> str | None:
        """Date string when the project was last saved.

        Returns ``None`` for context controllers (component exports) where
        this attribute is not present.

        Returns:
            The value of the ``LastModifiedDate`` XML attribute, or ``None``.
        """
        return self._element.get("LastModifiedDate")

    @property
    def project_sn(self) -> str | None:
        """Project serial number.

        Returns ``None`` for context controllers (component exports) where
        this attribute is not present.

        Returns:
            The value of the ``ProjectSN`` XML attribute, or ``None``.
        """
        return self._element.get("ProjectSN")

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
    # Unrecognised attributes
    # ------------------------------------------------------------------

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Keys are the original XML attribute names (e.g.
        ``"SFCExecutionControl"``) so they can be cross-referenced directly
        against the Rockwell L5X export manual.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v for k, v in self._element.attrib.items() if k not in _KNOWN_XML_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on the ``<Controller>`` element.

        Unlike :attr:`extra_attributes`, this returns *every* attribute
        including the ones exposed as explicit properties (``Name``,
        ``ProcessorType``, etc.), so it can be used for serialization
        or full cross-referencing against the Rockwell L5X export manual.

        Returns:
            Dictionary mapping every XML attribute name to its string value.
        """
        return dict(self._element.attrib)

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

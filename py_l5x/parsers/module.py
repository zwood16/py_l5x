"""Module and I/O connection parsing.

This module parses ``<Modules>`` in an L5X controller export and exposes:

- ``ModulesCollection``: mapping of module name -> ``Module``.
- ``Module``: one module's identity, ports, communications, and metadata.
- ``PortsView`` / ``Port``: mapping of port id -> port metadata.
- ``Communications`` / ``Connection``: connection-level I/O metadata.
- ``ConfigTag`` / ``InputTag`` / ``OutputTag``: tag-like ``<Data>`` wrappers
  for module communication payloads.

Tag-like value parsing reuses :class:`py_l5x.parsers.tag.TagNode` so nested
structures and arrays behave the same way as controller/program tags.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import BaseCollection, BaseElement
from py_l5x.parsers.tag import TagNode, TypeRegistry, _build_node, _TagOverrides

_MODULE_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {
        "Name",
        "CatalogNumber",
        "Vendor",
        "ProductType",
        "ProductCode",
        "Major",
        "Minor",
        "ParentModule",
        "ParentModPortId",
        "Inhibited",
        "MajorFault",
        "SafetyEnabled",
        "AutoDiagsEnabled",
        "DataExchangeId",
    }
)

_COMM_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {"CommMethod", "PrimCxnInputSize", "PrimCxnOutputSize"}
)

_CONNECTION_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {
        "Name",
        "RPI",
        "Type",
        "InputCxnPoint",
        "OutputCxnPoint",
        "OutputSize",
        "InputSize",
        "EventID",
        "ProgrammaticallySendEventTrigger",
        "Priority",
        "InputConnectionType",
        "InputProductionTrigger",
        "ConnectionPath",
        "InputTagSuffix",
        "OutputTagSuffix",
        "Unicast",
    }
)

_MODULE_DATA_TAG_BASE_KEYS: frozenset[str] = frozenset(
    {"ExternalAccess", "OpcUaAccess"}
)
_CONFIG_TAG_KNOWN_XML_KEYS: frozenset[str] = _MODULE_DATA_TAG_BASE_KEYS | frozenset(
    {"ConfigSize"}
)

_PORT_KNOWN_XML_KEYS: frozenset[str] = frozenset({"Id", "Address", "Type", "Upstream"})


def _parse_int(value: str) -> int | None:
    """Parse an int attribute; return ``None`` for empty/unparseable values.

    Args:
        value: The string value to parse.

    Returns:
        The parsed integer, or None if the value is empty or not a valid integer.
    """
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_bool(value: str) -> bool:
    """Parse Rockwell-style bool attributes (``"true"``/``"false"``).

    Args:
        value: The string value to parse.

    Returns:
        True if the value is "true", False otherwise.
    """
    return value == "true"


class Port(BaseElement):
    """One ``<Port>`` under a module's ``<Ports>`` section.

    Attributes:
        id (int): Port id as an integer.
        address (str): Port address string (slot, IP, etc.).
        type (str): Port type string (for example ``"5069"`` or ``"Ethernet"``).
        upstream (bool): Whether this port is marked as upstream.
        bus_size (int | None): Bus size from ``<Bus Size="...">`` when present.
    """

    @property
    def id(self) -> int:
        """Port id as an integer."""
        return int(self._get("Id"))

    @property
    def address(self) -> str:
        """Port address string (slot, IP, etc.)."""
        return self._get("Address")

    @property
    def type(self) -> str:
        """Port type string (for example ``"5069"`` or ``"Ethernet"``)."""
        return self._get("Type")

    @property
    def upstream(self) -> bool:
        """Whether this port is marked as upstream."""
        return _parse_bool(self._get("Upstream"))

    @property
    def bus_size(self) -> int | None:
        """Bus size from ``<Bus Size="...">`` when present."""
        bus = self._element.find("Bus")
        if bus is None:
            return None
        return _parse_int(bus.get("Size", ""))

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _PORT_KNOWN_XML_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<Port>`` element."""
        return dict(self._element.attrib)

    def __repr__(self) -> str:
        return f"Port({self.id}, {self.type!r})"


class PortsView(Mapping[int, Port]):
    """Live mapping of module ports keyed by integer port id.

    Args:
        module_element (ET.Element): The XML element for the module.
    """

    def __init__(self, module_element: ET.Element) -> None:
        """Initialize a live view over a module's ``<Ports>`` collection.

        Args:
            module_element: The XML element for the owning module.
        """
        self._module_element = module_element

    def _children(self) -> list[ET.Element]:
        """Return direct ``<Port>`` child elements.

        Returns:
            A list of ``<Port>`` elements, or an empty list when absent.
        """
        ports_el = self._module_element.find("Ports")
        if ports_el is None:
            return []
        return ports_el.findall("Port")

    def __getitem__(self, port_id: int) -> Port:
        """Get a port by integer id.

        Args:
            port_id: The integer ``Id`` attribute of the target port.

        Returns:
            The matching wrapped ``Port``.

        Raises:
            KeyError: If no port with the requested id exists.
        """
        for el in self._children():
            raw_id = el.get("Id", "")
            if _parse_int(raw_id) == port_id:
                return Port(el)
        raise KeyError(port_id)

    def __iter__(self) -> Iterator[int]:
        """Iterate available integer port ids.

        Yields:
            Parsed integer port ids for ports with valid ``Id`` values.
        """
        for el in self._children():
            raw_id = el.get("Id", "")
            parsed = _parse_int(raw_id)
            if parsed is not None:
                yield parsed

    def __len__(self) -> int:
        """Return number of ports with parseable integer ids.

        Returns:
            The count of valid port ids yielded by ``__iter__``.
        """
        return sum(1 for _ in self.__iter__())

    def __repr__(self) -> str:
        """Return a debug-friendly representation of this ports view.

        Returns:
            A representation containing the currently visible port ids.
        """
        return f"PortsView({list(self)!r})"


class ModuleDataTag(BaseElement):
    """Base wrapper for ``ConfigTag``/``InputTag``/``OutputTag`` data sections.

    Args:
        element (ET.Element): The XML element to wrap.
        type_registry (TypeRegistry): The type registry used for parsing tag values.
    """

    _KNOWN_KEYS: frozenset[str] = _MODULE_DATA_TAG_BASE_KEYS

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry
        self._overrides = _TagOverrides(element)

    @property
    def external_access(self) -> str:
        """External access level for this tag-like section."""
        return self._get("ExternalAccess")

    @property
    def data(self) -> TagNode | None:
        """Root value-tree node parsed from ``Data Format=\"Decorated\"``."""
        decorated = self._element.find("Data[@Format='Decorated']")
        if decorated is None:
            return None
        child = next(iter(decorated), None)
        if child is None:
            return None
        return _build_node(child, None, self._overrides, "", self._type_registry)

    @property
    def value(self) -> int | float | str | bool | None:
        """Shortcut for scalar roots: ``self.data.value``."""
        node = self.data
        return node.value if node is not None else None

    @property
    def members(self) -> Mapping[str, TagNode]:
        """Shortcut for structured roots: ``self.data.members``."""
        node = self.data
        return node.members if node is not None else {}

    @property
    def elements(self) -> Sequence[TagNode]:
        """Array-element shortcut with ``.Data`` member fallback.

        Many module payloads are ``Structure`` roots whose only meaningful
        payload is an ``ArrayMember Name=\"Data\"``. Expose that array as a
        convenience via ``.elements``.
        """
        node = self.data
        if node is None:
            return []
        if node.kind == "array":
            return node.elements
        if node.kind == "structure" and "Data" in node.members:
            data_member = node.members["Data"]
            if data_member.kind == "array":
                return data_member.elements
        return []

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v for k, v in self._element.attrib.items() if k not in self._KNOWN_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this tag-like element."""
        return dict(self._element.attrib)


class ConfigTag(ModuleDataTag):
    """``<ConfigTag>`` under a module ``<Communications>`` element.

    Attributes:
        config_size (int | None): Configured byte size of this config payload.
    """

    _KNOWN_KEYS: frozenset[str] = _CONFIG_TAG_KNOWN_XML_KEYS

    @property
    def config_size(self) -> int | None:
        """Configured byte size of this config payload."""
        return _parse_int(self._get("ConfigSize"))

    @property
    def data(self) -> TagNode | None:
        """Root value-tree node for config data.

        Generic ethernet module config payloads are often wrapped as:

        ``Structure -> ArrayMember(Name=\"Data\")``

        For that shape, expose the ``Data`` array as the logical root.
        """
        node = super().data
        if node is None:
            return None
        if node.kind == "structure" and "Data" in node.members:
            data_member = node.members["Data"]
            if data_member.kind == "array":
                return data_member
        return node

    def __repr__(self) -> str:
        return (
            "ConfigTag("
            f"ExternalAccess={self.external_access!r}, "
            f"ConfigSize={self.config_size!r}"
            ")"
        )


class InputTag(ModuleDataTag):
    """``<InputTag>`` under a module ``<Connection>`` element."""

    def __repr__(self) -> str:
        return f"InputTag(ExternalAccess={self.external_access!r})"


class OutputTag(ModuleDataTag):
    """``<OutputTag>`` under a module ``<Connection>`` element."""

    def __repr__(self) -> str:
        return f"OutputTag(ExternalAccess={self.external_access!r})"


class Connection(BaseElement):
    """One ``<Connection>`` under ``Communications/Connections``.

    Args:
        element (ET.Element): The XML element to wrap.
        type_registry (TypeRegistry): The type registry used for parsing tag values.
    """

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry

    @property
    def name(self) -> str:
        """Connection name from the ``Name`` attribute."""
        return self._get("Name")

    @property
    def rpi(self) -> int | None:
        """Requested Packet Interval (RPI) in milliseconds when available."""
        return _parse_int(self._get("RPI"))

    @property
    def type(self) -> str:
        """Connection type string from the ``Type`` attribute."""
        return self._get("Type")

    @property
    def input_cxn_point(self) -> int | None:
        """Input connection point number when present."""
        return _parse_int(self._get("InputCxnPoint"))

    @property
    def output_cxn_point(self) -> int | None:
        """Output connection point number when present."""
        return _parse_int(self._get("OutputCxnPoint"))

    @property
    def input_size(self) -> int | None:
        """Configured input payload size in bytes when present."""
        return _parse_int(self._get("InputSize"))

    @property
    def output_size(self) -> int | None:
        """Configured output payload size in bytes when present."""
        return _parse_int(self._get("OutputSize"))

    @property
    def event_id(self) -> int | None:
        """Event trigger id when event-based messaging is configured."""
        return _parse_int(self._get("EventID"))

    @property
    def programmatically_send_event_trigger(self) -> bool:
        """Whether event triggers can be sent programmatically."""
        return _parse_bool(self._get("ProgrammaticallySendEventTrigger"))

    @property
    def priority(self) -> str:
        """Connection priority string."""
        return self._get("Priority")

    @property
    def input_connection_type(self) -> str:
        """Input connection type string."""
        return self._get("InputConnectionType")

    @property
    def input_production_trigger(self) -> str:
        """Input production trigger mode string."""
        return self._get("InputProductionTrigger")

    @property
    def connection_path(self) -> str:
        """Backplane/network connection path string."""
        return self._get("ConnectionPath")

    @property
    def input_tag_suffix(self) -> str:
        """Input tag suffix used by generated module tags."""
        return self._get("InputTagSuffix")

    @property
    def output_tag_suffix(self) -> str:
        """Output tag suffix used by generated module tags."""
        return self._get("OutputTagSuffix")

    @property
    def unicast(self) -> bool | None:
        """Whether this connection is configured for unicast traffic.

        Returns:
            True or False when specified; None if the attribute is missing.
        """
        raw = self._get("Unicast")
        if raw == "":
            return None
        return _parse_bool(raw)

    @property
    def input_tag(self) -> InputTag | None:
        """Parse and return the optional ``<InputTag>`` section.

        Returns:
            The wrapped input tag section when present, otherwise None.
        """
        el = self._element.find("InputTag")
        if el is None:
            return None
        return InputTag(el, self._type_registry)

    @property
    def output_tag(self) -> OutputTag | None:
        """Parse and return the optional ``<OutputTag>`` section.

        Returns:
            The wrapped output tag section when present, otherwise None.
        """
        el = self._element.find("OutputTag")
        if el is None:
            return None
        return OutputTag(el, self._type_registry)

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _CONNECTION_KNOWN_XML_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<Connection>`` element."""
        return dict(self._element.attrib)

    def __repr__(self) -> str:
        """Return a concise debug representation for this connection."""
        return f"Connection({self.name!r}, {self.type!r})"


class ConnectionsCollection(BaseCollection[Connection]):
    """Mapping of connection name -> ``Connection`` for a comms section.

    Args:
        comm_element (ET.Element): The XML element containing the connections.
        type_registry (TypeRegistry): The type registry used for parsing tag values.
    """

    def __init__(self, comm_element: ET.Element, type_registry: TypeRegistry) -> None:
        """Initialize a mapping over ``Communications/Connections/Connection``.

        Args:
            comm_element: The ``<Communications>`` XML element.
            type_registry: Registry used for nested input/output tag parsing.
        """
        super().__init__(
            comm_element,
            "Connections/Connection",
            Connection,
            item_args=(type_registry,),
        )


class Communications(BaseElement):
    """The ``<Communications>`` section of a module.

    Args:
        element (ET.Element): The XML element to wrap.
        type_registry (TypeRegistry): The type registry used for parsing tag values.
    """

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry

    @property
    def comm_method(self) -> str:
        """Primary communications method string."""
        return self._get("CommMethod")

    @property
    def prim_cxn_input_size(self) -> int | None:
        """Primary connection input size in bytes when provided."""
        return _parse_int(self._get("PrimCxnInputSize"))

    @property
    def prim_cxn_output_size(self) -> int | None:
        """Primary connection output size in bytes when provided."""
        return _parse_int(self._get("PrimCxnOutputSize"))

    @property
    def config_tag(self) -> ConfigTag | None:
        """Return the optional module-level ``<ConfigTag>`` payload.

        Returns:
            The wrapped config tag when present, otherwise None.
        """
        el = self._element.find("ConfigTag")
        if el is None:
            return None
        return ConfigTag(el, self._type_registry)

    @property
    def connections(self) -> ConnectionsCollection:
        """Return live mapping of connection name to ``Connection``."""
        return ConnectionsCollection(self._element, self._type_registry)

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _COMM_KNOWN_XML_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<Communications>`` element."""
        return dict(self._element.attrib)

    def __repr__(self) -> str:
        """Return a concise debug representation for communications settings."""
        return f"Communications(CommMethod={self.comm_method!r})"


class Module(BaseElement):
    """One ``<Module>`` element from ``<Modules>``.

    Args:
        element (ET.Element): The XML element to wrap.
        type_registry (TypeRegistry): The type registry used for parsing tag values.
    """

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry

    @property
    def name(self) -> str:
        """Module name from the ``Name`` attribute."""
        return self._get("Name")

    @property
    def description(self) -> str:
        """CDATA description text from the module ``Description`` element."""
        return self._get_description()

    @property
    def catalog_number(self) -> str:
        """Catalog number string for this module."""
        return self._get("CatalogNumber")

    @property
    def vendor(self) -> str:
        """Vendor identifier as exported by Studio 5000."""
        return self._get("Vendor")

    @property
    def product_type(self) -> str:
        """Product type code string."""
        return self._get("ProductType")

    @property
    def product_code(self) -> str:
        """Product code string."""
        return self._get("ProductCode")

    @property
    def major(self) -> str:
        """Major revision string."""
        return self._get("Major")

    @property
    def minor(self) -> str:
        """Minor revision string."""
        return self._get("Minor")

    @property
    def parent_module(self) -> str:
        """Parent module name for nested modules, when present."""
        return self._get("ParentModule")

    @property
    def parent_mod_port_id(self) -> str:
        """Parent module port id used for nested module attachments."""
        return self._get("ParentModPortId")

    @property
    def inhibited(self) -> bool:
        """Whether the module is inhibited."""
        return _parse_bool(self._get("Inhibited"))

    @property
    def major_fault(self) -> bool:
        """Whether the module currently reports a major fault."""
        return _parse_bool(self._get("MajorFault"))

    @property
    def safety_enabled(self) -> bool | None:
        """Whether safety mode is enabled, if the attribute exists.

        Returns:
            True or False when specified; None when not present.
        """
        raw = self._get("SafetyEnabled")
        if raw == "":
            return None
        return _parse_bool(raw)

    @property
    def auto_diags_enabled(self) -> bool | None:
        """Whether auto diagnostics are enabled, if the attribute exists.

        Returns:
            True or False when specified; None when not present.
        """
        raw = self._get("AutoDiagsEnabled")
        if raw == "":
            return None
        return _parse_bool(raw)

    @property
    def data_exchange_id(self) -> str | None:
        """Optional data exchange id for data-sharing features."""
        raw = self._get("DataExchangeId")
        return raw if raw else None

    @property
    def ekey_state(self) -> str:
        """Electronic keying state from the nested ``<EKey>`` element."""
        ekey = self._element.find("EKey")
        if ekey is None:
            return ""
        return ekey.get("State", "")

    @property
    def ports(self) -> PortsView:
        """Live mapping of integer port id to ``Port`` wrapper."""
        return PortsView(self._element)

    @property
    def communications(self) -> Communications | None:
        """Optional wrapped ``<Communications>`` section for this module."""
        el = self._element.find("Communications")
        if el is None:
            return None
        return Communications(el, self._type_registry)

    @property
    def extended_properties_xml(self) -> str | None:
        """Serialized XML string for the ``<ExtendedProperties>`` block.

        Returns:
            Unicode XML string when the block exists, otherwise None.
        """
        el = self._element.find("ExtendedProperties")
        if el is None:
            return None
        return ET.tostring(el, encoding="unicode")

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _MODULE_KNOWN_XML_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this ``<Module>`` element."""
        return dict(self._element.attrib)

    def __repr__(self) -> str:
        """Return a concise debug representation for this module."""
        return f"Module({self.name!r}, {self.catalog_number!r})"


class ModulesCollection(BaseCollection[Module]):
    """Mapping of module name -> ``Module`` from a controller element.

    Args:
        controller_element (ET.Element): The XML element containing the modules.
        type_registry (TypeRegistry): The type registry used for parsing tag values.
    """

    def __init__(
        self, controller_element: ET.Element, type_registry: TypeRegistry
    ) -> None:
        """Initialize a mapping over ``Modules/Module`` entries.

        Args:
            controller_element: The top-level controller XML element.
            type_registry: Registry used for module communication payload parsing.
        """
        super().__init__(
            controller_element,
            "Modules/Module",
            Module,
            item_args=(type_registry,),
        )

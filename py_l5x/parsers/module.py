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

from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    bool_attr,
    int_attr,
    str_attr,
)
from py_l5x.parsers.tag import TagNode, TypeRegistry, _build_node, _TagOverrides


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


class Port(BaseElement):
    """One ``<Port>`` under a module's ``<Ports>`` section.

    Args:
        element: The ``<Port>`` XML element to wrap.
    """

    id = int_attr("Id", doc="Port id as an integer.")
    address = str_attr("Address", doc="Port address string (slot, IP, etc.).")
    type = str_attr("Type", doc='Port type string (for example "5069" or "Ethernet").')
    upstream = bool_attr(
        "Upstream", default=False, doc="Whether this port is marked as upstream."
    )

    @property
    def bus_size(self) -> int | None:
        """Bus size from ``<Bus Size="...">`` when present."""
        bus = self._element.find("Bus")
        if bus is None:
            return None
        return _parse_int(bus.get("Size", ""))

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

    external_access = str_attr(
        "ExternalAccess", doc="External access level for this tag-like section."
    )
    opc_ua_access = str_attr("OpcUaAccess", doc="OPC UA exposure level, if configured.")

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry
        self._overrides = _TagOverrides(element)

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


class ConfigTag(ModuleDataTag):
    """``<ConfigTag>`` under a module ``<Communications>`` element.

    Args:
        element: The ``<ConfigTag>`` XML element to wrap.
        type_registry: The type registry used for parsing tag values.
    """

    config_size = int_attr(
        "ConfigSize", doc="Configured byte size of this config payload."
    )

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

    name = str_attr("Name", doc="Connection name.")
    rpi = int_attr(
        "RPI", doc="Requested Packet Interval (RPI) in milliseconds when available."
    )
    type = str_attr("Type", doc="Connection type string.")
    input_cxn_point = int_attr(
        "InputCxnPoint", doc="Input connection point number when present."
    )
    output_cxn_point = int_attr(
        "OutputCxnPoint", doc="Output connection point number when present."
    )
    input_size = int_attr(
        "InputSize", doc="Configured input payload size in bytes when present."
    )
    output_size = int_attr(
        "OutputSize", doc="Configured output payload size in bytes when present."
    )
    event_id = int_attr(
        "EventID", doc="Event trigger id when event-based messaging is configured."
    )
    programmatically_send_event_trigger = bool_attr(
        "ProgrammaticallySendEventTrigger",
        default=False,
        doc="Whether event triggers can be sent programmatically.",
    )
    priority = str_attr("Priority", doc="Connection priority string.")
    input_connection_type = str_attr(
        "InputConnectionType", doc="Input connection type string."
    )
    input_production_trigger = str_attr(
        "InputProductionTrigger", doc="Input production trigger mode string."
    )
    connection_path = str_attr(
        "ConnectionPath", doc="Backplane/network connection path string."
    )
    input_tag_suffix = str_attr(
        "InputTagSuffix", doc="Input tag suffix used by generated module tags."
    )
    output_tag_suffix = str_attr(
        "OutputTagSuffix", doc="Output tag suffix used by generated module tags."
    )
    unicast = bool_attr(
        "Unicast", doc="Whether this connection is configured for unicast traffic."
    )

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry

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

    comm_method = str_attr("CommMethod", doc="Primary communications method string.")
    prim_cxn_input_size = int_attr(
        "PrimCxnInputSize", doc="Primary connection input size in bytes when provided."
    )
    prim_cxn_output_size = int_attr(
        "PrimCxnOutputSize",
        doc="Primary connection output size in bytes when provided.",
    )

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry

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

    def __repr__(self) -> str:
        """Return a concise debug representation for communications settings."""
        return f"Communications(CommMethod={self.comm_method!r})"


class Module(BaseElement):
    """One ``<Module>`` element from ``<Modules>``.

    Args:
        element (ET.Element): The XML element to wrap.
        type_registry (TypeRegistry): The type registry used for parsing tag values.
    """

    name = str_attr("Name", doc="Module name.")
    description = CDataField(
        "Description", doc="CDATA description text from the module Description element."
    )
    catalog_number = str_attr(
        "CatalogNumber", doc="Catalog number string for this module."
    )
    vendor = str_attr("Vendor", doc="Vendor identifier as exported by Studio 5000.")
    product_type = str_attr("ProductType", doc="Product type code string.")
    product_code = str_attr("ProductCode", doc="Product code string.")
    major = str_attr("Major", doc="Major revision string.")
    minor = str_attr("Minor", doc="Minor revision string.")
    parent_module = str_attr(
        "ParentModule", doc="Parent module name for nested modules, when present."
    )
    parent_mod_port_id = str_attr(
        "ParentModPortId",
        doc="Parent module port id used for nested module attachments.",
    )
    inhibited = bool_attr(
        "Inhibited", default=False, doc="Whether the module is inhibited."
    )
    major_fault = bool_attr(
        "MajorFault",
        default=False,
        doc="Whether the module currently reports a major fault.",
    )
    safety_enabled = bool_attr(
        "SafetyEnabled", doc="Whether safety mode is enabled, if the attribute exists."
    )
    auto_diags_enabled = bool_attr(
        "AutoDiagsEnabled",
        doc="Whether auto diagnostics are enabled, if the attribute exists.",
    )

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry

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

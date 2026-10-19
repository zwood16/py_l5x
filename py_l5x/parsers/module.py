"""Module and I/O connection parsing.

This module parses ``<Modules>`` in an L5X controller export and exposes:

- ``ModulesCollection``: mapping of module name -> ``Module``.
- ``Module``: one module's identity, ports, communications, and metadata.
- ``PortsView`` / ``Port``: mapping of port id -> port metadata.
- ``Communications`` / ``Connection``: connection-level I/O metadata.
- ``ConfigTag`` / ``InputTag`` / ``OutputTag``: tag-like ``<Data>`` wrappers
  for module communication payloads. Unlike controller/program tags, these keep
  a ``.data`` property pointing to the structured node (typically a
  ``StructNode`` or ``ArrayNode`` with a single member). Access members via
  ``.data.members[...]`` or ``.data.elements[...]``.
- ``Module.tags`` / ``ModuleTagsView`` / ``ModuleTagRef``: a live view of a
  module's I/O tags keyed by their Studio 5000 *global variable* names (for
  example ``ValveBank:I``, ``Local:1:C``). Each :class:`ModuleTagRef` is a thin
  reference to the underlying tag with back-references to the owning
  :class:`Module` and :class:`Connection`.

Tag-like value parsing reuses :class:`py_l5x.parsers.tag.TagNode` so nested
structures and arrays behave the same way as controller/program tag nodes.

Global-name convention and known limitation
--------------------------------------------
In Studio 5000 a module's communication tags surface as *global variables*.
Remote modules are named after the module (``ValveBank:I``); modules on the
local backplane are addressed by position (``Local:1:I``). ``Module.tag_prefix``
implements this rule, and :class:`ModuleTagsView` builds each name as
``<tag_prefix>:<suffix>`` where the suffix comes from the connection's
``InputTagSuffix``/``OutputTagSuffix`` when present, else is derived from the
tag's root data type (the second-to-last colon segment), falling back to ``I``/
``O``, or is ``C`` for a config tag.

Known limitation: Studio 5000 does *not* generate tags for servo-drive
connections unless they carry a safety connection. The view applies the general
suffix rule uniformly, so a non-safety servo-drive connection would still be
reported here even though Studio would not surface it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    bool_attr,
    int_attr,
    str_attr,
)
from py_l5x.parsers.tag import (
    ArrayNode,
    StringNode,
    StructNode,
    TagNode,
    TypeRegistry,
    _build_node,
    _TagOverrides,
)


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


def _suffix_from_data_type(data_type: str) -> str | None:
    """Derive a Studio 5000 global-tag suffix from a module tag data type.

    Module tag data types encode their global-name suffix as the second-to-last
    colon-separated segment -- for example ``AB:Motion_Diagnostics:S:1`` ->
    ``S``, or ``AB:5000_DI16:C:0`` -> ``C``.

    Args:
        data_type: The root node's data type string.

    Returns:
        The derived suffix, or None when the data type has fewer than two
        colon-separated segments (no usable suffix).
    """
    parts = data_type.split(":")
    if len(parts) < 2:
        return None
    suffix = parts[-2]
    return suffix or None


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
    def root_data_type(self) -> str:
        """``DataType`` attribute of the raw root decorated value node.

        Unlike :attr:`data` (which may unwrap a config payload's ``Data`` array),
        this reads the ``DataType`` directly off the first child of
        ``<Data Format="Decorated">`` -- typically the root ``Structure``. Module
        tag data types encode their Studio 5000 global-name suffix as the
        second-to-last colon-separated segment (for example
        ``AB:Motion_Diagnostics:S:1`` -> ``S``), so this is the source used to
        derive a tag suffix when the connection omits an explicit suffix.

        Returns:
            The root node's data type string, or ``""`` when absent.
        """
        decorated = self._element.find("Data[@Format='Decorated']")
        if decorated is None:
            return ""
        child = next(iter(decorated), None)
        if child is None:
            return ""
        return child.get("DataType", "") or ""


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
        if isinstance(node, StructNode) and "Data" in node.members:
            data_member = node.members["Data"]
            if isinstance(data_member, ArrayNode):
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

    data_exchange_id = str_attr(
        "DataExchangeId",
        default=None,
        doc="Optional data exchange id for data-sharing features.",
    )

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
    def tag_prefix(self) -> str:
        """Prefix used in this module's Studio 5000 global tag names.

        In Studio 5000, module I/O tags surface as *global variables*. Remote
        modules are named after the module itself (for example ``ValveBank:I``),
        while modules mounted on the local backplane are addressed by position
        (for example ``Local:1:I``).

        A module is treated as a local backplane module when its upstream port
        (``Upstream="true"``) has a ``5069`` backplane type; its position is that
        port's address. Remote modules (Ethernet upstream, or any non-backplane
        upstream port) use their own name.

        Returns:
            The global-name prefix, e.g. ``"ValveBank"`` or ``"Local:1"``.
        """
        upstream_address = ""
        is_local_backplane = False
        for port in self.ports.values():
            if port.upstream:
                is_local_backplane = port.type == "5069"
                upstream_address = port.address or ""
                break
        if not is_local_backplane:
            return self.name
        if upstream_address:
            return f"Local:{upstream_address}"
        # No usable address on the upstream backplane port; fall back to the
        # parent-module port id (the slot the module occupies on the chassis).
        if self.parent_mod_port_id:
            return f"Local:{self.parent_mod_port_id}"
        return "Local"

    @property
    def tags(self) -> ModuleTagsView:
        """Live mapping of this module's I/O tags keyed by global tag name.

        See :class:`ModuleTagsView` for the naming convention and the known
        servo-drive limitation. Modules without tag-bearing communication
        sections yield an empty view.
        """
        return ModuleTagsView(self)

    def __repr__(self) -> str:
        """Return a concise debug representation for this module."""
        return f"Module({self.name!r}, {self.catalog_number!r})"


class ModuleTagRef:
    """A reference to one module I/O tag under its Studio 5000 global name.

    In Studio 5000, the tags a module exposes for its communication payloads
    (``<ConfigTag>``, ``<InputTag>``, ``<OutputTag>``) appear as *global
    variables* with names such as ``ValveBank:I``, ``Local:1:C``, or
    ``Test_Servo_Drive:SI``. This class wraps the underlying :class:`ModuleDataTag`
    and surfaces it under that global name, while keeping the module as the
    single source of truth.

    It is intentionally *not* a subclass of :class:`py_l5x.parsers.tag.Tag`:
    module tags wrap a :class:`ModuleDataTag`, which has a different shape than a
    controller/program tag. Instead it exposes a small set of identity
    properties (``name``, ``kind``, ``module_name``, ``data_type``) plus
    back-references to the owning :class:`Module` and (for connection tags)
    :class:`Connection`, delegates :attr:`data` to the wrapped tag, and forwards
    any other attribute access (e.g. helpers living on the wrapped tag) via
    ``__getattr__``.

    Args:
        name: The Studio 5000 global tag name (for example ``"ValveBank:I"``).
        kind: The tag suffix/kind, e.g. ``"C"``, ``"I"``, ``"O"``.
        module: The owning :class:`Module`.
        connection: The owning :class:`Connection`, or ``None`` for config tags.
        wrapped_tag: The underlying :class:`ModuleDataTag` this ref points at.
    """

    def __init__(
        self,
        name: str,
        kind: str,
        module: Module,
        connection: Connection | None,
        wrapped_tag: ModuleDataTag,
    ) -> None:
        """Initialize a reference to a module tag under its global name.

        Args:
            name: The Studio 5000 global tag name (for example ``"ValveBank:I"``).
            kind: The tag suffix/kind, e.g. ``"C"``, ``"I"``, ``"O"``.
            module: The owning :class:`Module`.
            connection: The owning :class:`Connection`, or ``None`` for config tags.
            wrapped_tag: The underlying :class:`ModuleDataTag` this ref points at.
        """
        self._name = name
        self._kind = kind
        self._module = module
        self._connection = connection
        self._wrapped = wrapped_tag

    @property
    def name(self) -> str:
        """The Studio 5000 global tag name (e.g. ``"ValveBank:I"``)."""
        return self._name

    @property
    def kind(self) -> str:
        """The tag suffix/kind, e.g. ``"C"``, ``"I"``, ``"O"``."""
        return self._kind

    @property
    def module_name(self) -> str:
        """Name of the owning :class:`Module`."""
        return self._module.name

    @property
    def module(self) -> Module:
        """Back-reference to the owning :class:`Module`."""
        return self._module

    @property
    def connection(self) -> Connection | None:
        """Back-reference to the owning :class:`Connection`.

        Returns:
            The connection this tag belongs to, or ``None`` for config tags.
        """
        return self._connection

    @property
    def data_type(self) -> str:
        """Data type name of the wrapped tag's root value node, if any."""
        data = self.data
        return data.data_type if data is not None else ""

    @property
    def external_access(self) -> str:
        """External access level of the wrapped tag-like section."""
        return self._wrapped.external_access

    @property
    def opc_ua_access(self) -> str:
        """OPC UA exposure level of the wrapped tag-like section."""
        return self._wrapped.opc_ua_access

    @property
    def data(self) -> TagNode | None:
        """Root value-tree node, delegating to the wrapped tag's ``.data``.

        For struct payloads this is a :class:`StructNode`; use
        ``ref.data.members[...]`` or ``ref.data.elements[...]`` to reach nested
        values, mirroring how controller/program tags behave.
        """
        return self._wrapped.data

    def __getattr__(self, item: str):
        """Forward unknown attributes to the wrapped :class:`ModuleDataTag`.

        Only invoked when normal attribute lookup fails, so the properties and
        back-references defined above always take precedence. Underscore-prefixed
        names are never forwarded (this also guards against recursion if a
        private attribute is missing).
        """
        if item.startswith("_"):
            raise AttributeError(item)
        return getattr(self._wrapped, item)

    def __repr__(self) -> str:
        """Return a multi-line summary resembling :class:`py_l5x.parsers.tag.Tag`.

        Shows identity (name, data type), the tag kind, access levels, and --
        for struct/string payloads -- the member names one per line.
        """
        lines = [f"ModuleTagRef({self.name!r}, {self.data_type!r})"]
        lines.append(f"  kind: {self.kind!r}")
        for attr in ("external_access", "opc_ua_access"):
            val = getattr(self, attr)
            if val not in (None, ""):
                lines.append(f"  {attr}: {val!r}")
        data = self.data
        if isinstance(data, (StructNode, StringNode)):
            names = [name for name in data.members]
            if names:
                items = ",\n    ".join(repr(name) for name in names)
                lines.append(f"  members: [\n    {items}\n  ]")
        elif isinstance(data, ArrayNode):
            lines.append(f"  elements: len={len(data)}")
        return "\n".join(lines)


class ModuleTagsView(Mapping[str, ModuleTagRef]):
    """Live mapping of one module's I/O tags keyed by Studio 5000 global name.

    Built from the module's ``<Communications>`` section: the optional
    ``<ConfigTag>`` (suffix ``C``), then each connection's ``<InputTag>`` and
    ``<OutputTag>``. A tag's suffix comes from its connection's
    ``InputTagSuffix``/``OutputTagSuffix`` when present, else is derived from
    the tag's root data type (the second-to-last colon segment, e.g.
    ``AB:Motion_Diagnostics:S:1`` -> ``S``), falling back to ``I``/``O``. Each
    is exposed under ``<tag_prefix>:<suffix>`` (see :meth:`Module.tag_prefix`).

    Known limitation: Studio 5000 does *not* generate tags for servo-drive
    connections unless they carry a safety connection. This view applies the
    general suffix rule uniformly, so a non-safety servo-drive connection would
    still be reported here even though Studio would not surface it.

    Args:
        module (Module): The module whose tags are exposed.
    """

    def __init__(self, module: Module) -> None:
        """Initialize a live view over a single module's tag references.

        Args:
            module: The module whose communication tags are exposed.
        """
        self._module = module

    def _items(self) -> list[ModuleTagRef]:
        """Return the ordered list of tag references for this module.

        Returns:
            A list of :class:`ModuleTagRef` instances (config tag first, then
            each connection's input/output tags). Empty when the module has no
            tag-bearing communication sections or no usable prefix.
        """
        prefix = self._module.tag_prefix
        comms = self._module.communications
        if comms is None or not prefix:
            return []
        refs: list[ModuleTagRef] = []
        config_tag = comms.config_tag
        if config_tag is not None:
            refs.append(
                ModuleTagRef(f"{prefix}:C", "C", self._module, None, config_tag)
            )
        for connection in comms.connections.values():
            input_tag = connection.input_tag
            if input_tag is not None:
                suffix = (
                    connection.input_tag_suffix
                    or _suffix_from_data_type(input_tag.root_data_type)
                    or "I"
                )
                ref_name = f"{prefix}:{suffix}"
                refs.append(
                    ModuleTagRef(ref_name, suffix, self._module, connection, input_tag)
                )
            output_tag = connection.output_tag
            if output_tag is not None:
                suffix = (
                    connection.output_tag_suffix
                    or _suffix_from_data_type(output_tag.root_data_type)
                    or "O"
                )
                ref_name = f"{prefix}:{suffix}"
                refs.append(
                    ModuleTagRef(ref_name, suffix, self._module, connection, output_tag)
                )
        return refs

    def __getitem__(self, name: str) -> ModuleTagRef:
        """Get a tag reference by its global name.

        Args:
            name: The Studio 5000 global tag name (for example ``"ValveBank:I"``).

        Returns:
            The matching :class:`ModuleTagRef`.

        Raises:
            KeyError: If the module has no tag with that name.
        """
        for ref in self._items():
            if ref.name == name:
                return ref
        raise KeyError(name)

    def __iter__(self) -> Iterator[str]:
        """Iterate the global tag names exposed by this module.

        Yields:
            Each unique global tag name, in config-then-connection order.
        """
        seen: set[str] = set()
        for ref in self._items():
            if ref.name not in seen:
                seen.add(ref.name)
                yield ref.name

    def __len__(self) -> int:
        """Return the number of distinct global tag names for this module.

        Returns:
            The count of names yielded by ``__iter__``.
        """
        return sum(1 for _ in self.__iter__())

    def __contains__(self, name: object) -> bool:
        """Return whether the module exposes a tag with the given global name."""
        if not isinstance(name, str):
            return False
        try:
            self[name]
        except KeyError:
            return False
        return True

    def __repr__(self) -> str:
        """Return a debug-friendly representation of this module tags view.

        Returns:
            A representation containing the currently visible tag names.
        """
        return f"ModuleTagsView({list(self)!r})"


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

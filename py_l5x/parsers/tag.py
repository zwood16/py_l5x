"""PLC tag values: nested structure/array drill-down over ``<Tag>`` data.

Logix Designer exports each tag's runtime value as a ``Data`` child in one of
three formats: ``Decorated`` (a ``<DataValue>``, ``<Structure>``, or ``<Array>``
tree mirroring the tag's data type shape), ``String`` (used only for top-level
STRING-family tags, which have no ``Decorated`` section at all), or ``Message``
(``MESSAGE`` type tags, out of scope for value parsing here).

This module walks the ``Decorated``/``String`` shape directly rather than
re-deriving it from the ``<DataType>``/AOI ``<Parameter>`` definitions, since
Logix has already done the work of resolving packed booleans into plain
``BOOL`` members. Those definitions are only consulted for *metadata*
(description, min/max, engineering unit, state text) via :class:`TypeRegistry`.

Tag/member instances can also override that metadata per "operand" path (e.g.
``.A_SINT_WITH_PROPS`` for a UDT member, or ``.1`` for a bit within a plain
DINT tag) via ``<Comments>``, ``<Maxes>``, ``<Mins>``, ``<EngineeringUnits>``,
``<State0s>``, ``<State1s>``, and ``<ExternalLoggings>`` containers on the
``<Tag>`` element. :class:`_TagOverrides` collects these once per tag and
:class:`TagNode` resolves them with priority over the type-definition
metadata.

Every node in a tag's value tree -- scalar, structure, or array -- is a
:class:`TagNode`. Its ``kind`` attribute says which of ``.value``
(scalars), ``.members`` (structures), or ``.elements`` (arrays) is
meaningful, so autocomplete never degrades while drilling down through
nested UDTs/AOIs/arrays.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    XmlAttrMixin,
    bool_attr,
    float_attr,
    int_attr,
    str_attr,
)
from py_l5x.parsers.datatype import (
    AddOnDataTypeCollection,
    AddOnParameter,
    DataTypeMember,
    DataTypesCollection,
)
from py_l5x.parsers.specialty_tags import (
    AxisParameters,
    MessageParameters,
    MotionGroupParameters,
)
from py_l5x.parsers.utils import CDATA_TAG, convert_numeric

#: A member/parameter definition used for metadata cross-reference. Both
#: classes expose the same property surface (description/min/max/
#: engineering_unit/state0/state1/radix/external_access).
MemberDef = DataTypeMember | AddOnParameter

#: ``Data`` element ``Format`` values that carry a normal value tree. ``L5K``
#: is a legacy, redundant raw-text mirror of the same data present in the
#: ``Decorated``/``String``/(specialty parameter) sibling and is intentionally
#: ignored throughout this module. Any ``Format`` not in this set (e.g.
#: ``Message``, ``MotionGroup``, ``Axis``, or an unrecognised future format)
#: has no standard value tree -- see :attr:`Tag.special_data_format`/
#: :attr:`Tag.special_data_attributes`.
_VALUE_DATA_FORMATS: frozenset[str] = frozenset({"L5K", "Decorated", "String"})


class TypeRegistry:
    """Resolves a data type name to its member/parameter definitions.

    Checks the UDT ``<DataTypes>`` collection first, then the AOI
    ``<AddOnInstructionDefinitions>`` collection. Built-in system structures
    that appear in neither section (e.g. ``TIMER``, ``COUNTER``, ``MESSAGE``,
    module IO/config structures) resolve to ``None`` -- their values still
    parse correctly, they simply have no cross-referenced metadata.

    Args:
        data_types: The controller's UDT collection.
        aoi_types: The controller's AOI parameter collection.
    """

    def __init__(
        self, data_types: DataTypesCollection, aoi_types: AddOnDataTypeCollection
    ) -> None:
        """Initialise from the controller's UDT and AOI collections.

        Args:
            data_types: The controller's UDT collection.
            aoi_types: The controller's AOI parameter collection.
        """
        self._data_types = data_types
        self._aoi_types = aoi_types

    def resolve_members(self, type_name: str) -> dict[str, MemberDef] | None:
        """Look up the member/parameter definitions for a data type name.

        Args:
            type_name: The ``DataType`` name to resolve (e.g. ``"A_UDT"``,
                ``"GenericInput"``).

        Returns:
            A mapping of member/parameter name to its definition object, or
            ``None`` if *type_name* is not a known UDT or AOI.
        """
        if type_name in self._data_types:
            return self._data_types[type_name].visible_members
        if type_name in self._aoi_types:
            return self._aoi_types[type_name].datatype_members
        return None


# ----------------------------------------------------------------------
# Tag-instance operand overrides
# ----------------------------------------------------------------------

#: Maps each override container's XML tag name to the child element tag name
#: it holds, and the metadata key that override contributes.
_OVERRIDE_CONTAINERS: dict[str, tuple[str, str]] = {
    "Comments": ("Comment", "comment"),
    "Maxes": ("Max", "max"),
    "Mins": ("Min", "min"),
    "EngineeringUnits": ("EngineeringUnit", "engineering_unit"),
    "State0s": ("State0", "state0"),
    "State1s": ("State1", "state1"),
    "ExternalLoggings": ("ExternalLogging", "external_logging"),
}


class _TagOverrides:
    """Per-operand-path metadata overrides collected from a ``<Tag>`` element.

    Rockwell exports operand paths (e.g. ``.A_SINT_WITH_PROPS``, ``.1``) in
    upper case regardless of the actual member's casing, so lookups are
    always matched case-insensitively.

    Args:
        tag_element: The ``<Tag>`` element to scan for override containers.
    """

    def __init__(self, tag_element: ET.Element) -> None:
        """Scan the tag element's override containers into a path -> dict map.

        Args:
            tag_element: The ``<Tag>`` element to scan.
        """
        self._by_path: dict[str, dict[str, str]] = {}
        for container_tag, (child_tag, key) in _OVERRIDE_CONTAINERS.items():
            container = tag_element.find(container_tag)
            if container is None:
                continue
            for child in container.findall(child_tag):
                operand = child.get("Operand", "")
                if not operand:
                    continue
                path = operand.upper()
                cdata_el = child.find(CDATA_TAG)
                if cdata_el is not None and cdata_el.text:
                    text = cdata_el.text.strip()
                elif child.text:
                    text = child.text.strip()
                else:
                    text = ""
                self._by_path.setdefault(path, {})[key] = text

    def get(self, operand_path: str) -> dict[str, str]:
        """Return the override dict for an operand path.

        Args:
            operand_path: The operand path to look up (e.g. ``".1"``,
                ``".A_SINT_WITH_PROPS"``). Matched case-insensitively.

        Returns:
            A dict with whichever of ``comment``/``min``/``max``/
            ``engineering_unit``/``state0``/``state1``/``external_logging``
            were overridden at that path. Empty if none were.
        """
        return self._by_path.get(operand_path.upper(), {})


def _parse_string_literal(text: str) -> str:
    """Strip the single-quote wrapping Logix uses for exported string text.

    Args:
        text: The raw CDATA text (e.g. ``"'SRVO-003'"``).

    Returns:
        The text with a single layer of surrounding single quotes removed,
        or the original text unchanged if it isn't quoted.
    """
    text = text.strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1]
    return text


class _StructureMembers(Mapping):
    """Lazily-resolved ``name -> TagNode`` mapping for a structure node.

    Args:
        node: The owning structure :class:`TagNode`.
    """

    def __init__(self, node: TagNode) -> None:
        """Bind this view to its owning structure node.

        Args:
            node: The owning structure :class:`TagNode`.
        """
        self._node = node

    def __getitem__(self, name: str) -> TagNode:
        """Retrieve a member by name.

        Args:
            name: The member's ``Name`` attribute.

        Returns:
            The member's :class:`TagNode`.

        Raises:
            KeyError: If no member with the given name is found.
        """
        node = self._node
        member_defs = (
            node._type_registry.resolve_members(node.data_type)
            if node._type_registry
            else None
        ) or {}
        for child in node._element:
            if child.get("Name") == name:
                path = f"{node._operand_path}.{name.upper()}"
                return _build_node(
                    child,
                    member_defs.get(name),
                    node._overrides,
                    path,
                    node._type_registry,
                )
        raise KeyError(name)

    def __iter__(self):
        """Iterate over member names in document order."""
        for child in self._node._element:
            name = child.get("Name")
            if name:
                yield name

    def __len__(self) -> int:
        """Return the number of members."""
        return sum(1 for child in self._node._element if child.get("Name"))

    def __repr__(self) -> str:
        """Return a string representation listing member names."""
        return f"members({list(self)!r})"


class _ArrayElements(Sequence):
    """Lazily-resolved ``index -> TagNode`` sequence for an array node.

    Args:
        node: The owning array :class:`TagNode`.
    """

    def __init__(self, node: TagNode) -> None:
        """Bind this view to its owning array node.

        Args:
            node: The owning array :class:`TagNode`.
        """
        self._node = node

    @staticmethod
    def _index_of(element: ET.Element) -> int:
        """Parse an ``<Element Index="[n]">``'s bracketed index as an int."""
        return int(element.get("Index", "").strip("[]"))

    def _els(self) -> list[ET.Element]:
        """Return all ``<Element>`` children in document order."""
        return self._node._element.findall("Element")

    def __getitem__(self, index: int) -> TagNode:
        """Retrieve an element by its zero-based index.

        Args:
            index: The array index.

        Returns:
            A structure-kind :class:`TagNode` for struct-typed elements, or
            a scalar-kind :class:`TagNode` for atomic elements.

        Raises:
            IndexError: If no element with the given index is found.
        """
        node = self._node
        for element in self._els():
            if self._index_of(element) == index:
                path = f"{node._operand_path}[{index}]"
                struct_child = element.find("Structure")
                if struct_child is not None:
                    return TagNode(
                        struct_child,
                        node._member_def,
                        node._overrides,
                        path,
                        node._type_registry,
                    )
                return TagNode(element, node._member_def, node._overrides, path)
        raise IndexError(index)

    def __len__(self) -> int:
        """Return the number of elements."""
        return len(self._els())

    def __repr__(self) -> str:
        """Return a string representation showing the element count."""
        return f"elements(len={len(self)})"


class TagNode(XmlAttrMixin):
    """A single node in a tag's value tree: scalar, structure, or array.

    Every node -- whether the tag's root value or any nested member/element
    reached by drilling down -- is a ``TagNode``. Its :attr:`kind` says which
    of :attr:`value` (scalars), :attr:`members` (structures), or
    :attr:`elements` (arrays) is meaningful; the other two are ``None``/empty.
    Metadata (:attr:`description`, :attr:`min`, :attr:`max`, etc.) is
    available on every node regardless of kind.

    Args:
        element: The XML element this node wraps (``None`` for a bit node,
            which is synthetic).
        member_def: The resolved UDT member or AOI parameter definition for
            this node, if any.
        overrides: The owning tag's collected operand overrides.
        operand_path: This node's operand path (e.g. ``".A_NESTED_UDT.DINT"``),
            used to look up *overrides*.
        type_registry: Used to resolve structure/array children's own member
            definitions. ``None`` for scalar/bit nodes.
        raw_text: Pre-extracted text to use instead of the element's
            ``Value`` attribute (used for CDATA-based string members).
        from_cdata: If ``True``, *raw_text* came from quoted CDATA text (e.g.
            a STRING ``DATA`` member) and should be quote-stripped rather
            than passed through :func:`convert_numeric`.
        is_bit: If ``True``, this is a synthetic bit node (see :meth:`bit`).
        bit_value: The precomputed boolean value for a bit node.
    """

    kind: Literal["scalar", "structure", "array"]
    value: int | float | str | bool | None
    members: Mapping[str, TagNode]
    elements: Sequence[TagNode]

    def __init__(
        self,
        element: ET.Element | None,
        member_def: MemberDef | None,
        overrides: _TagOverrides,
        operand_path: str,
        type_registry: TypeRegistry | None = None,
        *,
        raw_text: str | None = None,
        from_cdata: bool = False,
        is_bit: bool = False,
        bit_value: bool | None = None,
    ) -> None:
        """Initialise a value-tree node and resolve its kind/value/children.

        Args:
            element: The XML element this node wraps, or ``None`` for a bit
                node.
            member_def: The resolved member/parameter definition, or
                ``None``.
            overrides: The owning tag's collected operand overrides.
            operand_path: This node's operand path.
            type_registry: Used to resolve structure/array children.
            raw_text: Pre-extracted text overriding the ``Value`` attribute.
            from_cdata: Whether *raw_text* is quoted CDATA string content.
            is_bit: Whether this is a synthetic bit node.
            bit_value: The precomputed boolean value for a bit node.
        """
        self._element = element
        self._member_def = member_def
        self._overrides = overrides
        self._operand_path = operand_path
        self._type_registry = type_registry
        self._raw_text = raw_text
        self._from_cdata = from_cdata
        self._is_bit = is_bit

        self.members = {}
        self.elements = []

        if is_bit:
            self.kind = "scalar"
            self.value = bit_value
        elif element is not None and element.tag in ("Structure", "StructureMember"):
            self.kind = "structure"
            self.value = None
            self.members = _StructureMembers(self)
        elif element is not None and element.tag in ("Array", "ArrayMember"):
            self.kind = "array"
            self.value = None
            self.elements = _ArrayElements(self)
        else:
            self.kind = "scalar"
            self.value = self._compute_scalar_value()

    def _compute_scalar_value(self) -> int | float | str | bool | None:
        """Resolve this scalar node's value, converted per its data type."""
        text = self._raw_text
        if text is None and self._element is not None:
            text = self._element.get("Value")
        if text is None:
            return None
        if self._from_cdata:
            return _parse_string_literal(text)
        return convert_numeric(text, self.data_type)

    def bit(self, bit_number: int) -> TagNode:
        """Access a single bit of this scalar for override-only metadata.

        This does not require the underlying UDT/AOI to define per-bit
        members -- it exists so plain atomic tags with bit-addressed
        ``Comments``/``EngineeringUnits``/``State0s``/``State1s`` overrides
        (e.g. ``a_commented_dint``) can still expose that metadata, and
        (when this scalar's value is an ``int``) the bit's boolean value.

        Args:
            bit_number: The zero-based bit position.

        Returns:
            A scalar-kind :class:`TagNode` bound to this bit.
        """
        path = f"{self._operand_path}.{bit_number}"
        value = None
        if isinstance(self.value, int):
            value = bool((self.value >> bit_number) & 1)
        return TagNode(None, None, self._overrides, path, is_bit=True, bit_value=value)

    def _override(self, key: str) -> str | None:
        """Return the override value for *key* at this node's operand path."""
        return self._overrides.get(self._operand_path).get(key)

    @property
    def data_type(self) -> str:
        """This node's data type name (always ``"BOOL"`` for a bit node)."""
        if self._is_bit:
            return "BOOL"
        if self._element is not None and self._element.get("DataType"):
            return self._element.get("DataType", "")
        return self._member_def.data_type if self._member_def else ""

    @property
    def radix(self) -> str:
        """This node's display radix, if any."""
        if self._element is not None and self._element.get("Radix"):
            return self._element.get("Radix", "")
        return self._member_def.radix if self._member_def else ""

    @property
    def external_access(self) -> str:
        """This node's external access level, if any."""
        if self._element is not None and self._element.get("ExternalAccess"):
            return self._element.get("ExternalAccess", "")
        return self._member_def.external_access if self._member_def else ""

    @property
    def description(self) -> str:
        """This node's description, from an override or its type definition."""
        override = self._override("comment")
        if override is not None:
            return override
        return self._member_def.description if self._member_def else ""

    @property
    def min(self) -> int | float | str | None:
        """This node's minimum value, from an override or its type definition."""
        override = self._override("min")
        if override is not None:
            return convert_numeric(override, self.data_type)
        return self._member_def.min if self._member_def else None

    @property
    def max(self) -> int | float | str | None:
        """This node's maximum value, from an override or its type definition."""
        override = self._override("max")
        if override is not None:
            return convert_numeric(override, self.data_type)
        return self._member_def.max if self._member_def else None

    @property
    def engineering_unit(self) -> str:
        """This node's engineering unit, from an override or type definition."""
        override = self._override("engineering_unit")
        if override is not None:
            return override
        return self._member_def.engineering_unit if self._member_def else ""

    @property
    def state0(self) -> str:
        """This node's zero-state text, from an override or type definition."""
        override = self._override("state0")
        if override is not None:
            return override
        return self._member_def.state0 if self._member_def else ""

    @property
    def state1(self) -> str:
        """This node's one-state text, from an override or type definition."""
        override = self._override("state1")
        if override is not None:
            return override
        return self._member_def.state1 if self._member_def else ""

    @property
    def external_logging(self) -> bool | None:
        """Whether external logging is enabled, from an override or type def.

        Note:
            ``AddOnParameter`` does not currently expose ``external_logging``,
            so ``getattr`` is used defensively for that member-def type.
        """
        override = self._override("external_logging")
        if override is not None:
            return override == "true"
        return getattr(self._member_def, "external_logging", None)

    def __repr__(self) -> str:
        """Return a detailed representation of the node and its properties."""
        lines = [f"TagNode({self.kind})"]

        props = [
            ("Value", self.value),
            ("DataType", self.data_type),
            ("Radix", self.radix),
            ("ExternalAccess", self.external_access),
            ("Description", self.description),
            ("Min", self.min),
            ("Max", self.max),
            ("EngineeringUnit", self.engineering_unit),
            ("State0", self.state0),
            ("State1", self.state1),
            ("ExternalLogging", self.external_logging),
        ]

        for label, val in props:
            if val is not None and val != "":
                lines.append(f"  {label}: {val!r}")

        if self.kind == "structure":
            lines.append(f"  Members: {list(self.members.keys())}")
        elif self.kind == "array":
            lines.append(f"  Elements: len={len(self.elements)}")

        return "\n".join(lines)


def _build_node(
    element: ET.Element,
    member_def: MemberDef | None,
    overrides: _TagOverrides,
    operand_path: str,
    type_registry: TypeRegistry | None,
) -> TagNode:
    """Dispatch any value-tree element (root or nested) to a :class:`TagNode`.

    Handles both the root element names (``DataValue``/``Structure``/
    ``Array``) and the nested member names (``DataValueMember``/
    ``StructureMember``/``ArrayMember``) identically.

    Args:
        element: The element to build a node for.
        member_def: The resolved member/parameter definition, if any.
        overrides: The owning tag's collected operand overrides.
        operand_path: This node's operand path.
        type_registry: Used by structure/array nodes to resolve their own
            children's member definitions.

    Returns:
        A structure-, array-, or scalar-kind :class:`TagNode` as appropriate.
    """
    if element.tag in ("Array", "ArrayMember"):
        return TagNode(element, member_def, overrides, operand_path, type_registry)
    if element.tag in ("Structure", "StructureMember"):
        return TagNode(element, member_def, overrides, operand_path, type_registry)
    # DataValue/DataValueMember: scalar, either a "Value" attribute or CDATA
    # text (the latter for STRING-family DATA members).
    if element.get("Value") is not None:
        return TagNode(element, member_def, overrides, operand_path)
    cdata_el = element.find(CDATA_TAG)
    if cdata_el is not None and cdata_el.text:
        text = cdata_el.text
    else:
        text = element.text or ""
    return TagNode(
        element, member_def, overrides, operand_path, raw_text=text, from_cdata=True
    )


# ----------------------------------------------------------------------
# Tag facets
# ----------------------------------------------------------------------


class ProduceInfo(BaseElement):
    """``<ProduceInfo>``, present on ``Produced`` tags.

    Args:
        element: The ``<ProduceInfo>`` element from a parsed L5X tree.
    """

    produce_count = int_attr(
        "ProduceCount", doc="Number of consumers this tag is configured to serve."
    )
    programmatically_send_event_trigger = bool_attr(
        "ProgrammaticallySendEventTrigger",
        default=False,
        doc="Whether event triggers can be sent programmatically.",
    )
    unicast_permitted = bool_attr(
        "UnicastPermitted",
        default=False,
        doc="Whether unicast consumer connections are permitted.",
    )
    minimum_rpi = float_attr(
        "MinimumRPI", doc="Minimum allowed Requested Packet Interval, in ms."
    )
    maximum_rpi = float_attr(
        "MaximumRPI", doc="Maximum allowed Requested Packet Interval, in ms."
    )
    default_rpi = float_attr(
        "DefaultRPI", doc="Default Requested Packet Interval, in ms."
    )

    def __repr__(self) -> str:
        return f"ProduceInfo(produce_count={self.produce_count!r})"


class ConsumeInfo(BaseElement):
    """``<ConsumeInfo>``, present on ``Consumed`` tags.

    Args:
        element: The ``<ConsumeInfo>`` element from a parsed L5X tree.
    """

    producer = str_attr("Producer", doc="Name of the producing controller.")
    remote_tag = str_attr(
        "RemoteTag", doc="Name of the produced tag on the remote controller."
    )
    remote_instance = int_attr(
        "RemoteInstance", doc="CIP instance id of the remote produced tag."
    )
    rpi = int_attr("RPI", doc="Requested Packet Interval, in ms.")
    unicast = bool_attr(
        "Unicast", doc="Whether this connection is configured for unicast traffic."
    )

    def __repr__(self) -> str:
        return (
            f"ConsumeInfo(producer={self.producer!r}, remote_tag={self.remote_tag!r})"
        )


class TagExtendedProperties:
    """Studio 5000 "Extended Properties" set directly on a ``<Tag>`` element.

    Bundles the ``Min``/``Max``/``EngineeringUnit``/``State0``/``State1``/
    ``ExternalLogging`` values that Logix allows to be set on the tag itself
    -- separate from the per-member/per-bit operand overrides used for
    nested UDT/AOI members (see :class:`_TagOverrides`). Obtained via
    :attr:`Tag.extended_properties`, which is ``None`` when none of these
    are set.

    Args:
        tag: The owning :class:`Tag` instance.
    """

    def __init__(self, tag: Tag) -> None:
        """Bind this view to its owning tag.

        Args:
            tag: The owning :class:`Tag` instance.
        """
        self._tag = tag

    @property
    def min(self) -> int | float | str | None:
        """The tag's own minimum value, if set directly on ``<Tag>``."""
        value = self._tag._element.get("Min")
        return None if value is None else convert_numeric(value, self._tag.data_type)

    @property
    def max(self) -> int | float | str | None:
        """The tag's own maximum value, if set directly on ``<Tag>``."""
        value = self._tag._element.get("Max")
        return None if value is None else convert_numeric(value, self._tag.data_type)

    @property
    def engineering_unit(self) -> str:
        """The tag's own engineering unit, if set directly on ``<Tag>``."""
        return self._tag._root_metadata("EngineeringUnits", "EngineeringUnit") or ""

    @property
    def state0(self) -> str:
        """The tag's own zero-state text, if set directly on ``<Tag>``."""
        return self._tag._root_metadata("State0s", "State0") or ""

    @property
    def state1(self) -> str:
        """The tag's own one-state text, if set directly on ``<Tag>``."""
        return self._tag._root_metadata("State1s", "State1") or ""

    @property
    def external_logging(self) -> bool | None:
        """Whether external logging is enabled, if set directly on ``<Tag>``."""
        value = self._tag._element.get("ExternalLogging")
        return None if value is None else value == "true"

    def __repr__(self) -> str:
        """Return a multi-line representation of the populated metadata."""
        lines = ["TagExtendedProperties"]
        props = [
            ("Min", self.min),
            ("Max", self.max),
            ("EngineeringUnit", self.engineering_unit),
            ("State0", self.state0),
            ("State1", self.state1),
            ("ExternalLogging", self.external_logging),
        ]
        for label, val in props:
            if val is not None and val != "":
                lines.append(f"  {label}: {val!r}")
        return "\n".join(lines)


class Tag(BaseElement):
    """A single ``<Tag>`` element (controller- or program-scoped).

    Args:
        element: The ``<Tag>`` element from a parsed L5X tree.
        type_registry: Used to resolve this tag's own value tree members.
    """

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        """Initialise from a ``<Tag>`` XML element.

        Args:
            element: The ``<Tag>`` element to wrap.
            type_registry: Used to resolve this tag's value tree members.
        """
        super().__init__(element)
        self._type_registry = type_registry
        self._overrides = _TagOverrides(element)

    # ------------------------------------------------------------------
    # Identity (core -- always meaningful, regardless of tag kind)
    # ------------------------------------------------------------------

    name = str_attr("Name", doc="Tag name.")
    tag_type = str_attr(
        "TagType", doc='Tag kind: "Base", "Alias", "Produced", or "Consumed".'
    )
    data_type = str_attr("DataType", doc="The tag's data type name.")
    radix = str_attr("Radix", doc="Display radix, for atomic tags.")
    constant = bool_attr(
        "Constant", default=False, doc="Whether the tag is a constant."
    )
    external_access = str_attr(
        "ExternalAccess", doc='External access level (e.g. "Read/Write").'
    )
    usage = str_attr(
        "Usage",
        doc='Program-scoped parameter usage ("Input"/"Output"/"Public").',
    )
    class_ = str_attr(
        "Class",
        doc='Tag class: "Standard" or "Safety". Safety-class tags live in a '
        "safety-partitioned program/task and are subject to the "
        "controller's SafetyInfo restrictions.",
    )
    opc_ua_access = str_attr(
        "OpcUaAccess", doc='OPC UA exposure level for this tag (e.g. "None").'
    )
    description = CDataField(
        "Description", attr_fallback="Description", doc="Tag description text."
    )

    #: Attributes backed by a plain @property/facet rather than a declared
    #: XmlField/CDataField -- still "known", so excluded from
    #: extra_attributes (Min/Max/ExternalLogging are surfaced via
    #: :attr:`extended_properties`, AliasFor via :attr:`alias_for`).
    _DYNAMIC_KEYS: frozenset[str] = frozenset(
        {"Min", "Max", "ExternalLogging", "AliasFor"}
    )

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by declared fields or dynamic properties.

        See :attr:`_DYNAMIC_KEYS`.
        """
        extras = super().extra_attributes
        return {k: v for k, v in extras.items() if k not in self._DYNAMIC_KEYS}

    @property
    def is_safety(self) -> bool:
        """Whether this is a safety-class tag.

        Returns:
            ``True`` if :attr:`class_` is ``"Safety"``, ``False`` otherwise.
        """
        return self.class_ == "Safety"

    @property
    def alias_for(self) -> str | None:
        """The referenced tag/member path, for ``Alias`` tags.

        Returns:
            The ``AliasFor`` XML attribute value, or ``None`` for non-Alias
            tags (this facet is not applicable to them).
        """
        return self._element.get("AliasFor")

    # ------------------------------------------------------------------
    # Root-level metadata shortcuts -- mirror :class:`TagNode`'s flat
    # min/max/engineering_unit/state0/state1/external_logging surface so
    # drilling into a tag's value tree doesn't feel like a different API
    # from the tag itself. Each is ``None``/``""``-safe when
    # :attr:`extended_properties` is ``None`` (nothing set directly on this
    # ``<Tag>``). :attr:`extended_properties` remains available too, for an
    # at-a-glance "is anything set at all" check and for :meth:`describe`.
    # ------------------------------------------------------------------

    @property
    def min(self) -> int | float | str | None:
        """Shortcut for ``self.extended_properties.min``.

        Returns:
            ``None`` if :attr:`extended_properties` is ``None``.
        """
        ext = self.extended_properties
        return ext.min if ext is not None else None

    @property
    def max(self) -> int | float | str | None:
        """Shortcut for ``self.extended_properties.max``.

        Returns:
            ``None`` if :attr:`extended_properties` is ``None``.
        """
        ext = self.extended_properties
        return ext.max if ext is not None else None

    @property
    def engineering_unit(self) -> str:
        """Shortcut for ``self.extended_properties.engineering_unit``.

        Returns:
            ``""`` if :attr:`extended_properties` is ``None``.
        """
        ext = self.extended_properties
        return ext.engineering_unit if ext is not None else ""

    @property
    def state0(self) -> str:
        """Shortcut for ``self.extended_properties.state0``.

        Returns:
            ``""`` if :attr:`extended_properties` is ``None``.
        """
        ext = self.extended_properties
        return ext.state0 if ext is not None else ""

    @property
    def state1(self) -> str:
        """Shortcut for ``self.extended_properties.state1``.

        Returns:
            ``""`` if :attr:`extended_properties` is ``None``.
        """
        ext = self.extended_properties
        return ext.state1 if ext is not None else ""

    @property
    def external_logging(self) -> bool | None:
        """Shortcut for ``self.extended_properties.external_logging``.

        Returns:
            ``None`` if :attr:`extended_properties` is ``None``.
        """
        ext = self.extended_properties
        return ext.external_logging if ext is not None else None

    # ------------------------------------------------------------------
    # Facets -- optional, context-dependent groups. ``None`` means "not
    # applicable to this tag"; check the facet rather than ``tag_type``.
    # ------------------------------------------------------------------

    @property
    def extended_properties(self) -> TagExtendedProperties | None:
        """Studio 5000 "Extended Properties" set directly on this ``<Tag>``.

        Bundles :attr:`TagExtendedProperties.min`/``max``/
        ``engineering_unit``/``state0``/``state1``/``external_logging`` --
        separate from the per-member/per-bit operand overrides used for
        nested UDT/AOI members (see :class:`_TagOverrides`). Named to match
        the "Extended Properties" tab/label Studio 5000 uses for this same
        data in its Tag Properties dialog.

        Returns:
            A :class:`TagExtendedProperties` view if any of those are set
            directly on ``<Tag>``, ``None`` otherwise.
        """
        if (
            self._element.get("Min") is None
            and self._element.get("Max") is None
            and self._element.get("ExternalLogging") is None
            and self._root_metadata("EngineeringUnits", "EngineeringUnit") is None
            and self._root_metadata("State0s", "State0") is None
            and self._root_metadata("State1s", "State1") is None
        ):
            return None
        return TagExtendedProperties(self)

    @property
    def produced(self) -> ProduceInfo | None:
        """``ProduceInfo`` details, for ``Produced`` tags.

        Returns:
            A :class:`ProduceInfo` instance if this tag has a
            ``<ProduceInfo>`` child, ``None`` otherwise.
        """
        el = self._element.find("ProduceInfo")
        return ProduceInfo(el) if el is not None else None

    @property
    def consumed(self) -> ConsumeInfo | None:
        """``ConsumeInfo`` details, for ``Consumed`` tags.

        Returns:
            A :class:`ConsumeInfo` instance if this tag has a
            ``<ConsumeInfo>`` child, ``None`` otherwise.
        """
        el = self._element.find("ConsumeInfo")
        return ConsumeInfo(el) if el is not None else None

    @property
    def message_parameters(self) -> MessageParameters | None:
        """``MessageParameters``, for ``MESSAGE`` type tags.

        Returns:
            A :class:`~py_l5x.parsers.specialty_tags.MessageParameters`
            instance if this tag has a ``<Data Format="Message">`` section,
            ``None`` otherwise.
        """
        el = self._element.find("Data[@Format='Message']/MessageParameters")
        return MessageParameters(el) if el is not None else None

    @property
    def motion_group_parameters(self) -> MotionGroupParameters | None:
        """``MotionGroupParameters``, for ``MOTION_GROUP`` type tags.

        A ``MOTION_GROUP`` tag represents a group of coordinated servo axes
        (at least one is required when any ``AXIS_CIP_DRIVE`` tag is
        present).

        Returns:
            A :class:`~py_l5x.parsers.specialty_tags.MotionGroupParameters`
            instance if this tag has a ``<Data Format="MotionGroup">``
            section, ``None`` otherwise.
        """
        el = self._element.find("Data[@Format='MotionGroup']/MotionGroupParameters")
        return MotionGroupParameters(el) if el is not None else None

    @property
    def axis_parameters(self) -> AxisParameters | None:
        """``AxisParameters``, for ``AXIS_CIP_DRIVE`` (and other Axis-family,
        e.g. ``AXIS_CIP_DRIVE_SAFETY``) type tags.

        Represents a single EtherNet/IP servo axis.

        Returns:
            An :class:`~py_l5x.parsers.specialty_tags.AxisParameters`
            instance if this tag has a ``<Data Format="Axis">`` section,
            ``None`` otherwise.
        """
        el = self._element.find("Data[@Format='Axis']/AxisParameters")
        return AxisParameters(el) if el is not None else None

    @property
    def special_data_format(self) -> str | None:
        """``Format`` of this tag's non-value ``<Data>`` section, if any.

        Tags whose data type has no standard value-tree export (e.g.
        ``MESSAGE``, ``MOTION_GROUP``, ``AXIS_CIP_DRIVE``, or any future/
        unrecognised type Logix exports this way) use a single ``<Data
        Format="...">`` element wrapping one parameter child instead of the
        usual ``Decorated``/``String`` pair. The legacy ``L5K`` mirror is
        ignored (see :data:`_VALUE_DATA_FORMATS`).

        Returns:
            The ``Format`` attribute value (e.g. ``"Message"``,
            ``"MotionGroup"``, ``"Axis"``), or ``None`` for ordinary tags.
        """
        for data_el in self._element.findall("Data"):
            fmt = data_el.get("Format")
            if fmt and fmt not in _VALUE_DATA_FORMATS:
                return fmt
        return None

    @property
    def special_data_attributes(self) -> dict[str, str] | None:
        """Fallback attributes for tag data types py_l5x doesn't dedicate a
        typed wrapper to.

        Reads the attributes directly on this tag's non-value ``<Data>``
        element (see :attr:`special_data_format`) -- typically just
        ``Format``. Known formats have dedicated typed wrappers
        (:attr:`message_parameters`/:attr:`motion_group_parameters`/
        :attr:`axis_parameters`); this exists for anything py_l5x doesn't
        yet recognise. If more detail is needed than this exposes, drop
        down to the underlying element via the parser internals.

        Returns:
            A dict of attribute names to values, or ``None`` if this tag
            has no special (non-value) ``<Data>`` section at all.
        """
        for data_el in self._element.findall("Data"):
            fmt = data_el.get("Format")
            if fmt and fmt not in _VALUE_DATA_FORMATS:
                return dict(data_el.attrib)
        return None

    # ------------------------------------------------------------------
    # Root-level metadata internals (backing :attr:`hmi`)
    # ------------------------------------------------------------------

    def _root_metadata(self, container_tag: str, child_tag: str) -> str | None:
        """Return CDATA text for a container child with no ``Operand`` attribute.

        ``EngineeringUnits``/``State0s``/``State1s``/``ExternalLoggings``
        containers on a ``<Tag>`` element can hold both the tag's own
        (un-qualified) metadata entry and per-member/per-bit entries
        qualified by an ``Operand`` attribute (see :class:`_TagOverrides`,
        which handles the latter). This returns only the former.

        Args:
            container_tag: The plural wrapper element name (e.g.
                ``"EngineeringUnits"``).
            child_tag: The child element name to read CDATA text from (e.g.
                ``"EngineeringUnit"``).

        Returns:
            The text content, stripped of surrounding whitespace, or
            ``None`` if no un-qualified entry is present.
        """
        container = self._element.find(container_tag)
        if container is None:
            return None
        for child in container.findall(child_tag):
            if child.get("Operand"):
                continue
            cdata_el = child.find(CDATA_TAG)
            if cdata_el is not None and cdata_el.text:
                return cdata_el.text.strip()
            return child.text.strip() if child.text else ""
        return None

    # ------------------------------------------------------------------
    # Value tree
    # ------------------------------------------------------------------

    @property
    def data(self) -> TagNode | None:
        """The tag's value tree root node.

        Returns:
            ``None`` for ``Alias`` tags and ``MESSAGE``-type tags (no value
            data is exported for either). Otherwise a scalar-kind
            :class:`TagNode` for atomic tags (including STRING-family tags,
            which use the ``Format="String"`` fallback since they have no
            ``Decorated`` section), or a structure-/array-kind
            :class:`TagNode` for UDT/AOI-instance or array tags.
        """
        if self.tag_type == "Alias":
            return None
        if self._element.find("Data[@Format='Message']") is not None:
            return None
        decorated = self._element.find("Data[@Format='Decorated']")
        if decorated is not None:
            child = next(iter(decorated), None)
            if child is None:
                return None
            return _build_node(child, None, self._overrides, "", self._type_registry)
        string_data = self._element.find("Data[@Format='String']")
        if string_data is not None:
            cdata_el = string_data.find(CDATA_TAG)
            text = (
                cdata_el.text
                if cdata_el is not None and cdata_el.text
                else (string_data.text or "")
            )
            return TagNode(
                string_data, None, self._overrides, "", raw_text=text, from_cdata=True
            )
        return None

    @property
    def value(self) -> int | float | str | bool | None:
        """Shortcut for ``self.data.value`` -- meaningful for scalar tags only.

        Returns:
            The root node's scalar value, or ``None`` if the tag has no
            value data or its root node is a structure/array.
        """
        node = self.data
        return node.value if node is not None else None

    @property
    def members(self) -> Mapping[str, TagNode]:
        """Shortcut for ``self.data.members`` -- meaningful for structures only.

        Returns:
            The root node's member mapping, or an empty dict if the tag has
            no value data or its root node is not a structure.
        """
        node = self.data
        return node.members if node is not None else {}

    @property
    def elements(self) -> Sequence[TagNode]:
        """Shortcut for ``self.data.elements`` -- meaningful for arrays only.

        Returns:
            The root node's element sequence, or an empty list if the tag
            has no value data or its root node is not an array.
        """
        node = self.data
        return node.elements if node is not None else []

    def __repr__(self) -> str:
        """Return a concise representation including the tag name and type."""
        return f"Tag({self.name!r}, {self.data_type!r})"

    def describe(self) -> str:
        """Extend :meth:`BaseElement.describe` to include populated facets.

        ``extended_properties``/``produced``/``consumed``/
        ``message_parameters``/``motion_group_parameters``/
        ``axis_parameters`` are plain properties (not declared fields), so
        the base implementation can't see them -- this appends each one's
        own repr when present.

        Returns:
            A formatted multi-line string suitable for interactive/debug use.
        """
        lines = [super().describe()]
        facets = (
            ("extended_properties", self.extended_properties),
            ("produced", self.produced),
            ("consumed", self.consumed),
            ("message_parameters", self.message_parameters),
            ("motion_group_parameters", self.motion_group_parameters),
            ("axis_parameters", self.axis_parameters),
        )
        for label, facet in facets:
            if facet is None:
                continue
            lines.append(f"  {label}:")
            lines.extend(f"    {line}" for line in repr(facet).splitlines())
        return "\n".join(lines)


class TagsCollection(BaseCollection[Tag]):
    """A ``Mapping`` over every ``<Tag>`` in a ``<Tags>`` section.

    Works identically for the controller-level ``<Tags>`` and each
    ``<Program>``'s ``<Tags>`` -- pass whichever element contains the
    ``Tags/Tag`` children.

    Args:
        scope_element: The ``<Controller>`` or ``<Program>`` element whose
            ``Tags/Tag`` children form this collection.
        type_registry: Used to resolve each tag's value tree members.
    """

    def __init__(self, scope_element: ET.Element, type_registry: TypeRegistry) -> None:
        """Initialise from a controller or program scope element.

        Args:
            scope_element: The element whose ``Tags/Tag`` children form this
                collection.
            type_registry: Used to resolve each tag's value tree members.
        """
        super().__init__(scope_element, "Tags/Tag", Tag, item_args=(type_registry,))

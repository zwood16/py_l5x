"""PLC tag values: nested structure/array drill-down over ``<Tag>`` data.

Logix Designer exports each tag's runtime value as a ``Data`` child in one of
three formats: ``Decorated`` (a ``<DataValue>``, ``<Structure>``, or ``<Array>``
tree mirroring the tag's data type shape), ``String`` (used only for top-level
STRING-family tags, which have no ``Decorated`` section at all), or specialty
parameter blocks (``MESSAGE``, ``MotionGroup``, ``Axis``, etc., out of scope
for standard value parsing here).

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
:class:`TagNode` and its subclasses resolve them with priority over the
type-definition metadata.

**Typed Tag classes and root-metadata behavior**

:class:`Tag` subclasses returned by :class:`TagsCollection` are dispatched via
:func:`_make_tag` based on the tag's data type and value structure:

- ``BoolTag``: BOOL scalar; has ``state0``, ``state1``, ``value``.
- ``IntegerTag``: INT/DINT/SINT/etc. scalar; has ``value``, ``min``, ``max``,
  ``radix``, ``signed``, ``bit_width``, and ``bit(n)``/``bits`` accessors.
- ``FloatTag``: REAL/LREAL scalar; has ``value``, ``min``, ``max``.
- ``TimeTag``: TIME/LTIME scalar (v37+); has ``value`` (string like ``"T#1ms"``),
  ``unit`` (``"ms"`` or ``"us"``).
- ``DateTimeTag``: DT/LDT scalar (v37+); has ``value`` (string datetime), ``unit``.
- ``StringTag``: STRING-family scalar; subclasses ``StringNode``, has ``value``,
  ``len``, ``max_length``, and ``members`` dict with ``"LEN"`` and ``"DATA"``.
- ``StructTag``: UDT or built-in structure instance; subclasses ``StructNode``,
  has ``members`` dict of child nodes.
- ``ArrayTag``: Array instance; subclasses ``ArrayNode``, has ``elements``,
  ``dimensions``, ``__len__``, ``__iter__``, subscript access.
- ``AtomicTag``: Unknown atomic type fallback; has ``value`` and ``raw_value``.
- ``AliasTag``: Alias; has ``alias_for`` path, no value/members/elements.
- ``MessageTag``: MESSAGE type; has ``message_parameters``, no value/members/elements.
- ``MotionGroupTag``: MOTION_GROUP type; has ``motion_group_parameters``.
- ``AxisTag``: AXIS_CIP_DRIVE type; has ``axis_parameters``.
- ``UnknownTag``: Unrecognized specialty type; has ``special_data_format``,
  ``special_data_attributes``, no value/members/elements.

Tags ARE their root value nodes — they directly subclass the corresponding
node class (e.g., ``IntegerTag`` subclasses both ``Tag`` and ``IntegerNode``),
so node accessors work directly on the tag without a ``.data`` property.

Root-level metadata (``description``, ``engineering_unit``, ``min``, ``max``,
``state0``, ``state1``, ``external_access``, ``external_logging``) comes from
the ``<Tag>`` element itself on value tags, combined with type-definition
defaults via :class:`_TagOverrides`. See :meth:`Tag.describe` for a
human-readable summary.

**Node hierarchy**

Value-tree nodes (members, array elements, bits) are organized in a typed hierarchy:

- :class:`TagNode`: Base class for all nodes. Exposes:
  ``data_type``, ``external_access``, ``operand_path``, ``value_element``
  (the raw value XML), ``element`` (the root ``<Tag>``), ``description``,
  ``engineering_unit``, ``external_logging``, ``__repr__``.

- :class:`AtomicNode`: Scalar with value/raw_value/radix. Used as fallback
  when DataType is not in ATOMIC_TYPES.

- :class:`BoolNode`: 1-bit bool value; adds ``state0`` and ``state1``.

- :class:`IntegerNode`: Integer value; adds ``bit_width``, ``signed``,
  ``min``, ``max``, ``bit(n)``, and ``bits``.

- :class:`FloatNode`: Float value; adds ``min`` and ``max``.

- :class:`TimeNode`: String time literal (e.g. ``"T#0us"``); adds ``unit``.

- :class:`DateTimeNode`: String datetime literal; adds ``unit``.

- :class:`StringNode`: Quote-stripped string value; adds ``value``, ``len``,
  ``max_length``, and a ``members`` mapping with ``"LEN"`` and ``"DATA"``.

- :class:`StructNode`: Structure members; exposes ``members`` mapping.

- :class:`ArrayNode`: Array elements; exposes ``dimensions``, a flat
  document-order ``elements`` sequence, ``__len__``, ``__iter__``, and
  ``__getitem__`` taking a flat position or a Logix subscript tuple
  (``arr[0, 1]``). Atomic elements inherit the array's DataType/Radix.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import overload
from xml.etree import ElementTree as ET

from py_l5x.parsers.atomic_types import (
    ATOMIC_TYPES,
    atomic_info,
    parse_float_literal,
    parse_integer_literal,
)
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

    def is_string_type(self, type_name: str) -> bool:
        """Check if a data type is a STRING-family type.

        Args:
            type_name: The data type name to check.

        Returns:
            ``True`` if the type is a STRING-family (built-in "STRING" or
            a UDT with family="StringFamily"), ``False`` otherwise.
        """
        if type_name == "STRING":
            return True
        if type_name in self._data_types:
            return self._data_types[type_name].is_string
        return False

    def string_max_length(self, type_name: str) -> int | None:
        """Get the maximum length for a STRING-family data type.

        Args:
            type_name: The data type name to check.

        Returns:
            The max length for a STRING-family type (82 for built-in
            "STRING", or the UDT's DATA member dimension), or ``None`` if
            the type is not STRING-family or the dimension is not found.
        """
        if type_name == "STRING":
            return 82
        if type_name in self._data_types:
            return self._data_types[type_name].max_length
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


def _find_value_root(
    element: ET.Element, data_tag: str, type_registry: TypeRegistry | None
) -> tuple[type[TagNode], ET.Element] | None:
    """Find and classify a value root element (String or Decorated format).

    Checks for ``{data_tag}[@Format='String']`` (root string types) and
    ``{data_tag}[@Format='Decorated']`` with a child element (structure/array/scalar).

    Args:
        element: The tag/local-tag element to scan for data.
        data_tag: The data element tag name ("Data" for tags, "DefaultData" for AOI locals).
        type_registry: Used to check if a structure is a STRING type.

    Returns:
        A tuple of (node_class, value_element) if found, or None.
    """
    # Check for String format
    string_el = element.find(f"{data_tag}[@Format='String']")
    if string_el is not None:
        return (StringNode, string_el)

    # Check for Decorated format with a child
    decorated = element.find(f"{data_tag}[@Format='Decorated']")
    if decorated is not None:
        child = next(iter(decorated), None)
        if child is not None:
            node_cls, _ = _classify_node(child, None, type_registry, element.get("DataType"))
            return (node_cls, child)

    return None


class _StructureMembers(Mapping):
    """Lazily-resolved ``name -> TagNode`` mapping for a structure node."""

    def __init__(self, node: StructNode) -> None:
        """Bind this view to its owning structure node."""
        self._node = node

    def __getitem__(self, name: str) -> TagNode:
        """Retrieve a member by name."""
        node = self._node
        member_defs = (
            node._type_registry.resolve_members(node.data_type)
            if node._type_registry
            else None
        ) or {}
        for child in node._value_element:
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
        for child in self._node._value_element:
            name = child.get("Name")
            if name:
                yield name

    def __len__(self) -> int:
        """Return the number of members."""
        return sum(1 for child in self._node._value_element if child.get("Name"))

    def __repr__(self) -> str:
        """Return a string representation listing member names."""
        return f"members({list(self)!r})"


class _ArrayElements(Sequence):
    """Lazily-resolved flat ``position -> TagNode`` sequence for an array.

    Positional (``int``) access is in document order, so it works the same
    for single- and multi-dimensional arrays and supports negative indexes.
    Lookup by Logix subscript (``[i]``/``[i,j,...]``) is via :meth:`by_index`.

    Args:
        node: The owning :class:`ArrayNode`.
    """

    def __init__(self, node: ArrayNode) -> None:
        """Bind this view to its owning array node."""
        self._node = node

    @staticmethod
    def _parse_index(index_str: str) -> tuple[int, ...]:
        """Parse an ``Index="[n]"``/``Index="[n,m,...]"`` attribute to a tuple."""
        return tuple(int(part) for part in index_str.strip("[]").split(","))

    def _els(self) -> list[ET.Element]:
        """Return all ``<Element>`` children in document order."""
        return self._node._value_element.findall("Element")

    def _build(self, element: ET.Element) -> TagNode:
        """Build the node for one ``<Element>``, inheriting array type/radix."""
        node = self._node
        subscript = ",".join(
            str(i) for i in self._parse_index(element.get("Index", ""))
        )
        path = f"{node._operand_path}[{subscript}]"
        child = element.find("Structure")
        return _build_node(
            child if child is not None else element,
            node._member_def,
            node._overrides,
            path,
            node._type_registry,
            data_type=node._value_element.get("DataType") or None,
            radix=node._value_element.get("Radix") or None,
        )

    @overload
    def __getitem__(self, index: int) -> TagNode: ...
    @overload
    def __getitem__(self, index: slice) -> list[TagNode]: ...
    def __getitem__(self, index: int | slice) -> TagNode | list[TagNode]:
        """Retrieve an element (or slice of elements) by flat position.

        Raises:
            IndexError: If *index* is out of range.
        """
        els = self._els()
        if isinstance(index, slice):
            return [self._build(el) for el in els[index]]
        return self._build(els[index])

    def by_index(self, index: tuple[int, ...]) -> TagNode:
        """Retrieve an element by its Logix subscript.

        Args:
            index: The subscript, one int per dimension (e.g. ``(0, 1)``).

        Raises:
            IndexError: If no element has that subscript.
        """
        for element in self._els():
            if self._parse_index(element.get("Index", "")) == index:
                return self._build(element)
        raise IndexError(index)

    def __len__(self) -> int:
        """Return the number of elements."""
        return len(self._els())

    def __iter__(self) -> Iterator[TagNode]:
        """Iterate over elements in document order."""
        for element in self._els():
            yield self._build(element)

    def __repr__(self) -> str:
        """Return a string representation showing the element count."""
        return f"elements(len={len(self)})"


class TagNode(XmlAttrMixin):
    """Base class for all value-tree nodes: scalars, structures, arrays.
    
    This is the public surface only with minimal methods that apply to all nodes.
    Subclasses add type-specific behavior and properties.
    """

    def __init__(
        self,
        element: ET.Element | None,
        member_def: MemberDef | None,
        overrides: _TagOverrides,
        operand_path: str,
        type_registry: TypeRegistry | None = None,
        *,
        data_type: str | None = None,
        radix: str | None = None,
        raw_text: str | None = None,
    ) -> None:
        """Initialize a TagNode.
        
        Args:
            element: The XML element this node wraps (None for synthetic nodes).
            member_def: The resolved member/parameter definition, or None.
            overrides: The owning tag's collected operand overrides.
            operand_path: This node's operand path for override lookup.
            type_registry: Used to resolve structure/array children.
            data_type: Overridden data type (for special cases).
            radix: Overridden radix (for special cases).
            raw_text: Pre-extracted text (for CDATA-based members).
        """
        self._value_element = element
        self._member_def = member_def
        self._overrides = overrides
        self._operand_path = operand_path
        self._type_registry = type_registry
        self._data_type_override = data_type
        self._radix_override = radix
        self._raw_text = raw_text

    @property
    def value_element(self) -> ET.Element | None:
        """The wrapped XML element (None for synthetic nodes like bits)."""
        return self._value_element

    @property
    def operand_path(self) -> str:
        """This node's operand path (for override lookup)."""
        return self._operand_path

    @property
    def data_type(self) -> str:
        """This node's data type name."""
        if self._data_type_override is not None:
            return self._data_type_override
        if self._value_element is not None and self._value_element.get("DataType"):
            return self._value_element.get("DataType", "")
        return self._member_def.data_type if self._member_def else ""

    @property
    def external_access(self) -> str:
        """This node's external access level, if any."""
        if self._value_element is not None and self._value_element.get("ExternalAccess"):
            return self._value_element.get("ExternalAccess", "")
        return self._member_def.external_access if self._member_def else ""

    def _meta_override(self, key: str) -> str | None:
        """Return override for a metadata key at this node's operand path."""
        return self._overrides.get(self._operand_path).get(key)

    def _meta_default(self, key: str) -> str | None:
        """Return default metadata value from member_def."""
        if self._member_def is None:
            return None
        # Map key names to member def attributes
        if key == "comment":
            return self._member_def.description
        return getattr(self._member_def, key, None)

    @property
    def description(self) -> str:
        """This node's description, from override or type definition."""
        override = self._meta_override("comment")
        if override is not None:
            return override
        default = self._meta_default("comment")
        return default if default else ""

    @property
    def engineering_unit(self) -> str:
        """This node's engineering unit, from override or type definition."""
        override = self._meta_override("engineering_unit")
        if override is not None:
            return override
        default = self._meta_default("engineering_unit")
        return default if default else ""

    @property
    def external_logging(self) -> bool | None:
        """Whether external logging is enabled, from override or type def."""
        override = self._meta_override("external_logging")
        if override is not None:
            return override == "true"
        default = self._meta_default("external_logging")
        if default is not None:
            return default
        return None

    #: Shape-specific attributes shown by :meth:`__repr__`, in order, when the
    #: concrete class has them.
    _REPR_SHAPE: tuple[str, ...] = (
        "value",
        "len",
        "max_length",
        "unit",
        "dimensions",
        "radix",
        "external_access",
    )
    #: Metadata attributes shown by :meth:`__repr__` when non-empty.
    _REPR_META: tuple[str, ...] = (
        "description",
        "min",
        "max",
        "engineering_unit",
        "state0",
        "state1",
        "external_logging",
    )

    def __repr__(self) -> str:
        """Return a multi-line summary: class, type, path, and set fields."""
        header = f"{type(self).__name__}({self.data_type!r}"
        if self._operand_path:
            header += f", path={self._operand_path!r}"
        lines = [header + ")"]
        for attr in self._REPR_SHAPE + self._REPR_META:
            if not hasattr(self, attr):
                continue
            val = getattr(self, attr)
            if val is None or val == "" or val == ():
                continue
            lines.append(f"  {attr}: {val!r}")
        if isinstance(self, (StructNode, StringNode)):
            lines.append(f"  members: {list(self.members)}")
        elif isinstance(self, ArrayNode):
            lines.append(f"  elements: len={len(self)}")
        return "\n".join(lines)


class AtomicNode(TagNode):
    """A scalar node with a value (integer, float, bool, string, or fallback)."""

    def __init__(
        self,
        element: ET.Element | None,
        member_def: MemberDef | None,
        overrides: _TagOverrides,
        operand_path: str,
        type_registry: TypeRegistry | None = None,
        *,
        data_type: str | None = None,
        radix: str | None = None,
        raw_text: str | None = None,
    ) -> None:
        """Initialize an AtomicNode."""
        super().__init__(
            element, member_def, overrides, operand_path, type_registry,
            data_type=data_type, radix=radix, raw_text=raw_text
        )
        self._radix_override = radix

    @property
    def raw_value(self) -> str | None:
        """The untouched text value."""
        if self._raw_text is not None:
            return self._raw_text
        if self._value_element is not None:
            return self._value_element.get("Value")
        return None

    @property
    def radix(self) -> str | None:
        """This node's display radix, if any."""
        if self._radix_override is not None:
            return self._radix_override
        if self._value_element is not None and self._value_element.get("Radix"):
            return self._value_element.get("Radix", "")
        return self._member_def.radix if self._member_def else None

    @property
    def value(self) -> int | float | str | bool | None:
        """This node's computed value."""
        text = self.raw_value
        if text is None:
            return None
        return convert_numeric(text, self.data_type)


class BoolNode(AtomicNode):
    """A BOOL (1-bit) atomic node."""

    @property
    def value(self) -> bool | str | None:
        """The boolean value.

        Returns:
            ``True``/``False``, ``None`` if no value text was exported, or
            the raw text if it isn't a valid BOOL literal.
        """
        text = self.raw_value
        if text is None:
            return None
        try:
            return bool(parse_integer_literal(text, ATOMIC_TYPES["BOOL"]))
        except ValueError:
            return text

    @property
    def state0(self) -> str:
        """Zero-state text, from override or type definition."""
        override = self._meta_override("state0")
        if override is not None:
            return override
        default = self._meta_default("state0")
        return default if default else ""

    @property
    def state1(self) -> str:
        """One-state text, from override or type definition."""
        override = self._meta_override("state1")
        if override is not None:
            return override
        default = self._meta_default("state1")
        return default if default else ""


class IntegerNode(AtomicNode):
    """An integer atomic node (SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT)."""

    @property
    def value(self) -> int | str | None:
        """The integer value (decimal, ``16#``/``8#``/``2#``, or ASCII literal).

        Returns:
            The parsed ``int``, ``None`` if no value text was exported, or
            the raw text if it can't be parsed/doesn't fit the type.
        """
        text = self.raw_value
        if text is None:
            return None
        try:
            return parse_integer_literal(text, ATOMIC_TYPES[self.data_type.upper()])
        except (ValueError, KeyError):
            return text

    @property
    def bit_width(self) -> int:
        """The bit width of this integer type."""
        info = atomic_info(self.data_type)
        return info.bit_width if info else 0

    @property
    def signed(self) -> bool:
        """Whether this integer type is signed."""
        info = atomic_info(self.data_type)
        return info.signed if info else False

    @property
    def min(self) -> int | None:
        """Minimum value, from override, member def, or ATOMIC_TYPES."""
        override = self._meta_override("min")
        if override is not None:
            try:
                return int(convert_numeric(override, self.data_type))
            except (ValueError, TypeError):
                return None
        if self._member_def and self._member_def.min is not None:
            return self._member_def.min
        info = atomic_info(self.data_type)
        return info.min if info else None

    @property
    def max(self) -> int | None:
        """Maximum value, from override, member def, or ATOMIC_TYPES."""
        override = self._meta_override("max")
        if override is not None:
            try:
                return int(convert_numeric(override, self.data_type))
            except (ValueError, TypeError):
                return None
        if self._member_def and self._member_def.max is not None:
            return self._member_def.max
        info = atomic_info(self.data_type)
        return info.max if info else None

    def bit(self, n: int) -> BoolNode:
        """Access bit *n* as a :class:`BoolNode`.

        Exposes per-bit operand metadata (e.g. a ``.1`` comment) and, when
        :attr:`value` is an ``int``, the bit's value.

        Args:
            n: Zero-based bit position.

        Raises:
            IndexError: If *n* is outside ``0 <= n < bit_width``.
        """
        if not 0 <= n < self.bit_width:
            raise IndexError(f"bit {n} out of range for {self.data_type}")
        value = self.value
        raw = str((value >> n) & 1) if isinstance(value, int) else None
        return BoolNode(
            None,
            None,
            self._overrides,
            f"{self._operand_path}.{n}",
            data_type="BOOL",
            raw_text=raw,
        )

    @property
    def bits(self) -> list[BoolNode]:
        """All bits of this integer as a list of BoolNodes."""
        return [self.bit(i) for i in range(self.bit_width)]


class FloatNode(AtomicNode):
    """A floating-point atomic node (REAL, LREAL)."""

    @property
    def value(self) -> float | str | None:
        """The float value (``1.#QNAN``/``1.#INF`` specials supported).

        Returns:
            The parsed ``float``, ``None`` if no value text was exported, or
            the raw text if it can't be parsed.
        """
        text = self.raw_value
        if text is None:
            return None
        try:
            return parse_float_literal(text)
        except ValueError:
            return text

    @property
    def min(self) -> float | None:
        """Minimum value, from override or member def."""
        override = self._meta_override("min")
        if override is not None:
            try:
                return float(convert_numeric(override, self.data_type))
            except (ValueError, TypeError):
                return None
        if self._member_def and self._member_def.min is not None:
            return self._member_def.min
        return None

    @property
    def max(self) -> float | None:
        """Maximum value, from override or member def."""
        override = self._meta_override("max")
        if override is not None:
            try:
                return float(convert_numeric(override, self.data_type))
            except (ValueError, TypeError):
                return None
        if self._member_def and self._member_def.max is not None:
            return self._member_def.max
        return None


class TimeNode(AtomicNode):
    """A TIME/TIME32/LTIME atomic node with a time literal string."""

    @property
    def value(self) -> str | None:
        """The time literal (e.g. 'T#0us')."""
        return self.raw_value

    @property
    def unit(self) -> str | None:
        """The time unit (us or ns)."""
        info = atomic_info(self.data_type)
        return info.unit if info else None


class DateTimeNode(AtomicNode):
    """A DT/LDT atomic node with a datetime literal string."""

    @property
    def value(self) -> str | None:
        """The datetime literal (e.g. 'DT#1970-01-01-00:00:00.000_000Z')."""
        return self.raw_value

    @property
    def unit(self) -> str | None:
        """The datetime unit (us or ns)."""
        info = atomic_info(self.data_type)
        return info.unit if info else None


class StringNode(TagNode):
    """A STRING-family node: text ``value``, ``len``, and LEN/DATA members.

    Wraps either a decorated ``Structure``/``StructureMember`` whose children
    are the real ``LEN``/``DATA`` members (nested strings and string array
    elements), or a root ``<Data Format="String" Length="n">`` element whose
    text is CDATA and whose ``LEN``/``DATA`` members are synthesised.
    """

    def _child(self, name: str) -> ET.Element | None:
        """Return the real ``LEN``/``DATA`` child element, if decorated."""
        if self._value_element is None or self._value_element.tag not in (
            "Structure",
            "StructureMember",
        ):
            return None
        for child in self._value_element:
            if child.get("Name") == name:
                return child
        return None

    def _raw_data_text(self) -> str:
        """Return the quoted CDATA text from DATA (decorated) or the root."""
        if self._raw_text is not None:
            return self._raw_text
        source = self._child("DATA")
        if source is None:
            source = self._value_element
        if source is None:
            return ""
        cdata_el = source.find(CDATA_TAG)
        if cdata_el is not None and cdata_el.text:
            return cdata_el.text
        return source.text or ""

    @property
    def value(self) -> str:
        """The string text, with Logix's surrounding single quotes removed."""
        return _parse_string_literal(self._raw_data_text())

    @property
    def len(self) -> int:
        """The string's current length (the ``LEN`` member / ``Length`` attr)."""
        len_el = self._child("LEN")
        if len_el is not None:
            raw = len_el.get("Value")
        elif self._value_element is not None:
            raw = self._value_element.get("Length")
        else:
            raw = None
        if raw is not None:
            try:
                return parse_integer_literal(raw, ATOMIC_TYPES["DINT"])
            except ValueError:
                pass
        return len(self.value)

    @property
    def max_length(self) -> int | None:
        """Maximum character capacity: 82 for ``STRING``, else the UDT's."""
        if self._type_registry is not None:
            return self._type_registry.string_max_length(self.data_type)
        return 82 if self.data_type == "STRING" else None

    @property
    def members(self) -> Mapping[str, TagNode]:
        """``{"LEN": IntegerNode, "DATA": AtomicNode}``."""
        return {"LEN": self._len_member(), "DATA": self._data_member()}

    def _len_member(self) -> TagNode:
        """Build the LEN member node (real child or synthetic DINT)."""
        path = f"{self._operand_path}.LEN"
        len_el = self._child("LEN")
        if len_el is not None:
            return _build_node(
                len_el, None, self._overrides, path, self._type_registry
            )
        return IntegerNode(
            None,
            None,
            self._overrides,
            path,
            data_type="DINT",
            raw_text=str(self.len),
        )

    def _data_member(self) -> TagNode:
        """Build the DATA member node; its value is the unquoted text."""
        data_el = self._child("DATA")
        data_type = data_el.get("DataType") if data_el is not None else None
        return AtomicNode(
            data_el,
            None,
            self._overrides,
            f"{self._operand_path}.DATA",
            data_type=data_type or self.data_type,
            raw_text=self.value,
        )

class StructNode(TagNode):
    """A structure node exposing a members mapping."""

    def __init__(
        self,
        element: ET.Element,
        member_def: MemberDef | None,
        overrides: _TagOverrides,
        operand_path: str,
        type_registry: TypeRegistry | None = None,
    ) -> None:
        """Initialize a StructNode."""
        super().__init__(
            element, member_def, overrides, operand_path, type_registry
        )
        self._members_cache = None

    @property
    def members(self) -> Mapping[str, TagNode]:
        """Members mapping (lazy)."""
        if self._members_cache is None:
            self._members_cache = _StructureMembers(self)
        return self._members_cache


class ArrayNode(TagNode):
    """An array node exposing dimensions and elements sequence."""

    def __init__(
        self,
        element: ET.Element,
        member_def: MemberDef | None,
        overrides: _TagOverrides,
        operand_path: str,
        type_registry: TypeRegistry | None = None,
    ) -> None:
        """Initialize an ArrayNode."""
        super().__init__(
            element, member_def, overrides, operand_path, type_registry
        )
        self._value_elements_cache = None

    @property
    def dimensions(self) -> tuple[int, ...]:
        """The array dimensions as a tuple of ints."""
        if self._value_element is None:
            return ()
        dims_str = self._value_element.get("Dimensions", "")
        if not dims_str:
            return ()
        try:
            return tuple(int(x.strip()) for x in dims_str.split(","))
        except ValueError:
            return ()

    @property
    def elements(self) -> Sequence[TagNode]:
        """Elements sequence (lazy)."""
        if self._value_elements_cache is None:
            self._value_elements_cache = _ArrayElements(self)
        return self._value_elements_cache

    def __len__(self) -> int:
        """Number of elements."""
        return len(self.elements)

    def __iter__(self):
        """Iterate over elements."""
        return iter(self.elements)

    def __getitem__(self, index: int | tuple[int, ...]) -> TagNode:
        """Index into the array.

        Args:
            index: A flat document-order position (``int``, negatives
                allowed; equal to the Logix subscript for 1-D arrays) or a
                Logix subscript tuple such as ``(0, 1)`` for multi-dim arrays.

        Raises:
            IndexError: If the position/subscript doesn't exist.
        """
        if isinstance(index, tuple):
            return self.elements.by_index(index)
        return self.elements[index]


_ATOMIC_NODE_CLASSES: dict[str, type[AtomicNode]] = {
    "bool": BoolNode,
    "integer": IntegerNode,
    "float": FloatNode,
    "time": TimeNode,
    "datetime": DateTimeNode,
}


def _build_node(
    element: ET.Element,
    member_def: MemberDef | None,
    overrides: _TagOverrides,
    operand_path: str,
    type_registry: TypeRegistry | None = None,
    *,
    data_type: str | None = None,
    radix: str | None = None,
) -> TagNode:
    """Build the appropriate node subclass for an element.

    Dispatches to ArrayNode, StructNode, StringNode, or various AtomicNode
    subclasses based on element tag and data type.

    Args:
        element: The element to build a node for.
        member_def: The resolved member/parameter definition, if any.
        overrides: The owning tag's collected operand overrides.
        operand_path: This node's operand path.
        type_registry: Used to resolve structure/array children.
        data_type: Data type to use for a scalar whose element carries no
            ``DataType`` attribute (array ``<Element>`` children inherit the
            parent array's type this way).
        radix: Radix to use for such a scalar, likewise inherited.
    """
    # Use _classify_node to determine the node class
    node_cls, resolved_dt = _classify_node(element, member_def, type_registry, data_type)
    
    # Arrays
    if node_cls is ArrayNode:
        return ArrayNode(element, member_def, overrides, operand_path, type_registry)
    
    # Structures
    if node_cls is StructNode:
        return StructNode(element, member_def, overrides, operand_path, type_registry)
    
    # StringNodes
    if node_cls is StringNode:
        return StringNode(
            element, member_def, overrides, operand_path, type_registry
        )
    
    # Scalars (AtomicNode and subclasses)
    # If Value attribute is present, use the typed node class
    if element.get("Value") is not None:
        return node_cls(
            element,
            member_def,
            overrides,
            operand_path,
            type_registry,
            data_type=resolved_dt,
            radix=radix,
        )
    
    # Scalar with CDATA text and no Value (e.g. a STRING's DATA member)
    cdata_el = element.find(CDATA_TAG)
    if cdata_el is not None and cdata_el.text:
        text = cdata_el.text
    else:
        text = element.text or ""
    return AtomicNode(
        element,
        member_def,
        overrides,
        operand_path,
        type_registry,
        data_type=resolved_dt,
        radix=radix,
        raw_text=_parse_string_literal(text),
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


def _describe_value_lines(obj: object) -> list[str]:
    """Extract value/members/elements description lines for a tag-like object.

    Produces lines for metadata attributes (value, len, max_length, unit, etc.)
    and summary lines for members/elements if present.

    Args:
        obj: A tag or tag-like object (e.g., Tag, AOILocalTag subclass).

    Returns:
        A list of formatted description lines (without leading indentation).
    """
    lines = []

    # Add any metadata attributes that have values
    for name in (
        "value", "len", "max_length", "unit", "dimensions", "radix",
        "min", "max", "engineering_unit", "state0", "state1",
        "external_logging", "alias_for", "special_data_format"
    ):
        if hasattr(obj, name):
            val = getattr(obj, name, None)
            if val is not None and val != "" and val != ():
                lines.append(f"  {name}: {val!r}")

    # Members list for struct/string tags
    if hasattr(obj, "members"):
        members = obj.members
        if members:
            lines.append(f"  members: {list(members.keys())}")

    # Element count for arrays
    if hasattr(obj, "elements"):
        elements = obj.elements
        if elements:
            lines.append(f"  elements: {len(elements)} items")

    return lines


class _RootMetadataMixin:
    """Mixin for metadata read from identity elements (tag-level Min/Max/etc).

    Reads metadata set directly on an identity element: Min/Max/ExternalLogging
    attributes and un-operanded EngineeringUnits/State0s/State1s entries.
    
    Requires ``self._element`` to be defined (the XML element).
    """

    def _meta_override(self, key: str) -> str | None:
        """Return override for a metadata key at the identity element's level.

        For tag-level metadata (min, max, engineering_unit, state0, state1,
        external_logging), this returns the value set directly on the element.
        """
        if key == "min":
            return self._element.get("Min")
        if key == "max":
            return self._element.get("Max")
        if key == "external_logging":
            return self._element.get("ExternalLogging")
        if key in ("engineering_unit", "state0", "state1"):
            container_map = {
                "engineering_unit": ("EngineeringUnits", "EngineeringUnit"),
                "state0": ("State0s", "State0"),
                "state1": ("State1s", "State1"),
            }
            container, child = container_map[key]
            return self._root_metadata(container, child)
        return None

    def _meta_default(self, key: str) -> str | None:
        """Return default metadata for a key (always None at element level)."""
        return None

    def _root_metadata(self, container_tag: str, child_tag: str) -> str | None:
        """Return CDATA text for a container child with no ``Operand`` attribute.

        ``EngineeringUnits``/``State0s``/``State1s``/``ExternalLoggings``
        containers on an element can hold both the element's own (un-qualified)
        metadata entry and per-member/per-bit entries qualified by an
        ``Operand`` attribute. This returns only the former.

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


class Tag(_RootMetadataMixin, BaseElement):
    """A single ``<Tag>`` element (controller- or program-scoped).
    
    Base class for all tag types. Provides identity metadata, facets, and
    metadata hooks. Subclasses add value-tree node functionality.

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
    #: XmlField/CDataField -- still "known", so excluded from extra_attributes.
    #: "Radix" and "Dimensions" are surfaced by the value-node radix/dimensions
    #: properties and should not be exposed as extra attributes.
    _DYNAMIC_KEYS: frozenset[str] = frozenset(
        {"Min", "Max", "ExternalLogging", "AliasFor", "Radix", "Dimensions"}
    )

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by declared fields or dynamic properties."""
        extras = super().extra_attributes
        return {k: v for k, v in extras.items() if k not in self._DYNAMIC_KEYS}

    @property
    def element(self) -> ET.Element:
        """The wrapped ``<Tag>`` XML element."""
        return self._element

    @property
    def is_safety(self) -> bool:
        """Whether this is a safety-class tag."""
        return self.class_ == "Safety"

    # ------------------------------------------------------------------
    # Facets -- optional, context-dependent groups.
    # ------------------------------------------------------------------

    @property
    def produced(self) -> ProduceInfo | None:
        """``ProduceInfo`` details, for ``Produced`` tags."""
        el = self._element.find("ProduceInfo")
        return ProduceInfo(el) if el is not None else None

    @property
    def consumed(self) -> ConsumeInfo | None:
        """``ConsumeInfo`` details, for ``Consumed`` tags."""
        el = self._element.find("ConsumeInfo")
        return ConsumeInfo(el) if el is not None else None

    def __repr__(self) -> str:
        """Return a concise representation including the tag name and type."""
        return f"{type(self).__name__}({self.name!r}, {self.data_type!r})"

    def describe(self) -> str:
        """Extend :meth:`BaseElement.describe` to include metadata and facets.
        
        Includes identity info from super(), then for each metadata attribute
        that exists on this tag with a non-None/non-empty value, adds a line.
        For struct/array tags, also includes member/element summaries.
        """
        lines = [super().describe()]
        
        # Add value/members/elements lines
        lines.extend(_describe_value_lines(self))
        
        # Add facets
        facets = (
            ("produced", self.produced),
            ("consumed", self.consumed),
        )
        for label, facet in facets:
            if facet is None:
                continue
            lines.append(f"  {label}:")
            lines.extend(f"    {line}" for line in repr(facet).splitlines())
        
        return "\n".join(lines)


class _ValueTag(Tag):
    """Base for tags that are also their root value node (private, not exported).
    
    Tags that carry a value tree (scalars, structures, arrays) inherit from both
    Tag and a node class. This base class initializes both parent classes.
    """

    def __init__(
        self, element: ET.Element, type_registry: TypeRegistry, value_element: ET.Element
    ) -> None:
        """Initialize a tag with a value node.

        Args:
            element: The ``<Tag>`` element.
            type_registry: Used to resolve value tree members.
            value_element: The ``Data[@Format='Decorated']`` child element, or the
                ``Data[@Format='String']`` element for STRING tags.
        """
        # Initialize Tag first (for MRO)
        Tag.__init__(self, element, type_registry)
        # Call the concrete node class's __init__ via super(BaseElement, self).
        # This resolves to the first TagNode subclass in the MRO after BaseElement,
        # allowing StructNode/ArrayNode to initialize their caches correctly.
        super(BaseElement, self).__init__(
            value_element, None, self._overrides, "", type_registry
        )


class BoolTag(_ValueTag, BoolNode):
    """A ``<Tag>`` whose value is a BOOL (1-bit) atomic type."""


class IntegerTag(_ValueTag, IntegerNode):
    """A ``<Tag>`` whose value is an integer atomic type (SINT, INT, DINT, etc.)."""


class FloatTag(_ValueTag, FloatNode):
    """A ``<Tag>`` whose value is a floating-point atomic type (REAL, LREAL)."""


class TimeTag(_ValueTag, TimeNode):
    """A ``<Tag>`` whose value is a TIME/TIME32/LTIME literal."""


class DateTimeTag(_ValueTag, DateTimeNode):
    """A ``<Tag>`` whose value is a DT/LDT datetime literal."""


class AtomicTag(_ValueTag, AtomicNode):
    """A ``<Tag>`` whose value is an atomic type not covered by specific subclasses."""


class StringTag(_ValueTag, StringNode):
    """A ``<Tag>`` whose value is a STRING or STRING-family type."""


class StructTag(_ValueTag, StructNode):
    """A ``<Tag>`` whose value is a UDT or AOI instance (structure)."""


class ArrayTag(_ValueTag, ArrayNode):
    """A ``<Tag>`` whose value is an array."""


class AliasTag(Tag):
    """A ``<Tag>`` that aliases another tag or member (no value data).
    
    Alias tags reference another tag/member via the ``AliasFor`` attribute
    and carry no value data themselves.
    """

    @property
    def alias_for(self) -> str | None:
        """The referenced tag/member path."""
        return self._element.get("AliasFor")


class _SpecialDataTag(Tag):
    """Base class for tags with non-value ``Data`` formats.

    Tags whose data type has no standard value-tree export (e.g.
    ``MESSAGE``, ``MOTION_GROUP``, ``AXIS_CIP_DRIVE``, or any future/
    unrecognised type Logix exports this way) use a single ``<Data
    Format="...">`` element wrapping one parameter child instead of the
    usual ``Decorated``/``String`` pair. The legacy ``L5K`` mirror is
    ignored (see :data:`_VALUE_DATA_FORMATS`).

    This class provides :attr:`special_data_format` and
    :attr:`special_data_attributes` to access the wrapped data. Known formats
    have dedicated typed wrappers; this handles the generic case.
    """

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
            The ``Format`` attribute of the non-value ``<Data>`` element,
            or ``None`` if this tag has no special data section.
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
            A mapping of XML attribute names to values on the non-value
            ``<Data>`` element, or ``None`` if this tag has no special data
            section.
        """
        for data_el in self._element.findall("Data"):
            fmt = data_el.get("Format")
            if fmt and fmt not in _VALUE_DATA_FORMATS:
                return dict(data_el.attrib)
        return None


class MessageTag(_SpecialDataTag):
    """A ``<Tag>`` with a MESSAGE data type (specialized parameter data).

    MESSAGE tags carry ``MessageParameters`` instead of standard value data.
    """

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


class AxisTag(_SpecialDataTag):
    """A ``<Tag>`` with an AXIS_CIP_DRIVE (or similar axis) data type.

    Represents a single EtherNet/IP servo axis.
    """

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


class MotionGroupTag(_SpecialDataTag):
    """A ``<Tag>`` with a MOTION_GROUP data type.

    A ``MOTION_GROUP`` tag represents a group of coordinated servo axes
    (at least one is required when any ``AXIS_CIP_DRIVE`` tag is
    present).
    """

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


class UnknownTag(_SpecialDataTag):
    """A ``<Tag>`` with a non-standard data format (future/unrecognized types).

    For tags with special ``<Data>`` formats py_l5x doesn't yet recognize,
    this tag type provides fallback access to the format name and attributes.
    """


# Mapping from node class to value tag class
_TAG_CLASSES: dict[type[TagNode], type[_ValueTag]] = {
    BoolNode: BoolTag,
    IntegerNode: IntegerTag,
    FloatNode: FloatTag,
    TimeNode: TimeTag,
    DateTimeNode: DateTimeTag,
    AtomicNode: AtomicTag,
    StringNode: StringTag,
    StructNode: StructTag,
    ArrayNode: ArrayTag,
}


def _classify_node(
    element: ET.Element,
    member_def: MemberDef | None,
    type_registry: TypeRegistry | None,
    data_type: str | None = None,
) -> tuple[type[TagNode], str]:
    """Classify an element to determine the node class and resolved data type.
    
    Helper used by both _build_node and _make_tag to factor out the dispatch logic.
    
    Args:
        element: The element to classify.
        member_def: The resolved member definition, if any.
        type_registry: Used to resolve string types.
        data_type: Overridden data type.
    
    Returns:
        A tuple of (node_class, resolved_data_type).
    """
    # Arrays
    if element.tag in ("Array", "ArrayMember"):
        return ArrayNode, element.get("DataType", member_def.data_type if member_def else "")
    
    # Structures and potential StringNodes
    if element.tag in ("Structure", "StructureMember"):
        dt = element.get("DataType", member_def.data_type if member_def else "")
        
        # Check if it's a STRING-family type
        if (
            (type_registry and type_registry.is_string_type(dt))
            or dt == "STRING"
        ):
            return StringNode, dt
        
        # Check for LEN+DATA structure (synthetic STRING representation)
        children_names = {
            child.get("Name") for child in element if child.get("Name")
        }
        if children_names == {"LEN", "DATA"}:
            return StringNode, dt
        
        return StructNode, dt
    
    # Scalars
    if data_type is None:
        data_type = element.get("DataType") or (
            member_def.data_type if member_def else ""
        )
    info = atomic_info(data_type) if data_type else None
    
    # Only use family class if Value attribute is present
    if element.get("Value") is not None:
        node_cls = (
            _ATOMIC_NODE_CLASSES.get(info.family, AtomicNode) if info else AtomicNode
        )
        return node_cls, data_type
    
    return AtomicNode, data_type


def _make_tag(element: ET.Element, type_registry: TypeRegistry) -> Tag:
    """Factory function to create the appropriate Tag subclass.
    
    Dispatches to AliasTag, MessageTag, AxisTag, MotionGroupTag, UnknownTag,
    or a specific value tag class (BoolTag, IntegerTag, etc.) based on the
    tag's structure and data.

    Args:
        element: The ``<Tag>`` element.
        type_registry: Used to resolve value tree members.

    Returns:
        An instance of the appropriate Tag subclass.
    """
    # Alias tags
    if element.get("TagType") == "Alias":
        return AliasTag(element, type_registry)
    
    # Check for non-value Data formats (Message, Axis, MotionGroup, unknown)
    for data_el in element.findall("Data"):
        fmt = data_el.get("Format")
        if fmt and fmt not in _VALUE_DATA_FORMATS:
            if fmt == "Message":
                return MessageTag(element, type_registry)
            if fmt == "Axis":
                return AxisTag(element, type_registry)
            if fmt == "MotionGroup":
                return MotionGroupTag(element, type_registry)
            return UnknownTag(element, type_registry)
    
    # Find value root (String or Decorated with child)
    root = _find_value_root(element, "Data", type_registry)
    if root is not None:
        node_cls, value_el = root
        tag_cls = _TAG_CLASSES.get(node_cls, AtomicTag)
        return tag_cls(element, type_registry, value_el)
    
    # No recognized value data
    return UnknownTag(element, type_registry)

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
        super().__init__(scope_element, "Tags/Tag", _make_tag, item_args=(type_registry,))

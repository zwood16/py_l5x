"""Default value trees for data types.

Builds the ``Decorated`` (or ``String``) data Studio 5000 holds for a freshly
created tag of any data type, so a tag created without ``<Data>`` can be given
a full value tree.

Layout rules, taken from Studio's own exports:

- **Atomic types** are a ``DataValue`` (root), ``DataValueMember`` (member) or
  an ``Element`` with a ``Value`` (array element). ``BOOL`` carries ``Radix``
  only at a tag root and on arrays, never on a member. Defaults are ``0``,
  ``0.0``, ``T#0us`` and so on, formatted for the radix.
- **UDTs** list their non-hidden members in order. ``BIT`` members appear as
  ``BOOL``. Structured members are ``StructureMember`` and array members are
  ``ArrayMember`` with ``Element`` children.
- **AOIs** list their parameters in definition order except ``InOut`` ones
  (local tags are not part of the data). A parameter's default comes from its
  ``DefaultData[@Format="Decorated"]``; ``EnableIn`` defaults to ``1`` when it
  has none. A source-protected AOI is laid out the same way from its readable
  ``<Parameters>`` (its encoded local tags and logic are never read, and no
  L5K is built; Studio regenerates it with the locals at defaults, exp36).
- **StringFamily** types (``STRING``, ``STRING_16``, user string UDTs) are
  ``<Data Format="String" Length="0">`` with ``''`` at a tag root, and a
  ``Structure`` with ``LEN`` and ``DATA`` anywhere else.
- **Built-in structures** (``TIMER``, ``PID``, ...) are copied from a table
  Studio generated, ``data/builtin_types.L5X.gz`` (cumulative: the
  v37 types plus those added since, such as ``TIMER_T`` from v38).
- ``Dimensions`` in decorated data are comma separated (``"2,3"``), and
  element indexes are row-major.

Whitespace follows what the reader produces from Studio files: an element
with children has ``text`` ``"\\n"`` and every child has ``tail`` ``"\\n"``.
The top element returned has no ``tail``.

Types without a decorated layout (``MESSAGE``, ``AXIS_*``, ``MOTION_GROUP``,
alarm types, ...) and unknown types raise :class:`LayoutError`.
"""

from __future__ import annotations

import copy
import gzip
import itertools
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.parsers.atomic_types import (
    ATOMIC_TYPES,
    AtomicInfo,
    default_radix,
    format_float_literal,
    format_integer_literal,
)
from py_l5x.parsers.utils import CDATA_TAG, replace_cdata_sections

if TYPE_CHECKING:
    from py_l5x.parsers.tag import TypeRegistry

#: Package data file holding Studio's default tree for each built-in type.
BUILTIN_TABLE_RESOURCE = "data/builtin_types.L5X.gz"

#: Default value text for the time and date-time types.
_TIME_DEFAULTS: dict[str, str] = {
    "TIME32": "T32#0us",
    "TIME": "T#0us",
    "LTIME": "LT#0ns",
    "DT": "DT#1970-01-01-00:00:00.000_000Z",
    "LDT": "LDT#1970-01-01-00:00:00.000_000_000Z",
}


class LayoutError(ValueError):
    """Raised for a type that has no decorated layout, or is unknown."""


@dataclass(frozen=True)
class MemberInfo:
    """One member of a structure type, as it appears in decorated data.

    Attributes:
        name: Member name.
        data_type: Data type name (``BIT`` members are reported as ``BOOL``).
        dimensions: Array dimensions, empty for a scalar.
        radix: Radix for atomic members (the type default if none was stated),
            otherwise ``None``.
        default: Default value text declared by an AOI parameter, or ``None``.
    """

    name: str
    data_type: str
    dimensions: tuple[int, ...]
    radix: str | None
    default: str | None = None


# ----------------------------------------------------------------------
# Built-in table
# ----------------------------------------------------------------------


@cache
def builtin_table() -> dict[str, ET.Element]:
    """Load Studio's default value data for every built-in type.

    The gzipped L5X is read once through :mod:`importlib.resources` and
    cached. Treat the returned elements as read-only (they are deep-copied
    before use).

    Returns:
        A mapping of type name to its ``<Data>`` element (``Format``
        ``Decorated``, or ``String`` for the string types).
    """
    data = (resources.files("py_l5x") / BUILTIN_TABLE_RESOURCE).read_bytes()
    text = gzip.decompress(data).decode("utf-8-sig").replace("\r\n", "\n")
    root = ET.fromstring(replace_cdata_sections(text).encode("utf-8"))
    table: dict[str, ET.Element] = {}
    for tag in root.iter("Tag"):
        for data_el in tag.findall("Data"):
            if data_el.get("Format") in ("Decorated", "String"):
                table[tag.get("Name", "")] = data_el
                break
    return table


# ----------------------------------------------------------------------
# Element helpers
# ----------------------------------------------------------------------


def _fill(element: ET.Element, children: list[ET.Element]) -> ET.Element:
    """Append *children* in Studio's one-element-per-line layout.

    Args:
        element: The parent.
        children: Its children.

    Returns:
        *element*.
    """
    if children:
        element.text = "\n"
        for child in children:
            child.tail = "\n"
            element.append(child)
    return element


def _make(tag: str, attributes: list[tuple[str, str]]) -> ET.Element:
    """Create an element with attributes in the given order.

    Args:
        tag: Element tag.
        attributes: ``(name, value)`` pairs.

    Returns:
        The element.
    """
    element = ET.Element(tag)
    for key, value in attributes:
        element.set(key, value)
    return element


def _finish(element: ET.Element) -> ET.Element:
    """Clear the tail of the element handed back to a caller.

    Args:
        element: A top-level result.

    Returns:
        *element*.
    """
    element.tail = None
    return element


# ----------------------------------------------------------------------
# Type classification
# ----------------------------------------------------------------------


def _is_string(data_type: str, registry: TypeRegistry) -> bool:
    """Report whether a type is StringFamily.

    Args:
        data_type: The type name.
        registry: The project's type registry.

    Returns:
        ``True`` for built-in string types and string UDTs.
    """
    table_entry = builtin_table().get(data_type)
    if table_entry is not None:
        return table_entry.get("Format") == "String"
    return registry.is_string_type(data_type)


def _builtin_structure(data_type: str) -> ET.Element | None:
    """Return a built-in structure's default ``Structure`` element.

    Args:
        data_type: The type name.

    Returns:
        The table's ``Structure`` element, or ``None`` if *data_type* is not a
        built-in structure.
    """
    entry = builtin_table().get(data_type)
    if entry is None or entry.get("Format") != "Decorated":
        return None
    first = next(iter(entry), None)
    return first if first is not None and first.tag == "Structure" else None


def _atomic(data_type: str) -> AtomicInfo | None:
    """Look up atomic info for the exact (upper-case) type name.

    Args:
        data_type: The type name.

    Returns:
        The info, or ``None`` if not an atomic type.
    """
    return ATOMIC_TYPES.get(data_type) if data_type.upper() == data_type else None


def _default_text(data_type: str, radix: str | None) -> str:
    """Return the default value text of an atomic type for a radix.

    Args:
        data_type: An atomic type name.
        radix: The display radix.

    Returns:
        ``"0"``, ``"0.0"``, ``"T#0us"``, ``"16#0000_0000"`` and so on.
    """
    info = ATOMIC_TYPES[data_type]
    if info.family == "bool":
        return "0"
    if info.family == "integer":
        return format_integer_literal(0, info, radix)
    if info.family == "float":
        return format_float_literal(0, data_type, radix)
    return _TIME_DEFAULTS[data_type]


def _resolve_kind(data_type: str, registry: TypeRegistry) -> str:
    """Classify *data_type* for layout purposes.

    Args:
        data_type: The type name.
        registry: The project's type registry.

    Returns:
        ``"atomic"``, ``"string"``, ``"builtin"``, ``"udt"`` or ``"aoi"``.

    Raises:
        LayoutError: If the type is unknown or has no decorated layout.
    """
    if _atomic(data_type) is not None:
        return "atomic"
    if data_type in builtin_table():
        return "string" if _is_string(data_type, registry) else "builtin"
    udt = registry.udt(data_type)
    if udt is not None:
        if udt.class_ == "ProductDefined":
            raise LayoutError(
                f"{data_type} has no decorated default layout (special data format)"
            )
        return "string" if udt.is_string else "udt"
    if registry.aoi(data_type) is not None or registry.is_protected_aoi(data_type):
        return "aoi"
    raise LayoutError(f"unknown data type {data_type!r}")


# ----------------------------------------------------------------------
# Members
# ----------------------------------------------------------------------


def _parse_dimensions(text: str | None) -> tuple[int, ...]:
    """Parse a ``Dimensions`` attribute (space or comma separated).

    Args:
        text: The attribute text, if any.

    Returns:
        The sizes, empty if absent.
    """
    return tuple(int(part) for part in (text or "").replace(",", " ").split())


def _aoi_default(element: ET.Element) -> str | None:
    """Return the ``Value`` of an AOI parameter's decorated default.

    Args:
        element: The ``<Parameter>`` element.

    Returns:
        The text, or ``None`` if there is no decorated atomic default.
    """
    for default in element.findall("DefaultData"):
        if default.get("Format") == "Decorated":
            value = next(iter(default), None)
            if value is not None and value.tag == "DataValue":
                return value.get("Value")
    return None


def members(data_type: str, registry: TypeRegistry) -> list[MemberInfo]:
    """List the ordered members of a UDT or AOI as decorated data shows them.

    Hidden UDT members and ``InOut`` AOI parameters are left out; ``BIT``
    members are reported as ``BOOL``.

    Args:
        data_type: A UDT or AOI name.
        registry: The project's type registry.

    Returns:
        The members in order.

    Raises:
        LayoutError: If the type is not a UDT or AOI (built-in structures are
            copied from the table and have no member list here).
    """
    kind = _resolve_kind(data_type, registry)
    if kind == "udt":
        udt = registry.udt(data_type)
        assert udt is not None
        out = []
        for member in udt.visible_members.values():
            member_type = "BOOL" if member.data_type == "BIT" else member.data_type
            dims = (member.dimension,) if member.dimension else ()
            out.append(
                MemberInfo(
                    member.name, member_type, dims, _radix(member_type, member.radix)
                )
            )
        return out
    if kind == "aoi":
        aoi = registry.aoi(data_type)
        if aoi is None:
            # Source-protected: only the readable <Parameters> are used.
            protected = registry.protected_aoi(data_type)
            assert protected is not None
            aoi = protected.parameters
        out = []
        for param in aoi.datatype_members.values():
            element = param.element
            param_type = element.get("DataType", "")
            default = _aoi_default(element)
            if default is None and param.name == "EnableIn":
                default = "1"
            out.append(
                MemberInfo(
                    param.name,
                    param_type,
                    _parse_dimensions(element.get("Dimensions")),
                    _radix(param_type, element.get("Radix")),
                    default,
                )
            )
        return out
    raise LayoutError(f"{data_type} is not a UDT or AOI")


def _radix(data_type: str, stated: str | None) -> str | None:
    """Pick the radix for an atomic member.

    Args:
        data_type: The member's type.
        stated: The radix on the definition, if any.

    Returns:
        *stated* when meaningful, else the type's default; ``None`` for
        non-atomic types.
    """
    if _atomic(data_type) is None:
        return None
    return stated if stated and stated != "NullType" else default_radix(data_type)


# ----------------------------------------------------------------------
# Builders
# ----------------------------------------------------------------------

_SCALAR_TAGS = {
    "root": ("DataValue", "Structure", "Array"),
    "member": ("DataValueMember", "StructureMember", "ArrayMember"),
}


def _head(
    context: str, kind_index: int, name: str | None, attributes: list[tuple[str, str]]
) -> ET.Element:
    """Create the opening element for a value in a given context.

    Args:
        context: ``"root"`` or ``"member"``.
        kind_index: 0 for a scalar, 1 for a structure, 2 for an array.
        name: The member name (member context only).
        attributes: Attributes after ``Name``.

    Returns:
        The new element.
    """
    tag = _SCALAR_TAGS[context][kind_index]
    pairs = (
        [("Name", name)] if context == "member" and name is not None else []
    ) + attributes
    return _make(tag, pairs)


def _string_structure(data_type: str, context: str, name: str | None) -> ET.Element:
    """Build a string as ``Structure`` with ``LEN`` and ``DATA`` members.

    Args:
        data_type: The string type name.
        context: ``"root"`` or ``"member"``.
        name: The member name.

    Returns:
        The element.
    """
    length = _make(
        "DataValueMember",
        [("Name", "LEN"), ("DataType", "DINT"), ("Radix", "Decimal"), ("Value", "0")],
    )
    data = _make(
        "DataValueMember",
        [("Name", "DATA"), ("DataType", data_type), ("Radix", "ASCII")],
    )
    empty = ET.SubElement(data, CDATA_TAG)
    empty.text = ""
    empty.tail = "\n"
    data.text = "\n"
    return _fill(_head(context, 1, name, [("DataType", data_type)]), [length, data])


def _scalar(
    data_type: str,
    registry: TypeRegistry,
    context: str,
    name: str | None,
    radix: str | None,
    value: str | None,
) -> ET.Element:
    """Build one non-array value.

    Args:
        data_type: The type name.
        registry: The project's type registry.
        context: ``"root"`` or ``"member"``.
        name: The member name.
        radix: The radix for an atomic value.
        value: Value text overriding the default (atomic only).

    Returns:
        The element.
    """
    kind = _resolve_kind(data_type, registry)
    if kind == "atomic":
        shown = _radix(data_type, radix)
        text = value if value is not None else _default_text(data_type, shown)
        attrs = [("DataType", data_type)]
        if shown and (data_type != "BOOL" or context == "root"):
            attrs.append(("Radix", shown))
        attrs.append(("Value", text))
        return _head(context, 0, name, attrs)
    if kind == "string":
        return _string_structure(data_type, context, name)
    if kind == "builtin":
        source = _builtin_structure(data_type)
        assert source is not None
        element = _head(context, 1, name, [("DataType", data_type)])
        return _fill(element, [copy.deepcopy(child) for child in source])
    children = [_member(info, registry) for info in members(data_type, registry)]
    return _fill(_head(context, 1, name, [("DataType", data_type)]), children)


def _member(info: MemberInfo, registry: TypeRegistry) -> ET.Element:
    """Build one structure member.

    Args:
        info: The member description.
        registry: The project's type registry.

    Returns:
        A ``DataValueMember``, ``StructureMember`` or ``ArrayMember``.
    """
    if info.dimensions:
        return _array(
            info.data_type, registry, info.dimensions, "member", info.name, info.radix
        )
    return _scalar(
        info.data_type, registry, "member", info.name, info.radix, info.default
    )


def _array(
    data_type: str,
    registry: TypeRegistry,
    dimensions: tuple[int, ...],
    context: str,
    name: str | None,
    radix: str | None,
) -> ET.Element:
    """Build an array value with default elements.

    Args:
        data_type: The element type.
        registry: The project's type registry.
        dimensions: Sizes per dimension.
        context: ``"root"`` or ``"member"``.
        name: The member name.
        radix: The radix for atomic arrays.

    Returns:
        An ``Array`` or ``ArrayMember``.
    """
    kind = _resolve_kind(data_type, registry)
    attrs = [
        ("DataType", data_type),
        ("Dimensions", ",".join(str(n) for n in dimensions)),
    ]
    shown = _radix(data_type, radix)
    if kind == "atomic" and shown:
        attrs.append(("Radix", shown))
    array = _head(context, 2, name, attrs)
    elements = []
    for position in itertools.product(*(range(n) for n in dimensions)):
        index = "[" + ",".join(str(i) for i in position) + "]"
        element = _make("Element", [("Index", index)])
        if kind == "atomic":
            element.set("Value", _default_text(data_type, shown))
        else:
            _fill(element, [_scalar(data_type, registry, "root", None, None, None)])
        elements.append(element)
    return _fill(array, elements)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def default_value_element(
    data_type: str,
    registry: TypeRegistry,
    *,
    dimensions: tuple[int, ...] | None = None,
    context: str = "root",
    name: str | None = None,
    radix: str | None = None,
) -> ET.Element:
    """Build Studio's default decorated value tree for a type.

    Args:
        data_type: The data type name.
        registry: The project's type registry (UDTs and AOIs).
        dimensions: Array sizes (``None`` or empty for a scalar).
        context: ``"root"`` for a tag root (``DataValue``/``Structure``/
            ``Array``) or ``"member"`` for a structure member
            (``...Member`` elements, which need *name*).
        name: The member name, for ``context="member"``.
        radix: Radix for atomic types (a tag's ``Radix`` or a member's);
            the type default when ``None``.

    Returns:
        The element, with Studio's whitespace and no ``tail``. A StringFamily
        scalar at a tag root is a ``Structure`` here; use
        :func:`default_data_element` for the ``Format="String"`` form.

    Raises:
        LayoutError: If the type is unknown or has no decorated layout.
        ValueError: If *context* is not ``"root"`` or ``"member"``, or a
            member has no *name*.
    """
    if context not in _SCALAR_TAGS:
        raise ValueError(f"context must be 'root' or 'member', not {context!r}")
    if context == "member" and not name:
        raise ValueError("a member value needs a name")
    if dimensions:
        element = _array(data_type, registry, tuple(dimensions), context, name, radix)
    else:
        element = _scalar(data_type, registry, context, name, radix, None)
    return _finish(element)


def default_data_element(
    data_type: str,
    registry: TypeRegistry,
    *,
    dimensions: tuple[int, ...] | None = None,
    radix: str | None = None,
) -> ET.Element:
    """Build the whole ``<Data>`` element of a new tag of a type.

    Args:
        data_type: The data type name.
        registry: The project's type registry.
        dimensions: Array sizes (``None`` or empty for a scalar).
        radix: The tag's ``Radix`` for atomic types; the type default if
            ``None``.

    Returns:
        ``<Data Format="Decorated">`` around the value tree, or
        ``<Data Format="String" Length="0">`` with ``''`` for a StringFamily
        scalar. No ``tail`` is set.

    Raises:
        LayoutError: If the type is unknown or has no decorated layout.
    """
    if not dimensions and _resolve_kind(data_type, registry) == "string":
        data = _make("Data", [("Format", "String"), ("Length", "0")])
        data.text = "\n"
        text = ET.SubElement(data, CDATA_TAG)
        text.text = "''"
        text.tail = "\n"
        return data
    value = default_value_element(
        data_type, registry, dimensions=dimensions, radix=radix
    )
    return _finish(_fill(_make("Data", [("Format", "Decorated")]), [value]))

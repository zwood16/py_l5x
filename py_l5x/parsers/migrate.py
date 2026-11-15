"""Migration of existing value trees when a data type's layout changes.

When a UDT is replaced, Studio keeps the values of every existing instance by
member name: new members get defaults, removed members are dropped and a
member whose type changed is converted where that makes sense. This module
does the same on the XML.

An *instance* is any ``Structure`` or ``StructureMember`` whose ``DataType`` is
the migrated type, at any depth of a ``Data[@Format="Decorated"]`` (tags) or
``DefaultData[@Format="Decorated"]`` (AOI parameters and local tags): as a tag
root, nested in other structures, or inside arrays (``Element``). Root
``Format="String"`` data of a StringFamily type is truncated to the new
``DATA`` size. Data-less tags need nothing.

The work is split into :func:`plan_instance_migration`, which builds every new
subtree without touching the document, and applying the returned edits. A
failure while planning therefore leaves the document untouched. The planner
only needs the type's new layout to be resolvable through the registry, so it
works for any type name (AOI parameter edits can reuse it).

The stale L5K block of every tag or ``DefaultData`` that is touched is
removed. Operand metadata (comments and so on) that points at removed members
is left in place, as Studio does.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.parsers.atomic_types import (
    ATOMIC_TYPES,
    _exponential,
    format_float_literal,
    format_integer_literal,
    format_string_literal,
    parse_float_literal,
    parse_integer_literal,
    parse_string_literal,
)
from py_l5x.parsers.layout import default_value_element
from py_l5x.parsers.schema import remove_child
from py_l5x.parsers.utils import CDATA_TAG

if TYPE_CHECKING:
    from py_l5x.parsers.tag import TypeRegistry

_STRUCT_TAGS = ("Structure", "StructureMember")
_ARRAY_TAGS = ("Array", "ArrayMember")
_ATOMIC_TAGS = ("DataValue", "DataValueMember")


def convert_atomic_value(
    text: str, old_type: str, new_type: str, new_radix: str | None
) -> str | None:
    """Convert a stored atomic value to another atomic type.

    Rules (measured in Studio on a UDT overwrite):

    ======================  ===============================================
    from -> to              result
    ======================  ===============================================
    same type               the text unchanged (reformatted if the radix
                            changed)
    REAL/LREAL -> integer   round half to even, then saturate at the target
                            range (``1e10`` -> DINT ``2147483647``)
    integer -> integer      two's complement wrap (DINT 300 -> SINT 44,
                            SINT -5 -> UINT 65531)
    integer -> REAL         rounded to float32
    integer -> LREAL        plain float
    REAL <-> LREAL          float32 rounding / widening
    BOOL -> numeric         0 or 1 (REAL ``1.0``)
    numeric -> BOOL         nonzero -> 1, zero -> 0
    anything else           ``None`` (the caller keeps the default)
    ======================  ===============================================

    Time and date-time values only carry over between identical types. NaN to
    an integer gives ``None``; an infinity saturates (not measured).

    Args:
        text: The old ``Value`` text.
        old_type: The old atomic type name.
        new_type: The new atomic type name.
        new_radix: The radix to format the result in.

    Returns:
        The new ``Value`` text, or ``None`` if there is no sensible
        conversion.
    """
    old = ATOMIC_TYPES.get(old_type)
    new = ATOMIC_TYPES.get(new_type)
    if old is None or new is None:
        return None
    if old.family in ("time", "datetime") or new.family in ("time", "datetime"):
        return text if old_type == new_type else None
    try:
        value: int | float
        if old.family in ("bool", "integer"):
            value = parse_integer_literal(text, old)
        else:
            value = parse_float_literal(text)
    except ValueError:
        return None
    try:
        if new.family == "bool":
            return "0" if value == 0 else "1"
        if new.family == "integer":
            if isinstance(value, float):
                if math.isnan(value):
                    return None
                assert new.min is not None and new.max is not None
                value = (
                    max(new.min, min(new.max, round(value)))
                    if math.isfinite(value)
                    else (new.max if value > 0 else new.min)
                )
            else:
                value &= 2**new.bit_width - 1
                if new.signed and value >= 2 ** (new.bit_width - 1):
                    value -= 2**new.bit_width
            return format_integer_literal(value, new, new_radix)
        if new_type == "REAL":
            value = _float32(float(value))
            if math.isfinite(value) and (new_radix or "").lower() == "exponential":
                # Studio prints the float32 value itself with nine digits
                # (DINT 2147483647 -> 2.14748365e+009), not its shortest form.
                return _exponential(value, 8)
        return format_float_literal(float(value), new_type, new_radix)
    except (ValueError, OverflowError):
        return None


def _float32(value: float) -> float:
    """Round a float to float32.

    Args:
        value: The float.

    Returns:
        The nearest float32 value.

    Raises:
        OverflowError: If the value is too large for float32.
    """
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _convert_same_or_other(
    text: str,
    old_type: str,
    old_radix: str | None,
    new_type: str,
    new_radix: str | None,
) -> str | None:
    """Convert a value, keeping the text verbatim when nothing changed.

    Args:
        text: The old ``Value`` text.
        old_type: The old type.
        old_radix: The old radix.
        new_type: The new type.
        new_radix: The new radix.

    Returns:
        The new text, or ``None`` to keep the default.
    """
    if old_type == new_type and (old_radix == new_radix or old_type == "BOOL"):
        return text
    info = ATOMIC_TYPES.get(new_type)
    if (
        old_type == new_type
        and info is not None
        and info.family in ("time", "datetime")
    ):
        return text
    return convert_atomic_value(text, old_type, new_type, new_radix)


def _raw_cdata(element: ET.Element) -> str:
    """Return an element's CDATA text exactly (empty CDATA gives ``""``).

    Args:
        element: An element holding one CDATA section.

    Returns:
        The text of its CDATA child, or the element's own text trimmed of
        newlines if it has none.
    """
    cdata = element.find(CDATA_TAG)
    if cdata is not None:
        return cdata.text or ""
    return (element.text or "").strip("\r\n")


def _by_name(element: ET.Element) -> dict[str, ET.Element]:
    """Index an element's named children, ignoring case.

    Args:
        element: A ``Structure``/``StructureMember``.

    Returns:
        Lower-cased name to child.
    """
    return {c.get("Name", "").lower(): c for c in element if c.get("Name")}


def _merge_string(old: ET.Element, new: ET.Element, max_length: int | None) -> None:
    """Copy a nested string's text into a fresh ``LEN``/``DATA`` structure.

    Args:
        old: The old string structure.
        new: The new (default) string structure, modified in place.
        max_length: The size of ``DATA`` to truncate to, if known.
    """
    old_data = _by_name(old).get("data")
    new_len = _by_name(new).get("len")
    new_data = _by_name(new).get("data")
    if old_data is None or new_len is None or new_data is None:
        return
    raw = _raw_cdata(old_data)
    text = parse_string_literal(raw)
    if max_length is not None and len(text) > max_length:
        text = text[:max_length]
        raw = format_string_literal(text) if text else ""
    new_len.set("Value", str(len(text)))
    cdata = new_data.find(CDATA_TAG)
    if cdata is None:
        cdata = ET.SubElement(new_data, CDATA_TAG)
        new_data.text = "\n"
        cdata.tail = "\n"
    cdata.text = raw


def _merge(
    old: ET.Element, new: ET.Element, registry: TypeRegistry, max_lengths: dict
) -> None:
    """Copy values from an old subtree into a fresh default subtree.

    Members are matched by name (ignoring case), array elements by index.
    Anything that has no compatible counterpart keeps its default.

    Args:
        old: The old subtree.
        new: The new default subtree, modified in place.
        registry: The project's type registry.
        max_lengths: ``{type name: DATA size}`` for string types being
            truncated.
    """
    if old.tag in _ATOMIC_TAGS and new.tag in _ATOMIC_TAGS:
        text = old.get("Value")
        if text is None:
            return
        converted = _convert_same_or_other(
            text,
            old.get("DataType", ""),
            old.get("Radix"),
            new.get("DataType", ""),
            new.get("Radix"),
        )
        if converted is not None:
            new.set("Value", converted)
    elif old.tag in _STRUCT_TAGS and new.tag in _STRUCT_TAGS:
        type_name = new.get("DataType", "")
        if old.get("DataType") != type_name:
            return
        names = {c.get("Name") for c in new if c.get("Name")}
        if names == {"LEN", "DATA"}:
            _merge_string(old, new, max_lengths.get(type_name))
            return
        old_children = _by_name(old)
        for child in new:
            name = child.get("Name")
            if name and name.lower() in old_children:
                _merge(old_children[name.lower()], child, registry, max_lengths)
    elif old.tag in _ARRAY_TAGS and new.tag in _ARRAY_TAGS:
        old_elements = {e.get("Index"): e for e in old.findall("Element")}
        for element in new.findall("Element"):
            previous = old_elements.get(element.get("Index"))
            if previous is None:
                continue
            if element.get("Value") is not None and previous.get("Value") is not None:
                converted = _convert_same_or_other(
                    previous.get("Value", ""),
                    old.get("DataType", ""),
                    old.get("Radix"),
                    new.get("DataType", ""),
                    new.get("Radix"),
                )
                if converted is not None:
                    element.set("Value", converted)
            else:
                old_struct = previous.find("Structure")
                new_struct = element.find("Structure")
                if old_struct is not None and new_struct is not None:
                    _merge(old_struct, new_struct, registry, max_lengths)


def _swap(parent: ET.Element, old: ET.Element, new: ET.Element) -> None:
    """Replace *old* by *new* in *parent*, keeping the position and tail.

    Args:
        parent: The parent element.
        old: The element to replace.
        new: Its replacement (its tail is set from *old*).
    """
    new.tail = old.tail
    parent[list(parent).index(old)] = new


def _drop_l5k(owner: ET.Element) -> None:
    """Remove the L5K ``Data``/``DefaultData`` blocks of *owner*.

    Args:
        owner: A ``Tag``, ``Parameter`` or ``LocalTag``.
    """
    for tag in ("Data", "DefaultData"):
        for child in owner.findall(tag):
            if child.get("Format") == "L5K":
                remove_child(owner, child)


def _truncate_root_string(container: ET.Element, max_length: int) -> Callable | None:
    """Plan truncating a root ``Format="String"`` value.

    Args:
        container: The ``Data``/``DefaultData`` element.
        max_length: The new ``DATA`` size.

    Returns:
        An edit, or ``None`` if the text already fits.
    """
    text = parse_string_literal(_raw_cdata(container))
    if len(text) <= max_length:
        return None
    text = text[:max_length]

    def apply() -> None:
        container.set("Length", str(len(text)))
        cdata = container.find(CDATA_TAG)
        if cdata is None:
            cdata = ET.SubElement(container, CDATA_TAG)
            container.text = "\n"
            cdata.tail = "\n"
        cdata.text = format_string_literal(text)

    return apply


def plan_instance_migration(
    root: ET.Element, registry: TypeRegistry, type_name: str
) -> list[Callable[[], None]]:
    """Plan the migration of every instance of a type to its current layout.

    Nothing is modified; the returned edits are applied in order by the
    caller. The type's new layout must already be resolvable through
    *registry* (for a UDT, its new ``<DataType>`` is in the document).

    Args:
        root: The element to search (normally the ``<Controller>``).
        registry: The project's type registry.
        type_name: The data type whose instances are migrated.

    Returns:
        The edits that replace each instance with a fresh default subtree
        carrying the old values, truncate root strings, and drop the stale
        L5K blocks of the touched tags.

    Raises:
        LayoutError: If the type has no decorated layout.
    """
    parents = {child: parent for parent in root.iter() for child in parent}
    max_length = registry.string_max_length(type_name)
    max_lengths = {type_name: max_length}
    ops: list[Callable[[], None]] = []
    owners: list[ET.Element] = []
    for container in list(root.iter()):
        if container.tag not in ("Data", "DefaultData"):
            continue
        owner = parents.get(container)
        fmt = container.get("Format")
        if fmt == "Decorated":
            touched = False
            for element in list(container.iter()):
                if (
                    element.tag not in _STRUCT_TAGS
                    or element.get("DataType") != type_name
                ):
                    continue
                member = element.tag == "StructureMember"
                fresh = default_value_element(
                    type_name,
                    registry,
                    context="member" if member else "root",
                    name=element.get("Name") if member else None,
                )
                _merge(element, fresh, registry, max_lengths)
                ops.append(_swap_op(parents[element], element, fresh))
                touched = True
            if touched and owner is not None:
                owners.append(owner)
        elif (
            fmt == "String"
            and owner is not None
            and owner.get("DataType") == type_name
            and max_length is not None
        ):
            truncate = _truncate_root_string(container, max_length)
            if truncate is not None:
                ops.append(truncate)
                owners.append(owner)
    seen: set[int] = set()
    for owner in owners:
        if id(owner) not in seen:
            seen.add(id(owner))
            ops.append(_drop_op(owner))
    return ops


def _swap_op(
    parent: ET.Element, old: ET.Element, new: ET.Element
) -> Callable[[], None]:
    """Bind :func:`_swap` for later application.

    Args:
        parent: The parent element.
        old: The element to replace.
        new: Its replacement.

    Returns:
        A no-argument edit.
    """
    return lambda: _swap(parent, old, new)


def _drop_op(owner: ET.Element) -> Callable[[], None]:
    """Bind :func:`_drop_l5k` for later application.

    Args:
        owner: The tag element.

    Returns:
        A no-argument edit.
    """
    return lambda: _drop_l5k(owner)


def _migrate_instances(root: ET.Element, registry: TypeRegistry, type_name: str) -> int:
    """Migrate every instance of a type, all or nothing.

    Args:
        root: The element to search (normally the ``<Controller>``).
        registry: The project's type registry.
        type_name: The data type whose layout changed.

    Returns:
        The number of edits applied.

    Raises:
        LayoutError: If the type has no decorated layout (nothing changed).
    """
    ops = plan_instance_migration(root, registry, type_name)
    for op in ops:
        op()
    return len(ops)

"""Build ``<Tag>`` elements from a :class:`~py_l5x.build.specs.TagSpec`.

``build_tag`` is the single code path behind ``TagsCollection.add``,
``TagsCollection.add_alias`` and program builders. It returns a detached
``<Tag>``:

- attributes in Studio's order: ``Name Class TagType DataType Dimensions Radix
  AliasFor Usage Constant ExternalAccess OpcUaAccess Max Min ExternalLogging
  DataExchangeId`` (only those present; unknown ones follow);
- children in schema order: ``Description``, operand containers, ``Data``;
- with no ``<Data>`` unless the spec has a value, which goes through the same
  plan/apply machinery as ``tag.value = ...``, so a bad value raises before
  anything is returned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.build.specs import TagSpec
from py_l5x.parsers.layout import LayoutError
from py_l5x.parsers.names import validate_new_name
from py_l5x.parsers.tag import TagNode, _make_tag, set_override

if TYPE_CHECKING:
    from py_l5x.parsers.tag import TypeRegistry

_ATTRIBUTE_ORDER = (
    "Name",
    "Class",
    "TagType",
    "DataType",
    "Dimensions",
    "Radix",
    "AliasFor",
    "Usage",
    "Constant",
    "ExternalAccess",
    "OpcUaAccess",
    "Max",
    "Min",
    "ExternalLogging",
    "DataExchangeId",
)

#: Fields written from the spec's own fields (not allowed in ``metadata``).
_OWN_ATTRIBUTES = frozenset(
    {"Name", "TagType", "DataType", "Dimensions", "Radix", "AliasFor", "Constant"}
    | {"ExternalAccess"}
)


def normalize_dimensions(
    dimensions: int | tuple[int, ...] | list[int] | None, data_type: str | None
) -> str | None:
    """Turn a spec's dimensions into the ``Dimensions`` attribute text.

    Args:
        dimensions: A size, a tuple of up to three sizes, or ``None``.
        data_type: The tag's type (BOOL arrays are rounded up to 32).

    Returns:
        Space-separated sizes (``"2 3"``), or ``None`` for a scalar.

    Raises:
        ValueError: If the sizes are not one to three positive integers, or a
            multi-dimensional BOOL array is requested.
    """
    if dimensions is None:
        return None
    sizes = tuple(dimensions) if isinstance(dimensions, tuple | list) else (dimensions,)
    if (
        not 1 <= len(sizes) <= 3
        or not all(type(n) is int for n in sizes)
        or any(n < 1 for n in sizes)
    ):
        raise ValueError(
            f"dimensions must be one to three positive integers: {dimensions!r}"
        )
    if data_type == "BOOL":
        if len(sizes) > 1:
            raise ValueError("multi-dimensional BOOL arrays are not supported")
        sizes = (-(-sizes[0] // 32) * 32,)
    return " ".join(str(n) for n in sizes)


def build_tag(spec: TagSpec, registry: TypeRegistry) -> ET.Element:
    """Build a detached ``<Tag>`` from a spec.

    Args:
        spec: The tag.
        registry: The project's type registry (needed for a value, and to
            classify the tag).

    Returns:
        The ``<Tag>`` element, with no ``tail``.

    Raises:
        ValueError: If the name is invalid, not exactly one of ``data_type``
            and ``alias_for`` is given, a value is given for an alias,
            ``metadata`` repeats a field, the dimensions are invalid, or the
            value is out of range.
        KeyError: If the value names an unknown structure member.
        TypeError: If the value has the wrong type.
        LayoutError: If a value is given for a type with no decorated layout.
    """
    validate_new_name(spec.name, [], "tag")
    if (spec.data_type is None) == (spec.alias_for is None):
        raise ValueError("a tag needs exactly one of data_type and alias_for")
    if spec.alias_for is not None and (
        spec.value is not None or spec.dimensions is not None
    ):
        raise ValueError("an alias tag has no value or dimensions")
    meta = dict(spec.metadata or {})
    clash = _OWN_ATTRIBUTES & meta.keys()
    if clash:
        raise ValueError(f"metadata cannot set {sorted(clash)}; use the spec fields")
    attributes: dict[str, str] = {
        "Name": spec.name,
        "TagType": "Base" if spec.alias_for is None else "Alias",
    }
    if spec.data_type is not None:
        attributes["DataType"] = spec.data_type
    dimensions = normalize_dimensions(spec.dimensions, spec.data_type)
    if dimensions is not None:
        attributes["Dimensions"] = dimensions
    if spec.radix is not None:
        attributes["Radix"] = spec.radix
    if spec.alias_for is not None:
        attributes["AliasFor"] = spec.alias_for
    if spec.constant is not None:
        attributes["Constant"] = "true" if spec.constant else "false"
    if spec.external_access is not None:
        attributes["ExternalAccess"] = spec.external_access
    attributes.update(meta)
    element = ET.Element("Tag")
    for key in _ATTRIBUTE_ORDER:
        if key in attributes:
            element.set(key, attributes.pop(key))
    for key, value in attributes.items():
        element.set(key, value)

    tag = _make_tag(element, registry)
    if spec.description:
        tag.description = spec.description
    for operand, text in (spec.operand_comments or {}).items():
        set_override(element, operand, "comment", text)
    for operand, entries in (spec.operand_metadata or {}).items():
        for key, text in entries.items():
            set_override(element, operand, key, text)
    if spec.value is not None:
        if not isinstance(tag, TagNode):
            raise LayoutError(f"cannot assign a value to {spec.data_type} tags")
        tag.value = spec.value
    return element

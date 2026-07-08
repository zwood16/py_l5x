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
``TagValue`` resolves them with priority over the type-definition metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from xml.etree import ElementTree as ET

from py_l5x.parse import CDATA_TAG
from py_l5x.parsers.base import BaseCollection, BaseElement, XmlAttrMixin
from py_l5x.parsers.datatype import (
    AddOnDataTypeCollection,
    AddOnParameter,
    DataTypeMember,
    DataTypesCollection,
)
from py_l5x.parsers.utils import convert_numeric

#: A member/parameter definition used for metadata cross-reference. Both
#: classes expose the same property surface (description/min/max/
#: engineering_unit/state0/state1/radix/external_access).
MemberDef = DataTypeMember | AddOnParameter


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


class TagValue(XmlAttrMixin):
    """Common metadata resolution for a node in a tag's value tree.

    Args:
        element: The XML element this node wraps (``None`` for synthetic
            nodes like :class:`TagValueBit`).
        member_def: The resolved UDT member or AOI parameter definition for
            this node, if any.
        overrides: The owning tag's collected operand overrides.
        operand_path: This node's operand path (e.g. ``".A_NESTED_UDT.DINT"``),
            used to look up *overrides*.
    """

    def __init__(
        self,
        element: ET.Element | None,
        member_def: MemberDef | None,
        overrides: _TagOverrides,
        operand_path: str,
    ) -> None:
        """Initialise the common metadata-resolution state for a value node.

        Args:
            element: The XML element this node wraps, or ``None``.
            member_def: The resolved member/parameter definition, or ``None``.
            overrides: The owning tag's collected operand overrides.
            operand_path: This node's operand path.
        """
        self._element = element
        self._member_def = member_def
        self._overrides = overrides
        self._operand_path = operand_path

    def _override(self, key: str) -> str | None:
        """Return the override value for *key* at this node's operand path."""
        return self._overrides.get(self._operand_path).get(key)

    @property
    def data_type(self) -> str:
        """This node's data type name."""
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


class TagValueScalar(TagValue):
    """A single atomic value within a tag's value tree.

    Args:
        element: The ``<DataValue>``/``<DataValueMember>``/``<Element>``
            element this scalar wraps.
        member_def: The resolved member/parameter definition, if any.
        overrides: The owning tag's collected operand overrides.
        operand_path: This node's operand path.
        raw_text: Pre-extracted text to use instead of the element's ``Value``
            attribute (used for CDATA-based string members).
        from_cdata: If ``True``, *raw_text* came from quoted CDATA text (e.g.
            a STRING ``DATA`` member) and should be quote-stripped rather
            than passed through :func:`convert_numeric`.
    """

    def __init__(
        self,
        element: ET.Element | None,
        member_def: MemberDef | None,
        overrides: _TagOverrides,
        operand_path: str,
        raw_text: str | None = None,
        from_cdata: bool = False,
    ) -> None:
        """Initialise a scalar value node.

        Args:
            element: The element this scalar wraps, or ``None``.
            member_def: The resolved member/parameter definition, if any.
            overrides: The owning tag's collected operand overrides.
            operand_path: This node's operand path.
            raw_text: Pre-extracted text overriding the ``Value`` attribute.
            from_cdata: Whether *raw_text* is quoted CDATA string content.
        """
        super().__init__(element, member_def, overrides, operand_path)
        self._raw_text = raw_text
        self._from_cdata = from_cdata

    @property
    def value(self) -> int | float | str | bool | None:
        """The scalar's value, converted per its data type.

        Returns:
            An ``int``/``float`` for numeric atomic types, a quote-stripped
            ``str`` for CDATA-based string content, or the raw string for
            anything else (e.g. ``DT#...`` date/time literals). ``None`` if
            no value could be found.
        """
        text = self._raw_text
        if text is None and self._element is not None:
            text = self._element.get("Value")
        if text is None:
            return None
        if self._from_cdata:
            return _parse_string_literal(text)
        return convert_numeric(text, self.data_type)

    def __getitem__(self, bit_number: int) -> TagValueBit:
        """Access a single bit of this scalar for override-only metadata.

        This does not require the underlying UDT/AOI to define per-bit
        members -- it exists so plain atomic tags with bit-addressed
        ``Comments``/``EngineeringUnits``/``State0s``/``State1s`` overrides
        (e.g. ``a_commented_dint``) can still expose that metadata, and
        (when the scalar value is an ``int``) the bit's boolean value.

        Args:
            bit_number: The zero-based bit position.

        Returns:
            A :class:`TagValueBit` bound to this scalar.
        """
        path = f"{self._operand_path}.{bit_number}"
        return TagValueBit(self, bit_number, self._overrides, path)

    def __repr__(self) -> str:
        """Return a concise representation showing the resolved value."""
        return f"TagValueScalar({self.value!r})"


class TagValueBit(TagValue):
    """A single bit within an integer :class:`TagValueScalar`.

    Carries only override-derived metadata (there is no UDT/AOI member
    definition for an ad-hoc bit on a plain atomic tag) plus a computed
    boolean value derived from the parent scalar's integer value.

    Args:
        parent: The scalar this bit belongs to.
        bit_number: The zero-based bit position.
        overrides: The owning tag's collected operand overrides.
        operand_path: This bit's operand path (e.g. ``".1"``).
    """

    def __init__(
        self,
        parent: TagValueScalar,
        bit_number: int,
        overrides: _TagOverrides,
        operand_path: str,
    ) -> None:
        """Initialise a bit view over a parent scalar.

        Args:
            parent: The scalar this bit belongs to.
            bit_number: The zero-based bit position.
            overrides: The owning tag's collected operand overrides.
            operand_path: This bit's operand path.
        """
        super().__init__(None, None, overrides, operand_path)
        self._parent = parent
        self._bit_number = bit_number

    @property
    def data_type(self) -> str:
        """Always ``"BOOL"`` -- a single bit is boolean."""
        return "BOOL"

    @property
    def value(self) -> bool | None:
        """The bit's boolean value, computed from the parent's integer value.

        Returns:
            ``True``/``False`` if the parent scalar's value is an ``int``,
            otherwise ``None``.
        """
        parent_value = self._parent.value
        if isinstance(parent_value, int):
            return bool((parent_value >> self._bit_number) & 1)
        return None

    def __repr__(self) -> str:
        """Return a concise representation showing the bit number and value."""
        return f"TagValueBit({self._bit_number}, value={self.value!r})"


def _build_value_node(
    element: ET.Element,
    member_def: MemberDef | None,
    overrides: _TagOverrides,
    operand_path: str,
    type_registry: TypeRegistry,
) -> TagValue:
    """Dispatch a ``StructureMember``/``ArrayMember``/``DataValueMember``.

    Args:
        element: The child element to build a node for.
        member_def: The resolved member/parameter definition, if any.
        overrides: The owning tag's collected operand overrides.
        operand_path: This node's operand path.
        type_registry: Used by structure/array nodes to resolve their own
            children's member definitions.

    Returns:
        A :class:`TagValueStructure`, :class:`TagValueArray`, or
        :class:`TagValueScalar` as appropriate.
    """
    if element.tag == "ArrayMember":
        return TagValueArray(
            element, member_def, overrides, operand_path, type_registry
        )
    if element.tag == "StructureMember":
        return TagValueStructure(
            element, member_def, overrides, operand_path, type_registry
        )
    # DataValueMember: scalar, either a "Value" attribute or CDATA text (the
    # latter for STRING-family DATA members).
    if element.get("Value") is not None:
        return TagValueScalar(element, member_def, overrides, operand_path)
    cdata_el = element.find(CDATA_TAG)
    if cdata_el is not None and cdata_el.text:
        text = cdata_el.text
    else:
        text = element.text or ""
    return TagValueScalar(
        element, member_def, overrides, operand_path, raw_text=text, from_cdata=True
    )


class TagValueStructure(TagValue, Mapping):
    """A structure/UDT/AOI-instance node in a tag's value tree.

    Maps member name to :class:`TagValue` (recursing into nested structures,
    arrays, or scalars as appropriate).

    Args:
        element: The ``<Structure>``/``<StructureMember>`` element this node
            wraps.
        member_def: The resolved member/parameter definition, if any.
        overrides: The owning tag's collected operand overrides.
        operand_path: This node's operand path.
        type_registry: Used to resolve this structure's own children's
            member definitions.
    """

    def __init__(
        self,
        element: ET.Element,
        member_def: MemberDef | None,
        overrides: _TagOverrides,
        operand_path: str,
        type_registry: TypeRegistry,
    ) -> None:
        """Initialise a structure value node.

        Args:
            element: The element this structure wraps.
            member_def: The resolved member/parameter definition, if any.
            overrides: The owning tag's collected operand overrides.
            operand_path: This node's operand path.
            type_registry: Used to resolve child member definitions.
        """
        super().__init__(element, member_def, overrides, operand_path)
        self._type_registry = type_registry

    def __getitem__(self, name: str) -> TagValue:
        """Retrieve a member by name.

        Args:
            name: The member's ``Name`` attribute.

        Returns:
            The member's :class:`TagValue` node.

        Raises:
            KeyError: If no member with the given name is found.
        """
        members = self._type_registry.resolve_members(self.data_type) or {}
        for child in self._element:
            if child.get("Name") == name:
                path = f"{self._operand_path}.{name.upper()}"
                return _build_value_node(
                    child, members.get(name), self._overrides, path, self._type_registry
                )
        raise KeyError(name)

    def __iter__(self):
        """Iterate over member names in document order."""
        for child in self._element:
            name = child.get("Name")
            if name:
                yield name

    def __len__(self) -> int:
        """Return the number of members."""
        return sum(1 for child in self._element if child.get("Name"))

    def __repr__(self) -> str:
        """Return a string representation listing member names."""
        return f"TagValueStructure({list(self)!r})"


class TagValueArray(TagValue, Mapping):
    """An array node in a tag's value tree, keyed by integer index.

    Args:
        element: The ``<Array>``/``<ArrayMember>`` element this node wraps.
        member_def: The resolved member/parameter definition, if any (shared
            across all elements, since arrays are described by one member).
        overrides: The owning tag's collected operand overrides.
        operand_path: This node's operand path.
        type_registry: Used to resolve struct-typed elements' own children.
    """

    def __init__(
        self,
        element: ET.Element,
        member_def: MemberDef | None,
        overrides: _TagOverrides,
        operand_path: str,
        type_registry: TypeRegistry,
    ) -> None:
        """Initialise an array value node.

        Args:
            element: The element this array wraps.
            member_def: The resolved member/parameter definition, if any.
            overrides: The owning tag's collected operand overrides.
            operand_path: This node's operand path.
            type_registry: Used to resolve struct-typed elements' children.
        """
        super().__init__(element, member_def, overrides, operand_path)
        self._type_registry = type_registry

    @staticmethod
    def _index_of(element: ET.Element) -> int:
        """Parse an ``<Element Index="[n]">``'s bracketed index as an int."""
        return int(element.get("Index", "").strip("[]"))

    def _elements(self) -> list[ET.Element]:
        """Return all ``<Element>`` children in document order."""
        return self._element.findall("Element")

    def __getitem__(self, index: int) -> TagValue:
        """Retrieve an element by its zero-based index.

        Args:
            index: The array index.

        Returns:
            A :class:`TagValueStructure` for struct-typed elements, or a
            :class:`TagValueScalar` for atomic elements.

        Raises:
            KeyError: If no element with the given index is found.
        """
        for element in self._elements():
            if self._index_of(element) == index:
                path = f"{self._operand_path}[{index}]"
                struct_child = element.find("Structure")
                if struct_child is not None:
                    return TagValueStructure(
                        struct_child,
                        self._member_def,
                        self._overrides,
                        path,
                        self._type_registry,
                    )
                return TagValueScalar(element, self._member_def, self._overrides, path)
        raise KeyError(index)

    def __iter__(self):
        """Iterate over element indices in document order."""
        for element in self._elements():
            yield self._index_of(element)

    def __len__(self) -> int:
        """Return the number of elements."""
        return len(self._elements())

    def __repr__(self) -> str:
        """Return a string representation showing the element count."""
        return f"TagValueArray(len={len(self)})"


def _build_root_value_node(
    element: ET.Element, overrides: _TagOverrides, type_registry: TypeRegistry
) -> TagValue | None:
    """Dispatch a tag's top-level ``Decorated`` value element.

    Unlike nested values, the top-level element is named ``DataValue``,
    ``Structure``, or ``Array`` (not ``DataValueMember``/``StructureMember``/
    ``ArrayMember``).

    Args:
        element: The ``Data[@Format='Decorated']``'s single child element.
        overrides: The tag's collected operand overrides.
        type_registry: Used by structure/array nodes to resolve members.

    Returns:
        The root :class:`TagValue` node, or ``None`` if the element tag is
        unrecognised.
    """
    if element.tag == "DataValue":
        return TagValueScalar(element, None, overrides, "")
    if element.tag == "Structure":
        return TagValueStructure(element, None, overrides, "", type_registry)
    if element.tag == "Array":
        return TagValueArray(element, None, overrides, "", type_registry)
    return None


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
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Tag name."""
        return self._get("Name")

    @property
    def tag_type(self) -> str:
        """Tag kind: ``"Base"``, ``"Alias"``, ``"Produced"``, or ``"Consumed"``."""
        return self._get("TagType")

    @property
    def data_type(self) -> str:
        """The tag's data type name."""
        return self._get("DataType")

    @property
    def radix(self) -> str:
        """Display radix, for atomic tags."""
        return self._get("Radix")

    @property
    def constant(self) -> bool:
        """Whether the tag is a constant."""
        return self._get("Constant") == "true"

    @property
    def external_access(self) -> str:
        """External access level (e.g. ``"Read/Write"``)."""
        return self._get("ExternalAccess")

    @property
    def usage(self) -> str:
        """Program-scoped parameter usage (``"Input"``/``"Output"``/``"Public"``)."""
        return self._get("Usage")

    @property
    def description(self) -> str:
        """Tag description text."""
        return self._get_description()

    # ------------------------------------------------------------------
    # Root-level limits (fallback, separate from the operand override maps
    # used for nested members)
    # ------------------------------------------------------------------

    @property
    def min(self) -> int | float | str | None:
        """The tag's own minimum value, if set directly on ``<Tag>``."""
        value = self._element.get("Min")
        return None if value is None else convert_numeric(value, self.data_type)

    @property
    def max(self) -> int | float | str | None:
        """The tag's own maximum value, if set directly on ``<Tag>``."""
        value = self._element.get("Max")
        return None if value is None else convert_numeric(value, self.data_type)

    # ------------------------------------------------------------------
    # Special tag kinds
    # ------------------------------------------------------------------

    @property
    def alias_for(self) -> str:
        """The referenced tag/member path, for ``Alias`` tags."""
        return self._get("AliasFor")

    @property
    def consume_info(self) -> dict[str, str] | None:
        """``ConsumeInfo`` attributes, for ``Consumed`` tags."""
        el = self._element.find("ConsumeInfo")
        return dict(el.attrib) if el is not None else None

    @property
    def produce_info(self) -> dict[str, str] | None:
        """``ProduceInfo`` attributes, for ``Produced`` tags."""
        el = self._element.find("ProduceInfo")
        return dict(el.attrib) if el is not None else None

    @property
    def message_parameters(self) -> dict[str, str] | None:
        """``MessageParameters`` attributes, for ``MESSAGE`` type tags."""
        el = self._element.find("Data[@Format='Message']/MessageParameters")
        return dict(el.attrib) if el is not None else None

    # ------------------------------------------------------------------
    # Value tree
    # ------------------------------------------------------------------

    @property
    def value(self) -> TagValue | None:
        """The tag's value tree root.

        Returns:
            ``None`` for ``Alias`` tags and ``MESSAGE``-type tags (no value
            data is exported for either). Otherwise a :class:`TagValueScalar`
            for atomic tags (including STRING-family tags, which use the
            ``Format="String"`` fallback since they have no ``Decorated``
            section), or a :class:`TagValueStructure`/:class:`TagValueArray`
            for UDT/AOI-instance or array tags.
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
            return _build_root_value_node(child, self._overrides, self._type_registry)
        string_data = self._element.find("Data[@Format='String']")
        if string_data is not None:
            cdata_el = string_data.find(CDATA_TAG)
            text = (
                cdata_el.text
                if cdata_el is not None and cdata_el.text
                else (string_data.text or "")
            )
            return TagValueScalar(
                string_data, None, self._overrides, "", raw_text=text, from_cdata=True
            )
        return None

    def __repr__(self) -> str:
        """Return a concise representation including the tag name and type."""
        return f"Tag({self.name!r}, {self.data_type!r})"


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

"""Add-On Instruction (AOI) definition parsing.

This module provides rich AOI inspection surfaces similar to program parsing:

- ``AOIDefinition`` for one AOI definition element.
- ``AOICollection`` for AOI lookup by name.
- ``AOILocalTag`` and ``AOILocalTagsCollection`` for AOI ``LocalTags`` with
  value drill-down (scalar/structure/array) reusing the tag-node model. Local
  tags are typed by static subclasses of ``AOILocalTag`` and the appropriate
  node class (e.g., ``AOILocalStructTag`` for ``StructNode``,
  ``AOILocalIntegerTag`` for ``IntegerNode``), mirroring the ``Tag`` subclasses
  in :mod:`py_l5x.parsers.tag`. This allows direct access to node properties
  like ``.members``, ``.value``, ``.elements`` without a ``.data`` indirection.

AOI routines reuse :class:`py_l5x.parsers.routine.RoutinesCollection`.
AOI parameters reuse :class:`py_l5x.parsers.datatype.AddOnParameters`.
"""

from __future__ import annotations

from typing import cast
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    bool_attr,
    str_attr,
)
from py_l5x.parsers.datatype import AddOnParameters
from py_l5x.parsers.routine import RoutinesCollection
from py_l5x.parsers.tag import (
    ArrayNode,
    AtomicNode,
    BoolNode,
    DateTimeNode,
    FloatNode,
    IntegerNode,
    StringNode,
    StructNode,
    TagNode,
    TimeNode,
    TypeRegistry,
    _describe_value_lines,
    _find_value_root,
    _RootMetadataMixin,
    _TagOverrides,
)


class AOILocalTag(_RootMetadataMixin, BaseElement):
    """A single ``<LocalTag>`` under an AOI definition (identity base).

    An identity base providing name, data_type, constant, external_access,
    description, and metadata hooks. Subclasses add value-tree node functionality.

    Args:
        element: The XML ``<LocalTag>`` element.
        type_registry: Shared type registry for resolving data type metadata.
    """

    name = str_attr("Name", doc="Local tag name.")
    data_type = str_attr("DataType", doc="The local tag's data type name.")
    constant = bool_attr(
        "Constant", default=False, doc="Whether the local tag is constant."
    )
    external_access = str_attr(
        "ExternalAccess",
        doc='External access level (commonly "None" for AOI locals).',
    )
    description = CDataField(
        "Description", attr_fallback="Description", doc="Local tag description text."
    )

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        """Initialize an AOI local tag identity wrapper.

        Args:
            element: The XML ``<LocalTag>`` element.
            type_registry: Shared type registry for resolving data type metadata.
        """
        super().__init__(element)
        self._type_registry = type_registry
        self._overrides = _TagOverrides(element)

    @property
    def element(self) -> ET.Element:
        """The wrapped ``<LocalTag>`` XML element."""
        return self._element

    def _header(self) -> str:
        """Return the single-line identity header for :meth:`describe`.

        Extends :meth:`BaseElement._header` to also include the data type, so a
        local tag stays identifiable in :meth:`describe` just as it is in
        :meth:`__repr__`.
        """
        return f"{type(self).__name__}({self.name!r}, {self.data_type!r})"

    def __repr__(self) -> str:
        """Return the full :meth:`describe` text for this local tag."""
        return self.describe()

    def _describe_lines(self) -> list[str]:
        """Return value, member and element lines for value-tree local tags.

        Returns:
            Formatted description lines (empty for identity-only local tags).
        """
        return _describe_value_lines(self)


class _AOILocalValueTag(AOILocalTag):
    """Base for AOI local tags that are also their root value node (private).

    Tags that carry a value tree (scalars, structures, arrays) inherit from both
    AOILocalTag and a node class. This base class initializes both parent classes.
    """

    def __init__(
        self,
        element: ET.Element,
        type_registry: TypeRegistry,
        value_element: ET.Element,
    ) -> None:
        """Initialize an AOI local tag with a value node.

        Args:
            element: The ``<LocalTag>`` element.
            type_registry: Used to resolve value tree members.
            value_element: The ``DefaultData[@Format='Decorated']`` child
                element, or the ``DefaultData[@Format='String']`` element for
                STRING-family local tags.
        """
        # AOILocalTag.__init__ sets the identity state. Its super() chain doesn't
        # reach TagNode, so the node base is initialized explicitly below; it
        # re-sets _overrides/_type_registry to the same values, which is harmless.
        AOILocalTag.__init__(self, element, type_registry)
        TagNode.__init__(
            cast(TagNode, self),
            value_element,
            None,
            self._overrides,
            "",
            type_registry,
        )


class AOILocalBoolTag(_AOILocalValueTag, BoolNode):
    """An AOI local tag whose value is a BOOL (1-bit) atomic type."""


class AOILocalIntegerTag(_AOILocalValueTag, IntegerNode):
    """An AOI local tag whose value is an integer atomic type."""


class AOILocalFloatTag(_AOILocalValueTag, FloatNode):
    """An AOI local tag whose value is a floating-point type (REAL, LREAL)."""


class AOILocalTimeTag(_AOILocalValueTag, TimeNode):
    """An AOI local tag whose value is a time-valued atomic type."""


class AOILocalDateTimeTag(_AOILocalValueTag, DateTimeNode):
    """An AOI local tag whose value is a DATETIME atomic type."""


class AOILocalAtomicTag(_AOILocalValueTag, AtomicNode):
    """An AOI local tag whose value is an atomic type with no specific node."""


class AOILocalStringTag(_AOILocalValueTag, StringNode):
    """An AOI local tag whose value is a STRING type."""


class AOILocalStructTag(_AOILocalValueTag, StructNode):
    """An AOI local tag whose value is a structure (UDT or AOI-typed) value."""


class AOILocalArrayTag(_AOILocalValueTag, ArrayNode):
    """An AOI local tag whose value is an array of elements."""


# Mapping from node class to AOI local value tag class
_AOI_LOCAL_TAG_CLASSES: dict[type[TagNode], type[_AOILocalValueTag]] = {
    BoolNode: AOILocalBoolTag,
    IntegerNode: AOILocalIntegerTag,
    FloatNode: AOILocalFloatTag,
    TimeNode: AOILocalTimeTag,
    DateTimeNode: AOILocalDateTimeTag,
    AtomicNode: AOILocalAtomicTag,
    StringNode: AOILocalStringTag,
    StructNode: AOILocalStructTag,
    ArrayNode: AOILocalArrayTag,
}


def _make_aoi_local_tag(
    element: ET.Element, type_registry: TypeRegistry
) -> AOILocalTag:
    """Factory function to create the appropriate AOI local tag subclass.

    Dispatches to a plain AOILocalTag if no value data is found, or to a
    typed local tag class (see ``_AOI_LOCAL_TAG_CLASSES``) if value data exists.

    Args:
        element: The ``<LocalTag>`` element.
        type_registry: Used to resolve value tree members.

    Returns:
        An instance of the appropriate AOI local tag subclass.
    """
    # Find value root (String or Decorated with child) using DefaultData
    root = _find_value_root(element, "DefaultData", type_registry)
    if root is None:
        # No value data
        return AOILocalTag(element, type_registry)

    # Value data found
    node_cls, value_el = root
    tag_cls = _AOI_LOCAL_TAG_CLASSES.get(node_cls, AOILocalAtomicTag)
    return tag_cls(element, type_registry, value_el)


class AOILocalTagsCollection(BaseCollection[AOILocalTag]):
    """A ``Mapping`` over every AOI ``<LocalTag>`` by name.

    Args:
        aoi_element: The XML ``<AddOnInstructionDefinition>`` element containing
            the LocalTags.
        type_registry: Shared type registry for resolving data type metadata.
    """

    def __init__(self, aoi_element: ET.Element, type_registry: TypeRegistry) -> None:
        """Index the AOI's ``LocalTags`` by name.

        Args:
            aoi_element: The XML ``<AddOnInstructionDefinition>`` element containing
                the LocalTags.
            type_registry: Shared type registry for resolving data type metadata.
        """
        super().__init__(
            aoi_element,
            "LocalTags/LocalTag",
            _make_aoi_local_tag,
            item_args=(type_registry,),
        )


class AOIDefinition(BaseElement):
    """One ``<AddOnInstructionDefinition>`` element.

    Args:
        element: The XML ``<AddOnInstructionDefinition>`` element.
        type_registry: Shared type registry for resolving data type metadata.
    """

    name = str_attr("Name", doc="AOI definition name.")
    description = CDataField("Description", doc="AOI description text.")
    revision = str_attr("Revision", doc="AOI revision string.")
    execute_prescan = bool_attr(
        "ExecutePrescan", default=False, doc="Whether AOI executes on prescan."
    )
    execute_postscan = bool_attr(
        "ExecutePostscan", default=False, doc="Whether AOI executes on postscan."
    )
    execute_enable_in_false = bool_attr(
        "ExecuteEnableInFalse",
        default=False,
        doc="Whether AOI executes when enable-in is false.",
    )
    created_date = str_attr("CreatedDate", doc="Creation timestamp.")
    created_by = str_attr("CreatedBy", doc="Author at creation.")
    edited_date = str_attr("EditedDate", doc="Last edit timestamp.")
    edited_by = str_attr("EditedBy", doc="Last editor.")
    software_revision = str_attr(
        "SoftwareRevision", doc="Studio/Logix software revision string."
    )

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        """Initialise from an ``<AddOnInstructionDefinition>`` XML element.

        Args:
            element: The XML ``<AddOnInstructionDefinition>`` element to wrap.
            type_registry: Shared type registry for resolving data type metadata.
        """
        super().__init__(element)
        self._type_registry = type_registry

    @property
    def parameters(self) -> AddOnParameters:
        """AOI parameters keyed by name.

        Returns:
            An :class:`AddOnParameters` instance containing all AOI parameters.
        """
        return AddOnParameters(self._element)

    @property
    def local_tags(self) -> AOILocalTagsCollection:
        """AOI local tags keyed by name.

        Returns:
            An :class:`AOILocalTagsCollection` containing all AOI local tags.
        """
        return AOILocalTagsCollection(self._element, self._type_registry)

    @property
    def routines(self) -> RoutinesCollection:
        """AOI routines keyed by routine name.

        Returns:
            A :class:`RoutinesCollection` containing all AOI routines.
        """
        return RoutinesCollection(self._element)

    def logic_text(self) -> str:
        """Render AOI routine logic as a quick-reference text block.

        Returns:
            A multi-line string containing the AOI name and all routine logic
            text.
        """
        lines: list[str] = [f"AOI: {self.name}"]
        for routine in self.routines.values():
            lines.append("")
            lines.append(f"Routine: {routine.name} ({routine.type_})")
            text = routine.as_text()
            if text:
                lines.extend(text.splitlines())
        return "\n".join(lines)

    def print_logic_text(self) -> str:
        """Print and return :meth:`logic_text` for quick interactive inspection.

        Returns:
            The multi-line logic text that was printed.
        """
        text = self.logic_text()
        print(text)
        return text

    def __repr__(self) -> str:
        """Return a concise representation including the AOI name."""
        return f"{type(self).__name__}({self.name!r})"


class AOICollection(BaseCollection[AOIDefinition]):
    """A ``Mapping`` over every ``<AddOnInstructionDefinition>`` by name.

    Args:
        controller_element: The root XML element of the controller/project.
        type_registry: Shared type registry for resolving data type metadata.
    """

    def __init__(
        self, controller_element: ET.Element, type_registry: TypeRegistry
    ) -> None:
        """Index the AOI definitions by name.

        Args:
            controller_element: The root XML element of the controller/project.
            type_registry: Shared type registry for resolving data type metadata.
        """
        super().__init__(
            controller_element,
            "AddOnInstructionDefinitions/AddOnInstructionDefinition",
            AOIDefinition,
            item_args=(type_registry,),
        )

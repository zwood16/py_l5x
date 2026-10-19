"""Add-On Instruction (AOI) definition parsing.

This module provides rich AOI inspection surfaces similar to program parsing:

- ``AddOnInstructionDefinition`` for one AOI definition element.
- ``AddOnInstructionDefinitionsCollection`` for AOI lookup by name.
- ``AOILocalTag`` and ``AOILocalTagsCollection`` for AOI ``LocalTags`` with
  value drill-down (scalar/structure/array) reusing the tag-node model. Local
  tags are dynamically typed via ``_aoi_local_tag_class`` to subclass both
  ``AOILocalTag`` and the appropriate node class (e.g., ``StructNode``,
  ``IntegerNode``), allowing direct access to node properties like ``.members``,
  ``.value``, ``.elements`` without a ``.data`` indirection.

AOI routines reuse :class:`py_l5x.parsers.routine.RoutinesCollection`.
AOI parameters reuse :class:`py_l5x.parsers.datatype.AddOnParameters`.
"""

from __future__ import annotations

import functools
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
    TagNode,
    TypeRegistry,
    _describe_value_lines,
    _find_value_root,
    _TagOverrides,
)


class AOILocalTag(BaseElement):
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
    description = CDataField("Description", doc="Local tag description text.")

    #: Attributes backed by a plain @property rather than a declared field
    #: (Radix, Dimensions are on value nodes, not the local tag element itself)
    _DYNAMIC_KEYS: frozenset[str] = frozenset(
        {"Radix", "Dimensions", "Min", "Max", "ExternalLogging"}
    )

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry
        self._overrides = _TagOverrides(element)

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by declared fields or dynamic properties."""
        extras = super().extra_attributes
        return {k: v for k, v in extras.items() if k not in self._DYNAMIC_KEYS}

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
        """Return a concise representation including the local tag name and type."""
        return f"{type(self).__name__}({self.name!r}, {self.data_type!r})"

    def describe(self) -> str:
        """Extend :meth:`BaseElement.describe` to include value/member/element metadata.

        Includes identity info from super(), then value, members, and elements lines
        if applicable (for value-tree typed local tags).
        """
        lines = [super().describe()]
        lines.extend(_describe_value_lines(self))
        return "\n".join(lines)


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
            value_element: The ``DefaultData[@Format='Decorated']`` child element, or the
                ``DefaultData[@Format='String']`` element for STRING-family local tags.
        """
        # Initialize AOILocalTag first (for MRO)
        AOILocalTag.__init__(self, element, type_registry)
        # Call the concrete node class's __init__ via super(BaseElement, self).
        # This resolves to the first TagNode subclass in the MRO after BaseElement,
        # allowing StructNode/ArrayNode to initialize their caches correctly.
        super(BaseElement, self).__init__(
            value_element, None, self._overrides, "", type_registry
        )


@functools.cache
def _aoi_local_tag_class(node_cls: type[TagNode]) -> type[_AOILocalValueTag]:
    """Factory for typed AOI local tag classes, cached by node class.

    Returns a dynamically-created class combining _AOILocalValueTag with the
    specified node class. Caching ensures that multiple local tags with the same
    underlying node type use the same class object (so type() comparisons work).

    Args:
        node_cls: The TagNode subclass (e.g., BoolNode, StructNode).

    Returns:
        A new _AOILocalValueTag subclass combining the given node class.
    """
    return type(
        f"AOILocal{node_cls.__name__.removesuffix('Node')}Tag",
        (_AOILocalValueTag, node_cls),
        {
            "__module__": __name__,
            "__doc__": f"An AOI local tag whose value is a :class:`{node_cls.__name__}`.",
        },
    )


def _make_aoi_local_tag(
    element: ET.Element, type_registry: TypeRegistry
) -> AOILocalTag:
    """Factory function to create the appropriate AOI local tag subclass.

    Dispatches to a plain AOILocalTag if no value data is found, or to a
    typed local tag class (_AOILocalValueTag + node class) if value data exists.

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
    tag_cls = _aoi_local_tag_class(node_cls)
    return tag_cls(element, type_registry, value_el)


class AOILocalTagsCollection(BaseCollection[AOILocalTag]):
    """A ``Mapping`` over every AOI ``<LocalTag>`` by name.

    Args:
        aoi_element: The XML ``<AddOnInstructionDefinition>`` element containing
            the LocalTags.
        type_registry: Shared type registry for resolving data type metadata.
    """

    def __init__(self, aoi_element: ET.Element, type_registry: TypeRegistry) -> None:
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
        return f"AddOnInstructionDefinition({self.name!r})"


class AOICollection(BaseCollection[AOIDefinition]):
    """A ``Mapping`` over every ``<AddOnInstructionDefinition>`` by name.

    Args:
        controller_element: The root XML element of the controller/project.
        type_registry: Shared type registry for resolving data type metadata.
    """

    def __init__(
        self, controller_element: ET.Element, type_registry: TypeRegistry
    ) -> None:
        super().__init__(
            controller_element,
            "AddOnInstructionDefinitions/AddOnInstructionDefinition",
            AOIDefinition,
            item_args=(type_registry,),
        )

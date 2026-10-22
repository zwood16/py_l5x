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
- ``AOIParameter`` for AOI ``<Parameter>`` elements. Input/Output parameters
  with a value tree are typed by static subclasses (``AOIParameterBoolTag``,
  ``AOIParameterIntegerTag``, ``AOIParameterFloatTag``, ``AOIParameterTimeTag``,
  ``AOIParameterDateTimeTag``, ``AOIParameterAtomicTag``) that mirror the
  ``AOILocal*Tag`` classes. InOut parameters have no value tree and remain
  plain ``AOIParameter`` instances.

AOI routines reuse :class:`py_l5x.parsers.routine.RoutinesCollection`.
AOI parameters reuse :class:`py_l5x.parsers.aoi.AOIParametersCollection`.
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


class _AOIDefinitionTag(_RootMetadataMixin, BaseElement):
    """Identity base shared by AOI ``<LocalTag>`` and ``<Parameter>`` elements.

    Both elements share the same XML shape: a Name/DataType/ExternalAccess
    identity, a Description, and operand-qualified ``Comments``/
    ``EngineeringUnits``/``State0s``/``State1s`` metadata. Metadata hooks come
    from :class:`~py_l5x.parsers.tag._RootMetadataMixin`, which reads the
    un-operanded entries on the element itself.

    Args:
        element: The ``<LocalTag>`` or ``<Parameter>`` XML element.
        type_registry: Shared type registry for resolving data type metadata.
    """

    name = str_attr("Name", doc="Name of the AOI local tag or parameter.")
    data_type = str_attr(
        "DataType", doc="Data type name of the AOI local tag or parameter."
    )
    constant = bool_attr(
        "Constant",
        default=False,
        doc="Whether the AOI local tag or parameter is constant.",
    )
    external_access = str_attr(
        "ExternalAccess",
        doc='External access level (e.g. "Read/Write", "Read Only", "None").',
    )
    description = CDataField(
        "Description",
        attr_fallback="Description",
        doc="Description text of the AOI local tag or parameter.",
    )

    def __init__(
        self, element: ET.Element, type_registry: TypeRegistry | None = None
    ) -> None:
        """Initialize the AOI identity wrapper.

        Args:
            element: The ``<LocalTag>`` or ``<Parameter>`` XML element.
            type_registry: Shared type registry for resolving data type metadata.
        """
        super().__init__(element)
        self._type_registry = type_registry
        self._overrides = _TagOverrides(element)

    @property
    def element(self) -> ET.Element:
        """The wrapped XML element (``<LocalTag>`` or ``<Parameter>``)."""
        return self._element

    def _header(self) -> str:
        """Return the single-line identity header for :meth:`describe`.

        Extends :meth:`BaseElement._header` to also include the data type, so
        the element stays identifiable in :meth:`describe` just as it is in
        :meth:`__repr__`.
        """
        return f"{type(self).__name__}({self.name!r}, {self.data_type!r})"

    def __repr__(self) -> str:
        """Return the full :meth:`describe` text for this element."""
        return self.describe()

    def _describe_lines(self) -> list[str]:
        """Return value, member and element lines for value-tree elements.

        Returns:
            Formatted description lines (empty for identity-only elements).
        """
        return _describe_value_lines(self)


def _init_aoi_value_node(
    tag: _AOIDefinitionTag,
    element: ET.Element,
    type_registry: TypeRegistry | None,
    value_element: ET.Element,
) -> None:
    """Initialise an AOI identity wrapper that is also its own value node.

    Shared by every AOI class that carries a value tree (local tags, and
    parameters once they gain typed value subclasses). The identity state is set
    first; the node base is then initialised explicitly, because the identity
    ``super()`` chain stops at :class:`BaseElement` and never reaches
    :class:`TagNode`. The node base re-uses the identity's ``_overrides``.

    Args:
        tag: The instance being initialised (identity base + node base).
        element: The ``<LocalTag>``/``<Parameter>`` element.
        type_registry: Used to resolve value tree members.
        value_element: The ``DefaultData[@Format='Decorated']`` child element,
            or the ``DefaultData[@Format='String']`` element for STRING-family
            tags.
    """
    _AOIDefinitionTag.__init__(tag, element, type_registry)
    TagNode.__init__(
        cast(TagNode, tag),
        value_element,
        None,
        tag._overrides,
        "",
        type_registry,
    )


class AOILocalTag(_AOIDefinitionTag):
    """A single ``<LocalTag>`` under an AOI definition (identity base).

    An identity base providing name, data_type, constant, external_access,
    description, and metadata hooks. Subclasses add value-tree node functionality.

    Args:
        element: The XML ``<LocalTag>`` element.
        type_registry: Shared type registry for resolving data type metadata.
    """


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
        _init_aoi_value_node(self, element, type_registry, value_element)


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
    def parameters(self) -> AOIParametersCollection:
        """AOI parameters keyed by name.

        Returns:
            An :class:`AOIParametersCollection` instance containing all AOI parameters.
        """
        return AOIParametersCollection(self._element, self._type_registry)

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


# ------------------------------------------------------------------
# AOI parameters
# ------------------------------------------------------------------

# Similar to data types, but derrived from non-InOut parameters
# Note: actual AOI definitions include all params, not just those that
# appear in the tag browser


class AOIParameter(_AOIDefinitionTag):
    """A single ``<Parameter>`` element within an ``<AddOnInstructionDefinition>``.

    Shares its identity, description and metadata hooks with
    :class:`AOILocalTag` via :class:`_AOIDefinitionTag`. Adds the parameter-only
    usage/radix/required/visible/external-logging attributes.

    Input/Output parameters with a value tree are created as typed subclasses
    (see :func:`_make_aoi_parameter`); this class is also used directly for
    InOut parameters and for any parameter without a usable value tree.

    Args:
        element: The ``<Parameter>`` element from a parsed L5X tree.
        type_registry: Shared type registry for resolving data type metadata.
    """

    tag_type = str_attr(
        "TagType", doc='Tag kind of the parameter (e.g. "Base"), as exported.'
    )
    usage = str_attr(
        "Usage", doc='Usage of the parameter (e.g., "Input", "Output", "InOut").'
    )
    radix = str_attr("Radix", doc="Display radix.")
    required = bool_attr(
        "Required", default=False, doc="Whether the parameter is required."
    )
    visible = bool_attr(
        "Visible",
        default=False,
        doc="Whether the parameter is visible in Logix Designer.",
    )
    external_logging = bool_attr(
        "ExternalLogging",
        doc="Whether external logging is enabled for this parameter.",
    )

    @property
    def is_inout(self) -> bool:
        """Whether this parameter uses InOut usage."""
        return self.usage == "InOut"


class _AOIParameterValueTag(AOIParameter):
    """Base for AOI parameters that are also their root value node (private).

    Mirrors :class:`_AOILocalValueTag`: the identity comes from
    :class:`AOIParameter`, and the concrete subclass mixes in the node class
    that provides the value tree.
    """

    def __init__(
        self,
        element: ET.Element,
        type_registry: TypeRegistry | None,
        value_element: ET.Element,
    ) -> None:
        """Initialize an AOI parameter with a value node.

        Args:
            element: The ``<Parameter>`` element.
            type_registry: Used to resolve value tree members.
            value_element: The ``DefaultData[@Format='Decorated']`` child element.
        """
        _init_aoi_value_node(self, element, type_registry, value_element)


class AOIParameterBoolTag(_AOIParameterValueTag, BoolNode):
    """An AOI Input/Output parameter whose value is BOOL."""


class AOIParameterIntegerTag(_AOIParameterValueTag, IntegerNode):
    """An AOI Input/Output parameter whose value is an integer type."""

    # AOIParameter.min/max precede IntegerNode in the MRO, so they would shadow
    # the node versions. Calling the node property's getter here restores the
    # typed int | None contract (the base version may return a raw str).

    @property
    def min(self) -> int | None:
        """Declared minimum as an ``int``, or ``None`` if not set."""
        return IntegerNode.min.__get__(self)

    @property
    def max(self) -> int | None:
        """Declared maximum as an ``int``, or ``None`` if not set."""
        return IntegerNode.max.__get__(self)


class AOIParameterFloatTag(_AOIParameterValueTag, FloatNode):
    """An AOI Input/Output parameter whose value is REAL or LREAL."""

    # Same MRO shadowing as AOIParameterIntegerTag; keeps the float | None type.

    @property
    def min(self) -> float | None:
        """Declared minimum as a ``float``, or ``None`` if not set."""
        return FloatNode.min.__get__(self)

    @property
    def max(self) -> float | None:
        """Declared maximum as a ``float``, or ``None`` if not set."""
        return FloatNode.max.__get__(self)


class AOIParameterTimeTag(_AOIParameterValueTag, TimeNode):
    """An AOI Input/Output parameter whose value is a TIME-family literal."""


class AOIParameterDateTimeTag(_AOIParameterValueTag, DateTimeNode):
    """An AOI Input/Output parameter whose value is a DT/LDT literal."""


class AOIParameterAtomicTag(_AOIParameterValueTag, AtomicNode):
    """An AOI Input/Output parameter whose atomic type has no specific node."""


# Mapping from node class to AOI parameter value tag class. STRING, structure
# and array values are intentionally absent: only InOut parameters may carry
# them, and InOut parameters never get a typed value class.
_AOI_PARAMETER_TAG_CLASSES: dict[type[TagNode], type[_AOIParameterValueTag]] = {
    BoolNode: AOIParameterBoolTag,
    IntegerNode: AOIParameterIntegerTag,
    FloatNode: AOIParameterFloatTag,
    TimeNode: AOIParameterTimeTag,
    DateTimeNode: AOIParameterDateTimeTag,
    AtomicNode: AOIParameterAtomicTag,
}


def _make_aoi_parameter(
    element: ET.Element, type_registry: TypeRegistry | None
) -> AOIParameter:
    """Factory function to create the appropriate AOI parameter subclass.

    InOut parameters, parameters without a value root, and parameters whose
    value node has no entry in ``_AOI_PARAMETER_TAG_CLASSES`` are returned as
    a plain :class:`AOIParameter`.

    Args:
        element: The ``<Parameter>`` element.
        type_registry: Used to resolve value tree members. Optional; atomic
            value nodes do not need it.

    Returns:
        An instance of the appropriate AOI parameter subclass.
    """
    if element.get("Usage") == "InOut":
        return AOIParameter(element, type_registry)

    root = _find_value_root(element, "DefaultData", type_registry)
    if root is None:
        return AOIParameter(element, type_registry)

    node_cls, value_el = root
    tag_cls = _AOI_PARAMETER_TAG_CLASSES.get(node_cls)
    if tag_cls is None:
        return AOIParameter(element, type_registry)
    return tag_cls(element, type_registry, value_el)


class AOIParametersCollection(BaseCollection[AOIParameter]):
    """A collection of parameters for a specific AOI definition.

    Args:
        aoi_element: The ``<AddOnInstructionDefinition>`` element.
        type_registry: Shared type registry passed to each parameter. Optional;
            parameter identity and metadata do not require it.
    """

    def __init__(
        self, aoi_element: ET.Element, type_registry: TypeRegistry | None = None
    ) -> None:
        super().__init__(
            aoi_element,
            "Parameters/Parameter",
            _make_aoi_parameter,
            item_args=(type_registry,),
        )

    @property
    def datatype_members(self) -> dict[str, AOIParameter]:
        """Input and Output parameters of the AOI, excluding InOut usage.

        These are the tags that appear as the tags members of the AOI instance
        in the Logix Tag Browser - excludes InOut parameters.

        Returns:
            Dictionary mapping parameter names to ``AOIParameter``.
        """
        return {name: p for name, p in self.items() if not p.is_inout}


class AOIDataTypesCollection(BaseCollection[AOIParametersCollection]):
    """A ``Mapping`` over every ``<AddOnInstructionDefinition>``'s parameters.

    Args:
        controller_element: The ``<Controller>`` element whose
            ``AddOnInstructionDefinitions/AddOnInstructionDefinition`` children form
            this collection.
    """

    def __init__(self, controller_element: ET.Element) -> None:
        """Initialise from a root XML element.

        Args:
            controller_element: The ``<Controller>`` element whose
                ``AddOnInstructionDefinitions/AddOnInstructionDefinition`` children form
                this collection.
        """
        super().__init__(
            controller_element,
            "AddOnInstructionDefinitions/AddOnInstructionDefinition",
            AOIParametersCollection,
        )

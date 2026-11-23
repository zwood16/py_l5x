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

A source-protected AOI is saved by Studio 5000 not as an
``<AddOnInstructionDefinition>`` but as ``<EncodedData EncodedType=
"AddOnInstructionDefinition" Name=..>`` under the same
``<AddOnInstructionDefinitions>`` container. ``ProtectedAOI`` wraps it and
``ProtectedAOICollection`` (``project.protected_aois``) lists them. A real v37
export carries a few attributes, a ``RevisionNote`` and the complete
``Parameters`` (read through the normal parameter wrappers); the encoded
payload follows as text and is never interpreted. Only ``Name`` and
``EncodedType`` are required, so everything else is read defensively.
``project.aois`` deliberately holds definitions only. (Not to be confused with
``AOIDefinition._PROTECTED_CHILDREN``, which handles ``EncodedData`` *inside* a
definition.) Encoded *routines* are the program-level counterpart
(``ProtectedRoutine`` in :mod:`py_l5x.parsers.routine`).

AOI routines reuse :class:`py_l5x.parsers.routine.RoutinesCollection`.
``AOIParametersCollection`` maps one AOI's parameters by name, and
``AOIDataTypesCollection`` maps every AOI name to its parameters; the latter
feeds the :class:`~py_l5x.parsers.tag.TypeRegistry` used to resolve AOI-typed
tag members.
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING, NamedTuple, cast
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    bool_attr,
    str_attr,
)
from py_l5x.parsers.datatype import find_type_users
from py_l5x.parsers.names import validate_new_name
from py_l5x.parsers.routine import RoutinesCollection
from py_l5x.parsers.schema import insert_child, insert_child_at, remove_child
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
from py_l5x.parsers.utils import CDATA_TAG

if TYPE_CHECKING:
    from py_l5x.build.specs import AOISpec


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

    #: Child elements ``to_spec`` can represent.
    _SPEC_CHILDREN = frozenset(
        {
            "Description",
            "RevisionNote",
            "AdditionalHelpText",
            "Parameters",
            "LocalTags",
            "Routines",
            "Dependencies",
        }
    )

    #: Elements that mark a protected (encrypted or sealed) AOI. Their payload
    #: cannot be read back, so ``to_spec`` refuses such definitions.
    _PROTECTED_CHILDREN = frozenset(
        {"EncodedData", "EncryptionInfo", "EncryptionConfig"}
    )

    def to_spec(self) -> AOISpec:
        """Convert this definition to a spec that rebuilds it.

        ``EnableIn`` and ``EnableOut`` are dropped (the builder re-adds them),
        as are L5K blocks. Descriptions, comments and code are read as raw
        CDATA text. A default equal to the type's default is stored as
        ``None``, as are ``required`` and ``visible`` equal to their derived
        values (``InOut``: both true; Input/Output: required false, visible
        equal to required), a radix and an external access equal to the default,
        and ``Execute*`` flags equal to "a routine of that name exists";
        anything else is kept. ``metadata`` gets every other attribute
        (``Class``, dates, ...) except ``Use``.

        Returns:
            An :class:`~py_l5x.build.specs.AOISpec`.

        Raises:
            ValueError: For a protected or encrypted AOI, an unsupported
                child element, a non-RLL/ST routine, a multi-dimensional or
                constant parameter, or an unreadable parameter.
        """
        from py_l5x.build.aoi import python_default
        from py_l5x.build.specs import (
            AOISpec,
            LocalTagSpec,
            ParameterSpec,
            RoutineSpec,
            RungSpec,
        )
        from py_l5x.parsers.atomic_types import ATOMIC_TYPES, default_radix
        from py_l5x.parsers.migrate import _raw_cdata

        element = self._element
        for child in element:
            if child.tag in self._PROTECTED_CHILDREN:
                raise ValueError(
                    f"AOI {self.name!r} is protected ({child.tag}); "
                    "its definition cannot be read"
                )
            if child.tag not in self._SPEC_CHILDREN:
                raise ValueError(f"AOI {self.name!r}: unsupported element {child.tag}")

        def text(parent: ET.Element, tag: str) -> str:
            found = parent.find(tag)
            return _raw_cdata(found) if found is not None else ""

        def plain(parent: ET.Element, container: str, tag: str) -> str:
            for entry in parent.findall(f"{container}/{tag}"):
                if "Operand" not in entry.attrib:
                    return _raw_cdata(entry)
            return ""

        def dimension(item: ET.Element) -> int:
            sizes = item.get("Dimensions", "").replace(",", " ").split()
            if len(sizes) > 1:
                raise ValueError(f"{item.get('Name')!r}: multi-dimensional arrays")
            return int(sizes[0]) if sizes else 0

        registry = self._type_registry
        parameters = []
        for pe in element.findall("Parameters/Parameter"):
            name = pe.get("Name", "")
            if name in ("EnableIn", "EnableOut"):
                continue
            if pe.get("Constant") == "true":
                raise ValueError(f"parameter {name!r}: constant parameters")
            usage = pe.get("Usage", "Input")
            data_type = pe.get("DataType", "")
            radix = pe.get("Radix")
            if radix is not None and radix == default_radix(data_type):
                radix = None
            access = pe.get("ExternalAccess")
            if access == {"Input": "Read/Write", "Output": "Read Only"}.get(usage):
                access = None
            default = None
            if usage != "InOut":
                node = self.parameters[name]
                if hasattr(node, "to_python"):
                    value = node.to_python()
                    base = python_default(
                        data_type,
                        0,
                        pe.get("Radix") or default_radix(data_type),
                        registry,
                    )
                    default = None if value == base else value
            required = pe.get("Required") == "true"
            visible = pe.get("Visible") == "true"
            derived_required = usage == "InOut"
            derived_visible = usage == "InOut" or required
            parameters.append(
                ParameterSpec(
                    name=name,
                    data_type=data_type,
                    usage=usage,
                    required=None if required == derived_required else required,
                    visible=None if visible == derived_visible else visible,
                    dimension=dimension(pe),
                    description=text(pe, "Description"),
                    default=default,
                    radix=radix,
                    external_access=access,
                    engineering_unit=plain(pe, "EngineeringUnits", "EngineeringUnit"),
                    min=pe.get("Min"),
                    max=pe.get("Max"),
                    state0=plain(pe, "State0s", "State0"),
                    state1=plain(pe, "State1s", "State1"),
                    operand_comments={
                        c.get("Operand", ""): _raw_cdata(c)
                        for c in pe.findall("Comments/Comment")
                    },
                )
            )

        local_tags = []
        for le in element.findall("LocalTags/LocalTag"):
            name = le.get("Name", "")
            data_type = le.get("DataType", "")
            size = dimension(le)
            radix = le.get("Radix")
            if radix is not None and radix == default_radix(data_type):
                radix = None
            default = None
            node = self.local_tags[name]
            if hasattr(node, "to_python"):
                value = node.to_python()
                base_radix = le.get("Radix") or (
                    default_radix(data_type) if data_type in ATOMIC_TYPES else None
                )
                base = python_default(data_type, size, base_radix, registry)
                default = None if value == base else value
            local_tags.append(
                LocalTagSpec(
                    name=name,
                    data_type=data_type,
                    dimension=size,
                    description=text(le, "Description"),
                    default=default,
                    radix=radix,
                    external_access=le.get("ExternalAccess", "Read/Write"),
                )
            )

        routines = []
        for re_ in element.findall("Routines/Routine"):
            kind = re_.get("Type", "")
            if kind not in ("RLL", "ST"):
                raise ValueError(
                    f"routine {re_.get('Name')!r}: unsupported type {kind}"
                )
            routines.append(
                RoutineSpec(
                    name=re_.get("Name", ""),
                    type_=kind,
                    rungs=[
                        RungSpec(text(r, "Text"), text(r, "Comment"))
                        for r in re_.findall("RLLContent/Rung")
                    ],
                    lines=[_raw_cdata(line) for line in re_.findall("STContent/Line")],
                    description=text(re_, "Description"),
                )
            )

        present = {r.name for r in routines}

        def flag(attribute: str, routine: str) -> bool | None:
            value = element.get(attribute) == "true"
            return None if value == (routine in present) else value

        known = {
            "Name",
            "Revision",
            "Vendor",
            "ExecutePrescan",
            "ExecutePostscan",
            "ExecuteEnableInFalse",
            "Use",
        }
        return AOISpec(
            name=self.name,
            parameters=parameters,
            local_tags=local_tags,
            routines=routines,
            revision=element.get("Revision", ""),
            revision_note=text(element, "RevisionNote"),
            description=text(element, "Description"),
            vendor=element.get("Vendor", ""),
            execute_prescan=flag("ExecutePrescan", "Prescan"),
            execute_postscan=flag("ExecutePostscan", "Postscan"),
            execute_enable_in_false=flag("ExecuteEnableInFalse", "EnableInFalse"),
            additional_help_text=text(element, "AdditionalHelpText"),
            metadata={k: v for k, v in element.attrib.items() if k not in known},
        )

    def __repr__(self) -> str:
        """Return a concise representation including the AOI name."""
        return f"{type(self).__name__}({self.name!r})"


#: ``EncodedType`` of an encoded Add-On Instruction definition.
PROTECTED_AOI_TYPE = "AddOnInstructionDefinition"

#: XPath (from ``<Controller>``) of the encoded AOI elements.
PROTECTED_AOI_XPATH = (
    f"AddOnInstructionDefinitions/EncodedData[@EncodedType='{PROTECTED_AOI_TYPE}']"
)


class ProtectedAOI(BaseElement):
    """A source-protected AOI: an ``<EncodedData>`` element.

    Studio 5000 (v37) writes the attributes below, a ``RevisionNote`` and the
    full ``Parameters`` definitions as readable children, and the encoded
    payload as the text after ``</Parameters>``. The payload is not
    interpreted. Only ``Name`` and ``EncodedType`` are required here; every
    other attribute and child is read if present and has an empty or ``None``
    default otherwise (``Description``, ``Vendor`` and ``Dependencies`` were
    not seen in a real export but are handled if they appear).

    Args:
        element: The XML ``<EncodedData EncodedType="AddOnInstructionDefinition">``
            element.
        type_registry: Shared type registry for resolving data type metadata
            (optional; parameter identity does not need it).
    """

    name = str_attr("Name", doc="AOI name.")
    encoded_type = str_attr("EncodedType", doc="Encoded component type.")
    class_ = str_attr("Class", default=None, doc="AOI class, if given.")
    revision = str_attr("Revision", default=None, doc="AOI revision, if given.")
    vendor = str_attr("Vendor", default=None, doc="AOI vendor, if given.")
    signature_id = str_attr("SignatureID", default=None, doc="Signature ID, if given.")
    signature_timestamp = str_attr(
        "SignatureTimestamp", default=None, doc="Signature timestamp, if given."
    )
    edited_date = str_attr("EditedDate", default=None, doc="Last edit timestamp.")
    software_revision = str_attr(
        "SoftwareRevision", default=None, doc="Studio/Logix software revision string."
    )
    encryption_config = str_attr(
        "EncryptionConfig", default=None, doc="Encryption configuration, if given."
    )
    description = CDataField("Description", doc="AOI description text, if visible.")
    revision_note = CDataField("RevisionNote", doc="AOI revision note, if visible.")

    def __init__(
        self, element: ET.Element, type_registry: TypeRegistry | None = None
    ) -> None:
        """Initialise from an ``<EncodedData>`` XML element.

        Args:
            element: The XML ``<EncodedData>`` element to wrap.
            type_registry: Shared type registry for resolving data type metadata.
        """
        super().__init__(element)
        self._type_registry = type_registry

    @property
    def parameters(self) -> AOIParametersCollection:
        """The visible parameter definitions, keyed by name.

        Returns:
            The same :class:`AOIParametersCollection` a normal AOI has; empty
            if the element has no ``Parameters`` child.
        """
        return AOIParametersCollection(self._element, self._type_registry)

    @property
    def dependency_names(self) -> list[str]:
        """The names listed in ``Dependencies/Dependency``, if any.

        Returns:
            The ``Name`` of each dependency in document order; empty if there
            is no ``Dependencies`` child.
        """
        return [
            d.get("Name", "")
            for d in self._element.findall("Dependencies/Dependency")
            if d.get("Name")
        ]


class ProtectedAOICollection(BaseCollection[ProtectedAOI]):
    """A ``Mapping`` over every encoded (source-protected) AOI by name.

    Args:
        controller_element: The ``<Controller>`` element.
    """

    def __init__(self, controller_element: ET.Element) -> None:
        """Index the encoded AOIs by name.

        Args:
            controller_element: The ``<Controller>`` element.
        """
        super().__init__(controller_element, PROTECTED_AOI_XPATH, self._make)
        #: Set by :class:`~py_l5x.parsers.project.Project`; resolves parameter
        #: metadata of the wrapped elements.
        self._registry: TypeRegistry | None = None

    def _make(self, element: ET.Element) -> ProtectedAOI:
        """Wrap an element with the bound registry.

        Args:
            element: An ``<EncodedData>`` element.

        Returns:
            The wrapper.
        """
        return ProtectedAOI(element, self._registry)


class CallSite(NamedTuple):
    """One place where an Add-On Instruction is called.

    Attributes:
        container_kind: ``"program"`` or ``"aoi"``.
        container: The program or AOI name.
        routine: The routine name.
        language: ``"RLL"`` or ``"ST"``.
        number: The rung number (RLL) or line number (ST).
        text: The rung text or the ST line.
    """

    container_kind: str
    container: str
    routine: str
    language: str
    number: int
    text: str

    def describe(self) -> str:
        """Describe the location for messages.

        Returns:
            For example ``"program MainProgram routine Main rung 3"``.
        """
        place = "rung" if self.language == "RLL" else "line"
        return (
            f"{self.container_kind} {self.container} routine {self.routine} "
            f"{place} {self.number}"
        )


def _mask(text: str, st: bool) -> str:
    """Blank out string literals (and ST comments) so calls inside them are
    ignored.

    Args:
        text: Rung text or joined ST lines.
        st: Whether *text* is structured text (``//`` and ``(* *)`` comments).

    Returns:
        A string of the same length with those parts replaced by spaces
        (newlines kept).
    """
    out = list(text)
    length = len(text)

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, length)):
            if text[k] != "\n":
                out[k] = " "

    i = 0
    while i < length:
        char = text[i]
        if char == "'":
            j = i + 1
            while j < length and text[j] != "'":
                j += 2 if text[j] == "$" else 1
            blank(i + 1, j)
            i = j + 1
        elif st and text.startswith("(*", i):
            j = text.find("*)", i + 2)
            j = length if j < 0 else j + 2
            blank(i, j)
            i = j
        elif st and text.startswith("//", i):
            j = text.find("\n", i)
            j = length if j < 0 else j
            blank(i, j)
            i = j
        else:
            i += 1
    return "".join(out)


def _call_pattern(name: str) -> re.Pattern[str]:
    """Compile the pattern matching calls of an AOI.

    The name must sit on identifier boundaries, must not follow a ``.``
    (so ``x.Name(`` is not a call), and must be followed by optional
    whitespace and ``(``. Matching ignores case, as Logix does.

    Args:
        name: The AOI name.

    Returns:
        A pattern whose match is exactly the name.
    """
    return re.compile(
        rf"(?<![A-Za-z0-9_.]){re.escape(name)}(?![A-Za-z0-9_])(?=\s*\()",
        re.IGNORECASE,
    )


def _logic(controller: ET.Element):
    """Iterate every routine of every AOI and program.

    Args:
        controller: The ``<Controller>`` element.

    Yields:
        ``(kind, container name, routine element)``.
    """
    for aoi in controller.findall(
        "AddOnInstructionDefinitions/AddOnInstructionDefinition"
    ):
        for routine in aoi.findall("Routines/Routine"):
            yield "aoi", aoi.get("Name", ""), routine
    for program in controller.findall("Programs/Program"):
        for routine in program.findall("Routines/Routine"):
            yield "program", program.get("Name", ""), routine


def _rung_text_element(rung: ET.Element) -> ET.Element | None:
    """Return the CDATA element holding a rung's text.

    Args:
        rung: A ``<Rung>``.

    Returns:
        The ``CDataContent`` child of ``<Text>``, or ``None``.
    """
    text = rung.find("Text")
    return None if text is None else text.find(CDATA_TAG)


class AOICollection(BaseCollection[AOIDefinition]):
    """A ``Mapping`` over every ``<AddOnInstructionDefinition>`` by name.

    Besides reading, the collection can add, replace, rename and remove
    instructions and list their call sites (:meth:`add`, :meth:`replace`,
    :meth:`rename`, :meth:`remove`, :meth:`call_sites`).

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
        self._registry = type_registry

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_element(self, name: str) -> ET.Element:
        """Return the AOI element with exactly this name.

        Args:
            name: The AOI name.

        Returns:
            The element.

        Raises:
            KeyError: If there is no such AOI.
        """
        for element in self._children():
            if element.get("Name") == name:
                return element
        raise KeyError(name)

    def _taken_names(self, ignore: str | None = None) -> list[str]:
        """List every name an AOI may not take.

        Args:
            ignore: A name to leave out (the AOI being renamed).

        Returns:
            Project UDT and AOI names, built-in table types and atomic types.
        """
        from py_l5x.parsers.atomic_types import ATOMIC_TYPES
        from py_l5x.parsers.layout import builtin_table

        names = [*self._registry.type_names(), *builtin_table(), *ATOMIC_TYPES]
        return [n for n in names if n != ignore]

    def _check_name(self, name: str, ignore: str | None = None) -> None:
        """Validate a new AOI name (rules plus collisions ignoring case).

        Args:
            name: The proposed name.
            ignore: A name to leave out of the collision check.

        Raises:
            ValueError: If the name is invalid or taken.
        """
        validate_new_name(name, self._taken_names(ignore), "add-on instruction")

    def _check_types(self, spec: AOISpec) -> None:
        """Check that every parameter and local tag type resolves.

        Args:
            spec: The spec.

        Raises:
            ValueError: If a type is not atomic, built-in, a project UDT or
                an AOI, or is the AOI itself.
        """
        from py_l5x.parsers.atomic_types import ATOMIC_TYPES
        from py_l5x.parsers.layout import builtin_table

        for item in [*spec.parameters, *spec.local_tags]:
            kind = item.data_type
            if kind == spec.name:
                raise ValueError(f"{item.name!r} cannot be of its own type")
            if self._registry.is_protected_aoi(kind):
                raise ValueError(
                    f"{item.name!r}: data type {kind!r} is a source-protected AOI, "
                    "which is not supported here"
                )
            if (
                kind in ATOMIC_TYPES
                or kind in builtin_table()
                or self._registry.udt(kind) is not None
                or self._registry.aoi(kind) is not None
            ):
                continue
            raise ValueError(f"{item.name!r}: unknown data type {kind!r}")

    def _container(self) -> ET.Element:
        """Return ``Controller/AddOnInstructionDefinitions``, creating it.

        Returns:
            The container element.
        """
        container = self._parent.find("AddOnInstructionDefinitions")
        if container is None:
            container = ET.Element("AddOnInstructionDefinitions")
            insert_child(self._parent, container)
        return container

    # ------------------------------------------------------------------
    # Call sites
    # ------------------------------------------------------------------

    def call_sites(self, name: str) -> list[CallSite]:
        """List every place an instruction is called.

        Searches the RLL rung text and the ST lines of every program and AOI
        routine. A call is the name followed by optional spaces and ``(``,
        on identifier boundaries, not preceded by ``.``, and outside string
        literals and ST comments. Matching ignores case. A tag or member
        merely named like the instruction (``Name_state``, ``x.Name``,
        ``XIC(Name)``) is not a call.

        Args:
            name: The AOI name.

        Returns:
            The call sites in document order (AOIs, then programs); a rung or
            line with several calls is listed once.
        """
        pattern = _call_pattern(name)
        sites: list[CallSite] = []
        for kind, container, routine in _logic(self._parent):
            routine_name = routine.get("Name", "")
            for rung in routine.findall("RLLContent/Rung"):
                holder = _rung_text_element(rung)
                text = (holder.text or "") if holder is not None else ""
                if pattern.search(_mask(text, st=False)):
                    sites.append(
                        CallSite(
                            kind,
                            container,
                            routine_name,
                            "RLL",
                            int(rung.get("Number", "0")),
                            text,
                        )
                    )
            lines = routine.findall("STContent/Line")
            if lines:
                texts = [self._line_text(line) for line in lines]
                masked = _mask("\n".join(texts), st=True).split("\n")
                for line, text, view in zip(lines, texts, masked, strict=True):
                    if pattern.search(view):
                        sites.append(
                            CallSite(
                                kind,
                                container,
                                routine_name,
                                "ST",
                                int(line.get("Number", "0")),
                                text,
                            )
                        )
        return sites

    @staticmethod
    def _line_text(line: ET.Element) -> str:
        """Return an ST line's raw text.

        Args:
            line: A ``<Line>``.

        Returns:
            Its CDATA text.
        """
        holder = line.find(CDATA_TAG)
        return (holder.text or "") if holder is not None else ""

    def _rename_calls(self, old: str, new: str) -> None:
        """Rewrite call sites of *old* to *new* in all logic.

        Args:
            old: The old AOI name.
            new: The new AOI name.
        """
        pattern = _call_pattern(old)

        def rewrite(text: str, st: bool) -> str:
            masked = _mask(text, st)
            spans = [m.span() for m in pattern.finditer(masked)]
            return "".join(_splice(text, spans, new))

        for _kind, _container, routine in _logic(self._parent):
            for rung in routine.findall("RLLContent/Rung"):
                holder = _rung_text_element(rung)
                if holder is not None and holder.text:
                    holder.text = rewrite(holder.text, False)
            lines = routine.findall("STContent/Line")
            holders = [line.find(CDATA_TAG) for line in lines]
            if lines and all(h is not None for h in holders):
                joined = "\n".join(h.text or "" for h in holders)
                rewritten = rewrite(joined, True).split("\n")
                for holder, text in zip(holders, rewritten, strict=True):
                    holder.text = text

    # ------------------------------------------------------------------
    # Edits
    # ------------------------------------------------------------------

    def add(self, spec: AOISpec) -> AOIDefinition:
        """Add an Add-On Instruction built from a spec.

        The element comes from :func:`~py_l5x.build.aoi.build_aoi` and is
        appended to ``Controller/AddOnInstructionDefinitions`` (created if
        missing): Studio orders AOIs so that dependencies come first, and a
        new AOI's dependencies already exist.

        Calls made by the new logic are not checked: a missing instruction
        cannot be told from an unknown mnemonic without Studio's instruction
        table, so only parameter and local types are resolved.

        Args:
            spec: The instruction.

        Returns:
            The new definition.

        Raises:
            ValueError: If the spec is invalid, the name matches (ignoring
                case) a UDT, an AOI, a built-in or an atomic type, or a
                parameter or local tag type does not resolve.
        """
        from py_l5x.build.aoi import build_aoi

        self._check_name(spec.name)
        self._check_types(spec)
        element = build_aoi(spec, self._registry)
        container = self._container()
        insert_child_at(container, len(container), element)
        return self[spec.name]

    def replace(
        self, spec: AOISpec, *, allow_signature_change: bool = False
    ) -> AOIDefinition:
        """Replace an Add-On Instruction and migrate its existing data.

        The definition is rebuilt in place. ``Class``, ``CreatedDate``,
        ``CreatedBy`` and ``SoftwareRevision`` are kept unless
        ``spec.metadata`` sets them; ``EditedDate`` and ``EditedBy`` are
        removed unless the metadata sets them to something other than the
        existing values (Studio stamps them on import, so the copies that
        ``to_spec`` carries do not count).
        Every instance of the AOI (``Structure``/``StructureMember`` with
        this ``DataType``: Input and Output parameters only) is migrated by
        parameter name with the conversion rules of
        :func:`~py_l5x.parsers.migrate.convert_atomic_value`; new parameters
        get the spec default. The change is all or nothing.

        Studio does not fix call sites: a call is
        ``Name(instance, <required parameters in order>)``, so changing the
        required parameters breaks every call (the build fails with
        ``RxCMP_E_AUDIT_INVALIDNOOFOPS``). If the required list changes and
        the AOI is called anywhere, a ``ValueError`` lists the call sites
        unless *allow_signature_change* is true; the call sites are then left
        as they are.

        Args:
            spec: The new definition; ``spec.name`` selects the AOI.
            allow_signature_change: Allow a changed required-parameter list
                even if call sites exist.

        Returns:
            The replaced definition.

        Raises:
            KeyError: If there is no AOI of that name.
            ValueError: If the spec is invalid, a type does not resolve, or
                the signature changes while call sites exist.
        """
        from py_l5x.build.aoi import aoi_call_operands, build_aoi
        from py_l5x.parsers.migrate import plan_instance_migration

        existing = self._find_element(spec.name)
        self._check_types(spec)
        old_operands = aoi_call_operands(self[spec.name])
        new_operands = aoi_call_operands(spec)
        if old_operands != new_operands and not allow_signature_change:
            sites = self.call_sites(spec.name)
            if sites:
                raise ValueError(
                    f"the required parameters of {spec.name!r} change from "
                    f"{old_operands} to {new_operands}, which breaks "
                    f"{len(sites)} call site(s): "
                    + "; ".join(site.describe() for site in sites)
                    + " (pass allow_signature_change=True to replace anyway)"
                )
        metadata = {
            key: value
            for key, value in existing.attrib.items()
            if key in ("Class", "CreatedDate", "CreatedBy", "SoftwareRevision")
        }
        for key, value in (spec.metadata or {}).items():
            # EditedDate/EditedBy copied unchanged from the existing definition
            # (as ``to_spec`` does) do not count as set: Studio re-stamps them.
            if key in ("EditedDate", "EditedBy") and existing.get(key) == value:
                continue
            metadata[key] = value
        merged = dataclasses.replace(spec, metadata=metadata)
        fresh = build_aoi(merged, self._registry)
        container = self._container()
        index = list(container).index(existing)
        fresh.tail = existing.tail
        container[index] = fresh
        try:
            ops = plan_instance_migration(self._parent, self._registry, spec.name)
        except BaseException:
            container[index] = existing
            raise
        for op in ops:
            op()
        return self[spec.name]

    def rename(self, old: str, new: str) -> AOIDefinition:
        """Rename an Add-On Instruction and everything that refers to it.

        Updates the ``Name``; the ``DataType`` attribute of tags (all scopes),
        UDT members, AOI parameters and local tags, and of value trees;
        ``<Dependency Type="AddOnInstructionDefinition">`` entries; and the
        **call sites in RLL rung text and ST lines** (an AOI name is an
        instruction in logic, so a rename that skipped logic would break the
        project). Calls are matched as in :meth:`call_sites`, so tags named
        like the instruction are untouched, and so are descriptions and
        comments. The AOI keeps its position.

        Args:
            old: The current name.
            new: The new name (same rules as :meth:`add`; the AOI itself is
                ignored by the collision check, so a case-only change works).

        Returns:
            The renamed definition.

        Raises:
            KeyError: If *old* does not exist.
            ValueError: If *new* is invalid or taken.
        """
        element = self._find_element(old)
        self._check_name(new, ignore=old)
        self._rename_calls(old, new)
        element.set("Name", new)
        for node in self._parent.iter():
            if node.get("DataType") == old:
                node.set("DataType", new)
            elif (
                node.tag == "Dependency"
                and node.get("Type") == "AddOnInstructionDefinition"
                and node.get("Name") == old
            ):
                node.set("Name", new)
        return self[new]

    def users(self, name: str) -> list[str]:
        """List what uses an Add-On Instruction.

        Args:
            name: The AOI name.

        Returns:
            Tags, UDT members, other AOIs' parameters and local tags, and
            call sites.
        """
        found = find_type_users(self._parent, name)
        found.extend(f"call in {site.describe()}" for site in self.call_sites(name))
        return found

    def remove(self, name: str, *, force: bool = False) -> None:
        """Delete an Add-On Instruction.

        Args:
            name: The AOI name.
            force: Delete even if something uses it (tags, members, other
                AOIs, call sites), leaving them dangling.

        Raises:
            KeyError: If there is no such AOI.
            ValueError: If the AOI is in use (listing the users) and *force*
                is false.
        """
        element = self._find_element(name)
        users = self.users(name)
        if users and not force:
            raise ValueError(
                f"add-on instruction {name!r} is in use by: " + ", ".join(users)
            )
        container = self._parent.find("AddOnInstructionDefinitions")
        assert container is not None
        remove_child(container, element)


def _splice(text: str, spans: list[tuple[int, int]], replacement: str):
    """Yield *text* with each span replaced.

    Args:
        text: The original text.
        spans: Non-overlapping ``(start, end)`` pairs, in order.
        replacement: The text to put in each span.

    Yields:
        The pieces of the new text.
    """
    position = 0
    for start, end in spans:
        yield text[position:start]
        yield replacement
        position = end
    yield text[position:]


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
        """Initialise from a ``<Controller>`` XML element.

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

"""Add-On Instruction (AOI) definition parsing.

This module provides rich AOI inspection surfaces similar to program parsing:

- ``AddOnInstructionDefinition`` for one AOI definition element.
- ``AddOnInstructionDefinitionsCollection`` for AOI lookup by name.
- ``AOILocalTag`` and ``AOILocalTagsCollection`` for AOI ``LocalTags`` with
  value drill-down (scalar/structure/array) reusing the tag-node model.

AOI routines reuse :class:`py_l5x.parsers.routine.RoutinesCollection`.
AOI parameters reuse :class:`py_l5x.parsers.datatype.AddOnParameters`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
from py_l5x.parsers.tag import TagNode, TypeRegistry, _build_node, _TagOverrides
from py_l5x.parsers.utils import CDATA_TAG


class AOILocalTag(BaseElement):
    """A single ``<LocalTag>`` under an AOI definition.

    Args:
        element: The XML ``<LocalTag>`` element.
        type_registry: Shared type registry for resolving data type metadata.
    """

    name = str_attr("Name", doc="Local tag name.")
    data_type = str_attr("DataType", doc="The local tag's data type name.")
    radix = str_attr("Radix", doc="Display radix, for atomic local tags.")
    constant = bool_attr(
        "Constant", default=False, doc="Whether the local tag is constant."
    )
    external_access = str_attr(
        "ExternalAccess",
        doc='External access level (commonly "None" for AOI locals).',
    )
    description = CDataField("Description", doc="Local tag description text.")

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry
        self._overrides = _TagOverrides(element)

    @property
    def data(self) -> TagNode | None:
        """The local tag's value-tree root node.

        AOI local tags store values under ``DefaultData`` instead of ``Data``.

        Returns:
            The root :class:`TagNode` for the tag value tree, or None if no
            data is available.
        """
        decorated = self._element.find("DefaultData[@Format='Decorated']")
        if decorated is not None:
            child = next(iter(decorated), None)
            if child is None:
                return None
            return _build_node(child, None, self._overrides, "", self._type_registry)

        string_data = self._element.find("DefaultData[@Format='String']")
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
        """Shortcut for ``self.data.value``.

        Returns:
            The scalar value of the tag, or None if the tag has no data.
        """
        node = self.data
        return node.value if node is not None else None

    @property
    def members(self) -> Mapping[str, TagNode]:
        """Shortcut for ``self.data.members``.

        Returns:
            A mapping of member names to :class:`TagNode` instances, or an
            empty dict if the tag has no data.
        """
        node = self.data
        return node.members if node is not None else {}

    @property
    def elements(self) -> Sequence[TagNode]:
        """Shortcut for ``self.data.elements``.

        Returns:
            A sequence of :class:`TagNode` instances, or an empty list if the
            tag has no data.
        """
        node = self.data
        return node.elements if node is not None else []

    def __repr__(self) -> str:
        """Return a concise representation including the tag name and type."""
        return f"AOILocalTag({self.name!r}, {self.data_type!r})"


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
            AOILocalTag,
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

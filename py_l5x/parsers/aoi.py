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

from py_l5x.parsers.base import BaseCollection, BaseElement
from py_l5x.parsers.datatype import AddOnParameters
from py_l5x.parsers.routine import RoutinesCollection
from py_l5x.parsers.tag import TagNode, TypeRegistry, _build_node, _TagOverrides
from py_l5x.parsers.utils import CDATA_TAG

_AOI_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {
        "Name",
        "Revision",
        "ExecutePrescan",
        "ExecutePostscan",
        "ExecuteEnableInFalse",
        "CreatedDate",
        "CreatedBy",
        "EditedDate",
        "EditedBy",
        "SoftwareRevision",
    }
)

_AOI_LOCAL_TAG_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {
        "Name",
        "DataType",
        "Radix",
        "ExternalAccess",
        "Constant",
    }
)


class AOILocalTag(BaseElement):
    """A single ``<LocalTag>`` under an AOI definition.

    Args:
        element: The XML ``<LocalTag>`` element.
        type_registry: Shared type registry for resolving data type metadata.
    """

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry
        self._overrides = _TagOverrides(element)

    @property
    def name(self) -> str:
        """Local tag name.

        Returns:
            The tag name as a string.
        """
        return self._get("Name")

    @property
    def data_type(self) -> str:
        """The local tag's data type name.

        Returns:
            The data type name as a string.
        """
        return self._get("DataType")

    @property
    def radix(self) -> str:
        """Display radix, for atomic local tags.

        Returns:
            The radix string (e.g. "Hex", "Decimal").
        """
        return self._get("Radix")

    @property
    def constant(self) -> bool:
        """Whether the local tag is constant.

        Returns:
            True if the tag is marked as constant, False otherwise.
        """
        return self._get("Constant") == "true"

    @property
    def external_access(self) -> str:
        """External access level (commonly ``"None"`` for AOI locals).

        Returns:
            The external access level string.
        """
        return self._get("ExternalAccess")

    @property
    def description(self) -> str:
        """Local tag description text.

        Returns:
            The description string.
        """
        return self._get_description()

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

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Returns:
            A dict of attribute names to values for any XML attributes that
            are not exposed as dedicated properties.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _AOI_LOCAL_TAG_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
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

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry

    @property
    def name(self) -> str:
        """AOI definition name.

        Returns:
            The AOI name as a string.
        """
        return self._get("Name")

    @property
    def description(self) -> str:
        """AOI description text.

        Returns:
            The description string.
        """
        return self._get_description()

    @property
    def revision(self) -> str:
        """AOI revision string.

        Returns:
            The revision string.
        """
        return self._get("Revision")

    @property
    def execute_prescan(self) -> bool:
        """Whether AOI executes on prescan.

        Returns:
            True if the AOI executes during prescan, False otherwise.
        """
        return self._get("ExecutePrescan") == "true"

    @property
    def execute_postscan(self) -> bool:
        """Whether AOI executes on postscan.

        Returns:
            True if the AOI executes during postscan, False otherwise.
        """
        return self._get("ExecutePostscan") == "true"

    @property
    def execute_enable_in_false(self) -> bool:
        """Whether AOI executes when enable-in is false.

        Returns:
            True if the AOI executes when enable-in is false, False otherwise.
        """
        return self._get("ExecuteEnableInFalse") == "true"

    @property
    def created_date(self) -> str:
        """Creation timestamp.

        Returns:
            The creation date/time string.
        """
        return self._get("CreatedDate")

    @property
    def created_by(self) -> str:
        """Author at creation.

        Returns:
            The name of the user who created the AOI.
        """
        return self._get("CreatedBy")

    @property
    def edited_date(self) -> str:
        """Last edit timestamp.

        Returns:
            The last edit date/time string.
        """
        return self._get("EditedDate")

    @property
    def edited_by(self) -> str:
        """Last editor.

        Returns:
            The name of the user who last edited the AOI.
        """
        return self._get("EditedBy")

    @property
    def software_revision(self) -> str:
        """Studio/Logix software revision string.

        Returns:
            The software revision string.
        """
        return self._get("SoftwareRevision")

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

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Returns:
            A dict of attribute names to values for any XML attributes that
            are not exposed as dedicated properties.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _AOI_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
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

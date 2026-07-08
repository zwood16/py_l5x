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

from py_l5x.parse import CDATA_TAG
from py_l5x.parsers.base import BaseCollection, BaseElement
from py_l5x.parsers.datatype import AddOnParameters
from py_l5x.parsers.routine import RoutinesCollection
from py_l5x.parsers.tag import TagNode, TypeRegistry, _build_node, _TagOverrides

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
    """A single ``<LocalTag>`` under an AOI definition."""

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry
        self._overrides = _TagOverrides(element)

    @property
    def name(self) -> str:
        """Local tag name."""
        return self._get("Name")

    @property
    def data_type(self) -> str:
        """The local tag's data type name."""
        return self._get("DataType")

    @property
    def radix(self) -> str:
        """Display radix, for atomic local tags."""
        return self._get("Radix")

    @property
    def constant(self) -> bool:
        """Whether the local tag is constant."""
        return self._get("Constant") == "true"

    @property
    def external_access(self) -> str:
        """External access level (commonly ``"None"`` for AOI locals)."""
        return self._get("ExternalAccess")

    @property
    def description(self) -> str:
        """Local tag description text."""
        return self._get_description()

    @property
    def data(self) -> TagNode | None:
        """The local tag's value-tree root node.

        AOI local tags store values under ``DefaultData`` instead of ``Data``.
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
        """Shortcut for ``self.data.value``."""
        node = self.data
        return node.value if node is not None else None

    @property
    def members(self) -> Mapping[str, TagNode]:
        """Shortcut for ``self.data.members``."""
        node = self.data
        return node.members if node is not None else {}

    @property
    def elements(self) -> Sequence[TagNode]:
        """Shortcut for ``self.data.elements``."""
        node = self.data
        return node.elements if node is not None else []

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _AOI_LOCAL_TAG_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
        return f"AOILocalTag({self.name!r}, {self.data_type!r})"


class AOILocalTagsCollection(BaseCollection[AOILocalTag]):
    """A ``Mapping`` over every AOI ``<LocalTag>`` by name."""

    def __init__(self, aoi_element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(
            aoi_element,
            "LocalTags/LocalTag",
            AOILocalTag,
            item_args=(type_registry,),
        )


class AOIDefinition(BaseElement):
    """One ``<AddOnInstructionDefinition>`` element."""

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        super().__init__(element)
        self._type_registry = type_registry

    @property
    def name(self) -> str:
        """AOI definition name."""
        return self._get("Name")

    @property
    def description(self) -> str:
        """AOI description text."""
        return self._get_description()

    @property
    def revision(self) -> str:
        """AOI revision string."""
        return self._get("Revision")

    @property
    def execute_prescan(self) -> bool:
        """Whether AOI executes on prescan."""
        return self._get("ExecutePrescan") == "true"

    @property
    def execute_postscan(self) -> bool:
        """Whether AOI executes on postscan."""
        return self._get("ExecutePostscan") == "true"

    @property
    def execute_enable_in_false(self) -> bool:
        """Whether AOI executes when enable-in is false."""
        return self._get("ExecuteEnableInFalse") == "true"

    @property
    def created_date(self) -> str:
        """Creation timestamp."""
        return self._get("CreatedDate")

    @property
    def created_by(self) -> str:
        """Author at creation."""
        return self._get("CreatedBy")

    @property
    def edited_date(self) -> str:
        """Last edit timestamp."""
        return self._get("EditedDate")

    @property
    def edited_by(self) -> str:
        """Last editor."""
        return self._get("EditedBy")

    @property
    def software_revision(self) -> str:
        """Studio/Logix software revision string."""
        return self._get("SoftwareRevision")

    @property
    def parameters(self) -> AddOnParameters:
        """AOI parameters keyed by name."""
        return AddOnParameters(self._element)

    @property
    def local_tags(self) -> AOILocalTagsCollection:
        """AOI local tags keyed by name."""
        return AOILocalTagsCollection(self._element, self._type_registry)

    @property
    def routines(self) -> RoutinesCollection:
        """AOI routines keyed by routine name."""
        return RoutinesCollection(self._element)

    def logic_text(self) -> str:
        """Render AOI routine logic as a quick-reference text block."""
        lines: list[str] = [f"AOI: {self.name}"]
        for routine in self.routines.values():
            lines.append("")
            lines.append(f"Routine: {routine.name} ({routine.type_})")
            text = routine.as_text()
            if text:
                lines.extend(text.splitlines())
        return "\n".join(lines)

    def print_logic_text(self) -> str:
        """Print and return :meth:`logic_text` for quick interactive inspection."""
        text = self.logic_text()
        print(text)
        return text

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _AOI_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
        return f"AddOnInstructionDefinition({self.name!r})"


class AOICollection(BaseCollection[AOIDefinition]):
    """A ``Mapping`` over every ``<AddOnInstructionDefinition>`` by name."""

    def __init__(
        self, controller_element: ET.Element, type_registry: TypeRegistry
    ) -> None:
        super().__init__(
            controller_element,
            "AddOnInstructionDefinitions/AddOnInstructionDefinition",
            AOIDefinition,
            item_args=(type_registry,),
        )

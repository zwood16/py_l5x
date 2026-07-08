"""Program-scoped data.

This module provides ``Program``, a wrapper around the ``<Program>`` element,
plus ``ProgramsCollection`` for accessing every ``<Program>`` by name.
Routine/logic parsing is out of scope -- this only exposes program identity
and its ``<Tags>`` section (via :class:`py_l5x.parsers.tag.TagsCollection`,
the same class used for the controller-level ``<Tags>``).
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from py_l5x.parsers.base import BaseCollection, BaseElement
from py_l5x.parsers.tag import TagsCollection, TypeRegistry

_PROGRAM_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {"Name", "TestEdits", "MainRoutineName", "Disabled", "UseAsFolder"}
)


class Program(BaseElement):
    """A single ``<Program>`` element from the ``<Programs>`` section.

    Args:
        element: The ``<Program>`` element from a parsed L5X tree.
        type_registry: Used to resolve this program's tags' value tree members.
    """

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        """Initialise from a ``<Program>`` XML element.

        Args:
            element: The ``<Program>`` element to wrap.
            type_registry: Used to resolve this program's tags' value tree
                members.
        """
        super().__init__(element)
        self._type_registry = type_registry

    @property
    def name(self) -> str:
        """Program name."""
        return self._get("Name")

    @property
    def description(self) -> str:
        """Program description text."""
        return self._get_description()

    @property
    def test_edits(self) -> bool:
        """Whether the program has pending test edits."""
        return self._get("TestEdits") == "true"

    @property
    def main_routine_name(self) -> str:
        """Name of the program's main routine."""
        return self._get("MainRoutineName")

    @property
    def disabled(self) -> bool:
        """Whether the program is disabled."""
        return self._get("Disabled") == "true"

    @property
    def use_as_folder(self) -> bool:
        """Whether the program is used purely as an organizational folder."""
        return self._get("UseAsFolder") == "true"

    @property
    def tags(self) -> TagsCollection:
        """This program's local tags, keyed by name."""
        return TagsCollection(self._element, self._type_registry)

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _PROGRAM_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
        """Return a concise representation including the program name."""
        return f"Program({self.name!r})"


class ProgramsCollection(BaseCollection[Program]):
    """A ``Mapping`` over every ``<Program>`` in the ``<Programs>`` section.

    Args:
        controller_element: The ``<Controller>`` element from a parsed L5X
            tree.
        type_registry: Used to resolve each program's tags' value tree members.
    """

    def __init__(
        self, controller_element: ET.Element, type_registry: TypeRegistry
    ) -> None:
        """Initialise from a ``<Controller>`` XML element.

        Args:
            controller_element: The ``<Controller>`` element whose
                ``Programs/Program`` children form this collection.
            type_registry: Used to resolve each program's tags' value tree
                members.
        """
        super().__init__(
            controller_element, "Programs/Program", Program, item_args=(type_registry,)
        )

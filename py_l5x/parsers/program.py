"""Program-scoped data.

This module provides ``Program``, a wrapper around the ``<Program>`` element,
plus ``ProgramsCollection`` for accessing every ``<Program>`` by name.
Program identity, local tags, and routines/logic are exposed directly via
typed parser wrappers.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from py_l5x.parsers.base import BaseCollection, BaseElement
from py_l5x.parsers.routine import RoutinesCollection
from py_l5x.parsers.tag import TagsCollection, TypeRegistry

_PROGRAM_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {"Name", "TestEdits", "MainRoutineName", "Disabled", "UseAsFolder"}
)
"""Known XML attribute names on ``<Program>`` elements."""


class Program(BaseElement):
    """A single ``<Program>`` element from the ``<Programs>`` section.

    Attributes:
        name: Program name.
        description: Program description text.
        test_edits: Whether the program has pending test edits.
        main_routine_name: Name of the program's main routine.
        disabled: Whether the program is disabled.
        use_as_folder: Whether the program is used purely as an organizational folder.
        tags: This program's local tags, keyed by name.
        routines: This program's routines, keyed by routine name.

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
        """Program name.

        Returns:
            The program name string.
        """
        return self._get("Name")

    @property
    def description(self) -> str:
        """Program description text.

        Returns:
            The description text string.
        """
        return self._get_description()

    @property
    def test_edits(self) -> bool:
        """Whether the program has pending test edits.

        Returns:
            True if the program has pending test edits, False otherwise.
        """
        return self._get("TestEdits") == "true"

    @property
    def main_routine_name(self) -> str:
        """Name of the program's main routine.

        Returns:
            The main routine name string.
        """
        return self._get("MainRoutineName")

    @property
    def disabled(self) -> bool:
        """Whether the program is disabled.

        Returns:
            True if the program is disabled, False otherwise.
        """
        return self._get("Disabled") == "true"

    @property
    def use_as_folder(self) -> bool:
        """Whether the program is used purely as an organizational folder.

        Returns:
            True if the program is a folder, False otherwise.
        """
        return self._get("UseAsFolder") == "true"

    @property
    def tags(self) -> TagsCollection:
        """This program's local tags, keyed by name.

        Returns:
            A TagsCollection of the program's local tags.
        """
        return TagsCollection(self._element, self._type_registry)

    @property
    def routines(self) -> RoutinesCollection:
        """This program's routines, keyed by routine name.

        Returns:
            A RoutinesCollection of the program's routines.
        """
        return RoutinesCollection(self._element)

    def logic_text(self) -> str:
        """Render this program's routine logic as a quick-reference text block.

        Formatting:
            - Ladder rungs are rendered as two lines per rung::

                  line_number : comment
                                     text

            - Structured Text routines are rendered line-by-line.

        Returns:
            A human-readable multi-line string containing all routines in the
            program, in XML order.
        """
        lines: list[str] = [f"Program: {self.name}"]
        rung_text_indent = " " * 23

        for routine in self.routines.values():
            lines.append("")
            lines.append(f"Routine: {routine.name} ({routine.type_})")

            if routine.type_ == "RLL":
                for rung in routine.rungs:
                    if rung.comment:
                        lines.append(f"{rung.number} : {rung.comment}")
                    else:
                        lines.append(f"{rung.number} :")
                    lines.append(f"{rung_text_indent}{rung.text}")
            elif routine.type_ == "ST":
                lines.extend(line.text for line in routine.st_lines)
            else:
                lines.append(f"[Unsupported routine type: {routine.type_}]")

        return "\n".join(lines)

    def print_logic_text(self) -> str:
        """Print and return :meth:`logic_text` for quick interactive inspection.

        Returns:
            The logic text string from :meth:`logic_text`.
        """
        text = self.logic_text()
        print(text)
        return text

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
        """Return a concise representation including the program name.

        Returns:
            A string in the format ``Program('name')``.
        """
        return f"Program({self.name!r})"


class ProgramsCollection(BaseCollection[Program]):
    """A ``Mapping`` over every ``<Program>`` in the ``<Programs>`` section.

    Attributes:
        programs: All programs in the collection, keyed by name.

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

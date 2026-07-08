"""Routine logic parsing shared by Programs and AOI definitions.

This module parses ``<Routine>`` elements and their logic bodies:

- Ladder routines (``Type=\"RLL\"``) via ``RLLContent/Rung``.
- Structured Text routines (``Type=\"ST\"``) via ``STContent/Line``.

The same XML shape is used under both ``Programs/Program/Routines`` and
``AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines``, so this
module can be reused directly by both parser surfaces.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from py_l5x.parse import CDATA_TAG
from py_l5x.parsers.base import BaseCollection, BaseElement

_ROUTINE_KNOWN_XML_KEYS: frozenset[str] = frozenset({"Name", "Type"})
_RUNG_KNOWN_XML_KEYS: frozenset[str] = frozenset({"Number", "Type"})
_ST_LINE_KNOWN_XML_KEYS: frozenset[str] = frozenset({"Number"})


class Rung(BaseElement):
    """A single ladder rung in ``<RLLContent>``."""

    @property
    def number(self) -> int:
        """Rung number."""
        return int(self._get("Number", "0"))

    @property
    def type_(self) -> str:
        """Rung type (typically ``\"N\"``)."""
        return self._get("Type")

    @property
    def comment(self) -> str:
        """Rung comment text, if present."""
        return self._get_cdata_child("Comment")

    @property
    def text(self) -> str:
        """Rung neutral text logic."""
        return self._get_cdata_child("Text")

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _RUNG_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
        """Return a concise rung representation."""
        return f"Rung(number={self.number}, type={self.type_!r})"


class StLine(BaseElement):
    """A single structured-text ``<Line>`` entry."""

    @property
    def number(self) -> int:
        """Line number."""
        return int(self._get("Number", "0"))

    @property
    def text(self) -> str:
        """Raw line text from CDATA or direct line content.

        Unlike most CDATA helpers in this project, this preserves leading
        whitespace so ST indentation remains intact, while trimming only
        XML-formatting newlines that can wrap the payload.
        """
        cdata_el = self._element.find(CDATA_TAG)
        if cdata_el is not None and cdata_el.text is not None:
            return cdata_el.text.strip("\r\n")
        if self._element.text is not None:
            return self._element.text.strip("\r\n")
        return ""

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _ST_LINE_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
        """Return a concise ST line representation."""
        return f"StLine(number={self.number})"


class Routine(BaseElement):
    """A single ``<Routine>`` with parsed ladder/ST logic text."""

    @property
    def name(self) -> str:
        """Routine name."""
        return self._get("Name")

    @property
    def type_(self) -> str:
        """Routine language/type (e.g. ``\"RLL\"`` or ``\"ST\"``)."""
        return self._get("Type")

    @property
    def description(self) -> str:
        """Routine description text."""
        return self._get_description()

    @property
    def rungs(self) -> list[Rung]:
        """All ladder rungs in this routine.

        Returns an empty list for non-RLL routines.
        """
        return [Rung(el) for el in self._element.findall("RLLContent/Rung")]

    @property
    def st_lines(self) -> list[StLine]:
        """All ST lines in this routine.

        Returns an empty list for non-ST routines.
        """
        return [StLine(el) for el in self._element.findall("STContent/Line")]

    @property
    def st_code(self) -> str:
        """Structured Text routine body as a newline-joined string.

        Returns an empty string for non-ST routines.
        """
        return "\n".join(line.text for line in self.st_lines)

    def as_text(self) -> str:
        """Return the routine body as end-user friendly text.

        For RLL routines, each rung is emitted as two lines::

            <line number> : <comment>
                                   <neutral text>

        For ST routines, lines are joined in order as plain structured text.

        Returns:
            A formatted routine text block suitable for quick inspection.
        """
        if self.type_ == "RLL":
            lines: list[str] = []
            for rung in self.rungs:
                comment = rung.comment.splitlines()[0].strip() if rung.comment else ""
                first_line = f"{rung.number} : {comment}".rstrip()
                lines.append(first_line)

                indent = first_line.find(":") + 2 if ":" in first_line else 0
                lines.append(f"{' ' * indent}{rung.text}")
            return "\n".join(lines)

        if self.type_ == "ST":
            return self.st_code

        return ""

    def print_text(self) -> None:
        """Print :meth:`as_text` for quick interactive inspection."""
        print(self.as_text())

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties."""
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _ROUTINE_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
        """Return a concise representation including name and type."""
        return f"Routine({self.name!r}, type={self.type_!r})"


class RoutinesCollection(BaseCollection[Routine]):
    """A ``Mapping`` over every ``<Routine>`` under a parent element.

    The parent can be either a ``<Program>`` element or an
    ``<AddOnInstructionDefinition>`` element.
    """

    def __init__(self, parent_element: ET.Element) -> None:
        """Initialise from a parent element containing a ``<Routines>`` child."""
        super().__init__(parent_element, "Routines/Routine", Routine)

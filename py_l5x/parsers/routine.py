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

from py_l5x.parsers.base import BaseCollection, BaseElement
from py_l5x.parsers.utils import CDATA_TAG

_ROUTINE_KNOWN_XML_KEYS: frozenset[str] = frozenset({"Name", "Type", "Use"})
"""Known XML attribute names on ``<Routine>`` elements."""
_RUNG_KNOWN_XML_KEYS: frozenset[str] = frozenset({"Number", "Type", "Use"})
"""Known XML attribute names on ``<Rung>`` elements."""
_ST_LINE_KNOWN_XML_KEYS: frozenset[str] = frozenset({"Number"})
"""Known XML attribute names on ``<Line>`` (ST) elements."""


class Rung(BaseElement):
    """A single ladder rung in ``<RLLContent>``.

    Attributes:
        number: Rung number.
        type_: Rung type (typically ``"N"``).
        comment: Rung comment text, if present.
        text: Rung neutral text logic.

    Args:
        element: The ``<Rung>`` XML element to wrap.
    """

    @property
    def number(self) -> int:
        """Rung number.

        Returns:
            The rung number as an integer, defaulting to 0.
        """
        return int(self._get("Number", "0"))

    @property
    def type_(self) -> str:
        """Rung type (typically ``"N"``).

        Returns:
            The rung type string.
        """
        return self._get("Type")

    @property
    def comment(self) -> str:
        """Rung comment text, if present.

        Returns:
            The comment text string, or empty string if none.
        """
        return self._get_cdata_child("Comment")

    @property
    def text(self) -> str:
        """Rung neutral text logic.

        Returns:
            The rung's neutral text content.
        """
        return self._get_cdata_child("Text")

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _RUNG_KNOWN_XML_KEYS
        }

    @property
    def use(self) -> str:
        """Export target role for this rung.

        ``"Target"`` when this rung is the exported target in a component
        export; empty string otherwise.

        Returns:
            The value of the ``Use`` XML attribute, or ``""`` if absent.
        """
        return self._get("Use")

    def __repr__(self) -> str:
        """Return a concise rung representation.

        Returns:
            A string in the format ``Rung(number=N, type='T')``.
        """
        return f"Rung(number={self.number}, type={self.type_!r})"


class StLine(BaseElement):
    """A single structured-text ``<Line>`` entry.

    Attributes:
        number: Line number.
        text: Raw line text from CDATA or direct content.

    Args:
        element: The ``<Line>`` XML element to wrap.
    """

    @property
    def number(self) -> int:
        """Line number.

        Returns:
            The line number as an integer, defaulting to 0.
        """
        return int(self._get("Number", "0"))

    @property
    def text(self) -> str:
        """Raw line text from CDATA or direct line content.

        Unlike most CDATA helpers in this project, this preserves leading
        whitespace so ST indentation remains intact, while trimming only
        XML-formatting newlines that can wrap the payload.

        Returns:
            The raw ST line text string.
        """
        cdata_el = self._element.find(CDATA_TAG)
        if cdata_el is not None and cdata_el.text is not None:
            return cdata_el.text.strip("\r\n")
        if self._element.text is not None:
            return self._element.text.strip("\r\n")
        return ""

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _ST_LINE_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
        """Return a concise ST line representation.

        Returns:
            A string in the format ``StLine(number=N)``.
        """
        return f"StLine(number={self.number})"


class Routine(BaseElement):
    """A single ``<Routine>`` with parsed ladder/ST logic text.

    Attributes:
        name: Routine name.
        type_: Routine language/type (e.g. ``"RLL"`` or ``"ST"``).
        description: Routine description text.
        rungs: All ladder rungs in this routine (empty for non-RLL).
        st_lines: All ST lines in this routine (empty for non-ST).
        st_code: Structured Text routine body as a newline-joined string.

    Args:
        element: The ``<Routine>`` XML element to wrap.
    """

    @property
    def name(self) -> str:
        """Routine name.

        Returns:
            The routine name string.
        """
        return self._get("Name")

    @property
    def use(self) -> str:
        """Export target role for this routine.

        ``"Target"`` when this routine is the exported target in a component
        export; empty string otherwise.

        Returns:
            The value of the ``Use`` XML attribute, or ``""`` if absent.
        """
        return self._get("Use")

    @property
    def type_(self) -> str:
        """Routine language/type (e.g. ``"RLL"`` or ``"ST"``).

        Returns:
            The routine type string.
        """
        return self._get("Type")

    @property
    def description(self) -> str:
        """Routine description text.

        Returns:
            The description text string.
        """
        return self._get_description()

    @property
    def rungs(self) -> list[Rung]:
        """All ladder rungs in this routine.

        Returns an empty list for non-RLL routines.

        Returns:
            A list of ``Rung`` objects.
        """
        return [Rung(el) for el in self._element.findall("RLLContent/Rung")]

    @property
    def st_lines(self) -> list[StLine]:
        """All ST lines in this routine.

        Returns an empty list for non-ST routines.

        Returns:
            A list of ``StLine`` objects.
        """
        return [StLine(el) for el in self._element.findall("STContent/Line")]

    @property
    def st_code(self) -> str:
        """Structured Text routine body as a newline-joined string.

        Returns an empty string for non-ST routines.

        Returns:
            The ST code string, or empty string if not an ST routine.
        """
        return "\n".join(line.text for line in self.st_lines)

    @property
    def target_rung(self) -> Rung | None:
        """The rung marked ``Use="Target"`` in a rung-level component export.

        When a single rung is exported from Studio 5000, that rung carries
        ``Use="Target"`` while all others are unmarked.  This property
        locates and returns it.  Returns ``None`` for non-rung-level exports
        (i.e. when no rung carries the marker) and for non-RLL routines.

        Returns:
            The target ``Rung``, or ``None`` if no rung is marked as target.
        """
        for el in self._element.findall("RLLContent/Rung"):
            if el.get("Use") == "Target":
                return Rung(el)
        return None

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
        """XML attributes not covered by explicit properties.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _ROUTINE_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
        """Return a concise representation including name and type.

        Returns:
            A string in the format ``Routine('name', type='T')``.
        """
        return f"Routine({self.name!r}, type={self.type_!r})"


class RoutinesCollection(BaseCollection[Routine]):
    """A ``Mapping`` over every ``<Routine>`` under a parent element.

    The parent can be either a ``<Program>`` element or an
    ``<AddOnInstructionDefinition>`` element.

    Attributes:
        routines: All routines in the collection, keyed by name.

    Args:
        parent_element: The parent element containing a ``<Routines>`` child.
    """

    def __init__(self, parent_element: ET.Element) -> None:
        """Initialise from a parent element containing a ``<Routines>`` child.

        Args:
            parent_element: The parent element (e.g. ``<Program>`` or
                ``<AddOnInstructionDefinition>``) whose ``Routines/Routine``
                children form this collection.
        """
        super().__init__(parent_element, "Routines/Routine", Routine)

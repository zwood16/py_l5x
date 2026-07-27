"""Routine logic parsing shared by Programs and AOI definitions.

This module parses ``<Routine>`` elements and their logic bodies:

- Ladder routines (``Type=\"RLL\"``) via ``RLLContent/Rung``.
- Structured Text routines (``Type=\"ST\"``) via ``STContent/Line``.

The same XML shape is used under both ``Programs/Program/Routines`` and
``AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines``, so this
module can be reused directly by both parser surfaces.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    int_attr,
    str_attr,
)
from py_l5x.parsers.utils import CDATA_TAG

_ST_COMMENT_RE = re.compile(
    r"'(?:[^']|'')*'"
    r"|//(?P<line>[^\r\n]*)"
    r"|\(\*(?P<block>.*?)\*\)",
    re.DOTALL,
)
"""Matches ST string literals (skipped) or comments (captured by group)."""


class Rung(BaseElement):
    """A single ladder rung in ``<RLLContent>``.

    Args:
        element: The ``<Rung>`` XML element to wrap.
    """

    number = int_attr("Number", default=0, doc="Rung number.")
    type_ = str_attr("Type", doc='Rung type (typically "N").')
    comment = CDataField("Comment", doc="Rung comment text, if present.")
    text = CDataField("Text", doc="Rung neutral text logic.")
    use = str_attr(
        "Use",
        doc='Export target role for this rung. "Target" when this rung is '
        "the exported target in a component export.",
    )

    def __repr__(self) -> str:
        """Return a concise rung representation.

        Returns:
            A string in the format ``Rung(number=N, type='T')``.
        """
        return f"Rung(number={self.number}, type={self.type_!r})"


class StLine(BaseElement):
    """A single structured-text ``<Line>`` entry.

    Args:
        element: The ``<Line>`` XML element to wrap.
    """

    number = int_attr("Number", default=0, doc="Line number.")

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

    def __repr__(self) -> str:
        """Return a concise ST line representation.

        Returns:
            A string in the format ``StLine(number=N)``.
        """
        return f"StLine(number={self.number})"


class Routine(BaseElement):
    """A single ``<Routine>`` with parsed ladder/ST logic text.

    Attributes:
        rungs: All ladder rungs in this routine (empty for non-RLL).
        st_lines: All ST lines in this routine (empty for non-ST).
        st_code: Structured Text routine body as a newline-joined string.

    Args:
        element: The ``<Routine>`` XML element to wrap.
    """

    name = str_attr("Name", doc="Routine name.")
    use = str_attr(
        "Use",
        doc='Export target role for this routine. "Target" when this '
        "routine is the exported target in a component export.",
    )
    type_ = str_attr("Type", doc='Routine language/type (e.g. "RLL" or "ST").')
    description = CDataField("Description", doc="Routine description text.")

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
    def comments(self) -> list[str]:
        """Return all comments in the routine as a list of strings.

        For ST routines, both ``//`` single-line comments and ``(* ... *)``
        block comments are extracted. Comment markers inside single-quoted
        string literals are ignored.
        """
        if self.type_ == "RLL":
            return [rung.comment for rung in self.rungs if rung.comment]
        if self.type_ == "ST":
            return self._extract_st_comments(self.st_code)
        return []

    @staticmethod
    def _extract_st_comments(text: str) -> list[str]:
        """Extract comments from Structured Text source.

        Args:
            text: Full ST source code.

        Returns:
            List of extracted comment bodies without comment delimiters.
        """
        comments: list[str] = []
        for m in _ST_COMMENT_RE.finditer(text):
            body = m.group("line")
            if body is not None:
                body = body.lstrip()
            else:
                body = m.group("block")
                if body is not None:
                    body = body.strip()
            if body:
                comments.append(body)
        return comments

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

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
from collections.abc import Sequence
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    int_attr,
    str_attr,
)
from py_l5x.parsers.names import validate_new_name
from py_l5x.parsers.schema import (
    insert_child,
    insert_child_at,
    new_cdata_element,
    remove_child,
)
from py_l5x.parsers.utils import cdata_text

_ST_COMMENT_RE = re.compile(
    r"'(?:[^']|'')*'"
    r"|//(?P<line>[^\r\n]*)"
    r"|\(\*(?P<block>.*?)\*\)",
    re.DOTALL,
)
"""Matches ST string literals (skipped) or comments (captured by group)."""

_RUNG_HEADER_WIDTH = 40
"""Total width of the ``Rung N ---`` header line in :meth:`Routine.as_text`."""


def _check_rung_text(text: str) -> None:
    """Run the light sanity check on new rung text.

    Args:
        text: The rung text.

    Raises:
        ValueError: If the text is empty, does not end with ``;``, or has
            unbalanced or badly nested ``()``/``[]`` outside quoted literals.
    """
    stripped = text.strip() if isinstance(text, str) else ""
    if not stripped:
        raise ValueError("rung text is empty")
    if not stripped.endswith(";"):
        raise ValueError("rung text must end with ';'")
    pairs = {")": "(", "]": "["}
    stack: list[str] = []
    in_string = False
    i = 0
    while i < len(stripped):
        ch = stripped[i]
        if in_string:
            if ch == "$":
                i += 1
            elif ch == "'":
                in_string = False
        elif ch == "'":
            in_string = True
        elif ch in "([":
            stack.append(ch)
        elif ch in pairs and (not stack or stack.pop() != pairs[ch]):
            raise ValueError(f"unbalanced {ch!r} in rung text")
        i += 1
    if in_string:
        raise ValueError("unterminated string literal in rung text")
    if stack:
        raise ValueError(f"unclosed {stack[-1]!r} in rung text")


if TYPE_CHECKING:
    from py_l5x.build.specs import RoutineSpec


def build_rung(text: str, comment: str | None = None, number: int = 0) -> ET.Element:
    """Create a ``<Rung>`` element in Studio's layout.

    Args:
        text: The rung's neutral text (stored as given; not validated here).
        comment: Optional rung comment.
        number: The ``Number`` attribute.

    Returns:
        ``<Rung Number=".." Type="N">`` with ``Comment`` (if any) then ``Text``.
    """
    element = ET.Element("Rung")
    element.set("Number", str(number))
    element.set("Type", "N")
    if comment:
        insert_child(element, new_cdata_element("Comment", comment))
    insert_child(element, new_cdata_element("Text", text))
    return element


def build_st_line(text: str, number: int) -> ET.Element:
    """Create a structured text ``<Line>`` element in Studio's layout.

    Args:
        text: The line (leading indentation kept; empty gives empty CDATA).
        number: The ``Number`` attribute.

    Returns:
        ``<Line Number="..">`` with the text as CDATA.
    """
    line = new_cdata_element("Line", text)
    line.set("Number", str(number))
    return line


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
        return cdata_text(self._element, strip="\r\n")

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

    # ------------------------------------------------------------------
    # Edits
    # ------------------------------------------------------------------

    def _content(self, tag: str, language: str) -> ET.Element:
        """Return the ``RLLContent``/``STContent`` element, creating it if missing.

        Args:
            tag: ``"RLLContent"`` or ``"STContent"``.
            language: The routine ``Type`` the content belongs to.

        Returns:
            The content element.

        Raises:
            TypeError: If this routine is not of the *language* type.
        """
        if self.type_ != language:
            raise TypeError(
                f"routine {self.name!r} is type {self.type_!r}, not {language!r}"
            )
        content = self._element.find(tag)
        if content is None:
            content = ET.Element(tag)
            insert_child(self._element, content)
        return content

    @staticmethod
    def _renumber(content: ET.Element) -> None:
        """Set every rung's ``Number`` to its position, from 0.

        Args:
            content: The ``<RLLContent>`` element.
        """
        for number, rung in enumerate(content.findall("Rung")):
            rung.set("Number", str(number))

    def add_rung(
        self, text: str, comment: str | None = None, index: int | None = None
    ) -> Rung:
        """Insert a ladder rung and renumber every rung from 0.

        The text is stored as given. Only a light check is made: it must be
        non-empty, end with ``;``, and have balanced, properly nested ``()``
        and ``[]`` (brackets inside single-quoted literals are ignored). This is
        **not** a logic check: undefined tags, bad operands and unknown
        instructions are only caught when Studio builds the project.

        Args:
            text: The rung's neutral text (for example ``"XIC(a)OTE(b);"``).
            comment: Optional rung comment.
            index: Position to insert at (``0`` to the current rung count);
                ``None`` appends.

        Returns:
            The new rung.

        Raises:
            TypeError: If this is not an RLL routine.
            ValueError: If the text fails the check above.
            IndexError: If *index* is out of range.
        """
        content = self._content("RLLContent", "RLL")
        _check_rung_text(text)
        count = len(content.findall("Rung"))
        position = count if index is None else index
        if not 0 <= position <= count:
            raise IndexError(f"rung index {index} out of range for {count} rungs")
        element = build_rung(text, comment, position)
        insert_child_at(content, position, element)
        self._renumber(content)
        return Rung(element)

    def remove_rung(self, index: int) -> None:
        """Remove a ladder rung and renumber the rest from 0.

        Args:
            index: Position of the rung.

        Raises:
            TypeError: If this is not an RLL routine.
            IndexError: If *index* is out of range.
        """
        content = self._content("RLLContent", "RLL")
        rungs = content.findall("Rung")
        if not 0 <= index < len(rungs):
            raise IndexError(f"rung index {index} out of range for {len(rungs)} rungs")
        remove_child(content, rungs[index])
        self._renumber(content)

    def set_st_lines(self, lines: str | Sequence[str]) -> None:
        """Replace the routine's structured text.

        Each line becomes a ``<Line Number="i">`` with CDATA text, numbered
        from 0; leading indentation is kept and an empty line becomes empty
        CDATA.

        Args:
            lines: A string, split on ``"\\n"`` (``"\\r\\n"`` and ``"\\r"`` are
                normalized first; an empty string means no lines), or a sequence
                of single lines.

        Raises:
            TypeError: If this is not an ST routine.
            ValueError: If an item of a sequence contains a line break.
        """
        content = self._content("STContent", "ST")
        if isinstance(lines, str):
            normalized = lines.replace("\r\n", "\n").replace("\r", "\n")
            items = normalized.split("\n") if normalized else []
        else:
            items = list(lines)
            if any("\n" in item or "\r" in item for item in items):
                raise ValueError("each ST line must be a single line")
        for old in content.findall("Line"):
            remove_child(content, old)
        if not items:
            content.text = None
        for number, item in enumerate(items):
            insert_child_at(content, number, build_st_line(item, number))

    def to_spec(self) -> RoutineSpec:
        """Convert this routine to a spec that rebuilds it.

        Rung and line text and comments are read as raw CDATA.

        Returns:
            A :class:`~py_l5x.build.specs.RoutineSpec`.

        Raises:
            ValueError: For a routine that is neither RLL nor ST.
        """
        from py_l5x.build.specs import RoutineSpec, RungSpec
        from py_l5x.parsers.migrate import _raw_cdata

        kind = self.type_
        if kind not in ("RLL", "ST"):
            raise ValueError(f"routine {self.name!r}: unsupported type {kind!r}")

        def text(parent: ET.Element, tag: str) -> str:
            found = parent.find(tag)
            return _raw_cdata(found) if found is not None else ""

        element = self._element
        return RoutineSpec(
            name=self.name,
            type_=kind,
            rungs=[
                RungSpec(text(rung, "Text"), text(rung, "Comment"))
                for rung in element.findall("RLLContent/Rung")
            ],
            lines=[_raw_cdata(line) for line in element.findall("STContent/Line")],
            description=text(element, "Description"),
        )

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

        For RLL routines, each rung is emitted as a header line followed by an
        optional ``Comment`` block (the full, possibly multi-line, comment) and
        a ``Logic`` block with the rung's neutral text. Rungs are separated by
        one blank line; there is no trailing blank line::

            Rung 0 ---------------------------------
            Comment
            <comment, possibly multi-line, verbatim>
            Logic
            <rung neutral text>

            Rung 1 ---------------------------------
            Logic
            <rung neutral text>

        The header is ``Rung <n> `` right-padded with ``-`` to 40 characters.
        The ``Comment`` block is omitted for rungs without a comment.

        For ST routines, lines are joined in order as plain structured text.

        Returns:
            A formatted routine text block suitable for quick inspection.
        """
        if self.type_ == "RLL":
            blocks: list[str] = []
            for rung in self.rungs:
                block = [f"Rung {rung.number} ".ljust(_RUNG_HEADER_WIDTH, "-")]
                if rung.comment:
                    block.append("Comment")
                    block.extend(rung.comment.splitlines())
                block.append("Logic")
                block.append(rung.text)
                blocks.append("\n".join(block))
            return "\n\n".join(blocks)

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

    @property
    def logic(self) -> list[str]:
        """Return the executable logic of the routine as a list of strings.

        For RLL routines, each rung's neutral text is returned in order,
        skipping empty rungs. For ST routines, the code is returned with
        ``//`` and ``(* ... *)`` comments removed; single-quoted string
        literals are preserved. Blank lines are dropped and leading
        indentation is kept. Other routine types return an empty list.

        Returns:
            A list of logic strings, one per rung or ST line.
        """
        if self.type_ == "RLL":
            return [rung.text for rung in self.rungs if rung.text]
        if self.type_ == "ST":
            return self._strip_st_comments(self.st_code).splitlines()
        return []

    @staticmethod
    def _strip_st_comments(text: str) -> str:
        """Remove ST comments from source code, keeping string literals.

        Args:
            text: Full ST source code.

        Returns:
            The source with comment text removed. Each line is right-stripped
            and lines that are blank after stripping are dropped; leading
            indentation is preserved.
        """

        def _drop_comment(m: re.Match[str]) -> str:
            if m.group("line") is not None or m.group("block") is not None:
                return ""
            return m.group(0)

        cleaned = _ST_COMMENT_RE.sub(_drop_comment, text)
        lines = (line.rstrip() for line in cleaned.splitlines())
        return "\n".join(line for line in lines if line)

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


#: The only routine names an AOI may have.
_AOI_ROUTINE_NAMES = frozenset({"Logic", "Prescan", "Postscan", "EnableInFalse"})


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

    # ------------------------------------------------------------------
    # Edits
    # ------------------------------------------------------------------

    def _is_aoi(self) -> bool:
        """Report whether the parent is an AOI definition.

        Returns:
            ``True`` for an ``<AddOnInstructionDefinition>`` parent.
        """
        return self._parent.tag == "AddOnInstructionDefinition"

    def _routine_elements(self) -> list[ET.Element]:
        """Return the parent's ``<Routine>`` elements.

        Returns:
            The elements in document order.
        """
        return self._parent.findall("Routines/Routine")

    def _find_element(self, name: str) -> ET.Element:
        """Return the routine element with exactly this name.

        Args:
            name: The routine name.

        Returns:
            The element.

        Raises:
            KeyError: If there is no such routine.
        """
        for element in self._routine_elements():
            if element.get("Name") == name:
                return element
        raise KeyError(name)

    def _check_new_name(self, name: str, ignore: ET.Element | None = None) -> None:
        """Validate a routine name against the shared name rules.

        Args:
            name: The proposed name.
            ignore: A routine element to leave out of the duplicate check.

        Raises:
            ValueError: If the name is invalid or taken (ignoring case), or,
                for an AOI parent, is not one of ``Logic``, ``Prescan``,
                ``Postscan`` and ``EnableInFalse``.
        """
        validate_new_name(
            name,
            (e.get("Name", "") for e in self._routine_elements() if e is not ignore),
            "routine",
        )

    def add(
        self, name: str, type_: str = "RLL", *, description: str | None = None
    ) -> Routine:
        """Create an empty routine at the end of ``<Routines>``.

        Creates ``<Routines>`` first if the parent has none. For an AOI parent
        only ``Logic``, ``Prescan``, ``Postscan`` and ``EnableInFalse`` are valid
        names. The AOI's ``Execute*`` flags are not touched: Studio keeps a
        routine even when its flag is false, and the flags are separate
        attributes.

        Args:
            name: The routine name (letters, digits, underscores; at most 40
                characters; no consecutive or trailing underscores).
            type_: ``"RLL"`` or ``"ST"``.
            description: Routine description.

        Returns:
            The new routine.

        Raises:
            ValueError: If *type_* is not ``"RLL"``/``"ST"``, or the name is
                invalid, taken (ignoring case) or not allowed for an AOI.
        """
        if type_ not in ("RLL", "ST"):
            raise ValueError(f"routine type must be 'RLL' or 'ST', not {type_!r}")
        self._check_new_name(name)
        if self._is_aoi() and name not in _AOI_ROUTINE_NAMES:
            raise ValueError(
                f"AOI routine name must be one of {sorted(_AOI_ROUTINE_NAMES)}, "
                f"not {name!r}"
            )
        element = ET.Element("Routine")
        element.set("Name", name)
        element.set("Type", type_)
        # Studio exports an empty routine with no content child at all;
        # add_rung/set_st_lines create RLLContent/STContent on first use.
        routines = self._parent.find("Routines")
        if routines is None:
            routines = ET.Element("Routines")
            insert_child(self._parent, routines)
        insert_child_at(routines, len(routines), element)
        routine = self[name]
        if description:
            routine.description = description
        return routine

    def remove(self, name: str) -> None:
        """Delete a routine.

        JSR references to it in other logic are **not** removed.

        Args:
            name: The routine name.

        Raises:
            KeyError: If there is no such routine.
            ValueError: If it is a program's main or fault routine, or an AOI's
                ``Logic`` routine.
        """
        element = self._find_element(name)
        if self._is_aoi():
            if name == "Logic":
                raise ValueError("cannot remove an AOI's Logic routine")
        elif name in (
            self._parent.get("MainRoutineName"),
            self._parent.get("FaultRoutineName"),
        ):
            raise ValueError(
                f"cannot remove routine {name!r}: it is the program's main or "
                "fault routine"
            )
        routines = self._parent.find("Routines")
        assert routines is not None
        remove_child(routines, element)

    def rename(self, old: str, new: str) -> Routine:
        """Rename a routine.

        For a program, ``MainRoutineName`` and ``FaultRoutineName`` follow the
        rename. JSR references in logic are **not** updated.

        Args:
            old: The current name.
            new: The new name (same rules as :meth:`add`; the routine itself is
                ignored by the duplicate check, so a case-only change works).

        Returns:
            The renamed routine.

        Raises:
            KeyError: If *old* does not exist.
            ValueError: If the parent is an AOI (its routine names are fixed),
                or *new* is invalid or taken.
        """
        element = self._find_element(old)
        if self._is_aoi():
            raise ValueError("AOI routines cannot be renamed")
        self._check_new_name(new, ignore=element)
        element.set("Name", new)
        for attribute in ("MainRoutineName", "FaultRoutineName"):
            if self._parent.get(attribute) == old:
                self._parent.set(attribute, new)
        return self[new]

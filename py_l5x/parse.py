"""L5X XML File Parsing."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from py_l5x.parsers.project import Project
from py_l5x.parsers.utils import CDATA_TAG

_CDATA_SECTION = r"<!\[CDATA\[(.*?)\]\]>"
#: One or more directly adjacent CDATA sections. Text containing ``]]>`` is
#: written as two sections (``]]]]><![CDATA[>``), so a run of sections is one
#: logical text value.
_CDATA_RE = re.compile(rf"(?:{_CDATA_SECTION})+", re.DOTALL)
_CDATA_SECTION_RE = re.compile(_CDATA_SECTION, re.DOTALL)


def _cdata_to_element(match: re.Match) -> str:
    """Replace a run of adjacent CDATA sections with a ``<CDATA_TAG>`` element.

    The sections' contents are joined, so text that was split around a
    ``]]>`` terminator is restored. The content is XML-escaped so characters
    like ``<``, ``>``, and ``&`` (common in Structured Text and rung comments)
    do not break the parser.
    """
    text = "".join(_CDATA_SECTION_RE.findall(match.group(0)))
    return f"<{CDATA_TAG}>{_xml_escape(text)}</{CDATA_TAG}>"


def _parse_text(raw: str) -> ET.Element:
    """Parse L5X text into an element tree, converting CDATA sections.

    Replaces ``<![CDATA[...]]>`` with ``<CDATA_TAG>`` elements. Content is
    XML-escaped so that characters like ``<``, ``>`` and ``&`` (common in
    Structured Text and rung comments) remain valid inside the element text.

    Args:
        raw (str): The L5X document text.

    Returns:
        ET.Element: The root element.

    Raises:
        ValueError: If the text cannot be parsed as XML.
    """
    processed = _CDATA_RE.sub(_cdata_to_element, raw)
    try:
        return ET.fromstring(processed.encode("utf-8"))
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse the L5X file: {e}") from e


def _load_l5x(file_path: str) -> ET.Element:
    """Load and parse an L5X XML file.

    CDATA sections (``<![CDATA[...]]>``) are converted to
    ``<CDataContent>...</CDataContent>`` elements before parsing so that
    ``xml.etree.ElementTree`` can handle them. The text content is fully
    preserved and accessible via ``element.text``. On write-back this
    substitution must be reversed.

    Args:
        file_path (str): The path to the L5X file.

    Returns:
        ET.Element: The root element of the parsed L5X XML file.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the file cannot be parsed as XML.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise FileNotFoundError(f"Could not read file {file_path}: {e}") from e

    return _parse_text(raw)


def load(file_path: str) -> Project:
    """Load an L5X file and return a hierarchical ``Project`` object.

    This is the primary public API for the ``py_l5x`` package.  It parses
    the L5X XML file, handles CDATA sections, and builds a complete
    object hierarchy with controller metadata, data types, modules,
    AOIs, tags, programs, and tasks.

    Args:
        file_path: Path to the L5X file.

    Returns:
        A ``Project`` instance providing typed access to all project data.

    Raises:
        FileNotFoundError: If the file does not exist or cannot be read.
        ValueError: If the file is not a valid L5X XML document or lacks
            a ``<Controller>`` element.

    Example:
        >>> from py_l5x import load
        >>> project = load("my_project.L5X")
        >>> print(project.controller.name)
        MyController
        >>> for task in project.tasks.values():
        ...     print(task.name, list(task.programs))
    """
    return Project(_load_l5x(file_path))


def loads(text: str) -> Project:
    """Parse L5X text and return a hierarchical ``Project`` object.

    Behaves like :func:`load` but takes the document text instead of a path.
    A leading byte order mark is stripped and line endings are normalized
    to ``"\\n"`` so results match file loading.

    Args:
        text: The L5X document text.

    Returns:
        A ``Project`` instance providing typed access to all project data.

    Raises:
        ValueError: If the text is not a valid L5X XML document or lacks
            a ``<Controller>`` element.
    """
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return Project(_parse_text(text))

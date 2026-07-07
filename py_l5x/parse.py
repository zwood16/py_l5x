"""L5X XML File Parsing."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

#: XML tag name used as a stand-in for CDATA sections during parsing.
#: ``<![CDATA[...]]>`` is replaced with ``<CDATA_TAG>...</CDATA_TAG>`` before
#: the document is fed to ElementTree. Import this constant wherever the tag
#: name is needed instead of hard-coding the string.
CDATA_TAG = "CDataContent"

_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)


def _cdata_to_element(match: re.Match) -> str:
    """Replace a CDATA section with a ``<CDATA_TAG>`` element.

    The content is XML-escaped so characters like ``<``, ``>``, and ``&``
    (common in Structured Text and rung comments) do not break the parser.
    """
    return f"<{CDATA_TAG}>{_xml_escape(match.group(1))}</{CDATA_TAG}>"


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

    # Replace <![CDATA[...]]> with <CDATA_TAG> elements. Content is
    # XML-escaped so that characters like < > & (common in Structured Text
    # and rung comments) remain valid inside the element text node.
    processed = _CDATA_RE.sub(_cdata_to_element, raw)

    try:
        root = ET.fromstring(processed.encode("utf-8"))
        return root
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse the L5X file: {e}") from e

"""L5X serialization.

Turns an element tree produced by :func:`py_l5x.parse.load` (or ``loads``)
back into L5X text. The reader replaces every ``<![CDATA[...]]>`` section
with a ``<CDATA_TAG>`` element; the writer reverses that substitution.

Output follows the conventions of real Studio 5000 exports: an XML
declaration, empty elements written as ``<Foo a="b"/>``, CDATA sections
restored, CRLF line endings, a trailing newline, and (for bytes) a UTF-8
byte order mark.

Ordering matters in :func:`to_string`: the ``" />"`` to ``"/>"`` fix runs
before CDATA restoration. At that point every ``>`` in attribute values and
text is escaped by ElementTree, so the pattern can only match real tags.
After CDATA restoration, raw ``>`` may appear in text.
"""

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from py_l5x.parsers.utils import CDATA_TAG

_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
_BOM = b"\xef\xbb\xbf"

_CDATA_ELEMENT_RE = re.compile(
    rf"<{CDATA_TAG}>(.*?)</{CDATA_TAG}>|<{CDATA_TAG}/>", re.DOTALL
)


def _unescape_text(text: str) -> str:
    """Reverse ElementTree's escaping of element text.

    Args:
        text: Escaped text from a serialized element.

    Returns:
        The text with ``&lt;``, ``&gt;``, ``&quot;`` and ``&amp;`` resolved.
    """
    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
    )


def _restore_cdata(match: re.Match) -> str:
    """Replace a serialized ``<CDATA_TAG>`` element with a CDATA section.

    Args:
        match: Match of ``_CDATA_ELEMENT_RE``. Group 1 is ``None`` for the
            empty-element form.

    Returns:
        The equivalent ``<![CDATA[...]]>`` section. Any ``]]>`` in the
        content is split across two sections so the output stays well formed.
    """
    text = _unescape_text(match.group(1) or "")
    text = text.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{text}]]>"


def to_string(root: ET.Element, *, newline: str = "\r\n") -> str:
    """Serialize an element tree to full L5X document text.

    The input tree is not modified.

    Args:
        root: The ``<RSLogix5000Content>`` root element.
        newline: Line ending used in the output. Every ``"\\n"`` becomes
            this string.

    Returns:
        The XML declaration, the serialized root and a trailing newline.
    """
    body = ET.tostring(root, encoding="unicode")
    body = body.replace(" />", "/>")
    body = _CDATA_ELEMENT_RE.sub(_restore_cdata, body)
    text = f"{_XML_DECLARATION}\n{body}\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline != "\n":
        text = text.replace("\n", newline)
    return text


def to_bytes(root: ET.Element, *, bom: bool = True, newline: str = "\r\n") -> bytes:
    """Serialize an element tree to UTF-8 encoded L5X bytes.

    Args:
        root: The ``<RSLogix5000Content>`` root element.
        bom: Whether to prefix the output with a UTF-8 byte order mark.
        newline: Line ending used in the output.

    Returns:
        The encoded document.
    """
    data = to_string(root, newline=newline).encode("utf-8")
    return _BOM + data if bom else data


def write(
    root: ET.Element,
    path: str | os.PathLike,
    *,
    bom: bool = True,
    newline: str = "\r\n",
) -> None:
    """Write an element tree to an L5X file.

    Args:
        root: The ``<RSLogix5000Content>`` root element.
        path: Destination file path. An existing file is overwritten.
        bom: Whether to write a UTF-8 byte order mark.
        newline: Line ending used in the output.
    """
    Path(path).write_bytes(to_bytes(root, bom=bom, newline=newline))

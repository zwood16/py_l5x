"""Miscellaneous helper functions."""

from xml.etree import ElementTree as ET

from py_l5x.parsers.atomic_types import (
    atomic_info,
    parse_float_literal,
    parse_integer_literal,
)

#: XML tag name used as a stand-in for CDATA sections during parsing.
#: ``<![CDATA[...]]>`` is replaced with ``<CDATA_TAG>...</CDATA_TAG>`` before
#: the document is fed to ElementTree. Import this constant wherever the tag
#: name is needed instead of hard-coding the string.
CDATA_TAG = "CDataContent"


def parse_int(value: str | None) -> int | None:
    """Parse an integer XML attribute value.

    Args:
        value: The raw attribute string, or ``None`` if the attribute is absent.

    Returns:
        The parsed integer, or ``None`` if *value* is ``None``, empty, or not
        a valid integer.
    """
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def cdata_text(element: ET.Element | None, strip: bool | str = True) -> str:
    """Return the text of an element, preferring its CDATA child.

    A ``<![CDATA[...]]>`` section is stored as a :data:`CDATA_TAG` child
    element. When that child exists and has non-empty text it is used;
    otherwise the element's own text is used.

    Args:
        element: The element to read, or ``None`` if it is absent.
        strip: How to trim the result. ``True`` (default) removes all
            surrounding whitespace via :meth:`str.strip`. ``False`` returns the
            text unchanged. A string removes only those characters, e.g.
            ``"\\r\\n"`` drops XML-formatting newlines while preserving
            leading indentation (used for structured text lines).

    Returns:
        The text, or an empty string if *element* is ``None`` or has no text.
    """
    if element is None:
        return ""
    cdata_el = element.find(CDATA_TAG)
    if cdata_el is not None and cdata_el.text:
        text = cdata_el.text
    else:
        text = element.text or ""
    if isinstance(strip, str):
        return text.strip(strip)
    return text.strip() if strip else text


def convert_numeric(value: str, data_type: str) -> int | float | str:
    """Convert a raw XML value string to a numeric type based on *data_type*.

    Integer/BOOL values may be decimal, based (``"16#FF"``,
    ``"2#0000_0001"``, ``"8#17"``), or single-quoted ASCII literals
    (``"'$00'"``); based and ASCII literals are interpreted as raw bit
    patterns with two's-complement sign adjustment for signed types.
    Float values accept the usual ``float()`` syntax plus the Logix
    specials ``1.#QNAN`` and ``1.#INF``.

    Args:
        value: The raw string value to convert (e.g. from a ``Min``, ``Max``,
            or tag value attribute).
        data_type: The L5X atomic data type name associated with *value*
            (e.g. ``"SINT"``, ``"REAL"``). Only known integer and
            floating-point atomic types are converted; anything else
            (time/datetime types, UDTs, AOIs, unrecognised types) is
            returned unchanged.

    Returns:
        An ``int`` or ``float`` when *data_type* is a known numeric atomic
        type and *value* parses cleanly, otherwise the original string.
    """
    info = atomic_info(data_type)
    if info is not None and info.family == "float":
        try:
            return parse_float_literal(value)
        except ValueError:
            return value
    if info is not None and info.family in ("bool", "integer"):
        try:
            return parse_integer_literal(value, info)
        except ValueError:
            return value
    return value

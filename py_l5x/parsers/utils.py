"""Miscellaneous helper functions."""

import re

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


def to_snake(name: str) -> str:
    """Convert PascalCase/camelCase XML keys to snake_case names.

    Args:
        name: The PascalCase or camelCase string to convert.

    Returns:
        The snake_case version of the input string.
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


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

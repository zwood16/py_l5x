"""Miscellaneous helper functions."""

import re

#: XML tag name used as a stand-in for CDATA sections during parsing.
#: ``<![CDATA[...]]>`` is replaced with ``<CDATA_TAG>...</CDATA_TAG>`` before
#: the document is fed to ElementTree. Import this constant wherever the tag
#: name is needed instead of hard-coding the string.
CDATA_TAG = "CDataContent"

#: Atomic L5X data types that hold integer values.
_INT_DATATYPES: frozenset[str] = frozenset(
    {
        "BOOL",
        "SINT",
        "INT",
        "DINT",
        "LINT",
        "USINT",
        "UINT",
        "UDINT",
        "ULINT",
        "BYTE",
        "WORD",
        "DWORD",
        "LWORD",
    }
)

#: Atomic L5X data types that hold floating-point values.
_REAL_DATATYPES: frozenset[str] = frozenset({"REAL", "LREAL"})


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

    Args:
        value: The raw string value to convert (e.g. from a ``Min``, ``Max``,
            or tag value attribute).
        data_type: The L5X atomic data type name associated with *value*
            (e.g. ``"SINT"``, ``"REAL"``). Only known integer and
            floating-point atomic types are converted; anything else
            (UDTs, AOIs, unrecognised types) is returned unchanged.

    Returns:
        An ``int`` or ``float`` when *data_type* is a known numeric atomic
        type and *value* parses cleanly, otherwise the original string.
    """
    if data_type in _REAL_DATATYPES:
        try:
            return float(value)
        except ValueError:
            return value
    if data_type in _INT_DATATYPES:
        try:
            return int(value)
        except ValueError:
            return value
    return value

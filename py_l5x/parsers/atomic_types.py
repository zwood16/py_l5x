"""Atomic L5X data type table.

Single source of truth for the built-in (atomic) Logix data types: their
family, bit width, signedness, numeric range, and time unit. This module is
a leaf module and must not import from any other ``py_l5x`` module so it can
be shared by ``utils`` and the parser classes without circular imports.

Note:
    ``TIME32``/``TIME``/``LTIME`` and ``DT``/``LDT`` require Logix v37+.
    Their exported values are literal strings (e.g. ``T#0us``,
    ``DT#1970-01-01-00:00:00.000_000Z``), so their ``min``/``max`` are
    ``None``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

AtomicFamily = Literal["bool", "integer", "float", "time", "datetime"]

#: Regular expression for a based literal (``2#``, ``8#``, or ``16#`` prefix
#: followed by digits with optional underscores).
_BASED_RE = re.compile(r"^(?P<base>16|2|8)#(?P<digits>[0-9a-fA-F_]+)$")

#: Regular expression for a plain decimal literal with an optional sign.
_DECIMAL_RE = re.compile(r"^[+-]?[0-9]+$")

#: Valid digit characters for each supported based-literal base.
_BASE_DIGITS: dict[int, str] = {
    2: "01",
    8: "01234567",
    16: "0123456789abcdef",
}

#: Single-character ASCII escapes (upper-case letter to byte value).
_ASCII_ESCAPES: dict[str, int] = {
    "L": 0x0A,
    "N": 0x0A,
    "P": 0x0C,
    "R": 0x0D,
    "T": 0x09,
}

#: Hex digit characters for ``$hh`` ASCII escapes.
_HEX_DIGITS = "0123456789abcdefABCDEF"


@dataclass(frozen=True, slots=True)
class AtomicInfo:
    """Metadata for a single atomic L5X data type.

    Args:
        name: Upper-case Logix type name (e.g. ``"DINT"``).
        family: The value family of the type.
        bit_width: Storage width in bits.
        signed: Whether the type is signed.
        min: Minimum numeric value, or ``None`` for non-numeric types.
        max: Maximum numeric value, or ``None`` for non-numeric types.
        unit: Time unit for time/datetime types, or ``None`` otherwise.
    """

    name: str
    family: AtomicFamily
    bit_width: int
    signed: bool
    min: int | None
    max: int | None
    unit: Literal["us", "ns"] | None


def _int_range(bit_width: int, signed: bool) -> tuple[int, int]:
    """Return the two's-complement (min, max) range for an integer type."""
    if signed:
        return -(2 ** (bit_width - 1)), 2 ** (bit_width - 1) - 1
    return 0, 2**bit_width - 1


def _integer(name: str, bit_width: int, signed: bool) -> AtomicInfo:
    """Build an ``AtomicInfo`` for an integer type."""
    lo, hi = _int_range(bit_width, signed)
    return AtomicInfo(name, "integer", bit_width, signed, lo, hi, None)


def _time(name: str, bit_width: int, unit: Literal["us", "ns"]) -> AtomicInfo:
    """Build an ``AtomicInfo`` for a time or datetime type."""
    return AtomicInfo(name, "time", bit_width, True, None, None, unit)


_ATOMIC_TYPES: dict[str, AtomicInfo] = {
    "BOOL": AtomicInfo("BOOL", "bool", 1, False, 0, 1, None),
    "SINT": _integer("SINT", 8, True),
    "INT": _integer("INT", 16, True),
    "DINT": _integer("DINT", 32, True),
    "LINT": _integer("LINT", 64, True),
    "USINT": _integer("USINT", 8, False),
    "UINT": _integer("UINT", 16, False),
    "UDINT": _integer("UDINT", 32, False),
    "ULINT": _integer("ULINT", 64, False),
    "BYTE": _integer("BYTE", 8, False),
    "WORD": _integer("WORD", 16, False),
    "DWORD": _integer("DWORD", 32, False),
    "LWORD": _integer("LWORD", 64, False),
    "REAL": AtomicInfo("REAL", "float", 32, True, None, None, None),
    "LREAL": AtomicInfo("LREAL", "float", 64, True, None, None, None),
    "TIME32": _time("TIME32", 32, "us"),
    "TIME": _time("TIME", 64, "us"),
    "LTIME": _time("LTIME", 64, "ns"),
    "DT": AtomicInfo("DT", "datetime", 64, True, None, None, "us"),
    "LDT": AtomicInfo("LDT", "datetime", 64, True, None, None, "ns"),
}

#: Read-only mapping of upper-case atomic type name to its metadata.
ATOMIC_TYPES: Mapping[str, AtomicInfo] = MappingProxyType(_ATOMIC_TYPES)


def atomic_info(data_type: str) -> AtomicInfo | None:
    """Look up atomic type metadata by name (case-insensitive).

    Args:
        data_type: The L5X atomic data type name (e.g. ``"dint"``).

    Returns:
        The matching ``AtomicInfo``, or ``None`` if *data_type* is not a
        known atomic type (e.g. a UDT or AOI name).
    """
    return ATOMIC_TYPES.get(data_type.upper())


def _apply_twos_complement(value: int, info: AtomicInfo) -> int:
    """Interpret an unsigned bit pattern as signed if *info* is signed.

    Args:
        value: The raw unsigned bit pattern.
        info: The ``AtomicInfo`` describing the target type.

    Returns:
        *value* unchanged when *info* is unsigned, or *value* minus
        ``2 ** bit_width`` when the top bit at ``info.bit_width`` is set.

    Raises:
        ValueError: If *value* does not fit in ``info.bit_width`` bits.
    """
    if value >= 2**info.bit_width:
        raise ValueError(f"bit pattern too wide for {info.name}")
    if info.signed and value >= 2 ** (info.bit_width - 1):
        return value - 2**info.bit_width
    return value


def _parse_based_literal(digits: str, base: int, info: AtomicInfo) -> int:
    """Parse a based literal's digit string and apply signedness.

    Args:
        digits: The digit string after the ``base#`` prefix (may contain
            underscores).
        base: The radix (2, 8, or 16).
        info: The ``AtomicInfo`` describing the target type.

    Returns:
        The integer value of the bit pattern, sign-adjusted for *info*.

    Raises:
        ValueError: If any digit is invalid for *base*.
    """
    valid = _BASE_DIGITS[base]
    for ch in digits:
        if ch != "_" and ch.lower() not in valid:
            raise ValueError(f"invalid digit {ch!r} for base {base}")
    return _apply_twos_complement(int(digits.replace("_", ""), base), info)


def _parse_ascii_literal(body: str, info: AtomicInfo) -> int:
    """Parse the body of a single-quoted ASCII literal.

    Args:
        body: The characters between the surrounding single quotes.
        info: The ``AtomicInfo`` describing the target type.

    Returns:
        The bytes combined big-endian into an unsigned int, sign-adjusted
        for *info*.

    Raises:
        ValueError: If a ``$`` escape is malformed.
    """
    out = bytearray()
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "$":
            out.append(ord(ch))
            i += 1
            continue
        if i + 1 >= len(body):
            raise ValueError("trailing '$' in ASCII literal")
        nxt = body[i + 1]
        if nxt == "$":
            out.append(0x24)
            i += 2
        elif nxt == "'":
            out.append(0x27)
            i += 2
        elif nxt.upper() in _ASCII_ESCAPES:
            out.append(_ASCII_ESCAPES[nxt.upper()])
            i += 2
        elif (
            nxt in _HEX_DIGITS
            and i + 2 < len(body)
            and body[i + 2] in _HEX_DIGITS
        ):
            out.append(int(body[i + 1 : i + 3], 16))
            i += 3
        else:
            raise ValueError(f"invalid escape '${nxt}' in ASCII literal")
    return _apply_twos_complement(int.from_bytes(bytes(out), "big"), info)


def parse_integer_literal(text: str, info: AtomicInfo) -> int:
    """Parse a Logix integer/BOOL value literal into an ``int``.

    Accepts decimal literals (``"0"``, ``"-5"``, ``"+7"``), based literals
    (``"16#00"``, ``"2#0000_0001"``, ``"8#17"``; bases 2/8/16 only, with
    underscores allowed anywhere in the digits), and single-quoted ASCII
    literals (``"'A'"``, ``"'$41$42'"``). Based and ASCII literals are raw
    bit patterns: when *info* is signed and the top bit at
    ``info.bit_width`` is set, ``2 ** bit_width`` is subtracted (so SINT
    ``"16#FF"`` is -1 while USINT ``"16#FF"`` is 255).

    Args:
        text: The raw literal string (surrounding whitespace is ignored).
        info: The ``AtomicInfo`` describing the target type.

    Returns:
        The parsed integer value.

    Raises:
        ValueError: If *text* is not a valid literal for the given rules
            (empty string, bad base, invalid digit, malformed ``$`` escape,
            etc.) or the value does not fit the type's bit width/range.
    """
    text = text.strip()
    if not text:
        raise ValueError("empty integer literal")
    if text[0] == "'":
        if len(text) < 2 or text[-1] != "'":
            raise ValueError("unterminated ASCII literal")
        return _parse_ascii_literal(text[1:-1], info)
    if m := _BASED_RE.match(text):
        return _parse_based_literal(m["digits"], int(m["base"]), info)
    if _DECIMAL_RE.match(text):
        value = int(text)
        if info.min is not None and info.max is not None and not (
            info.min <= value <= info.max
        ):
            raise ValueError(f"{value} out of range for {info.name}")
        return value
    raise ValueError(f"invalid integer literal: {text!r}")


def parse_float_literal(text: str) -> float:
    """Parse a Logix REAL/LREAL value literal into a ``float``.

    In addition to the usual ``float()`` syntax, the Logix specials
    ``"1.#QNAN"``/``"-1.#QNAN"`` (NaN), ``"1.#INF"`` (infinity), and
    ``"-1.#INF"`` (negative infinity) are recognised case-insensitively.

    Args:
        text: The raw literal string (surrounding whitespace is ignored).

    Returns:
        The parsed float value.

    Raises:
        ValueError: If *text* is not a valid float literal.
    """
    text = text.strip()
    upper = text.upper()
    if upper in ("1.#QNAN", "-1.#QNAN"):
        return math.nan
    if upper == "1.#INF":
        return math.inf
    if upper == "-1.#INF":
        return -math.inf
    return float(text)

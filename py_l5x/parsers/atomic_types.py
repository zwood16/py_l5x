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
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from types import MappingProxyType
from typing import Any, Literal

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
        elif nxt in _HEX_DIGITS and i + 2 < len(body) and body[i + 2] in _HEX_DIGITS:
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
        if (
            info.min is not None
            and info.max is not None
            and not (info.min <= value <= info.max)
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


# ----------------------------------------------------------------------
# Formatting (the inverse of the parsers above)
# ----------------------------------------------------------------------

#: Literal prefix required for each time/datetime type.
TIME_PREFIXES: Mapping[str, str] = MappingProxyType(
    {"TIME32": "T32#", "TIME": "T#", "LTIME": "LT#", "DT": "DT#", "LDT": "LDT#"}
)

#: Radix Studio gives a tag of each non-integer type when none is stated.
#: Integer and BOOL types use ``"Decimal"``.
_DEFAULT_RADIX: dict[str, str] = {
    "REAL": "Float",
    "LREAL": "Float",
    "TIME32": "Time32 (us)",
    "TIME": "Time (us)",
    "LTIME": "LTime (ns)",
    "DT": "Date/Time",
    "LDT": "Date/Time (ns)",
}


def default_radix(data_type: str) -> str | None:
    """Return the radix Studio uses for a tag of an atomic type by default.

    Args:
        data_type: The atomic type name (case-insensitive).

    Returns:
        ``"Decimal"`` for integers and BOOL, ``"Float"`` for REAL/LREAL, the
        time/date-time radix names (for example ``"Time (us)"``) for those
        types, or ``None`` if *data_type* is not atomic.
    """
    name = data_type.upper()
    if name in _DEFAULT_RADIX:
        return _DEFAULT_RADIX[name]
    info = ATOMIC_TYPES.get(name)
    return "Decimal" if info is not None else None


#: Exponent (base 10) range written positionally by the Float radix.
_POSITIONAL_EXP_RANGE = range(-4, 16)


def _group(digits: str, size: int) -> str:
    """Group *digits* in chunks of *size* from the right, joined by ``_``.

    Args:
        digits: The digit string.
        size: Chunk size.

    Returns:
        The grouped string (the leftmost chunk may be shorter).
    """
    head = len(digits) % size
    chunks = [digits[:head]] if head else []
    chunks += [digits[i : i + size] for i in range(head, len(digits), size)]
    return "_".join(chunks)


def _escape_byte(byte: int) -> str:
    """Return the Logix string-literal form of one byte.

    Args:
        byte: The byte value (0-255).

    Returns:
        The character for printable ASCII (with ``$`` and ``'`` escaped),
        otherwise ``$HH`` with upper-case hex.
    """
    if byte == 0x24:
        return "$$"
    if byte == 0x27:
        return "$'"
    if 0x20 <= byte <= 0x7E:
        return chr(byte)
    return f"${byte:02X}"


def format_integer_literal(value: int, info: AtomicInfo, radix: str | None) -> str:
    """Format an integer the way Studio exports it for a given radix.

    Args:
        value: The integer to format. ``bool`` is rejected.
        info: The ``AtomicInfo`` of the (integer) target type.
        radix: ``"Hex"``, ``"Octal"``, ``"Binary"`` or ``"ASCII"`` (matched
            case-insensitively); anything else, including ``None``, is
            decimal.

    Returns:
        The literal text: ``"255"``, ``"16#0000_00ff"``, ``"8#000_377"``,
        ``"2#0000_1111"`` or ``"'$00$FF'"``.

    Raises:
        TypeError: If *value* is not an ``int`` (or is a ``bool``).
        ValueError: If *value* is outside the range of the type.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{info.name} value must be an int, not {type(value).__name__}")
    if (
        info.min is not None
        and info.max is not None
        and not info.min <= value <= info.max
    ):
        raise ValueError(f"{value} out of range for {info.name}")
    pattern = value & (2**info.bit_width - 1)
    kind = (radix or "").lower()
    if kind == "hex":
        digits = f"{pattern:0{info.bit_width // 4}x}"
        return "16#" + _group(digits, 4)
    if kind == "octal":
        digits = f"{pattern:0{-(-info.bit_width // 3)}o}"
        return "8#" + _group(digits, 3)
    if kind == "binary":
        return "2#" + _group(f"{pattern:0{info.bit_width}b}", 4)
    if kind == "ascii":
        raw = pattern.to_bytes(info.bit_width // 8, "big")
        return "'" + "".join(_escape_byte(b) for b in raw) + "'"
    return str(value)


def _exponential(value: float, digits: int, *, truncate: bool = False) -> str:
    """Format *value* in Logix exponential form with a 3-digit exponent.

    Args:
        value: The finite float to format.
        digits: Digits after the decimal point in the mantissa.
        truncate: Cut the exact decimal expansion instead of rounding it.
            Studio's LREAL exports do this (``0.1`` is written
            ``1.0000000000000000e-001``, not ``...0001e-001``). The
            truncated text is used only when it still parses back to
            *value*; otherwise the rounded text is used.

    Returns:
        Text such as ``"1.50000000e+000"``.
    """
    if truncate and value:
        exact = Decimal(value)
        exponent = exact.adjusted()
        mantissa = exact.scaleb(-exponent).quantize(
            Decimal(1).scaleb(-digits), rounding=ROUND_DOWN
        )
        if float(f"{mantissa}e{exponent}") == value:
            sign = "-" if exponent < 0 else "+"
            return f"{mantissa}e{sign}{abs(exponent):03d}"
    mantissa, exponent = f"{value:.{digits}e}".split("e")
    return f"{mantissa}e{'-' if exponent[0] == '-' else '+'}{abs(int(exponent)):03d}"


def _to_float32(value: float) -> float:
    """Round *value* to the nearest float32.

    Args:
        value: The float to round.

    Returns:
        The float32-representable value.

    Raises:
        ValueError: If *value* is too large for float32.
    """
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        raise ValueError(f"{value} does not fit in a REAL") from None


def _decimal_text(value: float, single: bool) -> str:
    """Return the decimal text used to write a float.

    LREAL values use :func:`repr`. REAL values do too, unless that needs
    more than nine significant digits (more than a float32 can hold); then
    the shortest decimal that round-trips through float32 is used instead.

    Args:
        value: A finite float that fits the target type.
        single: Whether the target is a REAL (float32) rather than a LREAL.

    Returns:
        Text that :class:`~decimal.Decimal` can parse (for example
        ``"1e-10"`` or ``"0.30000000000000004"``).
    """
    text = repr(value)
    if single and len(Decimal(text).normalize().as_tuple().digits) > 9:
        rounded = _to_float32(value)
        for precision in range(9):
            text = f"{rounded:.{precision}e}"
            if _to_float32(float(text)) == rounded:
                break
    return text


def format_float_literal(value: int | float, data_type: str, radix: str | None) -> str:
    """Format a REAL/LREAL the way Studio exports it for a given radix.

    ``"Exponential"`` gives a mantissa with 8 (REAL) or 16 (LREAL) decimals
    and a 3-digit exponent (``1.50000000e+000``). Any other radix (normally
    ``"Float"``) gives the shortest decimal text (see :func:`_decimal_text`),
    written positionally with at least one decimal when its decimal exponent
    is from -4 to 15 (``1.5``, ``16777216.0``) and in exponential form
    otherwise. REAL values must fit in float32 but are *not* rounded to it:
    Studio's exports show the decimal of the value as entered.

    Args:
        value: The number to format. ``bool`` is rejected.
        data_type: ``"REAL"`` or ``"LREAL"`` (case-insensitive).
        radix: The node radix.

    Returns:
        The literal text.

    Raises:
        TypeError: If *value* is not an ``int`` or ``float``.
        ValueError: If *value* is not finite or does not fit the type.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(
            f"{data_type} value must be an int or float, not {type(value).__name__}"
        )
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{value} does not fit in a {data_type}") from None
    if not math.isfinite(number):
        raise ValueError(f"{data_type} value must be finite")
    single = data_type.upper() != "LREAL"
    if single:
        _to_float32(number)
    text = _decimal_text(number, single)
    decimal = Decimal(text)
    if (radix or "").lower() != "exponential" and (
        decimal.adjusted() in _POSITIONAL_EXP_RANGE
    ):
        positional = format(decimal, "f")
        return positional if "." in positional else positional + ".0"
    return _exponential(float(text), 8 if single else 16, truncate=not single)


#: Time units and their size in microseconds (TIME, TIME32) or nanoseconds
#: (LTIME), in the descending order the literal requires.
_TIME_UNITS: dict[str, dict[str, int]] = {
    "us": {
        "d": 86_400_000_000,
        "h": 3_600_000_000,
        "m": 60_000_000,
        "s": 1_000_000,
        "ms": 1_000,
        "us": 1,
    },
    "ns": {
        "d": 86_400_000_000_000,
        "h": 3_600_000_000_000,
        "m": 60_000_000_000,
        "s": 1_000_000_000,
        "ms": 1_000_000,
        "us": 1_000,
        "ns": 1,
    },
}

#: Exclusive upper bound of each unit except days.
_UNIT_LIMITS = {"h": 24, "m": 60, "s": 60, "ms": 1000, "us": 1000, "ns": 1000}

#: Largest magnitude accepted per type, in microseconds (TIME, TIME32) or
#: nanoseconds (LTIME). TIME32 is exact (a 32-bit count). For TIME the limit is
#: ``T#106750d_23h_59m_59s_999ms_999us``: Studio kept ``T#106750d`` and dropped
#: ``T#106751d``, so the true maximum lies between them and is not measured
#: more precisely. For LTIME 100000 days is a deliberately conservative limit
#: (``LT#106751d`` was dropped, the exact edge is unverified).
_TIME_LIMITS: dict[str, int] = {
    "TIME": 106_751 * 86_400_000_000 - 1,
    "TIME32": 2_147_483_647,
    "LTIME": 100_000 * 86_400 * 10**9,
}

_TIME_TOKEN = re.compile(r"(\d+)(ms|us|ns|d|h|m|s)", re.IGNORECASE)
_BARE_INT = re.compile(r"[+-]?\d+")
_DATETIME_RE = {
    "DT": re.compile(
        r"DT#(\d{4})-(\d{2})-(\d{2})-(\d{2}):(\d{2}):(\d{2})\.\d{3}_\d{3}Z"
    ),
    "LDT": re.compile(
        r"LDT#(\d{4})-(\d{2})-(\d{2})-(\d{2}):(\d{2}):(\d{2})"
        r"\.\d{3}_\d{3}_\d{3}Z"
    ),
}


def _time_kind(data_type: str) -> str:
    """Return the upper-case TIME-family type name.

    Args:
        data_type: ``TIME``, ``TIME32`` or ``LTIME`` (any case).

    Returns:
        The upper-case name.

    Raises:
        TypeError: If the type is not one of those three.
    """
    kind = data_type.upper()
    if kind not in _TIME_LIMITS:
        raise TypeError(f"{data_type} is not a TIME, TIME32 or LTIME type")
    return kind


def _time_base(kind: str) -> str:
    """Return the base unit of a TIME-family type.

    Args:
        kind: ``TIME``, ``TIME32`` or ``LTIME``.

    Returns:
        ``"ns"`` for LTIME, else ``"us"``.
    """
    return "ns" if kind == "LTIME" else "us"


def _check_time_range(count: int, kind: str) -> int:
    """Check a count against the type's (conservative) range.

    Args:
        count: Microseconds (TIME, TIME32) or nanoseconds (LTIME).
        kind: The upper-case type name.

    Returns:
        *count*.

    Raises:
        ValueError: If ``abs(count)`` exceeds the limit.
    """
    if abs(count) > _TIME_LIMITS[kind]:
        raise ValueError(
            f"{count} is out of range for {kind} (at most +/-{_TIME_LIMITS[kind]})"
        )
    return count


def parse_time_literal(text: str, data_type: str) -> int:
    """Parse a TIME, TIME32 or LTIME value the way Studio does.

    Accepts exactly what Studio keeps, as measured on v37:

    - a bare integer, meaning microseconds (TIME, TIME32) or nanoseconds
      (LTIME), possibly negative;
    - ``T#``, ``T32#`` or ``LT#`` (the type's own prefix, any case), an
      optional ``-`` right after it, then one or more ``<digits><unit>``
      groups with units ``d h m s ms us`` (plus ``ns`` for LTIME, any case),
      each at most once and in descending order, optionally separated by
      ``_``. Every unit except ``d`` must be in range (hours below 24,
      minutes and seconds below 60, the others below 1000), even as the first
      unit: ``T#90m`` is rejected.

    Everything Studio drops or zeroes raises: fractions (``T#2.5s``), spaces,
    ``-T#5s``, ``TIME#5s``, units out of order (``T#500ms5s``), ``ns`` in a
    TIME, a wrong prefix (``T#5s`` for TIME32 or LTIME), and counts beyond the
    range (TIME32 +/-2147483647 us; TIME up to just under 106751 days, and
    LTIME up to 100000 days, whose true edges are unverified).

    Args:
        text: The literal or bare integer text.
        data_type: ``TIME``, ``TIME32`` or ``LTIME``.

    Returns:
        The count in microseconds (TIME, TIME32) or nanoseconds (LTIME).

    Raises:
        TypeError: If *data_type* is not a TIME-family type.
        ValueError: If *text* is not accepted.
    """
    kind = _time_kind(data_type)
    prefix = TIME_PREFIXES[kind]
    text = text.strip()
    if _BARE_INT.fullmatch(text):
        return _check_time_range(int(text), kind)
    if not text.upper().startswith(prefix):
        raise ValueError(f"{kind} literal must start with {prefix!r}: {text!r}")
    body = text[len(prefix) :]
    sign = 1
    if body.startswith("-"):
        sign, body = -1, body[1:]
    units = _TIME_UNITS[_time_base(kind)]
    order = list(units)
    position = 0
    last = -1
    total = 0
    while True:
        match = _TIME_TOKEN.match(body, position)
        if match is None:
            raise ValueError(f"invalid {kind} literal: {text!r}")
        unit = match.group(2).lower()
        if unit not in units:
            raise ValueError(f"unit {unit!r} is not valid for {kind}: {text!r}")
        index = order.index(unit)
        if index <= last:
            raise ValueError(f"units out of order or repeated in {text!r}")
        value = int(match.group(1))
        if unit in _UNIT_LIMITS and value >= _UNIT_LIMITS[unit]:
            raise ValueError(f"{value}{unit} is out of range in {text!r}")
        total += value * units[unit]
        last = index
        position = match.end()
        if position == len(body):
            break
        if body[position] == "_":
            position += 1
            if position == len(body):
                raise ValueError(f"invalid {kind} literal: {text!r}")
    return _check_time_range(sign * total, kind)


def format_time_literal(count: int, data_type: str) -> str:
    """Format a count as Studio's canonical TIME, TIME32 or LTIME literal.

    Units are in descending order, joined by ``_``, zero-valued units are left
    out and units are lower case. The sign goes right after the prefix, and
    zero is written with the smallest unit (``T#0us``, ``T32#0us``,
    ``LT#0ns``).

    Args:
        count: Microseconds (TIME, TIME32) or nanoseconds (LTIME).
        data_type: ``TIME``, ``TIME32`` or ``LTIME``.

    Returns:
        For example ``"T#1h_30m"`` or ``"LT#5us"``.

    Raises:
        TypeError: If *count* is not an ``int`` (or is a ``bool``), or
            *data_type* is not a TIME-family type.
        ValueError: If *count* is out of range.
    """
    kind = _time_kind(data_type)
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError(f"{kind} count must be an int, not {type(count).__name__}")
    _check_time_range(count, kind)
    base = _time_base(kind)
    prefix = TIME_PREFIXES[kind]
    if count == 0:
        return f"{prefix}0{base}"
    remaining = abs(count)
    parts = []
    for unit, size in _TIME_UNITS[base].items():
        amount, remaining = divmod(remaining, size)
        if amount:
            parts.append(f"{amount}{unit}")
    return f"{prefix}{'-' if count < 0 else ''}{'_'.join(parts)}"


def time_count(value: Any, data_type: str) -> int:
    """Convert an ``int``, ``timedelta`` or ``str`` to a TIME-family count.

    Args:
        value: An ``int`` (microseconds, or nanoseconds for LTIME), a
            ``datetime.timedelta`` (exact: its resolution is one microsecond,
            so TIME and TIME32 never lose precision) or a literal ``str`` (see
            :func:`parse_time_literal`).
        data_type: ``TIME``, ``TIME32`` or ``LTIME``.

    Returns:
        The count in microseconds (TIME, TIME32) or nanoseconds (LTIME).

    Raises:
        TypeError: If *value* is another type (``bool`` included).
        ValueError: If a string is not accepted or the count is out of range.
    """
    kind = _time_kind(data_type)
    if isinstance(value, bool):
        raise TypeError(f"{kind} value must not be a bool")
    if isinstance(value, int):
        return _check_time_range(value, kind)
    if isinstance(value, timedelta):
        micros = value // timedelta(microseconds=1)
        return _check_time_range(micros * 1000 if kind == "LTIME" else micros, kind)
    if isinstance(value, str):
        return parse_time_literal(value, kind)
    raise TypeError(
        f"{kind} value must be an int, timedelta or str, not {type(value).__name__}"
    )


def normalize_time_literal(value: Any, data_type: str) -> str:
    """Turn an ``int``, ``timedelta`` or ``str`` into the canonical literal.

    Args:
        value: See :func:`time_count`.
        data_type: ``TIME``, ``TIME32`` or ``LTIME``.

    Returns:
        The canonical literal, so ``"T#1h30m"`` becomes ``"T#1h_30m"``.

    Raises:
        TypeError: If *value* has the wrong type.
        ValueError: If *value* is not accepted or out of range.
    """
    return format_time_literal(time_count(value, data_type), data_type)


def normalize_datetime_literal(value: Any, data_type: str) -> str:
    """Validate a DT or LDT value, or format a ``datetime``.

    A ``str`` must have the canonical shape
    ``DT#YYYY-MM-DD-hh:mm:ss.ffffff_Z`` (``LDT#...ffffffffff_Z`` with nine
    fraction digits, shown as ``fff_fff_fff``), including the trailing ``Z``:
    without it Studio applies the local time zone. It is kept verbatim. A
    ``datetime`` must be timezone-aware; it is converted to UTC and formatted
    canonically (an LDT gets zero nanoseconds beyond the microseconds).

    Args:
        value: A ``str`` or an aware ``datetime``.
        data_type: ``DT`` or ``LDT``.

    Returns:
        The literal.

    Raises:
        TypeError: If *value* has the wrong type or *data_type* is not DT/LDT.
        ValueError: If the string does not have the required shape, names an
            impossible date or time, or the ``datetime`` is naive.
    """
    kind = data_type.upper()
    if kind not in _DATETIME_RE:
        raise TypeError(f"{data_type} is not a DT or LDT type")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("a datetime must be timezone-aware (it is stored in UTC)")
        utc = value.astimezone(UTC)
        micro = f"{utc.microsecond:06d}"
        fraction = f"{micro[:3]}_{micro[3:]}" + ("_000" if kind == "LDT" else "")
        return f"{kind}#{utc:%Y-%m-%d-%H:%M:%S}.{fraction}Z"
    if not isinstance(value, str):
        raise TypeError(
            f"{kind} value must be a str or datetime, not {type(value).__name__}"
        )
    match = _DATETIME_RE[kind].fullmatch(value)
    if match is None:
        raise ValueError(
            f"{kind} literal must look like "
            f"{kind}#2026-11-16-12:30:00.000_000{'_000' if kind == 'LDT' else ''}Z "
            f"(the trailing Z is required): {value!r}"
        )
    try:
        datetime(*(int(part) for part in match.groups()))
    except ValueError as exc:
        raise ValueError(f"{kind} literal is not a valid date: {value!r}") from exc
    return value


#: Escapes Studio writes for control characters in string literals.
_STRING_ESCAPES: dict[int, str] = {
    0x0A: "$l",
    0x0D: "$r",
    0x09: "$t",
    0x0C: "$p",
    0x24: "$$",
    0x27: "$'",
}

#: Decoded form of each single-letter string escape (matched case-insensitively).
_STRING_LETTER_ESCAPES: dict[str, str] = {
    "L": "\n",
    "N": "\r\n",
    "R": "\r",
    "T": "\t",
    "P": "\f",
    "$": "$",
    "'": "'",
}


def parse_string_literal(text: str) -> str:
    """Decode the text of a Logix string literal.

    Surrounding whitespace and one pair of single quotes are removed, then
    escapes are decoded (letters case-insensitively): ``$$``, ``$'``,
    ``$L`` (newline), ``$N`` (CR LF), ``$R``, ``$T``, ``$P`` (form feed) and
    ``$hh`` (two hex digits, one character). A ``$`` that does not start a
    valid escape is kept as is.

    Args:
        text: The raw CDATA text (for example ``"'SRVO-003'"``).

    Returns:
        The decoded string. Unquoted text is decoded too.
    """
    text = text.strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        text = text[1:-1]
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "$" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt.upper() in _STRING_LETTER_ESCAPES:
                out.append(_STRING_LETTER_ESCAPES[nxt.upper()])
                i += 2
                continue
            pair = text[i + 1 : i + 3]
            if len(pair) == 2 and all(c in _HEX_DIGITS for c in pair):
                out.append(chr(int(pair, 16)))
                i += 3
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def format_string_literal(text: str) -> str:
    """Return the quoted Logix literal for a string, as Studio canonicalizes it.

    Newline, CR, tab and form feed become ``$l``, ``$r``, ``$t`` and ``$p``;
    ``$`` and ``'`` become ``$$`` and ``$'``; other characters below 0x20 or
    in 0x7F-0xFF become ``$HH`` (upper-case hex); printable ASCII, including
    ``"``, is written as is.

    Args:
        text: The string. Every character must be at most U+00FF.

    Returns:
        The text in single quotes with escapes applied.

    Raises:
        TypeError: If *text* is not a ``str``.
        ValueError: If a character is above U+00FF.
    """
    if not isinstance(text, str):
        raise TypeError(f"string value must be a str, not {type(text).__name__}")
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if code > 0xFF:
            raise ValueError(f"character {ch!r} is outside Latin-1")
        if code in _STRING_ESCAPES:
            out.append(_STRING_ESCAPES[code])
        elif 0x20 <= code <= 0x7E:
            out.append(ch)
        else:
            out.append(f"${code:02X}")
    return "'" + "".join(out) + "'"

"""Tests for py_l5x.parsers.atomic_types (atomic data type table)."""

from __future__ import annotations

import math

import pytest

from py_l5x.parsers.atomic_types import (
    ATOMIC_TYPES,
    AtomicInfo,
    atomic_info,
    parse_float_literal,
    parse_integer_literal,
)
from py_l5x.parsers.utils import convert_numeric


class TestAtomicTypesTable:
    """Every expected atomic type is present with correct metadata."""

    @pytest.mark.parametrize(
        ("name", "family", "bit_width", "signed", "unit"),
        [
            ("BOOL", "bool", 1, False, None),
            ("SINT", "integer", 8, True, None),
            ("INT", "integer", 16, True, None),
            ("DINT", "integer", 32, True, None),
            ("LINT", "integer", 64, True, None),
            ("USINT", "integer", 8, False, None),
            ("UINT", "integer", 16, False, None),
            ("UDINT", "integer", 32, False, None),
            ("ULINT", "integer", 64, False, None),
            ("BYTE", "integer", 8, False, None),
            ("WORD", "integer", 16, False, None),
            ("DWORD", "integer", 32, False, None),
            ("LWORD", "integer", 64, False, None),
            ("REAL", "float", 32, True, None),
            ("LREAL", "float", 64, True, None),
            ("TIME32", "time", 32, True, "us"),
            ("TIME", "time", 64, True, "us"),
            ("LTIME", "time", 64, True, "ns"),
            ("DT", "datetime", 64, True, "us"),
            ("LDT", "datetime", 64, True, "ns"),
        ],
    )
    def test_entry_metadata(
        self,
        name: str,
        family: str,
        bit_width: int,
        signed: bool,
        unit: str | None,
    ) -> None:
        """Each expected name has the right family, width, sign, and unit."""
        info = ATOMIC_TYPES[name]
        assert isinstance(info, AtomicInfo)
        assert info.name == name
        assert info.family == family
        assert info.bit_width == bit_width
        assert info.signed is signed
        assert info.unit == unit

    def test_signed_integer_ranges(self) -> None:
        """Signed integers use the natural two's-complement range."""
        assert (ATOMIC_TYPES["SINT"].min, ATOMIC_TYPES["SINT"].max) == (-128, 127)
        assert (ATOMIC_TYPES["DINT"].min, ATOMIC_TYPES["DINT"].max) == (
            -(2**31),
            2**31 - 1,
        )

    def test_unsigned_integer_ranges(self) -> None:
        """Unsigned integers range from 0 to 2**n - 1."""
        assert (ATOMIC_TYPES["ULINT"].min, ATOMIC_TYPES["ULINT"].max) == (
            0,
            2**64 - 1,
        )

    def test_bool_range(self) -> None:
        """BOOL ranges from 0 to 1."""
        assert (ATOMIC_TYPES["BOOL"].min, ATOMIC_TYPES["BOOL"].max) == (0, 1)

    def test_non_numeric_ranges_are_none(self) -> None:
        """Float and time/datetime types have no numeric min/max."""
        for name in ("REAL", "LREAL", "TIME32", "TIME", "LTIME", "DT", "LDT"):
            assert ATOMIC_TYPES[name].min is None
            assert ATOMIC_TYPES[name].max is None


class TestAtomicInfoLookup:
    """Case-insensitive lookup via atomic_info()."""

    def test_case_insensitive(self) -> None:
        """Lower-case names resolve to the same entry."""
        assert atomic_info("dint") is ATOMIC_TYPES["DINT"]
        assert atomic_info("Dint") is ATOMIC_TYPES["DINT"]

    def test_unknown_name_returns_none(self) -> None:
        """UDT/AOI names and typos return None."""
        assert atomic_info("simple_udt") is None
        assert atomic_info("NOT_A_TYPE") is None


class TestAtomicTypesReadOnly:
    """ATOMIC_TYPES is a read-only mapping."""

    def test_assignment_raises(self) -> None:
        """Adding a new key raises TypeError."""
        with pytest.raises(TypeError):
            ATOMIC_TYPES["FAKE"] = AtomicInfo(  # type: ignore[index]
                "FAKE", "bool", 1, False, 0, 1, None
            )

    def test_deletion_raises(self) -> None:
        """Removing a key raises TypeError."""
        with pytest.raises(TypeError):
            del ATOMIC_TYPES["BOOL"]  # type: ignore[index]


class TestConvertNumericWithAtomicTable:
    """convert_numeric behaviour driven by the atomic type table."""

    def test_time_literal_unchanged(self) -> None:
        """TIME values are literal strings and pass through unchanged."""
        assert convert_numeric("T#10ms", "TIME") == "T#10ms"

    def test_datetime_literal_unchanged(self) -> None:
        """DT values are literal strings and pass through unchanged."""
        assert (
            convert_numeric("DT#1970-01-01-00:00:00.000_000Z", "DT")
            == "DT#1970-01-01-00:00:00.000_000Z"
        )

    def test_based_literal(self) -> None:
        """Based literals are interpreted as raw bit patterns."""
        assert convert_numeric("16#FF", "SINT") == -1
        assert convert_numeric("2#0000_0001", "DINT") == 1

    def test_ascii_literal(self) -> None:
        """Single-quoted ASCII literals are byte patterns."""
        assert convert_numeric("'$00'", "SINT") == 0

    def test_float_specials(self) -> None:
        """Logix float specials convert to NaN/inf."""
        assert math.isnan(convert_numeric("1.#QNAN", "REAL"))

    def test_unparseable_based_falls_back_to_str(self) -> None:
        """Values that don't parse cleanly are returned unchanged."""
        assert convert_numeric("bogus", "DINT") == "bogus"


class TestParseIntegerLiteral:
    """parse_integer_literal handles decimal, based, and ASCII literals."""

    @pytest.mark.parametrize(
        ("text", "type_name", "expected"),
        [
            # Decimal with optional sign and surrounding whitespace.
            ("0", "SINT", 0),
            ("-5", "DINT", -5),
            ("+7", "DINT", 7),
            ("  42  ", "INT", 42),
            (" -12 ", "SINT", -12),
            # BOOL goes through the same rules.
            ("1", "BOOL", 1),
            ("0", "BOOL", 0),
            # Hex / binary / octal, with underscores anywhere.
            ("16#00", "SINT", 0),
            ("16#ff", "USINT", 255),
            ("2#0000_0001", "DINT", 1),
            ("8#17", "SINT", 15),
            ("16#_FF_", "USINT", 255),
            ("2#1_0_1", "BYTE", 5),
            ("8#1_7", "USINT", 15),
            # Signed wrap: top bit set at the type's bit width.
            ("16#FF", "SINT", -1),
            ("16#FFFF", "INT", -1),
            ("16#FFFFFFFF", "DINT", -1),
            ("16#FFFFFFFFFFFFFFFF", "LINT", -1),
            ("2#1000_0000", "SINT", -128),
            # No wrap for unsigned types.
            ("16#FF", "USINT", 255),
            ("16#FFFFFFFF", "UDINT", 2**32 - 1),
            ("16#FFFFFFFFFFFFFFFF", "ULINT", 2**64 - 1),
            # ASCII literals: single char, multi-char, and escapes.
            ("'A'", "SINT", 0x41),
            ("'$41$42'", "INT", 0x4142),
            ("'$00'", "SINT", 0),
            ("'$FF'", "SINT", -1),
            ("'$41'", "SINT", 0x41),
            ("'$$'", "SINT", 0x24),
            ("'$''", "SINT", 0x27),
            ("'$L'", "SINT", 0x0A),
            ("'$N'", "SINT", 0x0A),
            ("'$P'", "SINT", 0x0C),
            ("'$R'", "SINT", 0x0D),
            ("'$T'", "SINT", 0x09),
            ("'$l'", "SINT", 0x0A),
            ("'$t'", "SINT", 0x09),
            ("'aB'", "INT", 0x6142),
        ],
    )
    def test_valid_literals(self, text: str, type_name: str, expected: int) -> None:
        """Valid decimal, based, and ASCII literals parse correctly."""
        assert parse_integer_literal(text, ATOMIC_TYPES[type_name]) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "16#",
            "3#1",
            "16#G",
            "2#2",
            "8#8",
            "'$Z'",
            "'$4'",
            "'abc",
            "abc",
            "16#FF extra",
            "1.5",
        ],
    )
    def test_invalid_literals_raise(self, text: str) -> None:
        """Anything outside the literal grammar raises ValueError."""
        with pytest.raises(ValueError):
            parse_integer_literal(text, ATOMIC_TYPES["DINT"])

    @pytest.mark.parametrize(
        ("text", "type_name"),
        [
            ("16#1FF", "SINT"),
            ("'ABC'", "SINT"),
            ("128", "SINT"),
            ("-129", "SINT"),
            ("-1", "USINT"),
            ("2", "BOOL"),
            (str(2**64), "ULINT"),
        ],
    )
    def test_out_of_range_raises(self, text: str, type_name: str) -> None:
        """Values that don't fit the type's width/range raise ValueError."""
        with pytest.raises(ValueError):
            parse_integer_literal(text, ATOMIC_TYPES[type_name])


class TestParseFloatLiteral:
    """parse_float_literal handles plain floats and Logix specials."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("3.14", 3.14),
            ("-2.5", -2.5),
            ("  1.0  ", 1.0),
            ("1e3", 1000.0),
            ("1.#QNAN", math.nan),
            ("-1.#QNAN", math.nan),
            ("1.#qnan", math.nan),
            ("1.#INF", math.inf),
            ("1.#inf", math.inf),
            ("-1.#INF", -math.inf),
            ("-1.#Inf", -math.inf),
        ],
    )
    def test_valid_literals(self, text: str, expected: float) -> None:
        """Plain floats and Logix specials parse correctly."""
        result = parse_float_literal(text)
        if math.isnan(expected):
            assert math.isnan(result)
        else:
            assert result == expected

    @pytest.mark.parametrize("text", ["", "abc", "1.#QNaNx", "1.#INF0"])
    def test_invalid_literals_raise(self, text: str) -> None:
        """Unrecognised float literals raise ValueError."""
        with pytest.raises(ValueError):
            parse_float_literal(text)

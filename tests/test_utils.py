"""Tests for py_l5x.parsers.utils (parse_int and cdata_text)."""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.utils import CDATA_TAG, cdata_text, parse_int


def _el(xml: str) -> ET.Element:
    """Parse a single XML fragment into an element."""
    return ET.fromstring(xml)


class TestParseInt:
    """parse_int returns an int for valid input and None otherwise."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("0", 0), ("2", 2), ("-1", -1), ("65535", 65535)],
    )
    def test_valid_integers(self, value: str, expected: int) -> None:
        """Decimal integer strings parse to ints."""
        assert parse_int(value) == expected

    @pytest.mark.parametrize("value", [None, "", "abc", "1.5", "-", "16#FF"])
    def test_invalid_or_empty_returns_none(self, value: str | None) -> None:
        """Missing, empty, and non-integer values return None."""
        assert parse_int(value) is None


class TestCdataText:
    """cdata_text prefers the CDATA child and falls back to element text."""

    def test_none_element_returns_empty_string(self) -> None:
        """A missing element yields an empty string."""
        assert cdata_text(None) == ""

    def test_plain_text(self) -> None:
        """An element with only text content returns that text."""
        assert cdata_text(_el("<Desc>hello</Desc>")) == "hello"

    def test_no_text_returns_empty_string(self) -> None:
        """An element with no text at all returns an empty string."""
        assert cdata_text(_el("<Desc/>")) == ""

    def test_cdata_child_preferred_over_element_text(self) -> None:
        """When a CDATA child has text, it wins over the element's own text."""
        el = _el("<Desc>fallback<CDataContent>from cdata</CDataContent></Desc>")
        assert cdata_text(el) == "from cdata"

    def test_empty_cdata_falls_back_to_element_text(self) -> None:
        """An empty CDATA child defers to the element's own text."""
        el = _el("<Desc>plain<CDataContent></CDataContent></Desc>")
        assert cdata_text(el) == "plain"

    def test_empty_cdata_and_no_text_returns_empty_string(self) -> None:
        """An empty CDATA child with no element text yields an empty string."""
        assert cdata_text(_el("<Desc><CDataContent></CDataContent></Desc>")) == ""

    def test_default_strips_surrounding_whitespace(self) -> None:
        """The default (strip=True) removes all surrounding whitespace."""
        assert cdata_text(_el("<Desc>\n  spaced  \n</Desc>")) == "spaced"

    def test_whitespace_only_strips_to_empty(self) -> None:
        """Whitespace-only text strips to an empty string by default."""
        assert cdata_text(_el("<Desc>   </Desc>")) == ""

    def test_strip_false_returns_text_unchanged(self) -> None:
        """strip=False returns the raw text, including surrounding whitespace."""
        assert cdata_text(_el("<Desc>\n\t x \n</Desc>"), strip=False) == "\n\t x \n"

    def test_strip_false_with_cdata_child(self) -> None:
        """strip=False still prefers the CDATA child, untrimmed."""
        el = _el("<Desc><CDataContent>\n  raw\n</CDataContent></Desc>")
        assert cdata_text(el, strip=False) == "\n  raw\n"

    def test_strip_chars_preserves_leading_indentation(self) -> None:
        """A strip string removes only those characters (ST indentation kept)."""
        el = _el("<Line>\n\t  IF x THEN\n</Line>")
        assert cdata_text(el, strip="\r\n") == "\t  IF x THEN"

    def test_strip_chars_with_cdata_child(self) -> None:
        """Newline-only stripping applies to CDATA text as well."""
        el = _el(f"<Line><{CDATA_TAG}>\n    y := 1;\n</{CDATA_TAG}></Line>")
        assert cdata_text(el, strip="\r\n") == "    y := 1;"

    def test_strip_chars_empty_string_strips_nothing(self) -> None:
        """An empty strip string leaves the text untouched."""
        assert cdata_text(_el("<Line>  x  </Line>"), strip="") == "  x  "

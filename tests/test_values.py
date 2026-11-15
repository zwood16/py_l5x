"""Tests for writable tag values (``value`` setters on value-tree nodes)."""

import math
import re
import struct
from collections.abc import Callable
from pathlib import Path

import pytest

from py_l5x import Project, load, loads
from py_l5x.parsers.atomic_types import (
    ATOMIC_TYPES,
    format_float_literal,
    format_integer_literal,
    format_string_literal,
    parse_float_literal,
    parse_string_literal,
)
from py_l5x.parsers.tag import TagNode

FIXTURES = Path(__file__).parent / "fixtures"

#: Float-radix golden cases where Studio picks positional text but the
#: writer picks exponential (the values still round-trip exactly).
FLOAT_RADIX_MISMATCHES = {"v146_LREAL_Float"}


def _float32(value: float) -> float:
    """Round a float to float32.

    Args:
        value: The float to round.

    Returns:
        The nearest float32 value as a Python float.
    """
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _golden_tags() -> list[str]:
    """List the controller tag names in the golden radix file.

    Returns:
        Tag names in document order.
    """
    return list(load(str(FIXTURES / "radix_values_Tags.L5X")).controller_tags)


class TestGolden:
    """Writing a value back reproduces Studio's canonical text."""

    @pytest.mark.parametrize("name", _golden_tags())
    def test_write_back(self, name: str) -> None:
        """Rewriting a tag's own value gives the same ``Value`` text."""
        project = load(str(FIXTURES / "radix_values_Tags.L5X"))
        tag = project.controller_tags[name]
        element = tag.value_element
        before = element.get("Value")
        value = tag.value
        tag.value = value
        after = element.get("Value")
        assert tag.value == value
        if "REAL" in name:
            assert tag.data_type in ("REAL", "LREAL")
            parsed = parse_float_literal(after)
            expected = _float32(value) if tag.data_type == "REAL" else value
            assert (_float32(parsed) if tag.data_type == "REAL" else parsed) == expected
            if "_Float" in name and name in FLOAT_RADIX_MISMATCHES:
                assert after != before
                return
        assert after == before

    def test_mismatch_set_is_exact(self) -> None:
        """Every Float-radix mismatch is listed, and nothing else differs."""
        project = load(str(FIXTURES / "radix_values_Tags.L5X"))
        differing = set()
        for name, tag in project.controller_tags.items():
            before = tag.value_element.get("Value")
            tag.value = tag.value
            if tag.value_element.get("Value") != before:
                differing.add(name)
        assert differing == FLOAT_RADIX_MISMATCHES


def _example() -> Project:
    """Load the main example project.

    Returns:
        The parsed ``example.L5X`` project.
    """
    return load(str(FIXTURES / "example.L5X"))


def _main(p: Project, name: str) -> TagNode:
    """Return a ``MainProgram`` tag.

    Args:
        p: The project.
        name: Tag name.

    Returns:
        The tag.
    """
    return p.programs["MainProgram"].tags[name]


CASES: dict[str, tuple[Callable[[Project], TagNode], object]] = {
    "controller_dint": (lambda p: p.controller_tags["toSafety_reset"], 1),
    "program_dint": (lambda p: _main(p, "a_dint"), 42),
    "timer_pre": (lambda p: _main(p, "a_timer").members["PRE"], 1000),
    "udt_bool": (lambda p: _main(p, "a_udt_instance").members["a_Bool"], True),
    "udt_real": (lambda p: _main(p, "a_udt_instance").members["a_real"], 1.5),
    "array_1d": (lambda p: _main(p, "a_udt_instance").members["an_array"][2], 2.25),
    "array_2d": (lambda p: _main(p, "a_2d_array")[1, 2], 7),
    "nested_udt": (
        lambda p: _main(p, "a_udt_instance").members["a_nested_UDT"].members["Dint"],
        123,
    ),
    "string_root": (lambda p: _main(p, "a_string"), "abc"),
    "custom_string": (lambda p: _main(p, "a_custom_string"), "hello"),
    "string_in_array": (lambda p: p.controller_tags["ALLOWABLE_ALARMS"][3], "ABC-123"),
    "aoi_member": (
        lambda p: _main(p, "a_udt_instance").members["an_aoi"].members["onDelay"],
        500,
    ),
    "aoi_param_default": (lambda p: p.aois["Debounce"].parameters["onDelay"], 250),
    "aoi_local_default": (
        lambda p: p.aois["Debounce"].local_tags["debounceOnTimer"].members["PRE"],
        99,
    ),
}


def _l5k_count(text: str) -> int:
    """Count ``Format="L5K"`` sections in serialized text.

    Args:
        text: Document text.

    Returns:
        The number of L5K ``Data``/``DefaultData`` start tags.
    """
    return len(re.findall(r'<(?:Default)?Data Format="L5K"', text))


def _owner_l5k(node: TagNode) -> int:
    """Count the L5K data children of a node's owning element.

    Args:
        node: Any node of the tag.

    Returns:
        The number of ``Data``/``DefaultData`` children with ``Format="L5K"``.
    """
    owner = node._overrides.owner
    return sum(
        1
        for child in owner
        if child.tag in ("Data", "DefaultData") and child.get("Format") == "L5K"
    )


class TestWrites:
    """Writes against the example project."""

    @pytest.mark.parametrize("case", list(CASES))
    def test_write(self, case: str) -> None:
        """A write reads back, survives a round trip and drops only its L5K."""
        get, new_value = CASES[case]
        project = _example()
        before_text = project.to_string()
        node = get(project)
        stale = _owner_l5k(node)
        assert stale >= 1
        node.value = new_value

        assert get(project).value == new_value
        assert _owner_l5k(node) == 0

        text = project.to_string()
        assert get(loads(text)).value == new_value
        # Only the owner's L5K sections are gone.
        assert _l5k_count(text) == _l5k_count(before_text) - stale
        # No two elements share a line (outside CDATA), as before the write.
        without_cdata = re.sub(r"<!\[CDATA\[.*?\]\]>", "", text, flags=re.DOTALL)
        baseline = re.sub(r"<!\[CDATA\[.*?\]\]>", "", before_text, flags=re.DOTALL)
        assert without_cdata.count("><") == baseline.count("><")
        # No blank lines were introduced.
        assert text.count("\r\n\r\n") == before_text.count("\r\n\r\n")

    def test_nested_string_shape(self) -> None:
        """A nested string sets LEN and the quoted DATA literal."""
        project = _example()
        node = project.controller_tags["ALLOWABLE_ALARMS"][3]
        node.value = "ABC-123"
        element = node.value_element
        len_el, data_el = list(element)
        assert len_el.get("Value") == "7"
        assert data_el[0].text == "'ABC-123'"
        node.value = ""
        assert len_el.get("Value") == "0"
        assert data_el[0].text == ""

    def test_root_string_shape(self) -> None:
        """A root string sets Length and the CDATA literal."""
        project = _example()
        tag = _main(project, "a_string")
        tag.value = "abc"
        element = tag.value_element
        assert element.get("Length") == "3"
        assert element[0].text == "'abc'"
        tag.value = ""
        assert element.get("Length") == "0"
        assert element[0].text == "''"
        assert "<![CDATA['']]>" in project.to_string()

    def test_string_escapes(self) -> None:
        """Special characters are escaped in the stored literal."""
        project = _example()
        tag = _main(project, "a_string")
        tag.value = "a$'\né"
        assert tag.value_element[0].text == "'a$$$'$l$E9'"
        assert tag.value_element.get("Length") == "5"

    def test_radix_respected(self) -> None:
        """Writes use the node's radix."""
        project = load(str(FIXTURES / "radix_values_Tags.L5X"))
        tag = project.controller_tags["v006_SINT_Hex"]
        tag.value = -1
        assert tag.value_element.get("Value") == "16#ff"

    def test_bit_via_integer_not_writable(self) -> None:
        """Bits are read-only."""
        node = _main(_example(), "a_dint").bit(3)
        with pytest.raises(TypeError):
            node.value = True

    def test_synthetic_string_len_not_writable(self) -> None:
        """A synthetic LEN member (root string) is read-only."""
        node = _main(_example(), "a_string").members["LEN"]
        with pytest.raises(TypeError):
            node.value = 3

    def test_string_data_member_not_writable(self) -> None:
        """The DATA member (generic atomic fallback) is read-only."""
        node = _main(_example(), "a_custom_string").members["DATA"]
        with pytest.raises(TypeError):
            node.value = "x"


class TestErrors:
    """Invalid assignments raise and leave the XML unchanged."""

    @pytest.fixture
    def project(self) -> Project:
        """The example project."""
        return _example()

    def _unchanged(self, project: Project, action: Callable[[], None], exc: type):
        """Assert *action* raises *exc* and the document is untouched.

        Args:
            project: The project being edited.
            action: A callable performing the bad write.
            exc: The expected exception type.
        """
        before = project.to_string()
        with pytest.raises(exc):
            action()
        assert project.to_string() == before

    def test_out_of_range(self, project: Project) -> None:
        """SINT 128 and USINT -1 are out of range."""
        sint = _main(project, "a_sint")
        usint = _main(project, "an_unsigned_sint")

        def set_sint() -> None:
            sint.value = 128

        def set_usint() -> None:
            usint.value = -1

        self._unchanged(project, set_sint, ValueError)
        self._unchanged(project, set_usint, ValueError)

    @pytest.mark.parametrize("bad", ["5", True, 1.5])
    def test_wrong_type_for_dint(self, project: Project, bad: object) -> None:
        """str, bool and float are rejected for a DINT."""
        tag = _main(project, "a_dint")

        def go() -> None:
            tag.value = bad

        self._unchanged(project, go, TypeError)

    def test_bool_values(self, project: Project) -> None:
        """BOOL takes bools and 0/1 only."""
        tag = _main(project, "a_bool")
        tag.value = 1
        assert tag.value is True
        tag.value = False
        assert tag.value is False
        with pytest.raises(ValueError):
            tag.value = 2
        with pytest.raises(TypeError):
            tag.value = "1"

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, 1e39])
    def test_bad_real(self, project: Project, bad: float) -> None:
        """Non-finite or float32-overflowing values are rejected for a REAL."""
        tag = _main(project, "a_real")

        def go() -> None:
            tag.value = bad

        self._unchanged(project, go, ValueError)

    def test_real_wrong_type(self, project: Project) -> None:
        """A str is rejected for a REAL."""
        tag = _main(project, "a_real")

        def go() -> None:
            tag.value = "1.5"

        self._unchanged(project, go, TypeError)

    def test_string_too_long(self, project: Project) -> None:
        """Strings over max_length are rejected."""
        tag = _main(project, "a_string")

        def go() -> None:
            tag.value = "x" * 83

        self._unchanged(project, go, ValueError)

    def test_string_too_long_custom(self, project: Project) -> None:
        """A custom string type's own capacity applies."""
        tag = _main(project, "a_custom_string")

        def go() -> None:
            tag.value = "x" * (tag.max_length + 1)

        self._unchanged(project, go, ValueError)

    def test_string_non_latin1(self, project: Project) -> None:
        """Characters outside Latin-1 are rejected."""
        tag = _main(project, "a_string")

        def go() -> None:
            tag.value = "caf€"

        self._unchanged(project, go, ValueError)

    def test_string_wrong_type(self, project: Project) -> None:
        """A non-str is rejected for a string."""
        tag = _main(project, "a_string")

        def go() -> None:
            tag.value = 5

        self._unchanged(project, go, TypeError)

    def test_time_without_prefix(self, project: Project) -> None:
        """A TIME literal needs its prefix; the right one is stored as given."""
        tag = _main(project, "duration")

        def go() -> None:
            tag.value = "5s"

        self._unchanged(project, go, ValueError)
        tag.value = "T#5s"
        assert tag.value == "T#5s"
        assert tag.value_element.get("Value") == "T#5s"

    def test_time_wrong_type(self, project: Project) -> None:
        """A non-str is rejected for a TIME."""
        tag = _main(project, "duration")

        def go() -> None:
            tag.value = 5

        self._unchanged(project, go, TypeError)

    @pytest.mark.parametrize(
        ("name", "good", "wrong_prefix"),
        [
            ("short_duration", "T32#5ms", "T#5ms"),
            ("long_duration", "LT#5ns", "T#5ns"),
            ("datetime", "DT#2020-01-01-00:00:00.000_000Z", "LDT#2020"),
            ("long_datetime", "LDT#2020-01-01-00:00:00.000_000_000Z", "DT#2020"),
        ],
    )
    def test_time_family_prefixes(
        self, project: Project, name: str, good: str, wrong_prefix: str
    ) -> None:
        """Each time-family type requires its own prefix."""
        tag = _main(project, name)
        with pytest.raises(ValueError):
            tag.value = wrong_prefix
        tag.value = good
        assert tag.value == good


class TestFormatting:
    """Direct tests of the formatting helpers."""

    @pytest.mark.parametrize(
        ("type_name", "value", "radix", "expected"),
        [
            ("DINT", 255, "Hex", "16#0000_00ff"),
            ("SINT", -1, "Hex", "16#ff"),
            ("INT", 255, "Octal", "8#000_377"),
            ("DINT", -1, "Octal", "8#37_777_777_777"),
            ("SINT", 5, "Binary", "2#0000_0101"),
            ("SINT", 65, "ASCII", "'A'"),
            ("INT", 255, "ASCII", "'$00$FF'"),
            ("SINT", 0x24, "ASCII", "'$$'"),
            ("SINT", 0x27, "ASCII", "'$''"),
            ("DINT", -5, None, "-5"),
            ("DINT", 7, "Decimal", "7"),
        ],
    )
    def test_integers(
        self, type_name: str, value: int, radix: str | None, expected: str
    ) -> None:
        """Integer formats follow Studio's."""
        assert format_integer_literal(value, ATOMIC_TYPES[type_name], radix) == expected

    @pytest.mark.parametrize(
        ("type_name", "value", "radix", "expected"),
        [
            ("REAL", 0.0, "Float", "0.0"),
            ("REAL", 100.0, "Float", "100.0"),
            ("REAL", 1.5, "Exponential", "1.50000000e+000"),
            ("LREAL", 0.1, "Exponential", "1.0000000000000000e-001"),
            ("REAL", 1e20, "Float", "1.00000000e+020"),
            ("REAL", 0.1 + 0.2, "Float", "0.3"),
            ("LREAL", 1e-10, "Float", "1.0000000000000000e-010"),
            ("REAL", 3, "Float", "3.0"),
        ],
    )
    def test_floats(
        self, type_name: str, value: float, radix: str, expected: str
    ) -> None:
        """Float formats follow Studio's (see the radix golden tests)."""
        assert format_float_literal(value, type_name, radix) == expected

    @pytest.mark.parametrize("type_name", ["REAL", "LREAL"])
    @pytest.mark.parametrize("radix", ["Float", "Exponential"])
    def test_floats_round_trip(self, type_name: str, radix: str) -> None:
        """Formatted floats parse back to the same value (float32 for REAL)."""
        import random

        rng = random.Random(1)
        values = [rng.uniform(-1, 1) * 10 ** rng.randint(-30, 30) for _ in range(500)]
        for value in values:
            text = format_float_literal(value, type_name, radix)
            parsed = parse_float_literal(text)
            if type_name == "REAL":
                assert _float32(parsed) == _float32(value), (value, text)
            else:
                assert parsed == value, (value, text)

    def test_string_literal(self) -> None:
        """String literals escape ``$``, ``'`` and non-printables."""
        assert format_string_literal("a'b$c\x00") == "'a$'b$$c$00'"

    def test_string_literal_canonical(self) -> None:
        """Control characters use Studio's lower-case letter escapes."""
        assert format_string_literal('\n\r\t\f"~\x7f\xff') == ("'$l$r$t$p\"~$7F$FF'")
        with pytest.raises(ValueError):
            format_string_literal("\u0100")


ESCAPES_FILE = FIXTURES / "string_escapes_Tags.L5X"

#: Tag name -> decoded text Studio holds (s02's trailing "b" was cut by Length).
ESCAPE_EXPECTED = {
    "s00": "a\nb",
    "s01": "a\nb",
    "s02": "a\r\n",
    "s03": "a\rb",
    "s04": "a\tb",
    "s05": "a\fb",
    "s06": "a\nb",
    "s07": "a\nb",
    "s08": "a\tb",
    "s09": "a~b",
    "s10": "a\u00e9b",
    "s11": "$'",
    "s12": 'a"b',
    "s13": "\u00e9",
    "s14": "tab\there",
}


class TestStringEscapes:
    """Reading and writing Logix string escapes."""

    @pytest.fixture
    def project(self) -> Project:
        """The string-escapes golden project."""
        return load(str(ESCAPES_FILE))

    def test_all_tags_covered(self, project: Project) -> None:
        """The expectation table lists every tag in the fixture."""
        assert set(project.controller_tags) == set(ESCAPE_EXPECTED)

    @pytest.mark.parametrize("name", sorted(ESCAPE_EXPECTED))
    def test_read(self, project: Project, name: str) -> None:
        """Decoded text and length match."""
        tag = project.controller_tags[name]
        assert tag.value == ESCAPE_EXPECTED[name]
        assert tag.len == len(ESCAPE_EXPECTED[name])

    @pytest.mark.parametrize("name", sorted(ESCAPE_EXPECTED))
    def test_write_back_matches_studio(self, project: Project, name: str) -> None:
        """Writing the decoded value reproduces Studio's literal and Length."""
        element = project.controller_tags[name].value_element
        literal = element[0].text
        length = element.get("Length")
        project.controller_tags[name].value = ESCAPE_EXPECTED[name]
        assert element[0].text == literal
        assert element.get("Length") == length

    @pytest.mark.parametrize(
        "text",
        [
            "a\nb\rc\td\fe",
            "$ and ' and \"",
            "\x00\x01\x1f\x7f\x80\xff",
            "caf\u00e9 $$ $l $0A $",
            "",
            "ends with $",
        ],
    )
    def test_round_trip(self, project: Project, text: str) -> None:
        """Every escape class survives write, serialize and reload."""
        project.controller_tags["s00"].value = text
        reloaded = loads(project.to_string())
        assert reloaded.controller_tags["s00"].value == text
        assert reloaded.controller_tags["s00"].len == len(text)

    def test_nested_string_decoded(self) -> None:
        """A nested string's value is decoded and round-trips."""
        project = _example()
        node = project.controller_tags["ALLOWABLE_ALARMS"][0]
        node.value = "a\nb$"
        assert node.value == "a\nb$"
        assert node.members["DATA"].raw_value == "a\nb$"
        assert loads(project.to_string()).controller_tags["ALLOWABLE_ALARMS"][
            0
        ].value == ("a\nb$")

    @pytest.mark.parametrize(
        ("literal", "expected"),
        [
            ("'a$Lb'", "a\nb"),
            ("'a$Nb'", "a\r\nb"),
            ("'$$$''", "$'"),
            ("'a$0ab'", "a\nb"),
            ("'a$zb'", "a$zb"),
            ("'trailing$'", "trailing$"),
            ("'$1'", "$1"),
            ("plain", "plain"),
        ],
    )
    def test_parse_literal(self, literal: str, expected: str) -> None:
        """Decoding handles case, hex, CR LF and invalid escapes."""
        assert parse_string_literal(literal) == expected

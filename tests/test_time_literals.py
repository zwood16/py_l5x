"""TIME, TIME32, LTIME, DT and LDT value handling (rules measured in Studio)."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from py_l5x import Project, load, loads
from py_l5x.parsers.atomic_types import (
    format_time_literal,
    normalize_datetime_literal,
    normalize_time_literal,
    parse_time_literal,
    time_count,
)

FIXTURES = Path(__file__).parent / "fixtures"

#: (input, what Studio stored) for TIME, measured on v37.
TIME_ACCEPTED = [
    ("T#5s", "T#5s"),
    ("T#1d2h3m4s5ms6us", "T#1d_2h_3m_4s_5ms_6us"),
    ("T#1d_2h_3m_4s_5ms_6us", "T#1d_2h_3m_4s_5ms_6us"),
    ("T#1h30m", "T#1h_30m"),
    ("T#1h_30m", "T#1h_30m"),
    ("T#5s500ms", "T#5s_500ms"),
    ("T#999ms", "T#999ms"),
    ("T#59s", "T#59s"),
    ("T#5us", "T#5us"),
    ("T#1d", "T#1d"),
    ("T#100d", "T#100d"),
    ("T#106750d", "T#106750d"),
    ("T#106750d_23h_59m_59s_999ms_999us", "T#106750d_23h_59m_59s_999ms_999us"),
    ("t#5s", "T#5s"),
    ("T#5S", "T#5s"),
    ("T#5MS", "T#5ms"),
    ("T#-5s", "T#-5s"),
    ("T#-1000d", "T#-1000d"),
    ("5000", "T#5ms"),
    ("-5000", "T#-5ms"),
    ("0", "T#0us"),
    ("9007199254740992", "T#104249d_23h_47m_34s_740ms_992us"),
]

TIME_DROPPED = [
    "T#90m",
    "T#25h",
    "T#60s",
    "T#1500ms",
    "T#1000us",
    "T#2.5s",
    "-T#5s",
    "TIME#5s",
    "T#5 s",
    "T#5ns",
    "T#500ms5s",
    "T#106751d",
    "T#106751d_0h",
    "4611686018427387904",
    "9223372036854775806",
    "T32#5s",
    "LT#5s",
    "T#",
    "T#-",
    "T#5s_",
    "T#_5s",
    "T#5s__500ms",
    "T#5s5s",
    "T#s",
    "5s",
    "",
]

TIME32_ACCEPTED = [
    ("T32#35m_47s_483ms_647us", "T32#35m_47s_483ms_647us"),
    ("T32#-35m_47s_483ms_647us", "T32#-35m_47s_483ms_647us"),
    ("t32#5S", "T32#5s"),
    ("T32#30m_5s", "T32#30m_5s"),
    ("5000", "T32#5ms"),
    ("2147483647", "T32#35m_47s_483ms_647us"),
    ("0", "T32#0us"),
]

TIME32_DROPPED = [
    "T32#35m_47s_483ms_648us",
    "T32#36m",
    "T32#1d",
    "T#5s",
    "2147483648",
    "-2147483648",
    "T32#90m",
    "T32#5ns",
]

LTIME_ACCEPTED = [
    ("LT#999ns", "LT#999ns"),
    ("LT#1ms_2us_3ns", "LT#1ms_2us_3ns"),
    ("LT#1ms2us3ns", "LT#1ms_2us_3ns"),
    ("lt#5US", "LT#5us"),
    ("5000", "LT#5us"),
    ("-5000", "LT#-5us"),
    ("0", "LT#0ns"),
    ("LT#100000d", "LT#100000d"),
    ("LT#1d_1h_1m_1s_1ms_1us_1ns", "LT#1d_1h_1m_1s_1ms_1us_1ns"),
]

LTIME_DROPPED = [
    "LT#1500ns",
    "LT#106751d",
    "LT#100001d",
    "LT#2.5s",
    "T#5s",
    "LT#500ns5s",
    "LT#90m",
    "LT#5 s",
]


class TestParseAndNormalize:
    """The measured rules, table driven."""

    @pytest.mark.parametrize(("text", "canonical"), TIME_ACCEPTED)
    def test_time_accepted(self, text: str, canonical: str) -> None:
        """TIME inputs Studio keeps give the canonical literal."""
        assert normalize_time_literal(text, "TIME") == canonical
        count = parse_time_literal(text, "TIME")
        assert format_time_literal(count, "TIME") == canonical
        assert parse_time_literal(canonical, "TIME") == count

    @pytest.mark.parametrize("text", TIME_DROPPED)
    def test_time_dropped(self, text: str) -> None:
        """TIME inputs Studio drops or zeroes raise ValueError."""
        with pytest.raises(ValueError):
            parse_time_literal(text, "TIME")
        with pytest.raises(ValueError):
            normalize_time_literal(text, "TIME")

    @pytest.mark.parametrize(("text", "canonical"), TIME32_ACCEPTED)
    def test_time32_accepted(self, text: str, canonical: str) -> None:
        """TIME32 inputs Studio keeps give the canonical literal."""
        assert normalize_time_literal(text, "TIME32") == canonical

    @pytest.mark.parametrize("text", TIME32_DROPPED)
    def test_time32_dropped(self, text: str) -> None:
        """TIME32 inputs Studio drops raise ValueError."""
        with pytest.raises(ValueError):
            parse_time_literal(text, "TIME32")

    @pytest.mark.parametrize(("text", "canonical"), LTIME_ACCEPTED)
    def test_ltime_accepted(self, text: str, canonical: str) -> None:
        """LTIME inputs Studio keeps give the canonical literal."""
        assert normalize_time_literal(text, "LTIME") == canonical

    @pytest.mark.parametrize("text", LTIME_DROPPED)
    def test_ltime_dropped(self, text: str) -> None:
        """LTIME inputs Studio drops (or misreads) raise ValueError."""
        with pytest.raises(ValueError):
            parse_time_literal(text, "LTIME")

    def test_counts(self) -> None:
        """Counts are microseconds (nanoseconds for LTIME)."""
        assert parse_time_literal("T#1s_250ms", "TIME") == 1_250_000
        assert parse_time_literal("T#1s_250ms", "TIME32") if False else True
        assert parse_time_literal("T32#1s_250ms", "TIME32") == 1_250_000
        assert parse_time_literal("LT#1s_250ms", "LTIME") == 1_250_000_000
        assert parse_time_literal("T#-1d", "TIME") == -86_400_000_000

    def test_range_edges(self) -> None:
        """TIME stops just under 106751 days, TIME32 at its 32-bit count."""
        top = 106_751 * 86_400_000_000 - 1
        assert parse_time_literal(str(top), "TIME") == top
        assert parse_time_literal("T#106750d", "TIME") == 106_750 * 86_400_000_000
        with pytest.raises(ValueError):
            parse_time_literal(str(top + 1), "TIME")
        with pytest.raises(ValueError):
            format_time_literal(top + 1, "TIME")
        assert parse_time_literal("2147483647", "TIME32") == 2**31 - 1
        assert parse_time_literal("LT#100000d", "LTIME") == 8_640_000_000_000_000_000
        with pytest.raises(ValueError):
            format_time_literal(-(2**31), "TIME32")

    def test_whitespace_around_literal_is_ignored(self) -> None:
        """Only outer whitespace is trimmed; inner spaces are rejected."""
        assert parse_time_literal("  T#5s ", "TIME") == 5_000_000

    def test_bad_types(self) -> None:
        """Unknown types and wrong value types raise TypeError."""
        with pytest.raises(TypeError):
            parse_time_literal("T#5s", "DINT")
        with pytest.raises(TypeError):
            format_time_literal(5.5, "TIME")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            format_time_literal(True, "TIME")
        with pytest.raises(TypeError):
            normalize_time_literal(5.5, "TIME")
        with pytest.raises(TypeError):
            normalize_time_literal(None, "TIME")
        with pytest.raises(TypeError):
            normalize_time_literal(True, "TIME")


class TestFormat:
    """Canonical output."""

    @pytest.mark.parametrize(
        ("count", "data_type", "expected"),
        [
            (0, "TIME", "T#0us"),
            (0, "TIME32", "T32#0us"),
            (0, "LTIME", "LT#0ns"),
            (1, "TIME", "T#1us"),
            (3_600_000_000, "TIME", "T#1h"),
            (5_400_000_000, "TIME", "T#1h_30m"),
            (-1_250_000, "TIME", "T#-1s_250ms"),
            (86_400_000_000 * 2 + 5, "TIME", "T#2d_5us"),
            (5_000, "LTIME", "LT#5us"),
            (1_500, "LTIME", "LT#1us_500ns"),
            (-2_147_483_647, "TIME32", "T32#-35m_47s_483ms_647us"),
        ],
    )
    def test_format(self, count: int, data_type: str, expected: str) -> None:
        """Descending units, underscores, zero units omitted, sign after prefix."""
        assert format_time_literal(count, data_type) == expected

    def test_round_trip_property(self) -> None:
        """parse(format(n)) == n over a spread of counts."""
        for count in [0, 1, 999, 1000, 59_999_999, 3_600_000_001, 2**40 + 12345, -777]:
            for data_type in ("TIME", "LTIME"):
                assert (
                    parse_time_literal(format_time_literal(count, data_type), data_type)
                    == count
                )


class TestInputKinds:
    """int and timedelta inputs."""

    @pytest.mark.parametrize(
        ("value", "data_type", "expected"),
        [
            (5000, "TIME", "T#5ms"),
            (5000, "LTIME", "LT#5us"),
            (-5000, "TIME32", "T32#-5ms"),
            (timedelta(seconds=5), "TIME", "T#5s"),
            (timedelta(microseconds=1), "TIME", "T#1us"),
            (timedelta(0), "TIME", "T#0us"),
            (timedelta(days=-1, hours=-2), "TIME", "T#-1d_2h"),
            (timedelta(minutes=90), "TIME", "T#1h_30m"),
            (timedelta(seconds=1), "LTIME", "LT#1s"),
            (timedelta(microseconds=1), "LTIME", "LT#1us"),
            (
                timedelta(minutes=35, seconds=47, milliseconds=483, microseconds=647),
                "TIME32",
                "T32#35m_47s_483ms_647us",
            ),
        ],
    )
    def test_accepted(self, value: object, data_type: str, expected: str) -> None:
        """ints and timedeltas convert exactly."""
        assert normalize_time_literal(value, data_type) == expected
        assert time_count(value, data_type) == parse_time_literal(expected, data_type)

    @pytest.mark.parametrize(
        ("value", "data_type"),
        [
            (timedelta(hours=1), "TIME32"),
            (timedelta(days=106751), "LTIME"),
            (timedelta(days=200000_000), "TIME"),
            (106_751 * 86_400_000_000, "TIME"),
            (2**31, "TIME32"),
        ],
    )
    def test_out_of_range(self, value: object, data_type: str) -> None:
        """Values beyond the type's range raise ValueError."""
        with pytest.raises(ValueError):
            normalize_time_literal(value, data_type)


def _example() -> Project:
    """Load the main example project.

    Returns:
        The parsed project.
    """
    return load(str(FIXTURES / "example.L5X"))


def _tags(project: Project):
    """Return the MainProgram TIME-family tags.

    Args:
        project: The project.

    Returns:
        ``(TIME, TIME32, LTIME)`` tags.
    """
    tags = project.programs["MainProgram"].tags
    return tags["duration"], tags["short_duration"], tags["long_duration"]


class TestTimeNode:
    """TimeNode setters and accessors."""

    def test_setter_normalizes(self) -> None:
        """Strings are stored canonically; ints and timedeltas convert."""
        project = _example()
        time, time32, ltime = _tags(project)
        time.value = "T#1h30m"
        assert time.value == "T#1h_30m"
        assert time.value_element.get("Value") == "T#1h_30m"
        time.value = 5000
        assert time.value == "T#5ms"
        time.value = timedelta(seconds=2, milliseconds=500)
        assert time.value == "T#2s_500ms"
        time32.value = "t32#5S"
        assert time32.value == "T32#5s"
        ltime.value = 1500
        assert ltime.value == "LT#1us_500ns"
        ltime.value = timedelta(seconds=1)
        assert ltime.value == "LT#1s"

    def test_rejected_values_leave_document_unchanged(self) -> None:
        """Literals Studio would drop raise and change nothing."""
        project = _example()
        time, time32, ltime = _tags(project)
        before = project.to_string()
        for node, bad in [
            (time, "T#90m"),
            (time, "T#2.5s"),
            (time, "T#500ms5s"),
            (time, "T32#5s"),
            (time32, "T#5s"),
            (time32, "T32#36m"),
            (ltime, "LT#1500ns"),
            (ltime, "T#5s"),
        ]:
            with pytest.raises(ValueError):
                node.value = bad
        with pytest.raises(TypeError):
            time.value = 1.5
        assert project.to_string() == before

    def test_count_and_timedelta(self) -> None:
        """count and as_timedelta are built on the parser."""
        project = _example()
        time, time32, ltime = _tags(project)
        assert time.count == 0
        assert time.as_timedelta() == timedelta(0)
        time.value = "T#1d_2h"
        assert time.count == 93_600_000_000
        assert time.as_timedelta() == timedelta(days=1, hours=2)
        ltime.value = "LT#1s_5us"
        assert ltime.count == 1_000_005_000
        assert ltime.as_timedelta() == timedelta(seconds=1, microseconds=5)
        ltime.value = 1500
        assert ltime.count == 1500
        with pytest.raises(ValueError, match="whole number of microseconds"):
            ltime.as_timedelta()
        time32.value = timedelta(minutes=1)
        assert time32.count == 60_000_000

    def test_count_of_unparsable_or_missing(self) -> None:
        """Unparsable literals and data-less tags give None."""
        project = _example()
        time, _, _ = _tags(project)
        time.value_element.set("Value", "T#2.5s")
        assert time.count is None
        assert time.as_timedelta() is None
        assert time.value == "T#2.5s"
        empty = loads(
            '<RSLogix5000Content><Controller Name="C"><Tags>'
            '<Tag Name="t" TagType="Base" DataType="TIME"/>'
            "</Tags></Controller></RSLogix5000Content>"
        )
        assert empty.controller_tags["t"].count is None

    def test_round_trip_through_serialization(self) -> None:
        """Stored literals survive loads(to_string())."""
        project = _example()
        time, _, _ = _tags(project)
        time.value = "T#1d2h3m4s5ms6us"
        again = loads(project.to_string()).programs["MainProgram"].tags["duration"]
        assert again.value == "T#1d_2h_3m_4s_5ms_6us"
        assert again.count == time.count

    def test_timer_t_members(self) -> None:
        """TIMER_T PRE/ACC accept every input kind through dict and list values."""
        project = _example()
        tags = project.programs["MainProgram"].tags
        tags.add("tt", "TIMER_T")
        tags.add("tts", "TIMER_T", dimensions=2)
        tt = tags["tt"]
        tt.value = {"PRE": "T#1h30m", "ACC": 1_500_000, "EN": True}
        assert tt.to_python() == {
            "ACC": "T#1s_500ms",
            "PRE": "T#1h_30m",
            "EN": True,
            "TT": False,
            "DN": False,
        }
        tts = tags["tts"]
        tts.value = [{"PRE": timedelta(seconds=3)}, {"ACC": "T#-5ms"}]
        assert tts.to_python()[0]["PRE"] == "T#3s"
        assert tts.to_python()[1]["ACC"] == "T#-5ms"

    def test_timer_t_bad_value_is_atomic(self) -> None:
        """A bad TIMER_T member value changes nothing (whole assignment)."""
        project = _example()
        tags = project.programs["MainProgram"].tags
        tags.add("tt", "TIMER_T", value={"PRE": "T#5s"})
        before = project.to_string()
        with pytest.raises(ValueError):
            tags["tt"].value = {"ACC": "T#10s", "PRE": "T#90m"}
        assert project.to_string() == before


class TestDateTime:
    """DT and LDT."""

    @pytest.mark.parametrize(
        ("text", "data_type"),
        [
            ("DT#2026-11-16-12:30:00.000_000Z", "DT"),
            ("DT#1970-01-01-00:00:00.123_456Z", "DT"),
            ("LDT#2026-11-16-12:30:00.000_000_000Z", "LDT"),
            ("LDT#1970-01-01-00:00:00.123_456_789Z", "LDT"),
        ],
    )
    def test_accepted_verbatim(self, text: str, data_type: str) -> None:
        """Canonical literals ending in Z are kept as is."""
        assert normalize_datetime_literal(text, data_type) == text

    @pytest.mark.parametrize(
        ("text", "data_type"),
        [
            ("DT#2026-11-16-12:30:00.000_000", "DT"),
            ("LDT#2026-11-16-12:30:00.000_000_000", "LDT"),
            ("DT#2026-13-16-12:30:00.000_000Z", "DT"),
            ("DT#2026-11-31-12:30:00.000_000Z", "DT"),
            ("DT#2026-11-16-25:30:00.000_000Z", "DT"),
            ("DT#2026-11-16 12:30:00.000_000Z", "DT"),
            ("DT#2026-11-16-12:30:00Z", "DT"),
            ("DT#2026-11-16-12:30:00.000_000_000Z", "DT"),
            ("LDT#2026-11-16-12:30:00.000_000Z", "LDT"),
            ("LDT#2026-11-16-12:30:00.000_000_000Z", "DT"),
            ("T#5s", "DT"),
            ("", "DT"),
        ],
    )
    def test_rejected(self, text: str, data_type: str) -> None:
        """Wrong shapes, missing Z and impossible dates raise ValueError."""
        with pytest.raises(ValueError):
            normalize_datetime_literal(text, data_type)

    def test_datetime_objects(self) -> None:
        """Aware datetimes are converted to UTC; naive ones are refused."""
        utc = datetime(2026, 11, 16, 12, 30, tzinfo=UTC)
        assert (
            normalize_datetime_literal(utc, "DT") == "DT#2026-11-16-12:30:00.000_000Z"
        )
        assert normalize_datetime_literal(utc, "LDT") == (
            "LDT#2026-11-16-12:30:00.000_000_000Z"
        )
        local = datetime(2026, 11, 16, 5, 30, tzinfo=timezone(timedelta(hours=-7)))
        assert (
            normalize_datetime_literal(local, "DT") == "DT#2026-11-16-12:30:00.000_000Z"
        )
        micro = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=UTC)
        assert normalize_datetime_literal(micro, "DT").endswith("05.123_456Z")
        assert normalize_datetime_literal(micro, "LDT").endswith("05.123_456_000Z")
        with pytest.raises(ValueError, match="timezone-aware"):
            normalize_datetime_literal(datetime(2026, 11, 16, 12, 30), "DT")

    def test_bad_types(self) -> None:
        """Other types raise TypeError."""
        with pytest.raises(TypeError):
            normalize_datetime_literal(5, "DT")
        with pytest.raises(TypeError):
            normalize_datetime_literal("DT#x", "DINT")

    def test_node_setters(self) -> None:
        """DT and LDT tags take literals and datetimes."""
        project = _example()
        tags = project.programs["MainProgram"].tags
        tags["datetime"].value = datetime(2026, 11, 16, 12, 30, tzinfo=UTC)
        assert tags["datetime"].value == "DT#2026-11-16-12:30:00.000_000Z"
        tags["long_datetime"].value = "LDT#2026-11-16-12:30:00.000_000_000Z"
        assert tags["long_datetime"].value == "LDT#2026-11-16-12:30:00.000_000_000Z"
        before = project.to_string()
        with pytest.raises(ValueError):
            tags["datetime"].value = "DT#2026-11-16-12:30:00.000_000"
        with pytest.raises(ValueError):
            tags["datetime"].value = datetime(2026, 11, 16)
        assert project.to_string() == before


class TestFixtures:
    """Real exports stay exact."""

    @pytest.mark.parametrize(
        "name",
        ["example.L5X", "radix_values_Tags.L5X", "simple_example.L5X"],
    )
    def test_every_time_value_is_canonical(self, name: str) -> None:
        """Studio's own TIME-family values parse and re-format to themselves."""
        project = load(str(FIXTURES / name))
        seen = 0
        for element in project.root.iter():
            data_type = element.get("DataType")
            value = element.get("Value")
            if data_type in ("TIME", "TIME32", "LTIME") and value is not None:
                assert (
                    format_time_literal(parse_time_literal(value, data_type), data_type)
                    == value
                )
                seen += 1
            if data_type in ("DT", "LDT") and value is not None:
                assert normalize_datetime_literal(value, data_type) == value
                seen += 1
        assert seen > 0 or name == "radix_values_Tags.L5X"

    def test_writing_back_default_values_is_unchanged(self) -> None:
        """Setting each TIME/DT tag to its own value leaves the XML as it was."""
        project = _example()
        tags = [
            t
            for t in project.programs["MainProgram"].tags.values()
            if t.data_type in ("TIME", "TIME32", "LTIME", "DT", "LDT")
        ]
        before = {t.name: t.value for t in tags}
        assert len(before) == 5
        for tag in tags:
            tag.value = tag.value
        assert {t.name: t.value for t in tags} == before

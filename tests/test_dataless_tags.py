"""Tests for tags with no ``<Data>`` element."""

from collections import Counter
from pathlib import Path

import pytest

from py_l5x import (
    AliasTag,
    ArrayTag,
    BoolTag,
    DateTimeTag,
    FloatTag,
    IntegerTag,
    Project,
    StringTag,
    StructTag,
    TimeTag,
    UnknownTag,
    load,
    loads,
)
from py_l5x.parsers.layout import LayoutError
from py_l5x.parsers.tag import AxisTag, MessageTag, MotionGroupTag

FIXTURES = Path(__file__).parent / "fixtures"

_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0">
<Controller Name="C" ProcessorType="1756-L83E">
<DataTypes>
<DataType Name="MyStr" Family="StringFamily" Class="User">
<Members>
<Member Name="LEN" DataType="DINT" Dimension="0" Radix="Decimal" Hidden="true" ExternalAccess="Read/Write"/>
<Member Name="DATA" DataType="SINT" Dimension="10" Radix="ASCII" Hidden="false" ExternalAccess="Read/Write"/>
</Members>
</DataType>
<DataType Name="MyUdt" Family="NoFamily" Class="User">
<Members>
<Member Name="A" DataType="DINT" Dimension="0" Radix="Decimal" Hidden="false" ExternalAccess="Read/Write"/>
</Members>
</DataType>
</DataTypes>
<Tags>
<Tag Name="t_bool" TagType="Base" DataType="BOOL" Radix="Decimal" ExternalAccess="Read/Write"/>
<Tag Name="t_dint" TagType="Base" DataType="DINT" Radix="Hex" ExternalAccess="Read/Write"/>
<Tag Name="t_dint_noradix" TagType="Base" DataType="DINT"/>
<Tag Name="t_real" TagType="Base" DataType="REAL"/>
<Tag Name="t_lreal" TagType="Base" DataType="LREAL" Radix="Exponential"/>
<Tag Name="t_time" TagType="Base" DataType="TIME"/>
<Tag Name="t_time32" TagType="Base" DataType="TIME32"/>
<Tag Name="t_ltime" TagType="Base" DataType="LTIME"/>
<Tag Name="t_dt" TagType="Base" DataType="DT"/>
<Tag Name="t_ldt" TagType="Base" DataType="LDT"/>
<Tag Name="t_string" TagType="Base" DataType="STRING"/>
<Tag Name="t_mystr" TagType="Base" DataType="MyStr"/>
<Tag Name="t_udt" TagType="Base" DataType="MyUdt"/>
<Tag Name="t_timer" TagType="Base" DataType="TIMER"/>
<Tag Name="t_aoi" TagType="Base" DataType="SomeAoi"/>
<Tag Name="t_array" TagType="Base" DataType="DINT" Dimensions="5"/>
<Tag Name="t_array2" TagType="Base" DataType="TIMER" Dimensions="2 3"/>
<Tag Name="t_alias" TagType="Alias" Radix="Decimal" AliasFor="t_dint" ExternalAccess="Read/Write"/>
<Tag Name="t_message" TagType="Base" DataType="MESSAGE"/>
<Tag Name="t_group" TagType="Base" DataType="MOTION_GROUP"/>
<Tag Name="t_axis" TagType="Base" DataType="AXIS_CIP_DRIVE"/>
<Tag Name="t_l5k" TagType="Base" DataType="DINT" Radix="Decimal">
<Data Format="L5K">
<![CDATA[7]]>
</Data>
</Tag>
<Tag Name="t_desc" TagType="Base" DataType="DINT" Radix="Decimal">
<Description>
<![CDATA[hello]]>
</Description>
</Tag>
</Tags>
</Controller>
</RSLogix5000Content>
"""  # noqa: E501


@pytest.fixture
def project() -> Project:
    """A project of data-less tags."""
    return loads(_DOC)


@pytest.mark.parametrize(
    ("name", "cls"),
    [
        ("t_bool", BoolTag),
        ("t_dint", IntegerTag),
        ("t_real", FloatTag),
        ("t_lreal", FloatTag),
        ("t_time", TimeTag),
        ("t_time32", TimeTag),
        ("t_ltime", TimeTag),
        ("t_dt", DateTimeTag),
        ("t_ldt", DateTimeTag),
        ("t_string", StringTag),
        ("t_mystr", StringTag),
        ("t_udt", StructTag),
        ("t_timer", StructTag),
        ("t_aoi", StructTag),
        ("t_array", ArrayTag),
        ("t_array2", ArrayTag),
        ("t_alias", AliasTag),
        ("t_message", MessageTag),
        ("t_group", MotionGroupTag),
        ("t_axis", AxisTag),
        ("t_l5k", IntegerTag),
    ],
)
def test_classification(project: Project, name: str, cls: type) -> None:
    """A data-less tag gets the class its DataType and Dimensions imply."""
    tag = project.controller_tags[name]
    assert type(tag) is cls
    assert not isinstance(tag, UnknownTag)


class TestEmptyReads:
    """Reads on data-less tags return the documented empty values."""

    @pytest.mark.parametrize(
        "name",
        ["t_bool", "t_dint", "t_real", "t_time", "t_ldt", "t_l5k"],
    )
    def test_atomic_value_none(self, project: Project, name: str) -> None:
        """Atomic values are ``None``."""
        tag = project.controller_tags[name]
        assert tag.value is None
        assert tag.value_element is None

    @pytest.mark.parametrize("name", ["t_string", "t_mystr"])
    def test_string(self, project: Project, name: str) -> None:
        """Strings are empty with length zero."""
        tag = project.controller_tags[name]
        assert tag.value == ""
        assert tag.len == 0

    @pytest.mark.parametrize("name", ["t_udt", "t_timer", "t_aoi"])
    def test_struct_members_empty(self, project: Project, name: str) -> None:
        """Structure members are an empty mapping."""
        assert len(project.controller_tags[name].members) == 0
        assert list(project.controller_tags[name].members) == []

    def test_array(self, project: Project) -> None:
        """Arrays are empty but keep their dimensions."""
        array = project.controller_tags["t_array"]
        assert len(array) == 0
        assert array.dimensions == (5,)
        assert project.controller_tags["t_array2"].dimensions == (2, 3)

    def test_radix(self, project: Project) -> None:
        """Radix comes from the tag, else the type default."""
        tags = project.controller_tags
        assert tags["t_dint"].radix == "Hex"
        assert tags["t_dint_noradix"].radix == "Decimal"
        assert tags["t_bool"].radix == "Decimal"
        assert tags["t_real"].radix == "Float"
        assert tags["t_lreal"].radix == "Exponential"
        assert tags["t_time"].radix == "Time (us)"
        assert tags["t_time32"].radix == "Time32 (us)"
        assert tags["t_ltime"].radix == "LTime (ns)"
        assert tags["t_dt"].radix == "Date/Time"
        assert tags["t_ldt"].radix == "Date/Time (ns)"

    def test_metadata(self, project: Project) -> None:
        """Description and other metadata still work."""
        tag = project.controller_tags["t_desc"]
        assert tag.description == "hello"
        assert tag.data_type == "DINT"

    def test_describe(self, project: Project) -> None:
        """describe() and repr work on every data-less tag."""
        for tag in project.controller_tags.values():
            assert tag.name in repr(tag)
            assert tag.describe()


def _fragment(project: Project, name: str) -> str:
    """Extract one tag's serialized XML.

    Args:
        project: The project.
        name: Tag name.

    Returns:
        The text from the tag's start tag to its end (CRLF line endings).
    """
    text = project.to_string()
    start = text.index(f'<Tag Name="{name}"')
    return text[start : text.index("</Tag>", start) + len("</Tag>")]


class TestMaterialize:
    """Writing a value creates the ``Data`` element."""

    @pytest.mark.parametrize(
        ("name", "value", "cls", "data_type", "radix", "text"),
        [
            ("t_bool", True, BoolTag, "BOOL", "Decimal", "1"),
            ("t_dint", 255, IntegerTag, "DINT", "Hex", "16#0000_00ff"),
            ("t_dint_noradix", -4, IntegerTag, "DINT", "Decimal", "-4"),
            ("t_real", 1.5, FloatTag, "REAL", "Float", "1.5"),
            (
                "t_lreal",
                1.5,
                FloatTag,
                "LREAL",
                "Exponential",
                "1.5000000000000000e+000",
            ),
            ("t_time", "T#5s", TimeTag, "TIME", "Time (us)", "T#5s"),
            ("t_time32", "T32#5s", TimeTag, "TIME32", "Time32 (us)", "T32#5s"),
            ("t_ltime", "LT#5s", TimeTag, "LTIME", "LTime (ns)", "LT#5s"),
            (
                "t_ldt",
                "LDT#2020-01-01-00:00:00.000_000_000Z",
                DateTimeTag,
                "LDT",
                "Date/Time (ns)",
                "LDT#2020-01-01-00:00:00.000_000_000Z",
            ),
        ],
    )
    def test_atomic(
        self,
        project: Project,
        name: str,
        value: object,
        cls: type,
        data_type: str,
        radix: str,
        text: str,
    ) -> None:
        """An atomic write builds Studio's decorated Data shape."""
        tag = project.controller_tags[name]
        tag.value = value
        assert tag.value == value
        fragment = _fragment(project, name)
        assert fragment.endswith(
            '\r\n<Data Format="Decorated">\r\n'
            f'<DataValue DataType="{data_type}" Radix="{radix}" Value="{text}"/>\r\n'
            "</Data>\r\n</Tag>"
        )
        again = project.controller_tags[name]
        assert type(again) is cls
        assert again.value == value
        reloaded = loads(project.to_string()).controller_tags[name]
        assert type(reloaded) is cls
        assert reloaded.value == value

    @pytest.mark.parametrize(
        ("name", "value", "length", "literal"),
        [
            ("t_string", "abc", 3, "'abc'"),
            ("t_string", "", 0, "''"),
            ("t_mystr", "a\nb", 3, "'a$lb'"),
        ],
    )
    def test_string(
        self, project: Project, name: str, value: str, length: int, literal: str
    ) -> None:
        """A STRING write builds the String-format Data element."""
        tag = project.controller_tags[name]
        tag.value = value
        assert tag.value == value
        assert tag.len == length
        assert f'<Tag Name="{name}" TagType="Base" DataType=' in _fragment(
            project, name
        )
        assert _fragment(project, name).endswith(
            f'\r\n<Data Format="String" Length="{length}">\r\n'
            f"<![CDATA[{literal}]]>\r\n</Data>\r\n</Tag>"
        )
        again = project.controller_tags[name]
        assert type(again) is StringTag
        assert again.value == value
        reloaded = loads(project.to_string()).controller_tags[name]
        assert type(reloaded) is StringTag
        assert reloaded.value == value

    def test_second_write_updates_in_place(self, project: Project) -> None:
        """A later write on the same object edits the created element."""
        tag = project.controller_tags["t_dint_noradix"]
        tag.value = 1
        tag.value = 2
        assert tag.value == 2
        assert len(tag._element.findall("Data")) == 1

    def test_data_goes_after_description(self, project: Project) -> None:
        """The new Data follows existing Description."""
        tag = project.controller_tags["t_desc"]
        tag.value = 3
        assert [c.tag for c in tag._element] == ["Description", "Data"]

    def test_description_after_materialize_goes_first(self, project: Project) -> None:
        """A description set later lands before the created Data."""
        tag = project.controller_tags["t_dint_noradix"]
        tag.value = 3
        tag.description = "x"
        assert [c.tag for c in tag._element] == ["Description", "Data"]

    def test_stale_l5k_dropped(self, project: Project) -> None:
        """An existing L5K Data is replaced by the decorated one."""
        tag = project.controller_tags["t_l5k"]
        tag.value = 9
        assert [(c.tag, c.get("Format")) for c in tag._element] == [
            ("Data", "Decorated")
        ]
        assert project.controller_tags["t_l5k"].value == 9

    def test_failed_write_creates_nothing(self, project: Project) -> None:
        """An invalid value leaves the tag without a Data element."""
        tag = project.controller_tags["t_dint_noradix"]
        with pytest.raises(ValueError):
            tag.value = 2**40
        with pytest.raises(TypeError):
            tag.value = "x"
        assert tag._element.find("Data") is None
        string = project.controller_tags["t_string"]
        with pytest.raises(ValueError):
            string.value = "x" * 100
        assert string._element.find("Data") is None


class TestAggregateWritesOnDataless:
    """Bad assignments to data-less structures and arrays create nothing."""

    @pytest.mark.parametrize("name", ["t_udt", "t_timer", "t_array"])
    def test_wrong_type_raises(self, project: Project, name: str) -> None:
        """A scalar is rejected and no Data is created."""
        tag = project.controller_tags[name]
        with pytest.raises(TypeError):
            tag.value = 1
        assert tag._element.find("Data") is None

    def test_unknown_type_raises_layout_error(self, project: Project) -> None:
        """A type with no layout raises LayoutError."""
        tag = project.controller_tags["t_aoi"]
        with pytest.raises(LayoutError, match="unknown data type"):
            tag.value = {}
        assert tag._element.find("Data") is None


#: Tag classes across every fixture, recorded before data-less classification
#: was added (plus the type_defaults fixture, whose tags all carry data). No
#: fixture tag lacks data, so none may change class.
_FIXTURE_CLASSES = {
    "IntegerTag": 173,
    "FloatTag": 50,
    "StructTag": 44,
    "StringTag": 23,
    "BoolTag": 14,
    "TimeTag": 9,
    "DateTimeTag": 6,
    "AliasTag": 4,
    "ArrayTag": 13,
    "MessageTag": 2,
    "MotionGroupTag": 1,
    "AxisTag": 1,
}


def test_fixture_classification_unchanged() -> None:
    """Every fixture tag keeps the class it had before."""
    counts: Counter[str] = Counter()
    for path in sorted(FIXTURES.glob("*.L5X")):
        project = load(str(path))
        scopes = [project.controller_tags] + [
            program.tags for program in project.programs.values()
        ]
        for scope in scopes:
            for tag in scope.values():
                counts[type(tag).__name__] += 1
    assert dict(counts) == _FIXTURE_CLASSES

"""Tests for TagsCollection edits and operand metadata edits."""

import pytest

from py_l5x import (
    AliasTag,
    ArrayTag,
    BoolTag,
    IntegerTag,
    Project,
    StringTag,
    StructTag,
    loads,
)

_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0">
<Controller Name="C" ProcessorType="1756-L83E">
<Tags>
<Tag Name="existing" TagType="Base" DataType="DINT" Radix="Decimal">
<Data Format="Decorated">
<DataValue DataType="DINT" Radix="Decimal" Value="0"/>
</Data>
</Tag>
<Tag Name="timer" TagType="Base" DataType="TIMER">
<Data Format="L5K">
<![CDATA[[0,0,0]]]>
</Data>
<Data Format="Decorated">
<Structure DataType="TIMER">
<DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="0"/>
<DataValueMember Name="ACC" DataType="DINT" Radix="Decimal" Value="0"/>
<DataValueMember Name="EN" DataType="BOOL" Value="0"/>
</Structure>
</Data>
</Tag>
</Tags>
<Programs>
<Program Name="Empty" TestEdits="false" MainRoutineName="Main">
</Program>
<Program Name="SelfClosed" MainRoutineName="Main">
<Tags/>
</Program>
</Programs>
</Controller>
</RSLogix5000Content>
"""  # noqa: E501


@pytest.fixture
def project() -> Project:
    """A small project with tags and two programs."""
    return loads(_DOC)


def _frag(project: Project, name: str) -> str:
    """Return one tag's serialized XML.

    Args:
        project: The project.
        name: Tag name.

    Returns:
        The text of the ``<Tag>`` element (CRLF line endings).
    """
    text = project.to_string()
    start = text.index(f'<Tag Name="{name}"')
    end = text.index("</Tag>", start) if "</Tag>" in text[start:] else None
    first_close = text.index("/>", start)
    first_open_end = text.index(">", start)
    if text[first_open_end - 1] == "/":
        return text[start : first_close + 2]
    return text[start : end + len("</Tag>")]


class TestAdd:
    """TagsCollection.add."""

    @pytest.mark.parametrize(
        ("data_type", "cls"),
        [
            ("DINT", IntegerTag),
            ("BOOL", BoolTag),
            ("STRING", StringTag),
            ("TIMER", StructTag),
            ("MyUdt", StructTag),
            ("MyAoi", StructTag),
        ],
    )
    def test_kinds(self, project: Project, data_type: str, cls: type) -> None:
        """Each kind builds a typed tag with no Data and round trips."""
        tag = project.controller_tags.add("new_tag", data_type)
        assert type(tag) is cls
        assert tag._element.find("Data") is None
        assert _frag(project, "new_tag") == (
            f'<Tag Name="new_tag" TagType="Base" DataType="{data_type}"/>'
        )
        again = loads(project.to_string()).controller_tags["new_tag"]
        assert type(again) is cls
        assert again.data_type == data_type

    @pytest.mark.parametrize(
        ("dims", "text"), [(5, "5"), ((2, 3), "2 3"), ((2, 3, 4), "2 3 4")]
    )
    def test_arrays(self, project: Project, dims: object, text: str) -> None:
        """Dimensions are written space separated."""
        tag = project.controller_tags.add("arr", "DINT", dimensions=dims)
        assert type(tag) is ArrayTag
        assert tag.dimensions == tuple(int(n) for n in text.split())
        assert f'DataType="DINT" Dimensions="{text}"/>' in project.to_string()
        reloaded = loads(project.to_string()).controller_tags["arr"]
        assert type(reloaded) is ArrayTag
        assert reloaded.dimensions == tag.dimensions

    @pytest.mark.parametrize("bad", [0, (1, 2, 3, 4), (), (1, 0), "3", 1.5, True])
    def test_bad_dimensions(self, project: Project, bad: object) -> None:
        """Bad dimensions raise ValueError and add nothing."""
        with pytest.raises(ValueError):
            project.controller_tags.add("arr", "DINT", dimensions=bad)
        assert "arr" not in project.controller_tags

    def test_all_options_attribute_order(self, project: Project) -> None:
        """Optional attributes follow Studio's order."""
        project.controller_tags.add(
            "full",
            "DINT",
            dimensions=2,
            description="d",
            radix="Hex",
            external_access="Read Only",
            constant=True,
        )
        assert _frag(project, "full") == (
            '<Tag Name="full" TagType="Base" DataType="DINT" Dimensions="2" '
            'Radix="Hex" Constant="true" ExternalAccess="Read Only">\r\n'
            "<Description>\r\n<![CDATA[d]]>\r\n</Description>\r\n</Tag>"
        )

    def test_constant_false(self, project: Project) -> None:
        """constant=False is written as ``false``."""
        project.controller_tags.add("c", "DINT", constant=False)
        assert 'Constant="false"' in project.to_string()

    def test_added_at_end_and_formatting(self, project: Project) -> None:
        """New tags are appended, one element per line."""
        project.controller_tags.add("a", "DINT")
        project.controller_tags.add("b", "REAL")
        assert list(project.controller_tags) == ["existing", "timer", "a", "b"]
        text = project.to_string()
        assert (
            '</Tag>\r\n<Tag Name="a" TagType="Base" DataType="DINT"/>\r\n'
            '<Tag Name="b" TagType="Base" DataType="REAL"/>\r\n</Tags>'
        ) in text

    def test_value_write_materializes(self, project: Project) -> None:
        """A value write after add creates Data (atomic and STRING)."""
        dint = project.controller_tags.add("n", "DINT", radix="Hex")
        dint.value = 255
        string = project.controller_tags.add("s", "STRING")
        string.value = "hi"
        text = project.to_string()
        assert '<DataValue DataType="DINT" Radix="Hex" Value="16#0000_00ff"/>' in text
        assert '<Data Format="String" Length="2">\r\n<![CDATA[\'hi\']]>' in text
        reloaded = loads(text).controller_tags
        assert reloaded["n"].value == 255
        assert reloaded["s"].value == "hi"

    def test_program_without_tags(self, project: Project) -> None:
        """A program with no <Tags> gets one, before Routines."""
        program = project.programs["Empty"]
        program.tags.add("p", "DINT")
        assert [c.tag for c in program._element] == ["Tags"]
        assert list(loads(project.to_string()).programs["Empty"].tags) == ["p"]

    def test_self_closed_tags(self, project: Project) -> None:
        """A self-closed <Tags/> becomes a formatted container."""
        project.programs["SelfClosed"].tags.add("p", "DINT")
        text = project.to_string()
        assert (
            '<Tags>\r\n<Tag Name="p" TagType="Base" DataType="DINT"/>\r\n</Tags>'
            in text
        )

    def test_container_order_in_controller(self) -> None:
        """A missing <Tags> goes before <Programs>."""
        project = loads(_DOC.replace("<Tags>", "<Tagz>").replace("</Tags>", "</Tagz>"))
        project.controller_tags.add("x", "DINT")
        tags = [c.tag for c in project.controller_element]
        assert tags.index("Tags") < tags.index("Programs")

    def test_description_schema_order(self, project: Project) -> None:
        """A description set at add time precedes later Data."""
        tag = project.controller_tags.add("d", "DINT", description="x")
        tag.value = 1
        assert [c.tag for c in tag._element] == ["Description", "Data"]


class TestAlias:
    """add_alias."""

    def test_add_alias(self, project: Project) -> None:
        """Alias tags are written with TagType and AliasFor."""
        alias = project.controller_tags.add_alias("al", "existing", description="x")
        assert type(alias) is AliasTag
        assert alias.alias_for == "existing"
        assert _frag(project, "al") == (
            '<Tag Name="al" TagType="Alias" AliasFor="existing">\r\n'
            "<Description>\r\n<![CDATA[x]]>\r\n</Description>\r\n</Tag>"
        )
        assert type(loads(project.to_string()).controller_tags["al"]) is AliasTag

    def test_alias_validates_name(self, project: Project) -> None:
        """Alias names follow the same rules."""
        with pytest.raises(ValueError):
            project.controller_tags.add_alias("EXISTING", "timer")


class TestRemoveRename:
    """remove and rename."""

    def test_remove(self, project: Project) -> None:
        """Removing a tag deletes its element."""
        project.controller_tags.remove("existing")
        assert list(project.controller_tags) == ["timer"]
        assert 'Name="existing"' not in project.to_string()

    def test_remove_last_keeps_container(self, project: Project) -> None:
        """Removing every tag leaves a usable empty <Tags>."""
        project.controller_tags.remove("existing")
        project.controller_tags.remove("timer")
        assert len(project.controller_tags) == 0
        project.controller_tags.add("again", "DINT")
        assert list(loads(project.to_string()).controller_tags) == ["again"]

    def test_remove_missing(self, project: Project) -> None:
        """A missing name raises KeyError, also in a program without tags."""
        with pytest.raises(KeyError):
            project.controller_tags.remove("nope")
        with pytest.raises(KeyError):
            project.programs["Empty"].tags.remove("nope")

    def test_rename(self, project: Project) -> None:
        """Renaming changes only the Name."""
        tag = project.controller_tags.rename("existing", "renamed")
        assert tag.name == "renamed"
        assert tag.value == 0
        assert list(project.controller_tags) == ["renamed", "timer"]

    def test_rename_case_only(self, project: Project) -> None:
        """A case-only rename of the tag itself is allowed."""
        project.controller_tags.rename("existing", "Existing")
        assert "Existing" in project.controller_tags

    def test_rename_missing(self, project: Project) -> None:
        """Renaming a missing tag raises KeyError."""
        with pytest.raises(KeyError):
            project.controller_tags.rename("nope", "x")

    def test_rename_to_taken(self, project: Project) -> None:
        """Renaming onto another tag fails, case-insensitively."""
        with pytest.raises(ValueError):
            project.controller_tags.rename("existing", "TIMER")
        assert "existing" in project.controller_tags

    def test_rename_invalid(self, project: Project) -> None:
        """An invalid new name fails and changes nothing."""
        with pytest.raises(ValueError):
            project.controller_tags.rename("existing", "1abc")
        assert "existing" in project.controller_tags


class TestNameValidation:
    """Tag name rules."""

    @pytest.mark.parametrize(
        "name",
        ["1abc", "a__b", "a_", "x" * 41, "a b", "", "a-b", "a:b", "é"],
    )
    def test_invalid(self, project: Project, name: str) -> None:
        """Invalid names raise ValueError."""
        with pytest.raises(ValueError):
            project.controller_tags.add(name, "DINT")
        assert len(project.controller_tags) == 2

    @pytest.mark.parametrize("name", ["a", "_a", "_", "A_b_C1", "x" * 40])
    def test_valid(self, project: Project, name: str) -> None:
        """Valid names are accepted (except those the stated regex rejects)."""
        if name.endswith("_"):
            with pytest.raises(ValueError):
                project.controller_tags.add(name, "DINT")
        else:
            assert project.controller_tags.add(name, "DINT").name == name

    @pytest.mark.parametrize("name", ["existing", "EXISTING", "Existing"])
    def test_duplicates_case_insensitive(self, project: Project, name: str) -> None:
        """Names differing only in case are duplicates."""
        with pytest.raises(ValueError, match="already exists"):
            project.controller_tags.add(name, "DINT")

    def test_same_name_in_other_scope_ok(self, project: Project) -> None:
        """Duplicate checks are per scope."""
        project.programs["Empty"].tags.add("existing", "DINT")


def _tag(project: Project):
    """Return the ``timer`` tag.

    Args:
        project: The project.

    Returns:
        The tag.
    """
    return project.controller_tags["timer"]


class TestOperandMetadata:
    """set_operand_metadata and set_operand_comment."""

    def test_first_comment_layout(self, project: Project) -> None:
        """A first comment creates Comments before Data, exactly formatted."""
        tag = _tag(project)
        tag.set_operand_comment(".pre", "preset")
        assert [c.tag for c in tag._element] == ["Comments", "Data", "Data"]
        assert _frag(project, "timer").startswith(
            '<Tag Name="timer" TagType="Base" DataType="TIMER">\r\n'
            "<Comments>\r\n"
            '<Comment Operand=".PRE">\r\n<![CDATA[preset]]>\r\n</Comment>\r\n'
            "</Comments>\r\n"
            '<Data Format="L5K">'
        )

    def test_sorted(self, project: Project) -> None:
        """Entries stay sorted: .DN before .PRE, numeric-aware, any insert order."""
        tag = _tag(project)
        for operand in [".PRE", ".DN", ".FAULT.10", ".FAULT.2", "[1]", ".ACC", ".0"]:
            tag.set_operand_comment(operand, operand)
        order = [e.get("Operand") for e in tag._element.find("Comments")]
        assert order == [".0", ".ACC", ".DN", ".FAULT.2", ".FAULT.10", ".PRE", "[1]"]
        assert list(tag.operand_comments) == order

    def test_update_case_insensitive(self, project: Project) -> None:
        """Updating matches case-insensitively and adds no duplicate."""
        tag = _tag(project)
        tag.set_operand_comment(".PRE", "one")
        tag.set_operand_comment(".pre", "two")
        entries = list(tag._element.find("Comments"))
        assert len(entries) == 1
        assert entries[0].get("Operand") == ".PRE"
        assert tag.operand_comments == {".PRE": "two"}
        assert "\r\n\r\n" not in project.to_string()

    def test_remove(self, project: Project) -> None:
        """Removing entries removes the container with the last one."""
        tag = _tag(project)
        before = project.to_string()
        tag.set_operand_comment(".PRE", "a")
        tag.set_operand_comment(".ACC", "b")
        tag.set_operand_comment(".pre", None)
        assert tag.operand_comments == {".ACC": "b"}
        tag.set_operand_comment(".ACC", "")
        assert tag._element.find("Comments") is None
        assert tag.operand_comments == {}
        assert project.to_string() == before

    def test_remove_missing_is_noop(self, project: Project) -> None:
        """Removing something absent changes nothing."""
        before = project.to_string()
        _tag(project).set_operand_comment(".PRE", None)
        assert project.to_string() == before

    @pytest.mark.parametrize(
        ("key", "container", "cdata"),
        [
            ("comment", "Comments", True),
            ("engineering_unit", "EngineeringUnits", True),
            ("state0", "State0s", True),
            ("state1", "State1s", True),
            ("max", "Maxes", False),
            ("min", "Mins", False),
            ("external_logging", "ExternalLoggings", False),
        ],
    )
    def test_each_key(
        self, project: Project, key: str, container: str, cdata: bool
    ) -> None:
        """Each key uses its container and Studio's text shape."""
        tag = _tag(project)
        tag.set_operand_metadata(".PRE", key, "v")
        entry = tag._element.find(container)[0]
        assert entry.get("Operand") == ".PRE"
        if cdata:
            assert entry.text == "\n"
            assert entry[0].text == "v"
            assert entry[0].tail == "\n"
        else:
            assert entry.text == "v"
            assert len(entry) == 0
        assert tag.operand_metadata == {".PRE": {key: "v"}}
        text = loads(project.to_string()).controller_tags["timer"].operand_metadata
        assert text == {".PRE": {key: "v"}}

    def test_plain_text_fragment(self, project: Project) -> None:
        """Max/Min/ExternalLogging are single-line entries like Studio's."""
        tag = _tag(project)
        tag.set_operand_metadata(".PRE", "max", "100")
        assert (
            '<Maxes>\r\n<Max Operand=".PRE">100</Max>\r\n</Maxes>\r\n'
            in project.to_string()
        )

    def test_container_order(self, project: Project) -> None:
        """Containers follow the Tag schema order regardless of insert order."""
        tag = _tag(project)
        tag.set_operand_metadata(".PRE", "external_logging", "true")
        tag.set_operand_metadata(".PRE", "min", "0")
        tag.set_operand_metadata(".PRE", "engineering_unit", "ms")
        tag.set_operand_metadata(".PRE", "comment", "c")
        tag.description = "d"
        assert [c.tag for c in tag._element] == [
            "Description",
            "Comments",
            "EngineeringUnits",
            "Mins",
            "ExternalLoggings",
            "Data",
            "Data",
        ]

    def test_invalid_key(self, project: Project) -> None:
        """An unknown key raises ValueError."""
        with pytest.raises(ValueError, match="unknown operand metadata key"):
            _tag(project).set_operand_metadata(".PRE", "bogus", "x")

    @pytest.mark.parametrize("operand", ["PRE", "", "0", " .PRE"])
    def test_invalid_operand(self, project: Project, operand: str) -> None:
        """Operands must start with '.' or '['."""
        with pytest.raises(ValueError, match="operand"):
            _tag(project).set_operand_comment(operand, "x")
        assert _tag(project)._element.find("Comments") is None

    def test_existing_nodes_see_change(self, project: Project) -> None:
        """Node objects created before the edit see the new metadata."""
        tag = _tag(project)
        node = tag.members["PRE"]
        assert node.description == ""
        tag.set_operand_comment(".PRE", "preset")
        assert node.description == "preset"
        tag.set_operand_comment(".PRE", None)
        assert node.description == ""

    def test_bit_comment(self, project: Project) -> None:
        """Bit operands work."""
        tag = project.controller_tags["existing"]
        tag.set_operand_comment(".3", "bit three")
        assert tag.bit(3).description == "bit three"

    def test_array_operand(self, project: Project) -> None:
        """Bracket operands are accepted and kept after dotted ones."""
        tag = _tag(project)
        tag.set_operand_comment("[0,1]", "x")
        tag.set_operand_comment(".PRE", "y")
        assert list(tag.operand_comments) == [".PRE", "[0,1]"]


_AOI_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0">
<Controller Name="C" ProcessorType="1756-L83E">
<AddOnInstructionDefinitions>
<AddOnInstructionDefinition Name="Aoi" Revision="1.0">
<Parameters>
<Parameter Name="p" TagType="Base" DataType="DINT" Usage="Input" Radix="Decimal">
<DefaultData Format="L5K">
<![CDATA[0]]>
</DefaultData>
<DefaultData Format="Decorated">
<DataValue DataType="DINT" Radix="Decimal" Value="0"/>
</DefaultData>
</Parameter>
</Parameters>
<LocalTags>
<LocalTag Name="l" DataType="TIMER" ExternalAccess="None">
<DefaultData Format="Decorated">
<Structure DataType="TIMER">
<DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="0"/>
</Structure>
</DefaultData>
</LocalTag>
</LocalTags>
</AddOnInstructionDefinition>
</AddOnInstructionDefinitions>
</Controller>
</RSLogix5000Content>
"""  # noqa: E501


class TestAoiOperandMetadata:
    """The same API on AOI parameters and local tags."""

    def test_parameter(self) -> None:
        """Comments go before DefaultData on a Parameter."""
        project = loads(_AOI_DOC)
        param = project.aois["Aoi"].parameters["p"]
        param.set_operand_comment(".1", "bit")
        param.set_operand_comment(".0", "zero")
        assert [c.tag for c in param.element] == [
            "Comments",
            "DefaultData",
            "DefaultData",
        ]
        assert list(param.operand_comments) == [".0", ".1"]
        again = loads(project.to_string()).aois["Aoi"].parameters["p"]
        assert again.operand_comments == {".0": "zero", ".1": "bit"}

    def test_local_tag(self) -> None:
        """Local tags accept edits and existing nodes see them."""
        project = loads(_AOI_DOC)
        local = project.aois["Aoi"].local_tags["l"]
        node = local.members["PRE"]
        local.set_operand_metadata(".PRE", "engineering_unit", "ms")
        assert node.engineering_unit == "ms"
        assert [c.tag for c in local.element] == ["EngineeringUnits", "DefaultData"]
        text = project.to_string()
        assert (
            '<EngineeringUnit Operand=".PRE">\r\n<![CDATA[ms]]>\r\n</EngineeringUnit>'
            in text
        )

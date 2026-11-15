"""Tests for schema-ordered child insertion (``py_l5x.parsers.schema``)."""

import difflib
import xml.etree.ElementTree as ET
from pathlib import Path

from py_l5x import Project, load, loads
from py_l5x.parsers.schema import (
    CHILD_ORDER,
    insert_child,
    new_cdata_element,
    remove_child,
)
from py_l5x.parsers.utils import CDATA_TAG

FIXTURES = Path(__file__).parent / "fixtures"


def _example() -> Project:
    """Load the main example project.

    Returns:
        The parsed ``example.L5X`` project.
    """
    return load(str(FIXTURES / "example.L5X"))


def _child_tags(element: ET.Element) -> list[str]:
    """List the child tag names of an element.

    Args:
        element: The parent element.

    Returns:
        Child tags in document order.
    """
    return [c.tag for c in element]


def _assert_schema_order(root: ET.Element) -> None:
    """Assert every known parent in the tree has its children in order.

    Args:
        root: The root element to walk.
    """
    for parent in root.iter():
        order = CHILD_ORDER.get(parent.tag)
        if order is None:
            continue
        ranks = [order.index(c.tag) for c in parent if c.tag in order]
        assert ranks == sorted(ranks), (parent.tag, _child_tags(parent))


def _diff(before: str, after: str) -> list[str]:
    """Return the changed lines between two documents.

    Args:
        before: Original text.
        after: Modified text.

    Returns:
        Diff lines starting with ``+`` or ``-`` (headers excluded).
    """
    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(), lineterm="", n=0
    )
    return [ln for ln in lines if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]


class TestDescriptionPlacement:
    """Setting a CDataField puts the child at its schema position."""

    def test_tag_before_data(self) -> None:
        """Tag Description goes before Data."""
        project = _example()
        tag = project.controller_tags["ALLOWABLE_ALARMS"]
        assert "Description" not in _child_tags(tag._element)
        tag.description = "x"
        tags = _child_tags(tag._element)
        assert tags[0] == "Description"
        assert tags.index("Description") < tags.index("Data")
        _assert_schema_order(project.root)

    def test_tag_before_comments(self) -> None:
        """Tag Description goes before Comments."""
        project = _example()
        tag = project.programs["MainProgram"].tags["a_2d_array"]
        assert _child_tags(tag._element) == ["Comments", "Data", "Data"]
        tag.description = "x"
        assert _child_tags(tag._element) == ["Description", "Comments", "Data", "Data"]

    def test_rung_comment_before_text(self) -> None:
        """Rung Comment goes before Text."""
        project = _example()
        routine = project.programs["PeriodicProgram"].routines["main"]
        rung = next(r for r in routine.rungs if not r.comment)
        rung.comment = "hello"
        assert _child_tags(rung._element) == ["Comment", "Text"]
        assert rung.comment == "hello"

    def test_aoi_before_revision_note(self) -> None:
        """AOI Description goes before RevisionNote and Parameters."""
        project = _example()
        aoi = project.aois["Debounce"]
        assert not aoi.description
        aoi.description = "x"
        tags = _child_tags(aoi._element)
        assert tags[:3] == ["Description", "RevisionNote", "Parameters"]

    def test_aoi_parameter_and_local_tag(self) -> None:
        """Parameter and LocalTag Description go before DefaultData."""
        project = _example()
        aoi = project.aois["Debounce"]
        for collection in (aoi.parameters, aoi.local_tags):
            item = next(
                i
                for i in collection.values()
                if "DefaultData" in _child_tags(i._element)
            )
            item.description = ""
            item.description = "x"
            tags = _child_tags(item._element)
            assert tags.index("Description") < tags.index("DefaultData")
        _assert_schema_order(project.root)

    def test_datatype_before_members(self) -> None:
        """DataType Description goes before Members."""
        project = load(str(FIXTURES / "A_UDT_DataType.L5X"))
        data_type = project.data_types["A_UDT"]
        data_type.description = "x"
        assert _child_tags(data_type._element) == [
            "Description",
            "Members",
            "Dependencies",
        ]

    def test_member_before_engineering_unit(self) -> None:
        """Member Description goes before EngineeringUnit."""
        project = load(str(FIXTURES / "A_UDT_DataType.L5X"))
        member = next(
            m
            for dt in project.data_types.values()
            for m in dt.members.values()
            if "EngineeringUnit" in _child_tags(m._element)
        )
        member.description = ""
        assert "Description" not in _child_tags(member._element)
        member.description = "x"
        assert _child_tags(member._element)[:2] == ["Description", "EngineeringUnit"]

    def test_member_state0_after_unit(self) -> None:
        """Member State0 and State1 go after EngineeringUnit."""
        project = load(str(FIXTURES / "A_UDT_DataType.L5X"))
        member = next(
            m
            for dt in project.data_types.values()
            for m in dt.members.values()
            if _child_tags(m._element) == ["Description", "EngineeringUnit"]
        )
        member.state1 = "on"
        member.state0 = "off"
        assert _child_tags(member._element) == [
            "Description",
            "EngineeringUnit",
            "State0",
            "State1",
        ]

    def test_program_task_module_routine(self) -> None:
        """Program, Task, Module and Routine Descriptions come first."""
        project = _example()
        program = project.programs["EventProgram"]
        task = project.tasks["MainTask"]
        module = project.modules["Local"]
        routine = program.routines["Main"]
        for obj in (program, task, module, routine):
            obj.description = "x"
            assert _child_tags(obj._element)[0] == "Description"
        _assert_schema_order(project.root)

    def test_all_edited_documents_round_trip(self) -> None:
        """An edited document reloads with the same text."""
        project = _example()
        project.controller_tags["ALLOWABLE_ALARMS"].description = "a < b"
        again = loads(project.to_string())
        assert again.controller_tags["ALLOWABLE_ALARMS"].description == "a < b"


class TestFormatting:
    """Edits keep Studio's one-element-per-line layout."""

    def test_insert_layout(self) -> None:
        """An inserted Description is laid out exactly like Studio's."""
        project = _example()
        blank_lines = project.to_string().count("\r\n\r\n")
        project.controller_tags["ALLOWABLE_ALARMS"].description = "x"
        text = project.to_string()
        fragment = (
            "\r\n<Description>\r\n<![CDATA[x]]>\r\n</Description>\r\n"
            '<Data Format="L5K">'
        )
        assert fragment in text
        # Blank lines can exist inside CDATA; an insert must not add any.
        assert text.count("\r\n\r\n") == blank_lines

    def test_insert_diff(self) -> None:
        """An insert adds exactly three lines."""
        project = _example()
        before = project.to_string()
        project.controller_tags["ALLOWABLE_ALARMS"].description = "x"
        assert _diff(before, project.to_string()) == [
            "+<Description>",
            "+<![CDATA[x]]>",
            "+</Description>",
        ]

    def test_update_diff(self) -> None:
        """Updating a Description changes only its CDATA line."""
        project = _example()
        tag = next(t for t in project.controller_tags.values() if t.description)
        old = tag.description
        before = project.to_string()
        tag.description = "changed text"
        assert _diff(before, project.to_string()) == [
            f"-<![CDATA[{old}]]>",
            "+<![CDATA[changed text]]>",
        ]

    def test_remove_diff(self) -> None:
        """Removing a Description removes exactly three lines."""
        project = _example()
        tag = next(t for t in project.controller_tags.values() if t.description)
        old = tag.description
        before = project.to_string()
        tag.description = None
        assert _diff(before, project.to_string()) == [
            "-<Description>",
            f"-<![CDATA[{old}]]>",
            "-</Description>",
        ]

    def test_insert_then_remove_is_identity(self) -> None:
        """Inserting then removing restores the original text."""
        project = _example()
        before = project.to_string()
        tag = project.controller_tags["ALLOWABLE_ALARMS"]
        tag.description = "x"
        tag.description = ""
        assert project.to_string() == before

    def test_remove_compact_siblings(self) -> None:
        """Removal never leaves two elements on a line."""
        parent = ET.fromstring("<Rung><Comment/><Text/></Rung>")
        remove_child(parent, parent[0])
        assert parent.text == "\n"
        assert [c.tag for c in parent] == ["Text"]

    def test_new_cdata_element_shape(self) -> None:
        """new_cdata_element matches the reader's whitespace shape."""
        element = new_cdata_element("Description", "x")
        assert element.text == "\n"
        assert element[0].tag == CDATA_TAG
        assert element[0].text == "x"
        assert element[0].tail == "\n"
        assert element.tail is None

    def test_shape_matches_loaded_file(self) -> None:
        """A built element has the same text/tail as one from a file."""
        project = _example()
        loaded = next(
            t._element.find("Description")
            for t in project.controller_tags.values()
            if t.description
        )
        built = new_cdata_element("Description", "x")
        assert (built.text, built[0].tail) == (loaded.text, loaded[0].tail)


class TestInsertChild:
    """Unit tests for insert_child."""

    @staticmethod
    def _tag(xml: str) -> ET.Element:
        """Parse an XML snippet.

        Args:
            xml: The snippet.

        Returns:
            Its root element.
        """
        return ET.fromstring(xml)

    def test_unknown_parent_appends(self) -> None:
        """Unknown parent tags append."""
        parent = self._tag("<Foo>\n<A/>\n</Foo>")
        insert_child(parent, ET.Element("Description"))
        assert _child_tags(parent) == ["A", "Description"]

    def test_unknown_child_appends(self) -> None:
        """Unlisted child tags append."""
        parent = self._tag("<Tag>\n<Data/>\n</Tag>")
        insert_child(parent, ET.Element("Mystery"))
        assert _child_tags(parent) == ["Data", "Mystery"]

    def test_unlisted_existing_ignored(self) -> None:
        """Existing unlisted children are skipped when comparing."""
        parent = self._tag("<Tag>\n<Mystery/>\n<Data/>\n</Tag>")
        insert_child(parent, ET.Element("Description"))
        assert _child_tags(parent) == ["Mystery", "Description", "Data"]

    def test_data_l5k_goes_first(self) -> None:
        """A new L5K Data goes first in the Data slot."""
        parent = self._tag('<Tag>\n<Description/>\n<Data Format="Decorated"/>\n</Tag>')
        insert_child(parent, ET.Element("Data", Format="L5K"))
        assert [c.get("Format") for c in parent if c.tag == "Data"] == [
            "L5K",
            "Decorated",
        ]
        assert _child_tags(parent) == ["Description", "Data", "Data"]

    def test_data_other_goes_last(self) -> None:
        """A new non-L5K Data goes after existing ones."""
        parent = self._tag(
            '<Tag>\n<Data Format="L5K"/>\n<Data Format="Decorated"/>\n</Tag>'
        )
        insert_child(parent, ET.Element("Data", Format="String"))
        assert [c.get("Format") for c in parent] == ["L5K", "Decorated", "String"]

    def test_default_data_slot(self) -> None:
        """DefaultData follows the same slot rules under Parameter."""
        parent = self._tag('<Parameter><DefaultData Format="Decorated"/></Parameter>')
        insert_child(parent, ET.Element("DefaultData", Format="L5K"))
        insert_child(parent, ET.Element("Description"))
        assert [c.tag for c in parent] == ["Description", "DefaultData", "DefaultData"]
        assert parent[1].get("Format") == "L5K"

    def test_childless_self_closed_parent(self) -> None:
        """Inserting into an empty parent sets text and tail newlines."""
        parent = self._tag("<Rung/>")
        insert_child(parent, ET.Element("Text"))
        assert parent.text == "\n"
        assert parent[0].tail == "\n"
        assert ET.tostring(parent, encoding="unicode") == "<Rung>\n<Text />\n</Rung>"

    def test_previous_tail_gets_newline(self) -> None:
        """A compact preceding sibling gets a newline before the new child."""
        parent = self._tag("<Rung><Comment/></Rung>")
        insert_child(parent, ET.Element("Text"))
        assert parent[0].tail == "\n"
        assert parent[1].tail == "\n"

    def test_returns_child(self) -> None:
        """insert_child returns the child."""
        child = ET.Element("Text")
        assert insert_child(ET.Element("Rung"), child) is child

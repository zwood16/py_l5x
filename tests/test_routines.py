"""Tests for py_l5x.parsers.routine and Program.routines integration."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.program import ProgramsCollection
from py_l5x.parsers.routine import Routine
from py_l5x.parsers.tag import TypeRegistry

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLE_L5X = FIXTURES_DIR / "example.L5X"


@pytest.fixture
def example_tree() -> ET.ElementTree:
    """Load the example L5X file."""
    return ET.parse(str(EXAMPLE_L5X))


@pytest.fixture
def controller_element(example_tree: ET.ElementTree) -> ET.Element:
    """Extract the <Controller> element from the example L5X."""
    controller = example_tree.getroot().find("Controller")
    assert controller is not None, "Controller element not found in example.L5X"
    return controller


@pytest.fixture
def type_registry(controller_element: ET.Element) -> TypeRegistry:
    """Build a TypeRegistry from the example L5X's UDT and AOI collections."""
    return TypeRegistry(
        DataTypesCollection(controller_element),
        AddOnDataTypeCollection(controller_element),
    )


@pytest.fixture
def programs(
    controller_element: ET.Element, type_registry: TypeRegistry
) -> ProgramsCollection:
    """Programs collection."""
    return ProgramsCollection(controller_element, type_registry)


class TestProgramsRoutinesCollection:
    """Tests for Program.routines mapping behavior."""

    def test_program_routines_returns_routines_collection(
        self, programs: ProgramsCollection
    ) -> None:
        """Program.routines returns routines keyed by routine name."""
        routines = programs["MainProgram"].routines
        assert "MainRoutine" in routines
        assert isinstance(routines["MainRoutine"], Routine)


class TestRoutineParsing:
    """Tests for ladder and ST logic extraction via Routine."""

    def test_rll_rungs_parse_number_comment_text(
        self, programs: ProgramsCollection
    ) -> None:
        """RLL routines expose rung number/type/comment/text."""
        enable_in_false = programs["AnotherProgram"].routines["io"]
        assert enable_in_false.type_ == "RLL"

        rung0 = enable_in_false.rungs[0]
        assert rung0.number == 0
        assert rung0.type_ == "N"
        assert rung0.comment == ""
        assert rung0.text == "GenericInput(TestInput,Local:1:I.Pt00.Data);"

    def test_rll_routine_has_no_st_lines(self, programs: ProgramsCollection) -> None:
        """RLL routines expose empty ST content."""
        main = programs["MainProgram"].routines["MainRoutine"]
        assert main.type_ == "RLL"
        assert main.st_lines == []
        assert main.st_code == ""

    def test_st_lines_and_joined_code(self, programs: ProgramsCollection) -> None:
        """ST routines expose lines and newline-joined code."""
        st = programs["AnotherProgram"].routines["StructuredTextRoutine"]
        assert st.type_ == "ST"

        first = st.st_lines[0]
        assert first.number == 0
        assert first.text == "(*"
        assert "for i:=0 to 31 by 1 do" in st.st_code

    def test_st_routine_has_no_rungs(self, programs: ProgramsCollection) -> None:
        """ST routines expose empty rung content."""
        st = programs["AnotherProgram"].routines["StructuredTextRoutine"]
        assert st.rungs == []

    def test_rll_as_text_format(self, programs: ProgramsCollection) -> None:
        """RLL text formatting matches line/comment + indented rung text."""
        main = programs["MainProgram"].routines["MainRoutine"]
        assert main.as_text() == "0 :\n    JSR(SequenceRoutine,0);"

    def test_st_as_text_returns_line_by_line_text(
        self, programs: ProgramsCollection
    ) -> None:
        """ST text formatting returns code line-by-line."""
        st = programs["AnotherProgram"].routines["StructuredTextRoutine"]
        assert st.as_text() == st.st_code
        assert "for i:=0 to 31 by 1 do" in st.as_text()

    def test_print_text_prints_formatted_output(
        self, programs: ProgramsCollection, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """print_text emits formatted routine text to stdout."""
        main = programs["MainProgram"].routines["MainRoutine"]
        main.print_text()
        out = capsys.readouterr().out
        assert out == "0 :\n    JSR(SequenceRoutine,0);\n"

    def test_st_comments_extract_line_and_block_comments(
        self, programs: ProgramsCollection
    ) -> None:
        """ST comments include both // lines and (* ... *) blocks."""
        st = programs["AnotherProgram"].routines["StructuredTextRoutine"]

        assert (
            "Example of a structured text program. Loops through an inc a number"
            "\n\nThis is a multiline comment\n\t- Some indented text" in st.comments
        )
        assert "loop here" in st.comments
        assert "multiline if" in st.comments
        assert "some comment" in st.comments
        assert "another comment nearby" in st.comments

    def test_st_comments_ignore_markers_inside_string_literals(self) -> None:
        """Comment markers inside single-quoted strings are not parsed."""
        routine_el = ET.fromstring(
            """
            <Routine Name="InlineCommentTest" Type="ST">
                <STContent>
                    <Line Number="0">x := 'not // a comment'; // trailing</Line>
                    <Line Number="1">y := 'not (* block *) either';</Line>
                    <Line Number="2">(* block start</Line>
                    <Line Number="3">block end *) z := 1;</Line>
                </STContent>
            </Routine>
            """
        )
        routine = Routine(routine_el)

        assert routine.comments == ["trailing", "block start\nblock end"]

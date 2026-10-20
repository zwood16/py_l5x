"""Tests for py_l5x.parsers.routine and Program.routines integration."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.program import Program, ProgramsCollection
from py_l5x.parsers.routine import Routine
from py_l5x.parsers.tag import TypeRegistry

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLE_L5X = FIXTURES_DIR / "example.L5X"

# "Rung 0 " padded with "-" to the 40-character header width.
RUNG0_HEADER = "Rung 0 " + "-" * 33
RUNG1_HEADER = "Rung 1 " + "-" * 33

MULTILINE_RLL_XML = """
<Routine Name="Multi" Type="RLL">
    <RLLContent>
        <Rung Number="0" Type="N">
            <Comment><CDataContent>first line
second line</CDataContent></Comment>
            <Text><CDataContent>XIC(A)OTE(B);</CDataContent></Text>
        </Rung>
        <Rung Number="1" Type="N">
            <Text><CDataContent>XIO(C)OTE(D);</CDataContent></Text>
        </Rung>
    </RLLContent>
</Routine>
"""

ST_STRING_LITERAL_XML = """
<Routine Name="StStrings" Type="ST">
    <STContent>
        <Line Number="0">
            <CDataContent>x := 'not // a comment'; // trailing</CDataContent>
        </Line>
        <Line Number="1">
            <CDataContent>y := 'not (* block *) either';</CDataContent>
        </Line>
        <Line Number="2">
            <CDataContent>(* block start</CDataContent>
        </Line>
        <Line Number="3">
            <CDataContent>block end *) z := 1;</CDataContent>
        </Line>
        <Line Number="4">
            <CDataContent>s := 'it''s // not'; (* real *)</CDataContent>
        </Line>
        <Line Number="5">
            <CDataContent>    t := '(*';    // c</CDataContent>
        </Line>
    </STContent>
</Routine>
"""


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
        """RLL text without a comment has a header and a Logic block only."""
        main = programs["MainProgram"].routines["MainRoutine"]
        assert main.as_text() == f"{RUNG0_HEADER}\nLogic\nJSR(SequenceRoutine,0);"

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
        assert out == f"{RUNG0_HEADER}\nLogic\nJSR(SequenceRoutine,0);\n"

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


class TestProgramLogicText:
    """Tests for Program.logic_text / print_logic_text output."""

    def test_header_line_names_program(self, programs: ProgramsCollection) -> None:
        """logic_text starts with the program header line."""
        text = programs["MainProgram"].logic_text()
        assert text.splitlines()[0] == "Program: MainProgram"

    def test_routine_header_lines_present(self, programs: ProgramsCollection) -> None:
        """Each routine gets a blank line followed by a Routine header line."""
        lines = programs["AnotherProgram"].logic_text().splitlines()
        assert "" in lines
        assert "Routine: io (RLL)" in lines
        assert "Routine: Main (RLL)" in lines
        assert "Routine: StructuredTextRoutine (ST)" in lines

        for name, type_ in [
            ("io", "RLL"),
            ("Main", "RLL"),
            ("StructuredTextRoutine", "ST"),
        ]:
            idx = lines.index(f"Routine: {name} ({type_})")
            assert lines[idx - 1] == ""

    def test_rll_rung_text_present(self, programs: ProgramsCollection) -> None:
        """RLL routine rungs render as a header, a Logic block, and rung text."""
        text = programs["MainProgram"].logic_text()
        assert (
            f"Routine: MainRoutine (RLL)\n{RUNG0_HEADER}\nLogic\n"
            "JSR(SequenceRoutine,0);" in text
        )

    def test_rll_multiline_comment_rendered_in_full(
        self, programs: ProgramsCollection
    ) -> None:
        """logic_text includes every line of a multi-line rung comment."""
        seq = programs["MainProgram"].routines["SequenceRoutine"]
        comment = seq.rungs[0].comment
        assert "\n" in comment

        lines = programs["MainProgram"].logic_text().splitlines()
        idx = lines.index(f"Routine: SequenceRoutine ({seq.type_})")
        block = lines[idx + 1 :]
        assert block[0] == RUNG0_HEADER
        assert block[1] == "Comment"
        for offset, comment_line in enumerate(comment.splitlines()):
            assert block[2 + offset] == comment_line

    def test_st_code_present(self, programs: ProgramsCollection) -> None:
        """ST routine code is rendered line-by-line under its header."""
        st = programs["AnotherProgram"].routines["StructuredTextRoutine"]
        text = programs["AnotherProgram"].logic_text()
        assert "Routine: StructuredTextRoutine (ST)\n" in text
        assert st.st_code in text
        assert "for i:=0 to 31 by 1 do" in text

    def test_unsupported_routine_type_is_reported(
        self, type_registry: TypeRegistry
    ) -> None:
        """Routines of unsupported types show an explicit placeholder line."""
        program_el = ET.fromstring(
            """
            <Program Name="FBDProgram">
                <Routines>
                    <Routine Name="FBDRoutine" Type="FBD"/>
                </Routines>
            </Program>
            """
        )
        program = Program(program_el, type_registry)

        assert program.logic_text() == (
            "Program: FBDProgram\n"
            "\n"
            "Routine: FBDRoutine (FBD)\n"
            "[Unsupported routine type: FBD]"
        )

    def test_print_logic_text_matches_logic_text(
        self, programs: ProgramsCollection, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """print_logic_text prints and returns the same string as logic_text."""
        program = programs["AnotherProgram"]
        expected = program.logic_text()

        returned = program.print_logic_text()

        assert returned == expected
        assert capsys.readouterr().out == expected + "\n"


class TestRllAsText:
    """Tests for the Routine.as_text RLL rung layout."""

    def test_header_width_and_format(self) -> None:
        """Rung headers are 'Rung N ' padded with '-' to 40 characters."""
        routine = Routine(ET.fromstring(MULTILINE_RLL_XML))
        header0, header1 = (
            line for line in routine.as_text().splitlines() if line.startswith("Rung")
        )

        assert header0 == RUNG0_HEADER
        assert header1 == RUNG1_HEADER
        assert len(header0) == 40
        assert len(header1) == 40
        assert header0.endswith("-")

    def test_full_multiline_comment_and_blank_line_separation(self) -> None:
        """Every comment line is kept; rungs are separated by one blank line."""
        routine = Routine(ET.fromstring(MULTILINE_RLL_XML))

        assert routine.as_text() == (
            f"{RUNG0_HEADER}\n"
            "Comment\n"
            "first line\n"
            "second line\n"
            "Logic\n"
            "XIC(A)OTE(B);\n"
            "\n"
            f"{RUNG1_HEADER}\n"
            "Logic\n"
            "XIO(C)OTE(D);"
        )

    def test_rung_without_comment_has_no_comment_line(self) -> None:
        """A rung with no comment omits the Comment block entirely."""
        routine = Routine(ET.fromstring(MULTILINE_RLL_XML))
        rung1_block = routine.as_text().split("\n\n")[1]

        assert "Comment" not in rung1_block
        assert rung1_block == f"{RUNG1_HEADER}\nLogic\nXIO(C)OTE(D);"

    def test_no_trailing_blank_line(self) -> None:
        """The rendered text does not end with a newline or blank line."""
        routine = Routine(ET.fromstring(MULTILINE_RLL_XML))
        assert not routine.as_text().endswith("\n")

    def test_multiline_fixture_comment_rendered_in_full(
        self, programs: ProgramsCollection
    ) -> None:
        """A multi-line fixture rung comment appears line-for-line."""
        seq = programs["MainProgram"].routines["SequenceRoutine"]
        rung = seq.rungs[0]
        lines = seq.as_text().splitlines()

        assert lines[0] == RUNG0_HEADER
        assert lines[1] == "Comment"
        comment_lines = rung.comment.splitlines()
        assert lines[2 : 2 + len(comment_lines)] == comment_lines
        assert lines[2 + len(comment_lines)] == "Logic"

    def test_unsupported_type_as_text_is_empty(self) -> None:
        """Non-RLL, non-ST routines render as an empty string."""
        routine = Routine(ET.fromstring('<Routine Name="F" Type="FBD"/>'))
        assert routine.as_text() == ""


class TestRoutineLogic:
    """Tests for the Routine.logic property."""

    def test_rll_logic_is_rung_text_in_order(
        self, programs: ProgramsCollection
    ) -> None:
        """RLL logic returns each rung's neutral text in order."""
        main = programs["MainProgram"].routines["MainRoutine"]
        assert main.logic == ["JSR(SequenceRoutine,0);"]

    def test_rll_logic_skips_empty_rungs(self) -> None:
        """Rungs with no neutral text are skipped."""
        routine = Routine(
            ET.fromstring(
                """
                <Routine Name="R" Type="RLL">
                    <RLLContent>
                        <Rung Number="0" Type="N">
                            <Text><CDataContent>A;</CDataContent></Text>
                        </Rung>
                        <Rung Number="1" Type="N"/>
                        <Rung Number="2" Type="N">
                            <Text><CDataContent>B;</CDataContent></Text>
                        </Rung>
                    </RLLContent>
                </Routine>
                """
            )
        )
        assert routine.logic == ["A;", "B;"]

    def test_st_logic_removes_comments_and_keeps_string_literals(self) -> None:
        """ST logic drops // and (* *) comments but not markers in strings."""
        routine = Routine(ET.fromstring(ST_STRING_LITERAL_XML))

        assert routine.logic == [
            "x := 'not // a comment';",
            "y := 'not (* block *) either';",
            " z := 1;",
            "s := 'it''s // not';",
            "    t := '(*';",
        ]

    def test_st_logic_matches_fixture_comment_removal(
        self, programs: ProgramsCollection
    ) -> None:
        """Fixture ST logic has no comment text and keeps code lines in order."""
        st = programs["AnotherProgram"].routines["StructuredTextRoutine"]
        logic = st.logic

        assert logic[0] == "j := 0;"
        assert "for i:=0 to 31 by 1 do" in logic
        assert not any("loop here" in line for line in logic)
        assert not any("multiline" in line.lower() for line in logic)
        assert all(line == line.rstrip() and line.strip() for line in logic)

    def test_unsupported_type_logic_is_empty(self) -> None:
        """Routines of unsupported types have no logic."""
        routine = Routine(ET.fromstring('<Routine Name="F" Type="FBD"/>'))
        assert routine.logic == []

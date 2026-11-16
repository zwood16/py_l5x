"""Tests for routine, rung and structured text edits."""

import pytest

from py_l5x import Project, loads

_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0">
<Controller Name="C" ProcessorType="1756-L83E">
<AddOnInstructionDefinitions>
<AddOnInstructionDefinition Name="Aoi" Revision="1.0">
<Routines>
<Routine Name="Logic" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N">
<Text>
<![CDATA[NOP();]]>
</Text>
</Rung>
</RLLContent>
</Routine>
</Routines>
</AddOnInstructionDefinition>
<AddOnInstructionDefinition Name="NoRoutines" Revision="1.0">
</AddOnInstructionDefinition>
</AddOnInstructionDefinitions>
<Programs>
<Program Name="P" MainRoutineName="Main" FaultRoutineName="Fault">
<Routines>
<Routine Name="Main" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N">
<Text>
<![CDATA[XIC(a)OTE(b);]]>
</Text>
</Rung>
<Rung Number="1" Type="N">
<Comment>
<![CDATA[second]]>
</Comment>
<Text>
<![CDATA[XIC(b)OTE(c);]]>
</Text>
</Rung>
</RLLContent>
</Routine>
<Routine Name="Fault" Type="RLL">
<RLLContent/>
</Routine>
<Routine Name="Calc" Type="ST">
<STContent>
<Line Number="0">
<![CDATA[x := 1;]]>
</Line>
</STContent>
</Routine>
</Routines>
</Program>
<Program Name="NoRoutines" MainRoutineName="Main">
</Program>
</Programs>
</Controller>
</RSLogix5000Content>
"""


@pytest.fixture
def project() -> Project:
    """A project with a program, an AOI, and programs/AOIs lacking routines."""
    return loads(_DOC)


def _routines(project: Project, program: str = "P"):
    """Return a program's routine collection.

    Args:
        project: The project.
        program: Program name.

    Returns:
        The ``RoutinesCollection``.
    """
    return project.programs[program].routines


def _frag(project: Project, routine: str, program: str = "P") -> str:
    """Return one routine's serialized XML (CRLF line endings).

    Args:
        project: The project.
        routine: Routine name.
        program: Program name.

    Returns:
        The text from the routine's start tag to its end.
    """
    text = project.to_string()
    start = text.index(f'<Routine Name="{routine}"')
    return text[start : text.index("</Routine>", start) + len("</Routine>")]


class TestAddRoutine:
    """RoutinesCollection.add."""

    @pytest.mark.parametrize(
        ("type_", "content"), [("RLL", "RLLContent"), ("ST", "STContent")]
    )
    def test_add(self, project: Project, type_: str, content: str) -> None:
        """New routines are empty, self-closed like Studio's exports, and round trip."""
        routine = _routines(project).add("New", type_)
        assert routine.type_ == type_
        assert list(_routines(project))[-1] == "New"
        assert f'<Routine Name="New" Type="{type_}"/>' in project.to_string()
        assert routine._element.find(content) is None
        again = _routines(loads(project.to_string()))["New"]
        assert again.type_ == type_

    def test_description(self, project: Project) -> None:
        """A description goes before the content."""
        routine = _routines(project).add("New", description="hi")
        assert [c.tag for c in routine._element] == ["Description"]
        routine.add_rung("NOP();")
        assert [c.tag for c in routine._element] == ["Description", "RLLContent"]

    def test_program_without_routines(self, project: Project) -> None:
        """A missing <Routines> is created."""
        routine = _routines(project, "NoRoutines").add("Main")
        assert routine.name == "Main"
        assert [c.tag for c in project.programs["NoRoutines"]._element] == ["Routines"]
        assert "Main" in _routines(loads(project.to_string()), "NoRoutines")

    @pytest.mark.parametrize("name", ["Logic", "Prescan", "Postscan", "EnableInFalse"])
    def test_aoi_names(self, project: Project, name: str) -> None:
        """Each valid AOI routine name works (Logic exists already)."""
        routines = project.aois["NoRoutines"].routines
        assert routines.add(name).name == name
        assert [c.tag for c in project.aois["NoRoutines"]._element] == ["Routines"]

    def test_aoi_invalid_name(self, project: Project) -> None:
        """Other names are rejected for an AOI."""
        with pytest.raises(ValueError, match="AOI routine name"):
            project.aois["Aoi"].routines.add("Custom")
        with pytest.raises(ValueError):
            project.aois["Aoi"].routines.add("logic")  # duplicate, ignoring case

    def test_aoi_flags_untouched(self, project: Project) -> None:
        """Execute flags are not modified."""
        project.aois["Aoi"].routines.add("Prescan")
        assert "ExecutePrescan" not in project.aois["Aoi"]._element.attrib

    def test_bad_type(self, project: Project) -> None:
        """Only RLL and ST are accepted."""
        with pytest.raises(ValueError, match="routine type"):
            _routines(project).add("x", "FBD")

    @pytest.mark.parametrize("name", ["main", "MAIN", "Main"])
    def test_duplicates(self, project: Project, name: str) -> None:
        """Duplicates are detected ignoring case."""
        with pytest.raises(ValueError, match="already exists"):
            _routines(project).add(name)

    @pytest.mark.parametrize("name", ["1a", "a__b", "a_", "x" * 41, "a b", ""])
    def test_invalid_names(self, project: Project, name: str) -> None:
        """Invalid names raise ValueError."""
        with pytest.raises(ValueError):
            _routines(project).add(name)
        assert len(_routines(project)) == 3


class TestRemoveRename:
    """remove and rename."""

    def test_remove(self, project: Project) -> None:
        """A normal routine can be removed."""
        _routines(project).remove("Calc")
        assert list(_routines(project)) == ["Main", "Fault"]

    def test_remove_missing(self, project: Project) -> None:
        """A missing name raises KeyError."""
        with pytest.raises(KeyError):
            _routines(project).remove("nope")

    @pytest.mark.parametrize("name", ["Main", "Fault"])
    def test_remove_protected(self, project: Project, name: str) -> None:
        """Main and fault routines can't be removed."""
        with pytest.raises(ValueError, match="main or fault"):
            _routines(project).remove(name)
        assert name in _routines(project)

    def test_remove_aoi_logic(self, project: Project) -> None:
        """An AOI's Logic can't be removed; others can."""
        routines = project.aois["Aoi"].routines
        with pytest.raises(ValueError, match="Logic"):
            routines.remove("Logic")
        routines.add("Prescan")
        routines.remove("Prescan")
        assert list(routines) == ["Logic"]

    def test_rename(self, project: Project) -> None:
        """Renaming returns the routine and keeps its content."""
        routine = _routines(project).rename("Calc", "Calc2")
        assert routine.name == "Calc2"
        assert routine.st_code == "x := 1;"
        assert "Calc" not in _routines(project)

    def test_rename_updates_main_and_fault(self, project: Project) -> None:
        """MainRoutineName and FaultRoutineName follow a rename."""
        _routines(project).rename("Main", "Entry")
        _routines(project).rename("Fault", "Faulted")
        program = project.programs["P"]
        assert program.main_routine_name == "Entry"
        assert program._element.get("FaultRoutineName") == "Faulted"

    def test_rename_leaves_unrelated_attribute(self, project: Project) -> None:
        """Renaming another routine doesn't touch the attributes."""
        _routines(project).rename("Calc", "Other")
        assert project.programs["P"].main_routine_name == "Main"

    def test_rename_case_only(self, project: Project) -> None:
        """A case-only rename of the routine itself is allowed."""
        _routines(project).rename("Calc", "CALC")
        assert "CALC" in _routines(project)

    def test_rename_errors(self, project: Project) -> None:
        """Missing, taken and invalid names fail."""
        with pytest.raises(KeyError):
            _routines(project).rename("nope", "x")
        with pytest.raises(ValueError, match="already exists"):
            _routines(project).rename("Calc", "MAIN")
        with pytest.raises(ValueError):
            _routines(project).rename("Calc", "a__b")
        assert "Calc" in _routines(project)

    def test_rename_aoi(self, project: Project) -> None:
        """AOI routines can't be renamed."""
        with pytest.raises(ValueError, match="AOI"):
            project.aois["Aoi"].routines.rename("Logic", "Other")


def _numbers(routine) -> list[int]:
    """Return a routine's rung numbers.

    Args:
        routine: The routine.

    Returns:
        The ``Number`` of each rung, in order.
    """
    return [r.number for r in routine.rungs]


class TestRungs:
    """add_rung and remove_rung."""

    def test_append(self, project: Project) -> None:
        """Appending numbers the new rung after the last."""
        main = _routines(project)["Main"]
        rung = main.add_rung("XIC(x)OTE(y);")
        assert rung.number == 2
        assert [r.text for r in main.rungs][-1] == "XIC(x)OTE(y);"
        assert _numbers(main) == [0, 1, 2]

    def test_insert_front_and_middle(self, project: Project) -> None:
        """Inserting renumbers every rung."""
        main = _routines(project)["Main"]
        main.add_rung("A();", index=0)
        main.add_rung("B();", index=2)
        assert [r.text for r in main.rungs] == [
            "A();",
            "XIC(a)OTE(b);",
            "B();",
            "XIC(b)OTE(c);",
        ]
        assert _numbers(main) == [0, 1, 2, 3]
        assert [
            r.number
            for r in loads(project.to_string()).programs["P"].routines["Main"].rungs
        ] == [0, 1, 2, 3]

    def test_insert_at_end_index(self, project: Project) -> None:
        """index == len appends."""
        main = _routines(project)["Main"]
        main.add_rung("Z();", index=2)
        assert main.rungs[-1].text == "Z();"

    def test_comment(self, project: Project) -> None:
        """A comment goes before the text."""
        main = _routines(project)["Main"]
        rung = main.add_rung("NOP();", comment="note")
        assert rung.comment == "note"
        assert [c.tag for c in rung._element] == ["Comment", "Text"]
        assert "second" in [r.comment for r in main.rungs]

    def test_exact_fragment(self, project: Project) -> None:
        """Rung XML matches Studio's layout."""
        _routines(project)["Fault"].add_rung("NOP();", comment="c")
        assert _frag(project, "Fault") == (
            '<Routine Name="Fault" Type="RLL">\r\n<RLLContent>\r\n'
            '<Rung Number="0" Type="N">\r\n'
            "<Comment>\r\n<![CDATA[c]]>\r\n</Comment>\r\n"
            "<Text>\r\n<![CDATA[NOP();]]>\r\n</Text>\r\n"
            "</Rung>\r\n</RLLContent>\r\n</Routine>"
        )

    def test_into_empty_and_self_closed(self, project: Project) -> None:
        """A self-closed RLLContent becomes a formatted container."""
        fault = _routines(project)["Fault"]
        fault.add_rung("NOP();")
        assert _numbers(fault) == [0]
        assert (
            loads(project.to_string()).programs["P"].routines["Fault"].rungs[0].text
            == "NOP();"
        )

    def test_missing_content_created(self, project: Project) -> None:
        """A routine with no content element gets one."""
        main = _routines(project)["Main"]
        main._element.remove(main._element.find("RLLContent"))
        main.add_rung("NOP();")
        assert _numbers(main) == [0]

    def test_text_unchanged(self, project: Project) -> None:
        """Text is stored exactly as given."""
        text = "  XIC( a )  OTE(b) ;  "
        rung = _routines(project)["Main"].add_rung(text)
        assert rung._element.find("Text")[0].text == text

    def test_remove_and_renumber(self, project: Project) -> None:
        """Removing renumbers the rest."""
        main = _routines(project)["Main"]
        main.add_rung("C();")
        main.remove_rung(0)
        assert [r.text for r in main.rungs] == ["XIC(b)OTE(c);", "C();"]
        assert _numbers(main) == [0, 1]

    def test_remove_last_rung(self, project: Project) -> None:
        """Removing every rung leaves a usable routine."""
        main = _routines(project)["Main"]
        main.remove_rung(1)
        main.remove_rung(0)
        assert main.rungs == []
        main.add_rung("NOP();")
        assert _numbers(main) == [0]

    @pytest.mark.parametrize("index", [-1, 3, 99])
    def test_index_errors(self, project: Project, index: int) -> None:
        """Out of range indexes raise IndexError."""
        main = _routines(project)["Main"]
        with pytest.raises(IndexError):
            main.add_rung("NOP();", index=index)
        with pytest.raises(IndexError):
            main.remove_rung(index if index != 3 else 2)
        assert len(main.rungs) == 2

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "XIC(a)",
            "XIC(a;",
            "XIC(a));",
            "XIC[a);",
            "[XIC(a])];",
            "XIC(a)];",
        ],
    )
    def test_text_validation(self, project: Project, text: str) -> None:
        """Bad rung text raises ValueError and adds nothing."""
        main = _routines(project)["Main"]
        with pytest.raises(ValueError):
            main.add_rung(text)
        assert len(main.rungs) == 2

    @pytest.mark.parametrize(
        "text",
        ["XIC(a)OTE(b);", "[XIC(a),XIC(b)]OTE(c);", "MSG('a)b');", "ADD(a,[1],b);"],
    )
    def test_valid_text(self, project: Project, text: str) -> None:
        """Nested brackets and brackets in literals pass."""
        assert _routines(project)["Main"].add_rung(text).text == text

    def test_st_routine_type_error(self, project: Project) -> None:
        """Rung methods reject ST routines."""
        calc = _routines(project)["Calc"]
        with pytest.raises(TypeError):
            calc.add_rung("NOP();")
        with pytest.raises(TypeError):
            calc.remove_rung(0)
        assert calc._element.find("RLLContent") is None


class TestStLines:
    """set_st_lines."""

    def test_from_list(self, project: Project) -> None:
        """A list replaces the lines, numbered from 0."""
        calc = _routines(project)["Calc"]
        calc.set_st_lines(["a := 1;", "b := 2;"])
        assert calc.st_code == "a := 1;\nb := 2;"
        assert [line.number for line in calc.st_lines] == [0, 1]

    def test_from_crlf_string(self, project: Project) -> None:
        """A CRLF string is split into lines."""
        calc = _routines(project)["Calc"]
        calc.set_st_lines("a := 1;\r\nb := 2;\r\n")
        assert [line.text for line in calc.st_lines] == ["a := 1;", "b := 2;", ""]

    def test_indentation_and_empty_lines(self, project: Project) -> None:
        """Indentation is kept and empty lines are empty CDATA."""
        calc = _routines(project)["Calc"]
        calc.set_st_lines(["IF a THEN", "    b := 1;", "", "END_IF;"])
        assert [line.text for line in calc.st_lines] == [
            "IF a THEN",
            "    b := 1;",
            "",
            "END_IF;",
        ]
        text = project.to_string()
        assert '<Line Number="1">\r\n<![CDATA[    b := 1;]]>\r\n</Line>' in text
        assert '<Line Number="2">\r\n<![CDATA[]]>\r\n</Line>' in text
        again = _routines(loads(text))["Calc"]
        assert again.st_code == calc.st_code

    def test_exact_fragment(self, project: Project) -> None:
        """ST XML matches Studio's layout."""
        _routines(project)["Calc"].set_st_lines("x := 2;")
        assert _frag(project, "Calc") == (
            '<Routine Name="Calc" Type="ST">\r\n<STContent>\r\n'
            '<Line Number="0">\r\n<![CDATA[x := 2;]]>\r\n</Line>\r\n'
            "</STContent>\r\n</Routine>"
        )

    def test_replaces_all(self, project: Project) -> None:
        """Old lines are removed."""
        calc = _routines(project)["Calc"]
        calc.set_st_lines(["1;", "2;", "3;"])
        calc.set_st_lines(["only;"])
        assert calc.st_code == "only;"
        assert len(calc._element.find("STContent")) == 1

    def test_clear(self, project: Project) -> None:
        """No lines leaves an empty STContent."""
        calc = _routines(project)["Calc"]
        calc.set_st_lines("")
        assert calc.st_lines == []
        calc.set_st_lines(["a;"])
        assert calc.st_code == "a;"

    def test_new_st_routine(self, project: Project) -> None:
        """A routine from add() can be filled."""
        routine = _routines(project).add("New", "ST")
        routine.set_st_lines(["a := 1;", "  b := 2;"])
        again = _routines(loads(project.to_string()))["New"]
        assert again.st_code == "a := 1;\n  b := 2;"

    def test_line_break_in_item(self, project: Project) -> None:
        """Items with line breaks are rejected."""
        calc = _routines(project)["Calc"]
        with pytest.raises(ValueError):
            calc.set_st_lines(["a\nb"])
        assert calc.st_code == "x := 1;"

    def test_rll_type_error(self, project: Project) -> None:
        """ST methods reject RLL routines."""
        main = _routines(project)["Main"]
        with pytest.raises(TypeError):
            main.set_st_lines("a;")
        assert main._element.find("STContent") is None

"""Tests for spec templating (``py_l5x.build.template``)."""

import copy
import json
from pathlib import Path

import pytest

from py_l5x import (
    AOISpec,
    DataTypeSpec,
    MemberSpec,
    ParameterSpec,
    ProgramSpec,
    RoutineSpec,
    RungSpec,
    TagSpec,
    build_program,
    load,
    loads,
    stamp,
    substitute,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _motor(n: int = 1) -> ProgramSpec:
    """Create a small program spec using the ``M1_`` naming.

    Args:
        n: Unused marker so callers read naturally (always motor 1).

    Returns:
        The template spec.
    """
    return ProgramSpec(
        "Motor1",
        tags=[
            TagSpec("M1_RUN", "BOOL", description="Motor1 run"),
            TagSpec("M1_SPEED", "DINT", value=100),
            TagSpec("M1_NAME", "STRING", value="Motor1"),
            TagSpec(
                "M1_ALIAS",
                alias_for="M1_RUN",
                operand_comments={".M1_RUN": "Motor1 comment"},
            ),
        ],
        routines=[
            RoutineSpec(
                "M1_Main",
                rungs=[
                    RungSpec("XIC(M1_RUN)MOV(M1_SPEED,M1_SPEED);", "Run Motor1"),
                ],
            ),
            RoutineSpec("M1_Calc", "ST", lines=["M1_SPEED := 5; // Motor1"]),
        ],
        main_routine="M1_Main",
        description="Program for Motor1",
    )


class TestSubstitute:
    """Substitution rules."""

    def test_every_string(self) -> None:
        """Names, types, alias targets, text, comments, lines and values change."""
        spec = substitute(_motor(), {"Motor1": "Motor7", "M1_": "M7_"})
        assert spec.name == "Motor7"
        assert spec.description == "Program for Motor7"
        assert [t.name for t in spec.tags] == [
            "M7_RUN",
            "M7_SPEED",
            "M7_NAME",
            "M7_ALIAS",
        ]
        assert spec.tags[0].description == "Motor7 run"
        assert spec.tags[2].value == "Motor7"
        assert spec.tags[3].alias_for == "M7_RUN"
        assert spec.main_routine == "M7_Main"
        assert spec.routines[0].rungs[0].text == "XIC(M7_RUN)MOV(M7_SPEED,M7_SPEED);"
        assert spec.routines[0].rungs[0].comment == "Run Motor7"
        assert spec.routines[1].lines == ["M7_SPEED := 5; // Motor7"]

    def test_dict_keys_untouched_by_default(self) -> None:
        """Dict keys (operands, member names) stay; dict values change."""
        spec = substitute(_motor(), {"M1_": "M7_", "Motor1": "Motor7"})
        assert spec.tags[3].operand_comments == {".M1_RUN": "Motor7 comment"}
        tag = TagSpec("t", "TIMER", value={"PRE": "M1_x", "ACC": 5})
        assert substitute(tag, {"PRE": "P", "M1_": "M2_"}).value == {
            "PRE": "M2_x",
            "ACC": 5,
        }

    def test_dict_keys_with_keys_true(self) -> None:
        """keys=True substitutes dict keys as well as values."""
        spec = substitute(_motor(), {"M1_": "M7_", "Motor1": "Motor7"}, keys=True)
        assert spec.tags[3].operand_comments == {".M7_RUN": "Motor7 comment"}
        tag = TagSpec("t", "TIMER", value={"PRE": "M1_x"})
        assert substitute(tag, {"PRE": "P", "M1_": "M2_"}, keys=True).value == {
            "P": "M2_x"
        }

    def test_non_strings_untouched(self) -> None:
        """Numbers, booleans and None stay as they are."""
        spec = substitute(_motor(), {"100": "999", "True": "x"})
        assert spec.tags[1].value == 100
        assert spec.disabled is False
        assert spec.main_routine == "M1_Main"
        assert spec.fault_routine is None

    def test_longest_key_first(self) -> None:
        """Overlapping keys prefer the longest match."""
        text = substitute(
            RungSpec("Motor1 M1_x Motor1_y"),
            {"Motor1": "Motor7", "Motor1_y": "Y", "M1_": "M7_"},
        )
        assert text.text == "Motor7 M7_x Y"

    def test_does_not_cascade(self) -> None:
        """Replacements are simultaneous: A->B and B->C never give A->C."""
        assert (
            substitute(RungSpec("AB BA A B"), {"A": "B", "B": "C"}).text == "BC CB B C"
        )
        assert substitute(RungSpec("x"), {"x": "xx"}).text == "xx"

    def test_case_sensitive(self) -> None:
        """Matching is case-sensitive."""
        assert substitute(RungSpec("motor1 Motor1 MOTOR1"), {"Motor1": "M"}).text == (
            "motor1 M MOTOR1"
        )

    def test_empty_mapping_copies(self) -> None:
        """An empty mapping returns an equal but separate copy."""
        spec = _motor()
        result = substitute(spec, {})
        assert result == spec
        assert result is not spec
        assert result.tags is not spec.tags

    def test_input_unchanged(self) -> None:
        """The input spec is never modified."""
        spec = _motor()
        before = copy.deepcopy(spec)
        result = substitute(spec, {"M1_": "M7_", "Motor1": "Motor7"})
        assert spec == before
        result.tags[0].name = "changed"
        result.routines[0].rungs[0].text = "changed"
        assert spec == before

    def test_nested_aoi_spec(self) -> None:
        """AOI parameters, locals, routines and rungs are all reached."""
        spec = AOISpec(
            "Valve1",
            [
                ParameterSpec(
                    "V1_Cmd", "BOOL", description="Valve1 command", default=None
                )
            ],
            routines=[
                RoutineSpec("Logic", rungs=[RungSpec("XIC(V1_Cmd)NOP();", "V1_ note")])
            ],
            revision_note="for V1_",
            metadata={"EditedBy": "V1_user"},
        )
        result = substitute(spec, {"Valve1": "Valve9", "V1_": "V9_"})
        assert result.name == "Valve9"
        assert result.parameters[0].name == "V9_Cmd"
        assert result.parameters[0].description == "Valve9 command"
        assert result.routines[0].rungs[0].text == "XIC(V9_Cmd)NOP();"
        assert result.routines[0].rungs[0].comment == "V9_ note"
        assert result.revision_note == "for V9_"
        assert result.metadata == {"EditedBy": "V9_user"}

    def test_other_specs(self) -> None:
        """DataTypeSpec, TagSpec and RoutineSpec work too, and via the method."""
        udt = DataTypeSpec("M1_Type", [MemberSpec("M1_a", "M1_Other")])
        result = udt.substitute({"M1_": "M2_"})
        assert (result.name, result.members[0].name, result.members[0].data_type) == (
            "M2_Type",
            "M2_a",
            "M2_Other",
        )
        tag = TagSpec(
            "t", "DINT", value=[1, 2], operand_metadata={".M1_x": {"min": "M1_"}}
        )
        assert tag.substitute({"M1_": "M2_"}).operand_metadata == {
            ".M1_x": {"min": "M2_"}
        }
        keyed = tag.substitute({"M1_": "M2_"}, keys=True)
        assert keyed.operand_metadata == {".M2_x": {"min": "M2_"}}
        routine = RoutineSpec("R", "ST", lines=["M1_a := 1;"])
        assert routine.substitute({"M1_": "M2_"}).lines == ["M2_a := 1;"]

    def test_tuple_dimensions_survive(self) -> None:
        """Tuples are rebuilt as tuples."""
        spec = TagSpec("t", "DINT", dimensions=(2, 3))
        assert substitute(spec, {"t": "u"}).dimensions == (2, 3)

    def test_json_round_trip(self) -> None:
        """A substituted spec survives JSON."""
        spec = substitute(_motor(), {"Motor1": "Motor7", "M1_": "M7_"})
        data = json.loads(json.dumps(spec.to_dict()))
        assert ProgramSpec.from_dict(data) == spec

    @pytest.mark.parametrize(
        "mapping", [{"Motor1": "7Motor"}, {"Motor1": "Mo__tor"}, {"Motor1": ""}]
    )
    def test_invalid_resulting_name_raises(self, mapping: dict) -> None:
        """A top-level name that becomes invalid fails early."""
        with pytest.raises(ValueError):
            substitute(_motor(), mapping)

    def test_inner_invalid_names_surface_at_build(self) -> None:
        """Invalid inner names are only caught when the spec is built."""
        spec = substitute(_motor(), {"M1_": "7_"})
        assert spec.tags[0].name == "7_RUN"
        project = load(str(FIXTURES / "example.L5X"))
        with pytest.raises(ValueError):
            build_program(spec, project._type_registry)

    def test_bad_arguments(self) -> None:
        """Empty keys, non-string mappings and non-specs are rejected."""
        with pytest.raises(ValueError, match="empty"):
            substitute(_motor(), {"": "x"})
        with pytest.raises(TypeError):
            substitute(_motor(), {"a": 1})
        with pytest.raises(TypeError):
            substitute("text", {"a": "b"})

    def test_colliding_dict_keys_raise(self) -> None:
        """With keys=True, equal keys raise instead of losing data."""
        spec = TagSpec("t", "DINT", operand_comments={".A": "x", ".B": "y"})
        with pytest.raises(ValueError, match="two keys equal"):
            substitute(spec, {"A": "Z", "B": "Z"}, keys=True)
        result = substitute(spec, {"A": "Z", "B": "Z"})
        assert result.operand_comments == {".A": "x", ".B": "y"}


def base_comments(spec: ProgramSpec, tag: str) -> dict[str, str]:
    """Return a tag's operand comments from a program spec.

    Args:
        spec: The program spec.
        tag: The tag name.

    Returns:
        The tag's ``operand_comments``.
    """
    return next(t for t in spec.tags if t.name == tag).operand_comments or {}


class TestExampleProgram:
    """Templating a loaded program."""

    def test_main_program(self) -> None:
        """A broad prefix mapping builds and adds three copies of MainProgram."""
        project = load(str(FIXTURES / "example.L5X"))
        base = project.programs["MainProgram"].to_spec()
        copies = []
        for index in (1, 2, 3):
            mapping = {"MainProgram": f"Line{index}", "a_": f"m{index}_"}
            spec = substitute(base, mapping)
            copies.append(spec)
            assert spec.name == f"Line{index}"
            names = {t.name for t in spec.tags}
            assert {f"m{index}_dint", f"m{index}_timer"} <= names
            assert "a_dint" not in names
            built = build_program(spec, project._type_registry)
            assert built.get("Name") == f"Line{index}"
            project.programs.add(spec)
        assert len({s.name for s in copies}) == 3
        again = project.programs["Line2"]
        assert again.tags["m2_timer"].data_type == "TIMER"
        # UDT member names inside values (dict keys) are untouched.
        assert "a_Bool" in again.tags["m2_udt_instance"].to_python()
        assert again.tags["m2_commented_dint"].operand_comments == (
            base_comments(base, "a_commented_dint")
        )
        before = [
            r.text
            for r in project.programs["MainProgram"].routines["MainRoutine"].rungs
        ]
        after = [r.text for r in again.routines["MainRoutine"].rungs]
        assert after == [t.replace("a_", "m2_") for t in before]
        assert "MainProgram" in list(project.programs)
        reloaded = loads(project.to_string()).programs["Line3"]
        assert reloaded.tags["m3_dint"] is not None

    def test_descriptions_and_st(self) -> None:
        """Descriptions and ST lines change with the tag names."""
        project = load(str(FIXTURES / "example.L5X"))
        # The protected routine and the tag of the protected AOI type have no
        # spec; drop them so the program's ST routine can still be templated.
        element = project.programs["AnotherProgram"]._element
        routines = element.find("Routines")
        for encoded in routines.findall("EncodedData"):
            routines.remove(encoded)
        tags = element.find("Tags")
        for tag in tags.findall("Tag"):
            if tag.get("DataType") == "SeqCtrl_Protected":
                tags.remove(tag)
        spec = project.programs["AnotherProgram"].to_spec()
        st = next(r for r in spec.routines if r.type_ == "ST")
        source = next(line for line in st.lines if "i" in line)
        result = substitute(spec, {"AnotherProgram": "Other2"})
        assert result.name == "Other2"
        again = substitute(spec, {"j": "jj"})
        st_after = next(r for r in again.routines if r.type_ == "ST")
        assert [line.replace("j", "jj") for line in st.lines] == st_after.lines
        assert source in st.lines


class TestStamp:
    """stamp."""

    def test_ten_instances(self, tmp_path: Path) -> None:
        """Ten copies get distinct names, are all added, and survive a file."""
        project = load(str(FIXTURES / "example.L5X"))
        instances = [{"Motor1": f"Motor{n}", "M1_": f"M{n}_"} for n in range(10, 20)]
        specs = stamp(_motor(), instances)
        assert [s.name for s in specs] == [f"Motor{n}" for n in range(10, 20)]
        assert len({s.name for s in specs}) == 10
        for spec in specs:
            project.programs.add(spec)
        names = list(project.programs)
        assert names == sorted(names, key=str.lower)
        path = tmp_path / "stamped.L5X"
        project.write(path)
        again = load(str(path))
        for n in range(10, 20):
            program = again.programs[f"Motor{n}"]
            assert program.tags[f"M{n}_SPEED"].value == 100
            assert program.tags[f"M{n}_NAME"].value == f"Motor{n}"
            assert program.routines[f"M{n}_Main"].rungs[0].text == (
                f"XIC(M{n}_RUN)MOV(M{n}_SPEED,M{n}_SPEED);"
            )
        assert loads(project.to_string()).programs["Motor19"].description == (
            "Program for Motor19"
        )

    def test_empty_and_generator(self) -> None:
        """stamp accepts any iterable, including an empty one."""
        assert stamp(_motor(), []) == []
        specs = stamp(_motor(), ({"Motor1": f"Pump{n}"} for n in range(2)))
        assert [s.name for s in specs] == ["Pump0", "Pump1"]

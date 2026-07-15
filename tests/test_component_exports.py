"""Tests for loading component-level L5X exports (Phase 4).

Studio 5000 can export individual project components (a single Program,
Routine, AOI, DataType, Module, Rung, or Tag) rather than an entire project.
These files share the same ``<RSLogix5000Content>`` envelope used by full
project exports but set ``ContainsContext="true"`` and mark exactly one child
element with ``Use="Target"``.

These tests verify:
- Each fixture loads via ``load()`` without raising.
- ``project.target_type`` / ``project.target_name`` match the file header.
- ``project.contains_context`` is ``True`` for component exports and ``False``
  for full project exports.
- ``project.target`` returns the correct typed wrapper for each fixture.
- ``project.controller.is_context`` is ``True`` for component exports.
- Context controller metadata properties (processor_type, etc.) return ``None``.
- ``repr(project)`` includes a ``Target:`` line for component exports.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from py_l5x import load
from py_l5x.parsers.aoi import AOIDefinition
from py_l5x.parsers.datatype import DataType
from py_l5x.parsers.module import Module
from py_l5x.parsers.program import Program
from py_l5x.parsers.project import Project
from py_l5x.parsers.routine import Routine, Rung

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def udt_project() -> Project:
    return load(str(FIXTURES / "A_UDT_DataType.L5X"))


@pytest.fixture(scope="module")
def string_udt_project() -> Project:
    return load(str(FIXTURES / "robotAlarmCode_DataType_String.L5X"))


@pytest.fixture(scope="module")
def aoi_project() -> Project:
    return load(str(FIXTURES / "Debounce_AOI.L5X"))


@pytest.fixture(scope="module")
def module_project() -> Project:
    return load(str(FIXTURES / "ShopRobot_Module.L5X"))


@pytest.fixture(scope="module")
def program_project() -> Project:
    return load(str(FIXTURES / "MainProgram_Program.L5X"))


@pytest.fixture(scope="module")
def routine_project() -> Project:
    return load(str(FIXTURES / "SequenceRoutine_Routine_RLL.L5X"))


@pytest.fixture(scope="module")
def rung_project() -> Project:
    return load(str(FIXTURES / "Rung2_from_SequenceRoutine.L5X"))


@pytest.fixture(scope="module")
def full_project() -> Project:
    return load(str(FIXTURES / "example.L5X"))


# ---------------------------------------------------------------------------
# Load smoke-tests
# ---------------------------------------------------------------------------


class TestComponentLoading:
    """Each component fixture loads without raising."""

    @pytest.mark.parametrize(
        "filename",
        [
            "A_UDT_DataType.L5X",
            "robotAlarmCode_DataType_String.L5X",
            "Debounce_AOI.L5X",
            "ShopRobot_Module.L5X",
            "MainProgram_Program.L5X",
            "SequenceRoutine_Routine_RLL.L5X",
            "Rung2_from_SequenceRoutine.L5X",
        ],
    )
    def test_load_succeeds(self, filename: str) -> None:
        p = load(str(FIXTURES / filename))
        assert isinstance(p, Project)


# ---------------------------------------------------------------------------
# target_type / target_name / contains_context
# ---------------------------------------------------------------------------


class TestTargetAttributes:
    """target_type, target_name, and contains_context from the XML header."""

    def test_udt_target_type(self, udt_project: Project) -> None:
        assert udt_project.target_type == "DataType"

    def test_udt_target_name(self, udt_project: Project) -> None:
        assert udt_project.target_name == "A_UDT"

    def test_string_udt_target_type(self, string_udt_project: Project) -> None:
        assert string_udt_project.target_type == "DataType"

    def test_string_udt_target_name(self, string_udt_project: Project) -> None:
        assert string_udt_project.target_name == "robotAlarmCode"

    def test_aoi_target_type(self, aoi_project: Project) -> None:
        assert aoi_project.target_type == "AddOnInstructionDefinition"

    def test_aoi_target_name(self, aoi_project: Project) -> None:
        assert aoi_project.target_name == "Debounce"

    def test_module_target_type(self, module_project: Project) -> None:
        assert module_project.target_type == "Module"

    def test_module_target_name(self, module_project: Project) -> None:
        assert module_project.target_name == "ShopRobot"

    def test_program_target_type(self, program_project: Project) -> None:
        assert program_project.target_type == "Program"

    def test_program_target_name(self, program_project: Project) -> None:
        assert program_project.target_name == "MainProgram"

    def test_routine_target_type(self, routine_project: Project) -> None:
        assert routine_project.target_type == "Routine"

    def test_routine_target_name(self, routine_project: Project) -> None:
        assert routine_project.target_name == "SequenceRoutine"

    def test_rung_target_type(self, rung_project: Project) -> None:
        assert rung_project.target_type == "Rung"

    def test_rung_has_no_target_name(self, rung_project: Project) -> None:
        # Rung-level exports have no TargetName in the file header.
        assert rung_project.target_name == ""

    def test_full_project_target_type(self, full_project: Project) -> None:
        assert full_project.target_type == "Controller"

    def test_full_project_target_name(self, full_project: Project) -> None:
        assert full_project.target_name == "Example_PLC"

    # contains_context

    def test_component_exports_contain_context(
        self, udt_project: Project, aoi_project: Project, program_project: Project
    ) -> None:
        assert udt_project.contains_context is True
        assert aoi_project.contains_context is True
        assert program_project.contains_context is True

    def test_full_project_no_context(self, full_project: Project) -> None:
        assert full_project.contains_context is False


# ---------------------------------------------------------------------------
# project.target dispatch
# ---------------------------------------------------------------------------


class TestTargetDispatch:
    """project.target returns the correct typed wrapper."""

    def test_udt_target_is_datatype(self, udt_project: Project) -> None:
        assert isinstance(udt_project.target, DataType)

    def test_udt_target_name(self, udt_project: Project) -> None:
        assert udt_project.target.name == "A_UDT"  # type: ignore[union-attr]

    def test_string_udt_target_is_datatype(self, string_udt_project: Project) -> None:
        assert isinstance(string_udt_project.target, DataType)

    def test_string_udt_target_name(self, string_udt_project: Project) -> None:
        assert string_udt_project.target.name == "robotAlarmCode"  # type: ignore[union-attr]

    def test_aoi_target_is_aoidefinition(self, aoi_project: Project) -> None:
        assert isinstance(aoi_project.target, AOIDefinition)

    def test_aoi_target_name(self, aoi_project: Project) -> None:
        assert aoi_project.target.name == "Debounce"  # type: ignore[union-attr]

    def test_module_target_is_module(self, module_project: Project) -> None:
        assert isinstance(module_project.target, Module)

    def test_module_target_name(self, module_project: Project) -> None:
        assert module_project.target.name == "ShopRobot"  # type: ignore[union-attr]

    def test_program_target_is_program(self, program_project: Project) -> None:
        assert isinstance(program_project.target, Program)

    def test_program_target_name(self, program_project: Project) -> None:
        assert program_project.target.name == "MainProgram"  # type: ignore[union-attr]

    def test_routine_target_is_routine(self, routine_project: Project) -> None:
        assert isinstance(routine_project.target, Routine)

    def test_routine_target_name(self, routine_project: Project) -> None:
        assert routine_project.target.name == "SequenceRoutine"  # type: ignore[union-attr]

    def test_routine_target_use(self, routine_project: Project) -> None:
        assert routine_project.target.use == "Target"  # type: ignore[union-attr]

    def test_rung_target_is_rung(self, rung_project: Project) -> None:
        assert isinstance(rung_project.target, Rung)

    def test_rung_target_number(self, rung_project: Project) -> None:
        assert rung_project.target.number == 2  # type: ignore[union-attr]

    def test_rung_target_use(self, rung_project: Project) -> None:
        assert rung_project.target.use == "Target"  # type: ignore[union-attr]

    def test_full_project_target_is_none(self, full_project: Project) -> None:
        assert full_project.target is None


# ---------------------------------------------------------------------------
# ControllerInfo.is_context
# ---------------------------------------------------------------------------


class TestControllerIsContext:
    """is_context flag and None-returning metadata for context controllers."""

    def test_component_controller_is_context(
        self, udt_project: Project, aoi_project: Project
    ) -> None:
        assert udt_project.controller.is_context is True
        assert aoi_project.controller.is_context is True

    def test_full_project_controller_not_context(self, full_project: Project) -> None:
        assert full_project.controller.is_context is False

    def test_context_processor_type_is_none(self, udt_project: Project) -> None:
        assert udt_project.controller.processor_type is None

    def test_context_major_rev_is_none(self, udt_project: Project) -> None:
        assert udt_project.controller.major_rev is None

    def test_context_minor_rev_is_none(self, udt_project: Project) -> None:
        assert udt_project.controller.minor_rev is None

    def test_context_project_creation_date_is_none(self, udt_project: Project) -> None:
        assert udt_project.controller.project_creation_date is None

    def test_context_last_modified_date_is_none(self, udt_project: Project) -> None:
        assert udt_project.controller.last_modified_date is None

    def test_context_project_sn_is_none(self, udt_project: Project) -> None:
        assert udt_project.controller.project_sn is None

    def test_full_project_metadata_not_none(self, full_project: Project) -> None:
        assert full_project.controller.processor_type is not None
        assert full_project.controller.major_rev is not None
        assert full_project.controller.last_modified_date is not None


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------


class TestProjectRepr:
    """repr(project) includes a Target: line describing the exported object."""

    def test_component_repr_contains_target_line(self, udt_project: Project) -> None:
        assert "Target:" in repr(udt_project)

    def test_component_repr_contains_target_type(self, udt_project: Project) -> None:
        assert "DataType" in repr(udt_project)

    def test_component_repr_contains_target_name(self, udt_project: Project) -> None:
        assert "A_UDT" in repr(udt_project)

    def test_full_project_repr_contains_full_project(
        self, full_project: Project
    ) -> None:
        assert "Full project" in repr(full_project)

    def test_full_project_repr_contains_processor(self, full_project: Project) -> None:
        assert "5069-L310ERMS3" in repr(full_project)

    def test_rung_repr_contains_rung_number(self, rung_project: Project) -> None:
        assert "number=2" in repr(rung_project)

    def test_program_repr_target_line(self, program_project: Project) -> None:
        r = repr(program_project)
        assert "Program" in r
        assert "MainProgram" in r

    def test_routine_repr_target_line(self, routine_project: Project) -> None:
        r = repr(routine_project)
        assert "Routine" in r
        assert "SequenceRoutine" in r


# ---------------------------------------------------------------------------
# Program fixture — content reachable through collection API
# ---------------------------------------------------------------------------


class TestProgramFixtureContent:
    """Verify the program fixture's contents are reachable via collections."""

    def test_program_in_programs(self, program_project: Project) -> None:
        assert "MainProgram" in program_project.programs

    def test_program_has_routines(self, program_project: Project) -> None:
        prog = program_project.programs["MainProgram"]
        assert len(prog.routines) > 0

    def test_sequence_routine_reachable(self, program_project: Project) -> None:
        routine = program_project.programs["MainProgram"].routines["SequenceRoutine"]
        assert isinstance(routine, Routine)
        assert routine.type_ == "RLL"

    def test_program_use_attribute(self, program_project: Project) -> None:
        prog = program_project.programs["MainProgram"]
        assert prog.use == "Target"


# ---------------------------------------------------------------------------
# Routine fixture — Use attr and target_rung
# ---------------------------------------------------------------------------


class TestRoutineFixtureContent:
    """Routine-level export exposes use and target_rung correctly."""

    def test_routine_use_attribute(self, routine_project: Project) -> None:
        routine = routine_project.programs["MainProgram"].routines["SequenceRoutine"]
        assert routine.use == "Target"

    def test_routine_has_rungs(self, routine_project: Project) -> None:
        routine = routine_project.programs["MainProgram"].routines["SequenceRoutine"]
        assert len(routine.rungs) > 0

    def test_target_rung_is_none_for_full_routine(
        self, routine_project: Project
    ) -> None:
        # Routine-level export: no rung carries Use="Target", only the routine
        # itself is the target.
        routine = routine_project.programs["MainProgram"].routines["SequenceRoutine"]
        assert routine.target_rung is None


# ---------------------------------------------------------------------------
# Rung fixture — Rung.use and Routine.target_rung
# ---------------------------------------------------------------------------


class TestRungFixtureContent:
    """Rung-level export: target_rung finds the Use="Target" rung."""

    def test_rung_target_rung_via_routine(self, rung_project: Project) -> None:
        routine = rung_project.programs["MainProgram"].routines["SequenceRoutine"]
        rung = routine.target_rung
        assert rung is not None
        assert rung.number == 2

    def test_rung_use_attribute(self, rung_project: Project) -> None:
        routine = rung_project.programs["MainProgram"].routines["SequenceRoutine"]
        rung = routine.target_rung
        assert rung is not None
        assert rung.use == "Target"

    def test_only_one_rung_has_target_use(self, rung_project: Project) -> None:
        # A rung-level export only embeds the exported rung(s) in the routine;
        # context rungs are not included.  All embedded rungs with Use="Target"
        # should number exactly 1.
        routine = rung_project.programs["MainProgram"].routines["SequenceRoutine"]
        target_rungs = [r for r in routine.rungs if r.use == "Target"]
        assert len(target_rungs) == 1

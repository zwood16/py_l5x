"""Tests for py_l5x.parsers.project and py_l5x.parse.load()."""

from __future__ import annotations

from pathlib import Path

import pytest

from py_l5x import load
from py_l5x.parsers.module import ModuleTagRef
from py_l5x.parsers.project import Project, ProjectTagsView
from py_l5x.parsers.tag import StructNode, Tag

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLE_L5X = FIXTURES_DIR / "example.L5X"


@pytest.fixture
def project() -> Project:
    """Load the example L5X file as a Project."""
    return load(str(EXAMPLE_L5X))


# ---------------------------------------------------------------------------
# Basic loading
# ---------------------------------------------------------------------------


class TestLoad:
    """Tests for the public load() function."""

    def test_load_returns_project(self, project: Project) -> None:
        """load() returns a Project instance."""
        assert isinstance(project, Project)

    def test_load_with_path_object(self) -> None:
        """load() accepts a pathlib.Path."""
        p = load(EXAMPLE_L5X)
        assert isinstance(p, Project)

    def test_load_missing_file_raises(self) -> None:
        """load() raises FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            load("nonexistent_file.L5X")

    def test_load_non_l5x_raises(self, tmp_path: Path) -> None:
        """load() raises ValueError for non-L5X XML files."""
        bad_file = tmp_path / "bad.xml"
        bad_file.write_text("<root><not_l5x/></root>")
        with pytest.raises(ValueError, match="not a valid L5X file"):
            load(str(bad_file))


# ---------------------------------------------------------------------------
# Project structure
# ---------------------------------------------------------------------------


class TestProjectStructure:
    """Tests for Project property access."""

    def test_controller(self, project: Project) -> None:
        """project.controller returns ControllerInfo."""
        assert project.controller.name == "Example_PLC"
        assert project.controller.processor_type == "5069-L310ERMS3"

    def test_root_element(self, project: Project) -> None:
        """project.root is the RSLogix5000Content element."""
        assert project.root.tag == "RSLogix5000Content"

    def test_controller_element(self, project: Project) -> None:
        """project.controller_element is the Controller element."""
        assert project.controller_element.tag == "Controller"

    def test_data_types_populated(self, project: Project) -> None:
        """project.data_types contains UDTs from the fixture."""
        names = list(project.data_types)
        assert "A_UDT" in names
        assert "GenericRobotInputs" in names

    def test_modules_populated(self, project: Project) -> None:
        """project.modules contains modules from the fixture."""
        names = list(project.modules)
        assert len(names) > 0

    def test_aois_populated(self, project: Project) -> None:
        """project.aois contains AOI definitions from the fixture."""
        names = list(project.aois)
        assert len(names) > 0

    def test_controller_tags_populated(self, project: Project) -> None:
        """project.tags contains controller-level tags."""
        names = list(project.tags)
        assert len(names) > 0

    def test_programs_populated(self, project: Project) -> None:
        """project.programs contains programs from the fixture."""
        names = list(project.programs)
        assert len(names) > 0

    def test_tasks_populated(self, project: Project) -> None:
        """project.tasks contains tasks from the fixture."""
        names = list(project.tasks)
        assert len(names) > 0


# ---------------------------------------------------------------------------
# Hierarchical drill-down
# ---------------------------------------------------------------------------


class TestHierarchicalAccess:
    """Tests for navigating the project hierarchy."""

    def test_task_programs(self, project: Project) -> None:
        """Tasks expose scheduled programs via task.programs."""
        for task in project.tasks.values():
            # Each task should have at least the programs mapping accessible
            assert hasattr(task, "programs")
            assert len(task.programs) >= 0

    def test_task_program_tags(self, project: Project) -> None:
        """Programs accessed via tasks expose their local tags."""
        for task in project.tasks.values():
            for prog in task.programs.values():
                assert hasattr(prog, "tags")
                assert hasattr(prog, "routines")

    def test_program_routines(self, project: Project) -> None:
        """Programs have accessible routines."""
        for prog in project.programs.values():
            routines = list(prog.routines)
            assert len(routines) >= 0

    def test_direct_program_access(self, project: Project) -> None:
        """Programs are accessible directly from project.programs."""
        prog_names = list(project.programs)
        for name in prog_names:
            prog = project.programs[name]
            assert prog.name == name

    def test_module_communications(self, project: Project) -> None:
        """Modules expose communications data when present."""
        for module in project.modules.values():
            assert hasattr(module, "communications")
            assert hasattr(module, "ports")


# ---------------------------------------------------------------------------
# TypeRegistry wiring
# ---------------------------------------------------------------------------


class TestTypeRegistry:
    """Tests that TypeRegistry is correctly wired through the project."""

    def test_udt_tag_value_resolution(self, project: Project) -> None:
        """Tags using UDT types can drill into members."""
        # Find a tag that uses a UDT type and verify member access works
        for tag in project.tags.values():
            if tag is not None and isinstance(tag, StructNode):
                # Should be able to iterate members without error
                members = list(tag.members)
                assert isinstance(members, list)
                break

    def test_program_tag_value_resolution(self, project: Project) -> None:
        """Program tags can resolve their value tree."""
        for prog in project.programs.values():
            for tag in prog.tags.values():
                if tag is not None and hasattr(tag, "value"):
                    # Just verify access doesn't raise for value tags
                    _ = tag.value
                    break


# ---------------------------------------------------------------------------
# Merged global tag view (controller tags + module I/O tags)
# ---------------------------------------------------------------------------


class TestMergedTagsView:
    """Tests that project.tags merges controller and module I/O tags."""

    def test_tags_view_type(self, project: Project) -> None:
        """project.tags returns a ProjectTagsView."""
        assert isinstance(project.tags, ProjectTagsView)

    def test_module_tag_resolves_by_global_name(self, project: Project) -> None:
        """A module I/O tag resolves under its Studio 5000 global name."""
        ref = project.tags["ValveBank:I"]
        assert isinstance(ref, ModuleTagRef)
        assert ref.members["ConnectionFaulted"].value is False

    def test_local_backplane_module_tag_resolves(self, project: Project) -> None:
        """A local backplane module tag resolves under Local:<pos>:<suffix>."""
        ref = project.tags["Local:1:I"]
        assert isinstance(ref, ModuleTagRef)
        assert ref.module_name == "Test_Input_Module"

    def test_controller_tags_still_resolve(self, project: Project) -> None:
        """Controller tags keep resolving to Tag instances (not refs)."""
        for name in ("message_tag", "consumed_tag", "produced_tag"):
            tag = project.tags[name]
            assert isinstance(tag, Tag)
            assert not isinstance(tag, ModuleTagRef)

    def test_controller_tags_unchanged_names(self, project: Project) -> None:
        """Every controller tag name is still present in the merged view."""
        controller_names = set(project._tags)
        merged_names = set(project.tags)
        assert controller_names <= merged_names

    def test_module_tag_names_added(self, project: Project) -> None:
        """Module I/O global names are added to the merged view."""
        expected = {
            "ValveBank:I",
            "ValveBank:O",
            "ShopRobot:C",
            "Local:1:C",
            "Local:2:I",
            "Test_Servo_Drive:S",
        }
        merged_names = set(project.tags)
        assert expected <= merged_names

    def test_len_matches_iteration(self, project: Project) -> None:
        """len(project.tags) equals the number of names yielded by iteration."""
        assert len(project.tags) == len(list(project.tags))

    def test_controller_tag_names_have_no_colon(self, project: Project) -> None:
        """Controller tag names never contain ':' (so they cannot collide)."""
        for name in project._tags:
            assert ":" not in name

    def test_unknown_module_style_name_raises_key_error(self, project: Project) -> None:
        """A colon-qualified name with no matching module tag raises KeyError."""
        with pytest.raises(KeyError):
            project.tags["no_such:I"]

    def test_contains_uses_mapping_default(self, project: Project) -> None:
        """Membership follows the Mapping default (lookup succeeds or KeyError)."""
        assert "ValveBank:I" in project.tags
        assert "message_tag" in project.tags
        assert "no_such_tag" not in project.tags

    def test_module_tag_names_exactly_expected(self, project: Project) -> None:
        """The colon-qualified names are exactly the 32 expected module I/O tags."""
        expected = {
            "ValveBank:I",
            "ValveBank:O",
            "Test_Servo_Drive:S",
            "Test_Servo_Drive:SI",
            "Test_Servo_Drive:SO",
            "Local:1:C",
            "Local:1:I",
            "Local:2:I",
            "Local:3:C",
            "Local:3:EI",
            "Local:3:EO",
            "Local:3:I",
            "Local:3:O",
            "PointIO:1:C",
            "PointIO:2:C",
            "PointIO:3:C",
            "PointIO:3:I",
            "PointIO:4:C",
            "PointIO:4:I",
            "PointIO:4:O",
            "PointIO:5:I",
            "PointIO:5:O",
            "PointIO:6:I",
            "PointIO:6:O",
            "PointIO:I",
            "PointIO:O",
            "Compact5000_IO_Adapter:1:C",
            "Compact5000_IO_Adapter:1:I",
            "Compact5000_IO_Adapter:1:O",
            "ShopRobot:C",
            "ShopRobot:I",
            "ShopRobot:O",
        }
        colon_names = [name for name in project.tags if ":" in name]
        assert len(colon_names) == 32
        assert set(colon_names) == expected

    def test_len_includes_module_tags(self, project: Project) -> None:
        """len(project.tags) is the controller tag count plus 32 module I/O tags."""
        controller_count = len(project._tags)
        assert len(project.tags) == controller_count + 32

    @pytest.mark.parametrize(
        ("name", "module_name"),
        [
            ("PointIO:I", "PointIO"),
            ("PointIO:O", "PointIO"),
            ("PointIO:3:I", "PointIO_AnalogInput"),
            ("Compact5000_IO_Adapter:1:O", "Remote_Output"),
            ("Local:3:EI", "Fast_Local_Input"),
        ],
    )
    def test_new_module_prefixes_resolve(
        self, project: Project, name: str, module_name: str
    ) -> None:
        """Point I/O, Compact 5000, and local 5069 tags resolve to their module."""
        ref = project.tags[name]
        assert isinstance(ref, ModuleTagRef)
        assert ref.module_name == module_name

    @pytest.mark.parametrize(
        "name",
        ["PointIO:7:I", "Compact5000_IO_Adapter:I", "Local:3:X"],
    )
    def test_near_miss_module_names_raise_key_error(
        self, project: Project, name: str
    ) -> None:
        """Near-miss module tag names (no such slot/suffix) raise KeyError."""
        with pytest.raises(KeyError):
            project.tags[name]


# ---------------------------------------------------------------------------
# Representation
# ---------------------------------------------------------------------------


class TestRepr:
    """Tests for __repr__ output."""

    def test_project_repr(self, project: Project) -> None:
        """Project repr contains controller name and counts."""
        repr_str = repr(project)
        assert "Example_PLC" in repr_str
        assert "Data Types:" in repr_str
        assert "Modules:" in repr_str
        assert "Tasks:" in repr_str

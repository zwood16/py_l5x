"""Tests for source-protected (``<EncodedData>``) AOIs and routines.

Uses the real Studio v37 export ``example.L5X``: AOI ``SeqCtrl_Protected`` (an
``EncodedData`` with attributes, ``RevisionNote``, 34 full ``Parameters`` and the
payload as text after ``</Parameters>``), program ``AnotherProgram`` with tag
``seqCtrl_Protected_Instance`` of that type, a call to it, and the encoded
routine ``SequenceRoutine_Protected``. Optional children that the real data does
not carry (``Description``, ``Dependencies``, ``Vendor``) are checked on small
inline snippets and on edited copies of the loaded project.
"""

import re
import warnings
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x import (
    Project,
    ProtectedAOI,
    ProtectedContentWarning,
    ProtectedRoutine,
    export_component,
    load,
    loads,
)
from py_l5x.writer import to_bytes

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE = FIXTURES / "example.L5X"
AOI = "SeqCtrl_Protected"
ROUTINE = "SequenceRoutine_Protected"
INSTANCE = "seqCtrl_Protected_Instance"


@pytest.fixture
def project() -> Project:
    """Load the example project.

    Returns:
        The parsed project.
    """
    return load(str(EXAMPLE))


def _export(target, project: Project):
    """Export with warnings recorded.

    Args:
        target: The export target.
        project: The source project.

    Returns:
        ``(exported project, recorded ProtectedContentWarning messages)``.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = export_component(target, project)
    messages = [
        str(w.message)
        for w in caught
        if issubclass(w.category, ProtectedContentWarning)
    ]
    return out, messages


def _aoi_children(exported: Project) -> list[tuple[str, str]]:
    """List the AOI container's children as ``(tag, name)``.

    Args:
        exported: An exported project.

    Returns:
        One pair per child of ``AddOnInstructionDefinitions``.
    """
    container = exported.controller_element.find("AddOnInstructionDefinitions")
    return [] if container is None else [(e.tag, e.get("Name")) for e in container]


def _snippet(xml: str) -> ProtectedAOI:
    """Wrap an inline ``EncodedData`` element.

    Args:
        xml: The element text.

    Returns:
        The wrapper (no registry).
    """
    return ProtectedAOI(ET.fromstring(xml))


class TestParsing:
    """The AOI wrapper and collection."""

    def test_collection(self, project: Project) -> None:
        """The encoded AOI is listed; definitions stay separate."""
        assert list(project.protected_aois) == [AOI]
        assert AOI not in project.aois
        assert "SeqCtrl" in project.aois
        assert "Protected AOIs: 1" in str(project)

    def test_fields(self, project: Project) -> None:
        """Attributes of the real element."""
        aoi = project.protected_aois[AOI]
        assert isinstance(aoi, ProtectedAOI)
        assert aoi.name == AOI
        assert aoi.encoded_type == "AddOnInstructionDefinition"
        assert aoi.class_ == "Standard"
        assert aoi.revision == "3.3"
        assert aoi.signature_id == "38ADB3F7"
        assert aoi.signature_timestamp == "2026-11-22T05:35:29.637Z"
        assert aoi.edited_date == "2026-11-22T05:35:29.637Z"
        assert aoi.software_revision == "v37.00"
        assert aoi.encryption_config == "9"
        assert aoi.revision_note.startswith("v3.3 Fixed bug")
        assert aoi.vendor is None
        assert aoi.description == ""
        assert aoi.dependency_names == []
        assert "SeqCtrl_Protected" in aoi.describe()

    def test_parameters(self, project: Project) -> None:
        """Parameters are the normal parameter wrappers."""
        params = project.protected_aois[AOI].parameters
        assert len(params) == 34
        assert list(params)[:3] == ["EnableIn", "EnableOut", "mode"]
        mode = params["mode"]
        assert mode.data_type == "BOOL"
        assert mode.usage == "Input"
        assert mode.required
        assert mode.visible
        assert mode.description == (
            "System Mode. 0 = Manual (enable HMI). 1 = Auto (disable HMI)"
        )
        assert all(not p.is_inout for p in params.datatype_members.values())

    def test_matches_unprotected_copy(self, project: Project) -> None:
        """The protected copy lists the same parameters as SeqCtrl."""
        plain = project.aois["SeqCtrl"].parameters
        protected = project.protected_aois[AOI].parameters
        assert list(protected) == list(plain)

    def test_optional_children(self) -> None:
        """Description, Vendor and Dependencies are read when present."""
        aoi = _snippet(
            '<EncodedData EncodedType="AddOnInstructionDefinition" Name="X" '
            'Vendor="V"><Description><CDataContent>hi</CDataContent></Description>'
            '<Dependencies><Dependency Type="DataType" Name="A"/>'
            '<Dependency Type="AddOnInstructionDefinition" Name="B"/>'
            "</Dependencies>payload</EncodedData>"
        )
        assert aoi.vendor == "V"
        assert aoi.description == "hi"
        assert aoi.dependency_names == ["A", "B"]
        assert len(aoi.parameters) == 0

    def test_bare_element(self) -> None:
        """Only Name and EncodedType are required."""
        aoi = _snippet(
            '<EncodedData EncodedType="AddOnInstructionDefinition" Name="X">p'
            "</EncodedData>"
        )
        assert aoi.revision is None
        assert aoi.class_ is None
        assert aoi.signature_id is None
        assert aoi.revision_note == ""
        assert len(aoi.parameters) == 0

    def test_other_encoded_types_ignored(self) -> None:
        """EncodedData of another type is not a protected AOI."""
        text = EXAMPLE.read_text(encoding="utf-8").replace(
            f'EncodedType="AddOnInstructionDefinition" Name="{AOI}"',
            f'EncodedType="DataType" Name="{AOI}"',
        )
        assert list(loads(text).protected_aois) == []


class TestRoutines:
    """Encoded routines."""

    def test_collection(self, project: Project) -> None:
        """The encoded routine is listed apart from readable routines."""
        program = project.programs["AnotherProgram"]
        assert list(program.protected_routines) == [ROUTINE]
        assert ROUTINE not in program.routines
        assert list(program.routines) == ["io", "Main", "StructuredTextRoutine"]
        assert not project.programs["MainProgram"].protected_routines

    def test_fields(self, project: Project) -> None:
        """Attributes of the real element."""
        routine = project.programs["AnotherProgram"].protected_routines[ROUTINE]
        assert isinstance(routine, ProtectedRoutine)
        assert routine.name == ROUTINE
        assert routine.encoded_type == "Routine"
        assert routine.type_ == "RLL"
        assert routine.encryption_config == "9"

    def test_name_is_taken(self, project: Project) -> None:
        """A new routine cannot reuse the name of an encoded one."""
        routines = project.programs["AnotherProgram"].routines
        with pytest.raises(ValueError):
            routines.add(ROUTINE)
        with pytest.raises(ValueError):
            routines.rename("io", ROUTINE.lower())

    def test_routine_edits_still_work(self, project: Project) -> None:
        """Edits of readable routines ignore the encoded sibling."""
        routines = project.programs["AnotherProgram"].routines
        routines.add("Extra")
        assert list(project.programs["AnotherProgram"].protected_routines) == [ROUTINE]
        routines.remove("Extra")

    def test_to_spec_refused(self, project: Project) -> None:
        """A program with an encoded routine has no spec."""
        with pytest.raises(ValueError, match="source-protected"):
            project.programs["AnotherProgram"].to_spec()

    def test_logic_text_ignores_encoded(self, project: Project) -> None:
        """Logic text lists readable routines only."""
        assert ROUTINE not in project.programs["AnotherProgram"].logic_text()


class TestRegistry:
    """TypeRegistry knowledge of protected AOIs."""

    def test_lookup(self, project: Project) -> None:
        """Protected names are known and are not definitions."""
        registry = project._type_registry
        assert registry.is_protected_aoi(AOI)
        assert registry.protected_aoi(AOI).name == AOI
        assert not registry.is_protected_aoi("SeqCtrl")
        assert registry.protected_aoi("nope") is None
        assert registry.aoi(AOI) is None
        assert AOI in registry.type_names()
        assert registry.contains_aoi(AOI)

    def test_resolve_members(self, project: Project) -> None:
        """Member definitions are the visible parameters (not InOut)."""
        registry = project._type_registry
        members = registry.resolve_members(AOI)
        assert members is not None
        assert "mode" in members
        assert list(members) == list(registry.resolve_members("SeqCtrl"))

    def test_tag_value_tree_and_metadata(self, project: Project) -> None:
        """A tag of a protected type reads as a struct, with parameter metadata."""
        tag = project.programs["AnotherProgram"].tags[INSTANCE]
        assert tag.data_type == AOI
        members = tag.members
        assert {"EnableIn", "EnableOut", "mode"} <= set(members)
        assert members["mode"].description.startswith("System Mode.")
        plain = project.programs["AnotherProgram"].tags["sequence_protected"]
        assert list(plain.members) == list(members)
        for member in members.values():
            repr(member)
        assert str(tag)

    def test_name_is_taken(self, project: Project) -> None:
        """A new AOI cannot reuse a protected name."""
        with pytest.raises(ValueError):
            project.aois._check_name(AOI)

    def test_tag_spec_refused(self, project: Project) -> None:
        """A tag of a protected type has no spec (no layout to rebuild it)."""
        with pytest.raises(ValueError, match="source-protected"):
            project.programs["AnotherProgram"].tags[INSTANCE].to_spec()


class TestUsers:
    """Edits that look at protected AOIs."""

    def test_call_sites(self, project: Project) -> None:
        """Calls of the protected AOI are found in readable logic."""
        sites = project.aois.call_sites(AOI)
        assert [(s.container, s.routine) for s in sites] == [("AnotherProgram", "Main")]

    def test_remove_aoi_missing(self, project: Project) -> None:
        """A protected AOI is not an AOI definition."""
        with pytest.raises(KeyError):
            project.aois.remove(AOI)

    def test_udt_users_lists_protected(self, project: Project) -> None:
        """Visible parameters (and dependencies) count as users of a type."""
        aoi = project.protected_aois[AOI]
        aoi._element.find("Parameters/Parameter[@Name='mode']").set("DataType", "A_UDT")
        users = project.data_types.users("A_UDT")
        assert f"protected AOI {AOI} parameter mode" in users
        with pytest.raises(ValueError, match=AOI):
            project.data_types.remove("A_UDT")

    def test_dependency_counts_as_user(self, project: Project) -> None:
        """A listed dependency counts as a user."""
        aoi = project.protected_aois[AOI]
        deps = ET.SubElement(aoi._element, "Dependencies")
        ET.SubElement(deps, "Dependency", Type="DataType", Name="A_UDT")
        assert f"protected AOI {AOI} dependency" in project.data_types.users("A_UDT")


class TestExport:
    """Component export with protected AOIs and routines."""

    def test_tag(self, project: Project) -> None:
        """A tag of the protected type brings the element, verbatim."""
        tag = project.programs["AnotherProgram"].tags[INSTANCE]
        out, messages = _export(tag, project)
        assert _aoi_children(out) == [("EncodedData", AOI)]
        assert len(messages) == 1
        assert f"AOI '{AOI}' is source-protected" in messages[0]
        assert "copied unchanged" in messages[0]
        copied = out.controller_element.find("AddOnInstructionDefinitions/EncodedData")
        original = project.protected_aois[AOI]._element
        assert copied is not original
        assert copied.attrib == original.attrib
        assert [c.tag for c in copied] == [c.tag for c in original]
        assert copied.text == original.text
        assert [(c.tag, ET.tostring(c)) for c in copied] == [
            (c.tag, ET.tostring(c)) for c in original
        ]
        assert "Use" not in copied.attrib
        assert copied.find("Dependencies") is None

    def test_routine_with_call(self, project: Project) -> None:
        """A routine calling the AOI pulls it in as context."""
        routine = project.programs["AnotherProgram"].routines["Main"]
        out, messages = _export(routine, project)
        assert ("EncodedData", AOI) in _aoi_children(out)
        assert len(messages) == 1

    def test_program_keeps_encoded_routine(self, project: Project) -> None:
        """A program export keeps the encoded routine and warns about it."""
        program = project.programs["AnotherProgram"]
        out, messages = _export(program, project)
        assert any(f"routine '{ROUTINE}' is source-protected" in m for m in messages)
        assert any(f"AOI '{AOI}'" in m for m in messages)
        assert "could not be determined" in " ".join(messages)
        exported = out.programs["AnotherProgram"]
        assert list(exported.protected_routines) == [ROUTINE]
        original = program.protected_routines[ROUTINE]._element
        copied = exported.protected_routines[ROUTINE]._element
        assert copied.text == original.text
        assert copied.attrib == original.attrib
        assert ("EncodedData", AOI) in _aoi_children(out)

    def test_dependency_order(self, project: Project) -> None:
        """Context stays in project order (definitions, then the encoded AOI)."""
        out, _ = _export(project.programs["AnotherProgram"], project)
        children = _aoi_children(out)
        assert children.index(("EncodedData", AOI)) == len(children) - 1

    def test_parameter_types_extend_closure(self, project: Project) -> None:
        """A visible parameter of a UDT type brings the UDT as context."""
        aoi = project.protected_aois[AOI]
        aoi._element.find("Parameters/Parameter[@Name='mode']").set("DataType", "A_UDT")
        tag = project.programs["AnotherProgram"].tags[INSTANCE]
        out, _ = _export(tag, project)
        assert "A_UDT" in out.data_types
        copied = out.controller_element.find("AddOnInstructionDefinitions/EncodedData")
        assert copied.find("Dependencies") is None

    def test_declared_dependencies_followed(self, project: Project) -> None:
        """Names in a visible Dependencies list extend the closure."""
        aoi = project.protected_aois[AOI]
        deps = ET.SubElement(aoi._element, "Dependencies")
        ET.SubElement(deps, "Dependency", Type="DataType", Name="A_UDT")
        ET.SubElement(deps, "Dependency", Type="DataType", Name="Unknown_Type")
        tag = project.programs["AnotherProgram"].tags[INSTANCE]
        out, _ = _export(tag, project)
        assert "A_UDT" in out.data_types

    def test_unrelated_export_has_no_warning(self, project: Project) -> None:
        """Exports that need no protected content warn about none."""
        out, messages = _export(project.data_types["A_UDT"], project)
        assert messages == []
        assert ("EncodedData", AOI) not in _aoi_children(out)

    def test_other_program_has_no_warning(self, project: Project) -> None:
        """A program without protected content exports silently."""
        _, messages = _export(project.programs["MainProgram"], project)
        assert messages == []

    def test_protected_targets_refused(self, project: Project) -> None:
        """Neither a protected AOI nor a protected routine can be a target."""
        with pytest.raises(ValueError, match="source-protected"):
            export_component(project.protected_aois[AOI], project)
        routine = project.programs["AnotherProgram"].protected_routines[ROUTINE]
        with pytest.raises(ValueError, match="source-protected"):
            export_component(routine, project)

    def test_exported_file_round_trips(self, project: Project) -> None:
        """The export serializes and reloads with the encoded elements intact."""
        out, _ = _export(project.programs["AnotherProgram"], project)
        again = loads(out.to_string())
        assert list(again.protected_aois) == [AOI]
        assert list(again.programs["AnotherProgram"].protected_routines) == [ROUTINE]


class TestRoundTrip:
    """Loading and writing keeps EncodedData byte for byte."""

    def test_bytes(self) -> None:
        """AOI (payload as tail text) and routine (text payload) are unchanged.

        The writer normalizes whitespace inside other start tags, so the
        ``EncodedData`` elements are compared, not the whole file (the
        parametrized round trip in ``test_writer`` covers the whole file).
        """
        pattern = re.compile(rb"<EncodedData.*?</EncodedData>", re.DOTALL)
        raw = pattern.findall(EXAMPLE.read_bytes())
        written = pattern.findall(to_bytes(load(str(EXAMPLE)).root))
        assert len(raw) == 2
        assert written == raw
        assert b'EncodedType="AddOnInstructionDefinition"' in raw[0]
        assert b"</Parameters>\r\n" in raw[0]
        assert b'EncodedType="Routine"' in raw[1]

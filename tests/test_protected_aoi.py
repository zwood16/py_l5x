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
    AOISpec,
    DataTypeSpec,
    MemberSpec,
    ParameterSpec,
    ProgramSpec,
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


def _decorated_values(tag) -> dict[str, str]:
    """Collect ``Name -> Value`` of the top-level Decorated members.

    Args:
        tag: A tag wrapper.

    Returns:
        The member values as written.
    """
    data = [d for d in tag.element.findall("Data") if d.get("Format") == "Decorated"]
    assert len(data) == 1
    return {
        m.get("Name"): m.get("Value")
        for m in data[0].find("Structure")
        if m.get("Name")
    }


def _formats(tag) -> list[str]:
    """List the ``Format`` of each ``<Data>`` child.

    Args:
        tag: A tag wrapper.

    Returns:
        The formats in document order.
    """
    return [d.get("Format") for d in tag.element.findall("Data")]


class TestTagValues:
    """Tags of a protected type: layout, creation, values (exp36)."""

    def test_default_layout(self, project: Project) -> None:
        """Defaults follow the parameter order; EnableIn is 1; no L5K."""
        from py_l5x.parsers.layout import default_data_element, members

        registry = project._type_registry
        infos = members(AOI, registry)
        expected = [
            p.name
            for p in registry.protected_aoi(AOI).parameters.datatype_members.values()
        ]
        assert [m.name for m in infos] == expected
        assert infos[0].name == "EnableIn"
        assert infos[0].default == "1"
        data = default_data_element(AOI, registry)
        assert data.get("Format") == "Decorated"
        names = [m.get("Name") for m in data.find("Structure")]
        assert names == expected

    def test_add_without_value(self, project: Project) -> None:
        """A tag of the protected type can be added with no data."""
        program = project.programs["AnotherProgram"]
        tag = program.tags.add("newProt", AOI)
        assert tag.data_type == AOI
        assert tag.element.find("Data") is None

    @pytest.mark.parametrize("scope", ["program", "controller"])
    def test_add_with_value(self, project: Project, scope: str) -> None:
        """A value writes Decorated data only, and survives a reload."""
        tags = (
            project.programs["AnotherProgram"].tags
            if scope == "program"
            else project.controller_tags
        )
        tag = tags.add("newProt", AOI, value={"startupStep": 4321, "mode": True})
        assert _formats(tag) == ["Decorated"]
        values = _decorated_values(tag)
        assert values["EnableIn"] == "1"
        assert values["startupStep"] == "4321"
        assert values["mode"] == "1"
        order = list(values)
        assert order == [
            p
            for p in project._type_registry.protected_aoi(
                AOI
            ).parameters.datatype_members
        ]
        reloaded = loads(to_bytes(project.root).decode("utf-8"))
        tags2 = (
            reloaded.programs["AnotherProgram"].tags
            if scope == "program"
            else reloaded.controller_tags
        )
        assert tags2["newProt"].members["startupStep"].value == 4321
        assert _formats(tags2["newProt"]) == ["Decorated"]

    def test_program_spec_allows_protected_tag(self, project: Project) -> None:
        """A program spec may hold tags of the protected type."""
        from py_l5x import TagSpec

        spec = ProgramSpec("P2", tags=[TagSpec("t", AOI, value={"startupStep": 5})])
        program = project.programs.add(spec)
        assert program.tags["t"].members["startupStep"].value == 5

    def test_set_value_keeps_l5k(self, project: Project) -> None:
        """Changing a parameter changes Decorated and keeps the L5K block (exp36)."""
        tag = project.programs["AnotherProgram"].tags[INSTANCE]
        assert "L5K" in _formats(tag)
        tag.members["startupStep"].value = 1234
        assert "L5K" in _formats(tag)
        assert _decorated_values(tag)["startupStep"] == "1234"

    def test_udt_member_message(self, project: Project) -> None:
        """A UDT member of a protected type is refused with a clear message."""
        spec = DataTypeSpec("U1", [MemberSpec("m", AOI)])
        with pytest.raises(ValueError, match="source-protected AOI, which is not"):
            project.data_types.add(spec)
        with pytest.raises(ValueError, match="member 'm': data type 'SeqCtrl_Prot"):
            project.data_types.add(spec)

    def test_aoi_parameter_message(self, project: Project) -> None:
        """An AOI parameter of a protected type is refused with a clear message."""
        spec = AOISpec("A1", [ParameterSpec("p", AOI)])
        with pytest.raises(ValueError, match="'p': data type .* source-protected AOI"):
            project.aois.add(spec)


class TestCopyData:
    """``Tag.copy_data_from``."""

    def test_copies_all_formats(self, project: Project) -> None:
        """Both Data blocks are copied with equal values, in schema order."""
        program = project.programs["AnotherProgram"]
        source = program.tags[INSTANCE]
        source.members["startupStep"].value = 777
        new = program.tags.add("clone", AOI)
        new.copy_data_from(source)
        assert _formats(new) == _formats(source) == ["L5K", "Decorated"]
        assert _decorated_values(new) == _decorated_values(source)
        assert new.members["startupStep"].value == 777
        old = source.element.find("Data")
        copy = new.element.find("Data")
        assert copy is not old
        assert ET.tostring(copy) == ET.tostring(old)

    def test_replaces_existing(self, project: Project) -> None:
        """Existing Data is replaced, not appended to."""
        program = project.programs["AnotherProgram"]
        target = program.tags.add("clone", AOI, value={"startupStep": 1})
        target.copy_data_from(program.tags[INSTANCE])
        assert _formats(target) == ["L5K", "Decorated"]

    def test_any_tag_type(self, project: Project) -> None:
        """Works for a plain DINT tag."""
        tags = project.controller_tags
        a = tags.add("cdA", "DINT", value=5)
        b = tags.add("cdB", "DINT", value=0)
        b.copy_data_from(a)
        assert b.value == 5

    def test_type_mismatch(self, project: Project) -> None:
        """Different DataType or Dimensions raise ValueError."""
        tags = project.controller_tags
        a = tags.add("cdA", "DINT", value=5)
        with pytest.raises(ValueError, match="DINT"):
            tags.add("cdB", "INT").copy_data_from(a)
        with pytest.raises(ValueError, match="dimensions"):
            tags.add("cdC", "DINT", dimensions=2, value=[1, 2]).copy_data_from(a)

    def test_no_data_source(self, project: Project) -> None:
        """A source with no Data raises ValueError."""
        tags = project.controller_tags
        empty = tags.add("cdA", "DINT")
        with pytest.raises(ValueError, match="no data"):
            tags.add("cdB", "DINT").copy_data_from(empty)

    def test_alias_refused(self, project: Project) -> None:
        """Alias tags hold no data."""
        tags = project.controller_tags
        a = tags.add("cdA", "DINT", value=5)
        alias = tags.add_alias("cdAlias", "cdA")
        with pytest.raises(ValueError, match="Base"):
            alias.copy_data_from(a)
        with pytest.raises(ValueError, match="Base"):
            a.copy_data_from(alias)

    def test_round_trip(self, project: Project) -> None:
        """The copied L5K CDATA serialises and reloads."""
        program = project.programs["AnotherProgram"]
        source = program.tags[INSTANCE]
        new = program.tags.add("clone", AOI)
        new.copy_data_from(source)
        text = to_bytes(project.root).decode("utf-8")
        reloaded = loads(text)
        clone = reloaded.programs["AnotherProgram"].tags["clone"]
        assert _formats(clone) == ["L5K", "Decorated"]
        l5k = clone.element.find("Data")
        original = (
            reloaded.programs["AnotherProgram"].tags[INSTANCE].element.find("Data")
        )
        assert l5k.find("CDataContent") is not None or "<![CDATA[" in text
        assert ET.tostring(l5k) == ET.tostring(original)
        assert to_bytes(reloaded.root) == to_bytes(project.root)


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

"""Tests for editing Add-On Instructions in a loaded project."""

import re
from pathlib import Path

import pytest

from py_l5x import (
    AOISpec,
    CallSite,
    LocalTagSpec,
    ParameterSpec,
    Project,
    RoutineSpec,
    RungSpec,
    load,
    loads,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _example() -> Project:
    """Load the main example project.

    Returns:
        The parsed project.
    """
    return load(str(FIXTURES / "example.L5X"))


def _golden() -> Project:
    """Load the type_defaults project (AOI-typed tags in many shapes).

    Returns:
        The parsed project.
    """
    return load(str(FIXTURES / "type_defaults_Tags.L5X"))


def _simple(name: str = "Fresh", **changes) -> AOISpec:
    """Create a small AOI spec.

    Args:
        name: The instruction name.
        **changes: Fields to override.

    Returns:
        A spec with one Input, one Output and a Logic rung.
    """
    spec = AOISpec(
        name,
        [ParameterSpec("In1", "BOOL"), ParameterSpec("Out1", "BOOL", "Output")],
        routines=[RoutineSpec("Logic", rungs=[RungSpec("XIC(In1)OTE(Out1);")])],
    )
    for key, value in changes.items():
        setattr(spec, key, value)
    return spec


class TestAdd:
    """AOICollection.add."""

    def test_appended_and_round_trips(self) -> None:
        """A new AOI goes last and reads back after serialization."""
        project = _example()
        names = list(project.aois)
        added = project.aois.add(_simple())
        assert added.name == "Fresh"
        assert list(project.aois) == [*names, "Fresh"]
        again = loads(project.to_string()).aois["Fresh"]
        assert list(again.parameters) == ["EnableIn", "EnableOut", "In1", "Out1"]
        assert again.routines["Logic"].rungs[0].text == "XIC(In1)OTE(Out1);"

    @pytest.mark.parametrize(
        "name",
        ["Debounce", "debounce", "A_UDT", "a_udt", "TIMER", "timer", "DINT", "String"],
    )
    def test_name_collisions(self, name: str) -> None:
        """Names matching an AOI, UDT, built-in or atomic type fail."""
        project = _example()
        before = project.to_string()
        with pytest.raises(ValueError, match="already exists"):
            project.aois.add(_simple(name))
        assert project.to_string() == before

    @pytest.mark.parametrize("name", ["1a", "a__b", "a_", "x" * 41, "a b"])
    def test_invalid_names(self, name: str) -> None:
        """Invalid names are rejected."""
        with pytest.raises(ValueError):
            _example().aois.add(_simple(name))

    def test_unknown_types(self) -> None:
        """Unknown parameter and local types are rejected before any change."""
        project = _example()
        before = project.to_string()
        spec = _simple()
        spec.parameters.append(ParameterSpec("u", "Missing", "InOut"))
        with pytest.raises(ValueError, match="unknown data type"):
            project.aois.add(spec)
        spec = _simple(local_tags=[LocalTagSpec("t", "Missing")])
        with pytest.raises(ValueError, match="unknown data type"):
            project.aois.add(spec)
        assert project.to_string() == before

    def test_self_typed(self) -> None:
        """A member of the AOI's own type is rejected."""
        spec = _simple(local_tags=[LocalTagSpec("t", "Fresh")])
        with pytest.raises(ValueError, match="own type"):
            _example().aois.add(spec)

    def test_dependencies_and_defaults(self) -> None:
        """UDT and AOI members resolve and give Dependencies."""
        project = _example()
        spec = _simple(
            local_tags=[
                LocalTagSpec("deb", "Debounce"),
                LocalTagSpec("u", "simple_udt", default={"Dint": 4}),
            ]
        )
        project.aois.add(spec)
        local = project.aois["Fresh"].local_tags["u"]
        assert local.to_python()["Dint"] == 4
        deps = project.aois["Fresh"]._element.findall("Dependencies/Dependency")
        assert [(d.get("Type"), d.get("Name")) for d in deps] == [
            ("AddOnInstructionDefinition", "Debounce"),
            ("DataType", "simple_udt"),
        ]

    def test_calls_are_not_checked(self) -> None:
        """Calls to unknown instructions are accepted (documented limit)."""
        project = _example()
        spec = _simple(
            routines=[RoutineSpec("Logic", rungs=[RungSpec("NoSuchAoi(x);")])]
        )
        project.aois.add(spec)
        assert "Fresh" in project.aois

    def test_creates_container(self) -> None:
        """A controller without AOIs gets the container."""
        project = loads(
            '<RSLogix5000Content><Controller Name="C"><Tags/></Controller>'
            "</RSLogix5000Content>"
        )
        project.aois.add(_simple())
        assert [c.tag for c in project.controller_element] == [
            "AddOnInstructionDefinitions",
            "Tags",
        ]


def _set_instance_values(project: Project) -> None:
    """Give the Debounce instances non-default values.

    Args:
        project: The type_defaults project.
    """
    tags = project.controller_tags
    tags["d_Debounce"].value = {"onDelay": 7, "offDelay": 9, "state": True}
    tags["a_Debounce_2"].value = {0: {"onDelay": 1}, 1: {"offDelay": 2}}
    tags["d_DefMix"].value = {"deb": {"onDelay": 5, "offDelay": 6}}


class TestReplace:
    """AOICollection.replace."""

    def _changed(self, project: Project) -> AOISpec:
        """Build a changed Debounce spec: add one parameter, drop another.

        Args:
            project: The project.

        Returns:
            The new spec.
        """
        spec = project.aois["Debounce"].to_spec()
        names = [p.name for p in spec.parameters]
        spec.parameters.pop(names.index("offDelay"))
        spec.parameters.insert(
            names.index("onDelay") + 1, ParameterSpec("extra", "DINT", default=42)
        )
        return spec

    def test_instances_migrated_by_name(self) -> None:
        """Values carry over by name; new parameters get the spec default."""
        project = _golden()
        _set_instance_values(project)
        project.aois.replace(self._changed(project))
        tags = project.controller_tags
        assert tags["d_Debounce"].to_python() == {
            "EnableIn": True,
            "EnableOut": False,
            "state": True,
            "onDelay": 7,
            "extra": 42,
        }
        array = tags["a_Debounce_2"].to_python()
        assert (array[0]["onDelay"], array[0]["extra"]) == (1, 42)
        assert "offDelay" not in array[1]
        assert array[1]["extra"] == 42
        assert tags["d_DefMix"].to_python()["deb"]["onDelay"] == 5
        assert tags["d_DefMix"].to_python()["deb"]["extra"] == 42
        again = loads(project.to_string()).controller_tags
        assert again["d_Debounce"].to_python() == tags["d_Debounce"].to_python()

    def test_local_default_in_other_aoi(self) -> None:
        """GenericInput's Debounce local default is migrated."""
        project = _example()
        local = project.aois["GenericInput"].local_tags["debounce"]
        local.value = {"onDelay": 12}
        project.aois.replace(self._changed(project))
        local = project.aois["GenericInput"].local_tags["debounce"]
        data = local.to_python()
        assert data["onDelay"] == 12
        assert data["extra"] == 42
        assert "offDelay" not in data
        assert local._element.find("DefaultData[@Format='L5K']") is None

    def test_tag_instances_in_example(self) -> None:
        """AOI-typed members of tags are migrated too (GenericInput's debounce)."""
        project = _example()
        project.aois.replace(self._changed(project))
        tag = project.programs["MainProgram"].tags["a_udt_instance"]
        assert "debounce" not in tag.to_python()["an_aoi"]  # GenericInput member
        deb = project.aois["GenericInput"].local_tags["debounce"].to_python()
        assert list(deb) == ["EnableIn", "EnableOut", "state", "onDelay", "extra"]

    def test_call_sites_unchanged_and_allowed(self) -> None:
        """No required parameters, so the call site stays and replace works."""
        project = _example()
        before = [s.text for s in project.aois.call_sites("Debounce")]
        assert before
        project.aois.replace(self._changed(project))
        assert [s.text for s in project.aois.call_sites("Debounce")] == before

    def test_dates(self) -> None:
        """CreatedDate/CreatedBy are kept; Edited* are removed unless set."""
        project = _example()
        element = project.aois["Debounce"]._element
        created = (element.get("CreatedDate"), element.get("CreatedBy"))
        assert element.get("EditedDate") is not None
        project.aois.replace(project.aois["Debounce"].to_spec())
        element = project.aois["Debounce"]._element
        assert (element.get("CreatedDate"), element.get("CreatedBy")) == created
        assert element.get("EditedDate") is None
        assert element.get("EditedBy") is None
        assert element.get("Class") == "Standard"
        spec = project.aois["Debounce"].to_spec()
        spec.metadata["EditedDate"] = "2030-01-01T00:00:00.000Z"
        spec.metadata["EditedBy"] = "me"
        project.aois.replace(spec)
        element = project.aois["Debounce"]._element
        assert element.get("EditedDate") == "2030-01-01T00:00:00.000Z"
        assert element.get("EditedBy") == "me"

    def test_position_kept(self) -> None:
        """The AOI stays where it was."""
        project = _example()
        names = list(project.aois)
        project.aois.replace(project.aois["GenericInput"].to_spec())
        assert list(project.aois) == names

    def test_signature_change_guard(self) -> None:
        """Changing the required list with call sites raises, naming them."""
        project = _example()
        spec = project.aois["GenericInput"].to_spec()
        next(p for p in spec.parameters if p.name == "onDelay").required = True
        before = project.to_string()
        with pytest.raises(ValueError) as error:
            project.aois.replace(spec)
        assert "program AnotherProgram routine io rung 0" in str(error.value)
        assert project.to_string() == before
        project.aois.replace(spec, allow_signature_change=True)
        assert [
            p for p in project.aois["GenericInput"].to_spec().parameters if p.required
        ]
        sites = project.aois.call_sites("GenericInput")
        assert sites[0].text == "GenericInput(TestInput,Local:1:I.Pt00.Data);"

    def test_signature_change_without_call_sites(self) -> None:
        """An uncalled AOI may change its signature freely."""
        project = _example()
        project.aois.add(_simple())
        spec = _simple()
        spec.parameters[0].required = True
        project.aois.replace(spec)
        assert [
            p.name for p in project.aois["Fresh"].to_spec().parameters if p.required
        ] == ["In1"]

    def test_non_signature_change_allowed(self) -> None:
        """Changing visible-only metadata with call sites is fine."""
        project = _example()
        spec = project.aois["GenericInput"].to_spec()
        spec.description = "changed"
        project.aois.replace(spec)
        assert project.aois["GenericInput"].description == "changed"

    def test_errors_leave_document_untouched(self) -> None:
        """Unknown types, KeyError and invalid specs change nothing."""
        project = _example()
        before = project.to_string()
        with pytest.raises(KeyError):
            project.aois.replace(_simple("Nope"))
        spec = project.aois["Debounce"].to_spec()
        spec.local_tags.append(LocalTagSpec("bad", "Missing"))
        with pytest.raises(ValueError, match="unknown data type"):
            project.aois.replace(spec)
        spec = project.aois["Debounce"].to_spec()
        spec.parameters.append(ParameterSpec("p", "DINT", "Output", dimension=2))
        with pytest.raises(ValueError):
            project.aois.replace(spec)
        assert project.to_string() == before

    def test_failure_partway_restores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A failure while migrating restores the old definition."""
        from py_l5x.parsers import layout, migrate

        project = _golden()
        _set_instance_values(project)
        before = project.to_string()
        original = migrate.default_value_element
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise layout.LayoutError("boom")
            return original(*args, **kwargs)

        monkeypatch.setattr(migrate, "default_value_element", flaky)
        with pytest.raises(layout.LayoutError, match="boom"):
            project.aois.replace(self._changed(project))
        assert project.to_string() == before

    def test_type_change_converts(self) -> None:
        """A parameter turned REAL keeps its value as a float."""
        project = _golden()
        project.controller_tags["d_Debounce"].value = {"onDelay": 7}
        spec = project.aois["Debounce"].to_spec()
        next(p for p in spec.parameters if p.name == "onDelay").data_type = "REAL"
        project.aois.replace(spec)
        assert project.controller_tags["d_Debounce"].to_python()["onDelay"] == 7.0


_NORMALIZE = [
    (re.compile(r'<Data Format="L5K">.*?</Data>\r\n', re.DOTALL), ""),
    (re.compile(r'<DefaultData Format="L5K">.*?</DefaultData>\r\n', re.DOTALL), ""),
    (re.compile(r"<Dependencies>.*?</Dependencies>\r\n", re.DOTALL), ""),
    (re.compile(r' EditedDate="[^"]*"'), ""),
    (re.compile(r' EditedBy="[^"]*"'), ""),
]


def _normalize(text: str) -> str:
    """Strip what a replace legitimately changes.

    Args:
        text: Serialized document.

    Returns:
        Text without L5K blocks, Dependencies and Edited* attributes.
    """
    for pattern, replacement in _NORMALIZE:
        text = pattern.sub(replacement, text)
    return text


class TestReplaceRoundTrip:
    """replace(to_spec()) is a no-op apart from the known differences."""

    @pytest.mark.parametrize("file", ["example.L5X", "type_defaults_Tags.L5X"])
    def test_every_aoi(self, file: str) -> None:
        """Values are unchanged and the document is identical after normalizing."""
        reference = load(str(FIXTURES / file))
        values = {
            n: t.to_python()
            for n, t in reference.controller_tags.items()
            if hasattr(t, "to_python")
        }
        expected = _normalize(reference.to_string())
        for name in list(reference.aois):
            project = load(str(FIXTURES / file))
            project.aois.replace(project.aois[name].to_spec())
            assert _normalize(project.to_string()) == expected, name
            for tag_name, value in values.items():
                assert project.controller_tags[tag_name].to_python() == value


_EXPECTED_CALLS = {
    "Debounce": [("aoi", "GenericInput", "Logic", 2)],
    "GenericInput": [("program", "AnotherProgram", "io", 0)],
    "FanucAlarmLookup": [("aoi", "FanucRobot", "Logic", 8)],
    "FanucPNS": [("aoi", "FanucRobot", "Logic", 15)],
    "SeqCtrl": [
        ("aoi", "FanucRobot", "Logic", 9),
        ("program", "MainProgram", "SequenceRoutine", 2),
    ],
    "FanucRobot": [("program", "Robot", "RobotExample", 5)],
}


class TestCallSites:
    """call_sites matching."""

    @pytest.mark.parametrize("name", list(_EXPECTED_CALLS))
    def test_fixture_calls(self, name: str) -> None:
        """Every fixture AOI is called where expected."""
        sites = _example().aois.call_sites(name)
        assert [
            (s.container_kind, s.container, s.routine, s.number) for s in sites
        ] == _EXPECTED_CALLS[name]
        assert all(isinstance(s, CallSite) and s.language == "RLL" for s in sites)

    def test_call_text(self) -> None:
        """Texts are the raw call text."""
        project = _example()
        assert project.aois.call_sites("SeqCtrl")[1].text == "SeqCtrl(sequence,1,0);"
        assert (
            project.aois.call_sites("GenericInput")[0].describe()
            == "program AnotherProgram routine io rung 0"
        )

    @pytest.fixture
    def doc(self) -> Project:
        """A project whose logic holds calls and look-alikes of ``Debounce``."""
        rungs = [
            "XIC(Debounce_state)OTE(a);",
            "XIC(x.Debounce)OTE(a);",
            "XIC(Debounce)OTE(a);",
            "XIC(my_Debounce)OTE(a);",
            "MOV(1,Debounce2);",
            "XIC(a)Debounce (t,1);",
            "[XIC(a),debounce(u)]OTE(b);",
            "MSG('Debounce(x)');",
            "XIC(x.Debounce(y))OTE(a);",
        ]
        rung_xml = "".join(
            f'<Rung Number="{i}" Type="N"><Text><![CDATA[{t}]]></Text></Rung>'
            for i, t in enumerate(rungs)
        )
        lines = [
            "x := y; // Debounce(a)",
            "(* Debounce(a)",
            "   Debounce(b) *)",
            "Debounce(c);",
            "a.Debounce(d);",
            "Debounce_x(e);",
            "s := 'Debounce(q)';",
        ]
        line_xml = "".join(
            f'<Line Number="{i}"><![CDATA[{t}]]></Line>' for i, t in enumerate(lines)
        )
        return loads(
            '<RSLogix5000Content><Controller Name="C"><Programs>'
            '<Program Name="P" MainRoutineName="R"><Routines>'
            f'<Routine Name="R" Type="RLL"><RLLContent>{rung_xml}'
            "</RLLContent></Routine>"
            f'<Routine Name="S" Type="ST"><STContent>{line_xml}</STContent></Routine>'
            "</Routines></Program></Programs></Controller></RSLogix5000Content>"
        )

    def test_matcher_rules(self, doc: Project) -> None:
        """Only real calls match: boundaries, no dot, not in strings/comments."""
        sites = doc.aois.call_sites("Debounce")
        rll = [s.number for s in sites if s.language == "RLL"]
        st = [s.number for s in sites if s.language == "ST"]
        assert rll == [5, 6]
        assert st == [3]

    def test_rename_touches_only_calls(self, doc: Project) -> None:
        """A rename rewrites calls and leaves look-alikes, strings and comments."""
        aois = doc.aois
        aois._rename_calls("Debounce", "Renamed")
        routines = doc.programs["P"].routines
        rungs = [r.text for r in routines["R"].rungs]
        assert rungs == [
            "XIC(Debounce_state)OTE(a);",
            "XIC(x.Debounce)OTE(a);",
            "XIC(Debounce)OTE(a);",
            "XIC(my_Debounce)OTE(a);",
            "MOV(1,Debounce2);",
            "XIC(a)Renamed (t,1);",
            "[XIC(a),Renamed(u)]OTE(b);",
            "MSG('Debounce(x)');",
            "XIC(x.Debounce(y))OTE(a);",
        ]
        lines = [line.text for line in routines["S"].st_lines]
        assert lines == [
            "x := y; // Debounce(a)",
            "(* Debounce(a)",
            "   Debounce(b) *)",
            "Renamed(c);",
            "a.Debounce(d);",
            "Debounce_x(e);",
            "s := 'Debounce(q)';",
        ]


class TestRename:
    """AOICollection.rename."""

    def test_seqctrl(self) -> None:
        """Tags, nested types, Dependencies and call sites follow."""
        project = _example()
        project.aois.rename("SeqCtrl", "SeqControl")
        text = project.to_string()
        assert "SeqCtrl" not in project.aois
        assert "SeqControl" in project.aois
        assert (
            project.programs["MainProgram"].tags["sequence"].data_type == "SeqControl"
        )
        assert project.aois["FanucRobot"].parameters["seq"].data_type == "SeqControl"
        assert [s.container for s in project.aois.call_sites("SeqControl")] == [
            "FanucRobot",
            "MainProgram",
        ]
        assert project.aois.call_sites("SeqCtrl") == []
        assert "SeqControl(sequence,1,0);" in text
        assert "SeqControl(seq,mode,disableHmiStart);" in text
        reloaded = loads(text)
        assert reloaded.aois["SeqControl"].name == "SeqControl"
        assert len(reloaded.aois.call_sites("SeqControl")) == 2
        tag = reloaded.programs["MainProgram"].tags["sequence"]
        assert (
            tag.to_python()
            == project.programs["MainProgram"].tags["sequence"].to_python()
        )

    def test_old_name_survives_only_in_documentation(self) -> None:
        """No attribute and no logic mentions the old name any more."""
        project = _example()
        project.aois.rename("SeqCtrl", "SeqControl")
        for element in project.controller_element.iter():
            assert "SeqCtrl" not in element.attrib.values(), element.tag
        for aoi in project.aois.values():
            for routine in aoi.routines.values():
                for rung in routine.rungs:
                    assert "SeqCtrl(" not in rung.text
        for program in project.programs.values():
            for routine in program.routines.values():
                for rung in routine.rungs:
                    assert "SeqCtrl(" not in rung.text

    def test_dependencies_follow(self) -> None:
        """Dependency entries are renamed."""
        project = _golden()
        project.aois.rename("SeqCtrl", "SeqControl")
        deps = project.aois["FanucRobot"]._element.findall("Dependencies/Dependency")
        assert ("AddOnInstructionDefinition", "SeqControl") in [
            (d.get("Type"), d.get("Name")) for d in deps
        ]
        assert all(d.get("Name") != "SeqCtrl" for d in deps)

    def test_nested_type_references(self) -> None:
        """AOI-typed UDT members and value trees follow."""
        project = _example()
        project.aois.rename("GenericInput", "GenIn")
        member = project.data_types["A_UDT"].members["an_aoi"]
        assert member.data_type == "GenIn"
        tag = project.programs["MainProgram"].tags["a_udt_instance"]
        nested = tag.value_element.find("StructureMember[@Name='an_aoi']")
        assert nested.get("DataType") == "GenIn"
        assert (
            project.programs["AnotherProgram"]
            .routines["io"]
            .rungs[0]
            .text.startswith("GenIn(")
        )

    def test_tags_named_like_the_aoi_untouched(self) -> None:
        """Tag names and operands containing the AOI name are not rewritten."""
        project = _example()
        project.controller_tags.add("SeqCtrl_state", "DINT")
        project.controller_tags.add("seqctrl_x", "BOOL")
        routine = project.programs["MainProgram"].routines["MainRoutine"]
        routine.add_rung("XIC(seqctrl_x)MOV(SeqCtrl_state,sequence.SeqCtrl)NOP();")
        project.aois.rename("SeqCtrl", "SeqControl")
        assert "SeqCtrl_state" in project.controller_tags
        assert "seqctrl_x" in project.controller_tags
        rungs = [r.text for r in routine.rungs]
        assert "XIC(seqctrl_x)MOV(SeqCtrl_state,sequence.SeqCtrl)NOP();" in rungs

    def test_case_only(self) -> None:
        """A case-only rename of the AOI itself works."""
        project = _example()
        project.aois.rename("SeqCtrl", "SEQCTRL")
        assert "SEQCTRL" in project.aois
        assert "SEQCTRL(sequence,1,0);" in project.to_string()

    @pytest.mark.parametrize(
        "new", ["debounce", "a_udt", "TIMER", "DINT", "1x", "a__b"]
    )
    def test_errors(self, new: str) -> None:
        """Taken or invalid names are rejected and nothing changes."""
        project = _example()
        before = project.to_string()
        with pytest.raises(ValueError):
            project.aois.rename("SeqCtrl", new)
        assert project.to_string() == before

    def test_missing(self) -> None:
        """A missing name raises KeyError."""
        with pytest.raises(KeyError):
            _example().aois.rename("nope", "x")


class TestRemove:
    """AOICollection.remove and users."""

    def test_in_use(self) -> None:
        """A used AOI is refused; users include call sites and locals."""
        project = _example()
        before = project.to_string()
        with pytest.raises(ValueError) as error:
            project.aois.remove("Debounce")
        message = str(error.value)
        assert "AOI GenericInput local tag debounce" in message
        assert "call in aoi GenericInput routine Logic rung 2" in message
        assert project.to_string() == before

    def test_users(self) -> None:
        """users lists tags, members and calls."""
        project = _example()
        users = project.aois.users("GenericInput")
        assert "data type A_UDT member an_aoi" in users
        assert "call in program AnotherProgram routine io rung 0" in users

    def test_force(self) -> None:
        """force removes a used AOI."""
        project = _example()
        project.aois.remove("Debounce", force=True)
        assert "Debounce" not in project.aois

    def test_unused_and_missing(self) -> None:
        """An unused AOI is removed without force; a missing name raises."""
        project = _example()
        project.aois.add(_simple())
        project.aois.remove("Fresh")
        assert "Fresh" not in project.aois
        with pytest.raises(KeyError):
            project.aois.remove("nope")

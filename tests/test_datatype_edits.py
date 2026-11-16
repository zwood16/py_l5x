"""Tests for editing user-defined data types in a loaded project."""

import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x import DataTypeSpec, MemberSpec, Project, load, loads
from py_l5x.parsers import layout, migrate
from py_l5x.parsers.migrate import convert_atomic_value

FIXTURES = Path(__file__).parent / "fixtures"


def _golden() -> Project:
    """Load the type_defaults project (UDTs with instances of every shape).

    Returns:
        The parsed project.
    """
    return load(str(FIXTURES / "type_defaults_Tags.L5X"))


def _example() -> Project:
    """Load the main example project.

    Returns:
        The parsed project.
    """
    return load(str(FIXTURES / "example.L5X"))


def _shape(element: ET.Element) -> tuple:
    """Describe a tree ignoring ``Value`` attributes and CDATA text.

    Args:
        element: The root of the subtree.

    Returns:
        A nested tuple of tag, attributes without Value, and child shapes.
    """
    return (
        element.tag,
        tuple((k, v) for k, v in element.attrib.items() if k != "Value"),
        tuple(_shape(child) for child in element),
    )


class TestConvert:
    """convert_atomic_value, one test per rule."""

    @pytest.mark.parametrize(
        ("text", "old", "new", "radix", "expected"),
        [
            ("11", "DINT", "DINT", "Decimal", "11"),
            ("11", "DINT", "REAL", "Float", "11.0"),
            ("11", "DINT", "LREAL", "Float", "11.0"),
            ("2.7", "REAL", "DINT", "Decimal", "3"),
            ("-2.7", "REAL", "DINT", "Decimal", "-3"),
            ("2.5", "REAL", "DINT", "Decimal", "2"),
            ("3.5", "REAL", "DINT", "Decimal", "4"),
            ("-2.5", "LREAL", "DINT", "Decimal", "-2"),
            ("1.00000000e+010", "REAL", "DINT", "Decimal", "2147483647"),
            ("-1.00000000e+010", "REAL", "DINT", "Decimal", "-2147483648"),
            ("1e10", "LREAL", "SINT", "Decimal", "127"),
            ("-5.0", "REAL", "USINT", "Decimal", "0"),
            ("300", "DINT", "SINT", "Decimal", "44"),
            ("-5", "SINT", "UINT", "Decimal", "65531"),
            ("65535", "UINT", "INT", "Decimal", "-1"),
            ("200", "USINT", "SINT", "Decimal", "-56"),
            ("2147483647", "DINT", "REAL", "Exponential", "2.14748365e+009"),
            ("16777217", "DINT", "REAL", "Float", "16777216.0"),
            ("1", "BOOL", "REAL", "Float", "1.0"),
            ("1", "BOOL", "DINT", "Decimal", "1"),
            ("0", "BOOL", "LREAL", "Float", "0.0"),
            ("-1", "DINT", "BOOL", None, "1"),
            ("2", "DINT", "BOOL", None, "1"),
            ("4", "DINT", "BOOL", None, "1"),
            ("0", "DINT", "BOOL", None, "0"),
            ("0.5", "REAL", "BOOL", None, "1"),
            ("2.0", "REAL", "BOOL", None, "1"),
            ("0.0", "REAL", "BOOL", None, "0"),
            ("1.5", "REAL", "LREAL", "Float", "1.5"),
            ("1.5", "LREAL", "REAL", "Float", "1.5"),
            ("T#5s", "TIME", "TIME", "Time (us)", "T#5s"),
        ],
    )
    def test_rule(
        self, text: str, old: str, new: str, radix: str | None, expected: str
    ) -> None:
        """Each measured conversion gives the expected text."""
        assert convert_atomic_value(text, old, new, radix) == expected

    @pytest.mark.parametrize(
        ("text", "old", "new"),
        [
            ("T#5s", "TIME", "DINT"),
            ("5", "DINT", "TIME"),
            ("T#5s", "TIME", "LTIME"),
            ("5", "DINT", "STRING"),
            ("5", "Unknown", "DINT"),
            ("abc", "DINT", "SINT"),
            ("1.#QNAN", "REAL", "DINT"),
            ("1e300", "LREAL", "REAL"),
        ],
    )
    def test_no_conversion(self, text: str, old: str, new: str) -> None:
        """Everything else has no conversion (the default stays)."""
        assert convert_atomic_value(text, old, new, "Decimal") is None

    def test_infinity_saturates(self) -> None:
        """An infinity saturates at the target range."""
        assert convert_atomic_value("1.#INF", "REAL", "DINT", "Decimal") == "2147483647"
        assert convert_atomic_value("-1.#INF", "REAL", "SINT", "Decimal") == "-128"

    def test_radix_reformat(self) -> None:
        """Same type with another radix is reformatted."""
        assert convert_atomic_value("255", "DINT", "DINT", "Hex") == "16#0000_00ff"


def _set_values(project: Project) -> None:
    """Give the simple_udt instances non-default values.

    Args:
        project: The type_defaults project.
    """
    tags = project.controller_tags
    tags["d_simple_udt"].value = {"bool2": True, "Dint": 7, "real": 9, "lint": 11}
    tags["a_simple_udt_2x2"].value = {
        (0, 1): {"Dint": 21, "bool1": True},
        (1, 1): {"lint": 5, "real": 6},
    }
    tags["d_A_UDT"].value = {"a_nested_UDT": {"Dint": 31, "bool4": True}}
    tags["d_DefMix"].value = {"su": {"real": 41}}


def _snapshot(project: Project) -> dict:
    """Collect every simple_udt instance's values.

    Args:
        project: The type_defaults project.

    Returns:
        ``{place: to_python()}``.
    """
    tags = project.controller_tags
    return {
        "root": tags["d_simple_udt"].to_python(),
        "array": tags["a_simple_udt_2x2"].to_python(),
        "nested": tags["d_A_UDT"].to_python()["a_nested_UDT"],
        "mix": tags["d_DefMix"].to_python()["su"],
    }


def _instances(project: Project) -> list[tuple[str, ET.Element]]:
    """Find every simple_udt instance element with its place name.

    Args:
        project: The type_defaults project.

    Returns:
        ``(place, element)`` pairs.
    """
    tags = project.controller_tags
    return [
        ("root", tags["d_simple_udt"].value_element),
        *[
            ("array", e.find("Structure"))
            for e in tags["a_simple_udt_2x2"].value_element.findall("Element")
        ],
        (
            "nested",
            tags["d_A_UDT"].value_element.find("StructureMember[@Name='a_nested_UDT']"),
        ),
        ("mix", tags["d_DefMix"].value_element.find("StructureMember[@Name='su']")),
    ]


def _expected(values: dict, change) -> dict:
    """Apply a change to every instance dict of a snapshot.

    Args:
        values: A snapshot.
        change: A function mapping one instance dict to its new dict.

    Returns:
        The expected snapshot.
    """
    return {
        "root": change(values["root"]),
        "array": [[change(item) for item in row] for row in values["array"]],
        "nested": change(values["nested"]),
        "mix": change(values["mix"]),
    }


def _check_shapes(project: Project) -> None:
    """Assert every instance has exactly the default tree's shape.

    Args:
        project: The type_defaults project.
    """
    registry = project._type_registry
    for place, element in _instances(project):
        context = "member" if element.tag == "StructureMember" else "root"
        name = element.get("Name") if context == "member" else None
        fresh = layout.default_value_element(
            "simple_udt", registry, context=context, name=name
        )
        assert _shape(element) == _shape(fresh), place


def _replace(project: Project, change) -> DataTypeSpec:
    """Replace simple_udt with a modified spec.

    Args:
        project: The type_defaults project.
        change: A function modifying the member list in place.

    Returns:
        The spec used.
    """
    spec = project.data_types["simple_udt"].to_spec()
    change(spec.members)
    project.data_types.replace(spec)
    return spec


class TestReplace:
    """replace migrates every instance by member name."""

    @pytest.fixture
    def project(self) -> Project:
        """The golden project with non-default simple_udt values."""
        project = _golden()
        _set_values(project)
        return project

    def _finish(self, project: Project, before: dict, change) -> None:
        """Check values, shapes and the serialization round trip.

        Args:
            project: The edited project.
            before: The snapshot taken before the edit.
            change: Maps an old instance dict to its expected new dict.
        """
        after = _snapshot(project)
        assert after == _expected(before, change)
        _check_shapes(project)
        assert _snapshot(loads(project.to_string())) == after

    def test_add_member_in_middle(self, project: Project) -> None:
        """A new member gets its default; the others keep their values."""
        before = _snapshot(project)
        _replace(
            project,
            lambda m: m.insert(5, MemberSpec("mid", "DINT", radix="Hex")),
        )

        def change(old: dict) -> dict:
            out = dict(old)
            items = list(out.items())
            items.insert(5, ("mid", 0))
            return dict(items)

        self._finish(project, before, change)
        assert list(project.controller_tags["d_simple_udt"].to_python())[5] == "mid"
        data = project.controller_tags["d_simple_udt"].members["mid"]
        assert data.value_element.get("Value") == "16#0000_0000"

    def test_add_bool_in_middle_repacks(self, project: Project) -> None:
        """Adding BOOLs changes the packing but not the values."""
        before = _snapshot(project)
        _replace(project, lambda m: m.insert(2, MemberSpec("extra", "BOOL")))

        def change(old: dict) -> dict:
            items = list(old.items())
            items.insert(2, ("extra", False))
            return dict(items)

        self._finish(project, before, change)

    def test_remove_member(self, project: Project) -> None:
        """A removed member disappears; the rest keep their values."""
        before = _snapshot(project)
        _replace(project, lambda m: m.pop(5))
        self._finish(
            project, before, lambda old: {k: v for k, v in old.items() if k != "real"}
        )

    def test_reorder(self, project: Project) -> None:
        """Reordered members keep their values."""
        before = _snapshot(project)
        _replace(project, lambda m: m.reverse())

        def change(old: dict) -> dict:
            return dict(reversed(list(old.items())))

        self._finish(project, before, change)

    def test_dint_to_real_and_back(self, project: Project) -> None:
        """DINT converts to REAL; REAL back to DINT rounds half to even."""
        before = _snapshot(project)

        def to_real(members: list) -> None:
            members[4].data_type = "REAL"  # Dint
            members[5].data_type = "REAL"  # real

        _replace(project, to_real)
        self._finish(
            project,
            before,
            lambda old: {**old, "Dint": float(old["Dint"]), "real": float(old["real"])},
        )
        project.controller_tags["d_simple_udt"].value = {"Dint": 2.5, "real": 3.5}
        spec = project.data_types["simple_udt"].to_spec()
        spec.members[4].data_type = "DINT"
        spec.members[5].data_type = "DINT"
        project.data_types.replace(spec)
        data = project.controller_tags["d_simple_udt"].to_python()
        assert (data["Dint"], data["real"]) == (2, 4)
        _check_shapes(project)

    def test_type_change_to_struct_gets_default(self, project: Project) -> None:
        """A member turned into a structure has its default tree."""
        _replace(project, lambda m: m.__setitem__(4, MemberSpec("Dint", "TIMER")))
        data = project.controller_tags["d_simple_udt"].to_python()
        assert data["Dint"] == {
            "PRE": 0,
            "ACC": 0,
            "EN": False,
            "TT": False,
            "DN": False,
        }
        assert data["real"] == 9
        _check_shapes(project)

    def test_l5k_dropped_only_where_touched(self) -> None:
        """Touched tags lose L5K; others keep it (example.L5X has L5K data)."""
        project = _example()
        tags = project.programs["MainProgram"].tags
        for name in ("a_simple_udt_instance", "a_udt_instance", "a_timer"):
            assert tags[name]._element.find("Data[@Format='L5K']") is not None
        project.data_types.replace(project.data_types["simple_udt"].to_spec())
        assert (
            tags["a_simple_udt_instance"]._element.find("Data[@Format='L5K']") is None
        )
        assert tags["a_udt_instance"]._element.find("Data[@Format='L5K']") is None
        assert tags["a_timer"]._element.find("Data[@Format='L5K']") is not None

    def test_untouched_data_is_identical(self, project: Project) -> None:
        """Tags that don't contain the type are byte-identical."""
        before = ET.tostring(project.controller_tags["a_TIMER_2"]._element)
        _replace(project, lambda m: m.pop(5))
        assert ET.tostring(project.controller_tags["a_TIMER_2"]._element) == before

    def test_dependencies_and_position(self, project: Project) -> None:
        """The element keeps its position and gets Dependencies when needed."""
        names = list(project.data_types)
        spec = project.data_types["simple_udt"].to_spec()
        spec.members.append(MemberSpec("deb", "Debounce"))
        project.data_types.replace(spec)
        assert list(project.data_types) == names
        deps = project.data_types["simple_udt"]._element.findall(
            "Dependencies/Dependency"
        )
        assert [(d.get("Type"), d.get("Name")) for d in deps] == [
            ("AddOnInstructionDefinition", "Debounce")
        ]
        assert (
            project.controller_tags["d_simple_udt"].to_python()["deb"]["EnableIn"]
            is True
        )

    def test_operand_metadata_left_in_place(self) -> None:
        """Comments on a removed member's operand stay."""
        project = _example()
        tag = project.programs["MainProgram"].tags["a_simple_udt_with_overrides"]
        comments = tag.operand_comments
        assert ".BOOL1" in comments
        spec = project.data_types["simple_udt"].to_spec()
        spec.members.pop(0)
        project.data_types.replace(spec)
        assert (
            project.programs["MainProgram"]
            .tags["a_simple_udt_with_overrides"]
            .operand_comments
            == comments
        )

    def test_errors(self, project: Project) -> None:
        """Missing, non-user and family-changing replaces are rejected."""
        with pytest.raises(KeyError):
            project.data_types.replace(DataTypeSpec("Nope", [MemberSpec("a", "DINT")]))
        with pytest.raises(ValueError, match="not a user-defined"):
            project.data_types.replace(DataTypeSpec("TIMER", [MemberSpec("a", "DINT")]))
        with pytest.raises(ValueError, match="family"):
            project.data_types.replace(
                DataTypeSpec(
                    "simple_udt", [MemberSpec("a", "DINT")], family="StringFamily"
                )
            )


class TestAtomicity:
    """A failed replace leaves the document untouched."""

    def test_unknown_member_type(self) -> None:
        """An unknown member type is rejected before anything changes."""
        project = _golden()
        _set_values(project)
        before = project.to_string()
        spec = project.data_types["simple_udt"].to_spec()
        spec.members.append(MemberSpec("x", "NoSuchType"))
        with pytest.raises(ValueError, match="unknown data type"):
            project.data_types.replace(spec)
        assert project.to_string() == before

    def test_invalid_spec(self) -> None:
        """An invalid spec (duplicate member) changes nothing."""
        project = _golden()
        before = project.to_string()
        spec = project.data_types["simple_udt"].to_spec()
        spec.members.append(MemberSpec("DINT", "DINT"))
        spec.members.append(MemberSpec("dint", "DINT"))
        with pytest.raises(ValueError):
            project.data_types.replace(spec)
        assert project.to_string() == before

    def test_failure_partway_restores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A failure while planning (after the swap) restores the old type."""
        project = _golden()
        _set_values(project)
        before = project.to_string()
        original = migrate.default_value_element
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 3:
                raise layout.LayoutError("boom")
            return original(*args, **kwargs)

        monkeypatch.setattr(migrate, "default_value_element", flaky)
        spec = project.data_types["simple_udt"].to_spec()
        spec.members.pop()
        with pytest.raises(layout.LayoutError, match="boom"):
            project.data_types.replace(spec)
        assert project.to_string() == before
        assert len(calls) == 3


class TestReplaceStrings:
    """StringFamily UDTs shrink by truncation."""

    def test_truncation(self) -> None:
        """Root, array, nested and nested-in-UDT strings are truncated."""
        project = _golden()
        tags = project.controller_tags
        tags["d_robotString"].value = "abcdefghij"
        tags["a_robotString_3"].value = {1: "0123456789", 2: "xy"}
        tags["d_DefMix"].value = {"rs": "hello world"}
        tags["d_GenericRobotIO"].value = {
            "programStatus": "toolongstring",
            "lastAlarm": "ok",
        }
        project.data_types.replace(DataTypeSpec.string("robotString", 5))
        assert tags["d_robotString"].value == "abcde"
        assert tags["d_robotString"].len == 5
        assert tags["d_robotString"].value_element.get("Length") == "5"
        assert tags["a_robotString_3"].to_python() == ["", "01234", "xy"]
        assert tags["a_robotString_3"][1].len == 5
        assert tags["d_DefMix"].to_python()["rs"] == "hello"
        io = tags["d_GenericRobotIO"].to_python()
        assert (io["programStatus"], io["lastAlarm"]) == ("toolo", "ok")
        assert project.data_types["robotString"].max_length == 5
        again = loads(project.to_string()).controller_tags
        assert again["d_robotString"].value == "abcde"
        assert again["a_robotString_3"].to_python() == ["", "01234", "xy"]

    def test_short_values_untouched_and_longer_type(self) -> None:
        """A longer type keeps values; short strings keep their literal."""
        project = _golden()
        tags = project.controller_tags
        tags["d_robotAlarmCode"].value = "ab$c"
        project.data_types.replace(DataTypeSpec.string("robotAlarmCode", 20))
        assert tags["d_robotAlarmCode"].value == "ab$c"
        assert tags["d_robotAlarmCode"].value_element[0].text == "'ab$$c'"


_AOI_DOC = """<RSLogix5000Content SchemaRevision="1.0"><Controller Name="C">
<DataTypes>
<DataType Name="U" Family="NoFamily" Class="User">
<Members>
<Member Name="a" DataType="DINT" Dimension="0" Radix="Decimal" Hidden="false" ExternalAccess="Read/Write"/>
<Member Name="b" DataType="DINT" Dimension="0" Radix="Decimal" Hidden="false" ExternalAccess="Read/Write"/>
</Members>
</DataType>
</DataTypes>
<AddOnInstructionDefinitions>
<AddOnInstructionDefinition Name="Aoi" Revision="1.0">
<LocalTags>
<LocalTag Name="loc" DataType="U" ExternalAccess="None">
<DefaultData Format="L5K">
<![CDATA[[5,6]]]>
</DefaultData>
<DefaultData Format="Decorated">
<Structure DataType="U">
<DataValueMember Name="a" DataType="DINT" Radix="Decimal" Value="5"/>
<DataValueMember Name="b" DataType="DINT" Radix="Decimal" Value="6"/>
</Structure>
</DefaultData>
</LocalTag>
</LocalTags>
</AddOnInstructionDefinition>
</AddOnInstructionDefinitions>
<Tags>
<Tag Name="arr" TagType="Base" DataType="U" Dimensions="2">
<Data Format="Decorated">
<Array DataType="U" Dimensions="2">
<Element Index="[0]">
<Structure DataType="U">
<DataValueMember Name="a" DataType="DINT" Radix="Decimal" Value="1"/>
<DataValueMember Name="b" DataType="DINT" Radix="Decimal" Value="2"/>
</Structure>
</Element>
<Element Index="[1]">
<Structure DataType="U">
<DataValueMember Name="a" DataType="DINT" Radix="Decimal" Value="3"/>
<DataValueMember Name="b" DataType="DINT" Radix="Decimal" Value="4"/>
</Structure>
</Element>
</Array>
</Data>
</Tag>
</Tags>
</Controller></RSLogix5000Content>"""  # noqa: E501


class TestReplaceInAoi:
    """AOI local defaults and arrays are migrated too."""

    def test_local_default_and_array(self) -> None:
        """A local tag's DefaultData and a tag array carry values over."""
        project = loads(_AOI_DOC)
        spec = project.data_types["U"].to_spec()
        spec.members.insert(0, MemberSpec("new", "DINT"))
        spec.members.pop()  # drop b
        project.data_types.replace(spec)
        local = project.aois["Aoi"].local_tags["loc"]
        assert local.to_python() == {"new": 0, "a": 5}
        assert local._element.find("DefaultData[@Format='L5K']") is None
        assert project.controller_tags["arr"].to_python() == [
            {"new": 0, "a": 1},
            {"new": 0, "a": 3},
        ]
        again = loads(project.to_string())
        assert again.aois["Aoi"].local_tags["loc"].to_python() == {"new": 0, "a": 5}


class TestRoundTrip:
    """to_spec -> replace leaves values and the document alone."""

    @staticmethod
    def _normalize(text: str) -> str:
        """Strip what replace legitimately changes.

        Args:
            text: Serialized document.

        Returns:
            Text without L5K blocks and Dependencies.
        """
        for tag in ("Data", "DefaultData"):
            text = re.sub(
                rf'<{tag} Format="L5K">.*?</{tag}>\r\n', "", text, flags=re.DOTALL
            )
        return re.sub(
            r"<Dependencies>.*?</Dependencies>\r\n", "", text, flags=re.DOTALL
        )

    @pytest.mark.parametrize("file", ["example.L5X", "type_defaults_Tags.L5X"])
    def test_every_user_udt(self, file: str) -> None:
        """Replacing a UDT by its own spec changes nothing but L5K/Dependencies."""
        reference = load(str(FIXTURES / file))
        names = [
            n
            for n, dt in reference.data_types.items()
            if dt.class_ == "User" and n not in ("robotUI", "robotUO")
        ]
        values = {
            n: t.to_python()
            for n, t in reference.controller_tags.items()
            if hasattr(t, "to_python")
        }
        for name in names:
            project = load(str(FIXTURES / file))
            project.data_types.replace(project.data_types[name].to_spec())
            assert self._normalize(project.to_string()) == self._normalize(
                reference.to_string()
            ), name
            for tag_name, expected in values.items():
                assert project.controller_tags[tag_name].to_python() == expected


class TestAdd:
    """DataTypesCollection.add."""

    def test_sorted_position(self) -> None:
        """New types are inserted in case-insensitive name order."""
        project = _example()
        project.data_types.add(DataTypeSpec("gamma", [MemberSpec("a", "DINT")]))
        project.data_types.add(DataTypeSpec("Zeta", [MemberSpec("a", "DINT")]))
        project.data_types.add(DataTypeSpec("_first", [MemberSpec("a", "DINT")]))
        names = list(project.data_types)
        assert names == sorted(names, key=str.lower)
        assert names.index("gamma") < names.index("GenericRobotInputs")
        assert names[-1] == "Zeta" or names[-1].lower() > "zeta"

    def test_returns_and_round_trips(self) -> None:
        """The new type reads back after serialization."""
        project = _example()
        spec = DataTypeSpec(
            "NewOne", [MemberSpec("a", "BOOL"), MemberSpec("u", "simple_udt")]
        )
        added = project.data_types.add(spec)
        assert added.name == "NewOne"
        again = loads(project.to_string()).data_types["NewOne"]
        assert again.to_spec() == spec
        deps = again._element.findall("Dependencies/Dependency")
        assert [d.get("Name") for d in deps] == ["simple_udt"]

    @pytest.mark.parametrize(
        "name", ["A_UDT", "a_udt", "debounce", "TIMER", "timer", "DINT", "String"]
    )
    def test_name_collisions(self, name: str) -> None:
        """Names matching a UDT, an AOI, a built-in or an atomic type fail."""
        project = _example()
        before = project.to_string()
        with pytest.raises(ValueError, match="already in use"):
            project.data_types.add(DataTypeSpec(name, [MemberSpec("a", "DINT")]))
        assert project.to_string() == before

    def test_unknown_member_type(self) -> None:
        """An unknown member type is rejected."""
        project = _example()
        before = project.to_string()
        with pytest.raises(ValueError, match="unknown data type"):
            project.data_types.add(DataTypeSpec("X", [MemberSpec("a", "Missing")]))
        assert project.to_string() == before

    def test_member_types_resolve(self) -> None:
        """Atomic, built-in, UDT and AOI member types are accepted."""
        project = _example()
        spec = DataTypeSpec(
            "Mixed",
            [
                MemberSpec("a", "LINT"),
                MemberSpec("t", "TIMER"),
                MemberSpec("s", "STRING"),
                MemberSpec("u", "A_UDT"),
                MemberSpec("d", "Debounce"),
            ],
        )
        project.data_types.add(spec)
        deps = project.data_types["Mixed"]._element.findall("Dependencies/Dependency")
        assert [(d.get("Type"), d.get("Name")) for d in deps] == [
            ("DataType", "A_UDT"),
            ("AddOnInstructionDefinition", "Debounce"),
        ]

    def test_creates_container(self) -> None:
        """A controller without <DataTypes> gets one."""
        project = loads(
            '<RSLogix5000Content><Controller Name="C"><Tags/></Controller>'
            "</RSLogix5000Content>"
        )
        project.data_types.add(DataTypeSpec("U", [MemberSpec("a", "DINT")]))
        assert [c.tag for c in project.controller_element] == ["DataTypes", "Tags"]
        assert "U" in loads(project.to_string()).data_types

    def test_value_use_after_add(self) -> None:
        """A tag of the added type initializes with its layout."""
        project = _example()
        project.data_types.add(
            DataTypeSpec("Pt", [MemberSpec("x", "REAL"), MemberSpec("y", "REAL")])
        )
        tag = project.controller_tags.add("pt", "Pt", value={"y": 2.5})
        assert tag.to_python() == {"x": 0.0, "y": 2.5}


class TestRename:
    """rename updates every reference."""

    def test_simple_udt(self) -> None:
        """Types, tags, Dependencies and value trees follow; hosts do not."""
        project = _golden()
        _set_values(project)
        values_before = _snapshot(project)
        project.data_types.rename("simple_udt", "SimpleUdt2")
        text = project.to_string()
        assert 'DataType="simple_udt"' not in text
        assert 'Name="simple_udt"' not in text
        assert "ZZZZZZZZZZsimple_udt0" in text
        assert 'Name="SimpleUdt2"' in text
        assert 'Dependency Type="DataType" Name="SimpleUdt2"' in text
        assert (
            project.data_types["A_UDT"].members["a_nested_UDT"].data_type
            == "SimpleUdt2"
        )
        assert project.controller_tags["a_simple_udt_2x2"].data_type == "SimpleUdt2"
        element = project.controller_tags["d_simple_udt"].value_element
        assert element.get("DataType") == "SimpleUdt2"
        array = project.controller_tags["a_simple_udt_2x2"].value_element
        assert array.get("DataType") == "SimpleUdt2"
        mix = project.controller_tags["d_DefMix"].value_element
        assert mix.find("StructureMember[@Name='su']").get("DataType") == "SimpleUdt2"
        snap = {
            "root": project.controller_tags["d_simple_udt"].to_python(),
            "array": project.controller_tags["a_simple_udt_2x2"].to_python(),
            "nested": project.controller_tags["d_A_UDT"].to_python()["a_nested_UDT"],
            "mix": project.controller_tags["d_DefMix"].to_python()["su"],
        }
        assert snap == values_before
        assert list(project.data_types).index("SimpleUdt2") == list(
            load(str(FIXTURES / "type_defaults_Tags.L5X")).data_types
        ).index("simple_udt")
        assert loads(text).data_types["SimpleUdt2"].name == "SimpleUdt2"

    def test_string_type_everywhere(self) -> None:
        """Arrays, DATA members, AOI parameters and local tags follow."""
        project = _example()
        project.data_types.rename("robotAlarmCode", "AlarmCode2")
        text = project.to_string()
        assert 'DataType="robotAlarmCode"' not in text
        assert 'Name="robotAlarmCode"' in text  # the AOI local tag keeps its name
        assert project.data_types["AlarmCode2"].family == "StringFamily"
        alarms = project.controller_tags["ALLOWABLE_ALARMS"]
        assert alarms.data_type == "AlarmCode2"
        assert alarms.value_element.get("DataType") == "AlarmCode2"
        assert alarms.to_python()[1] == "SRVO-003"
        data = alarms[1].value_element.find("DataValueMember[@Name='DATA']")
        assert data.get("DataType") == "AlarmCode2"
        aoi = project.aois["FanucAlarmLookup"]
        assert aoi.parameters["allowableAlarms"].data_type == "AlarmCode2"
        assert aoi.local_tags["robotAlarmCode"].data_type == "AlarmCode2"
        assert (
            loads(text).controller_tags["ALLOWABLE_ALARMS"].to_python()[1] == "SRVO-003"
        )

    def test_case_only_rename(self) -> None:
        """A case-only change of the type itself is allowed."""
        project = _golden()
        project.data_types.rename("simple_udt", "Simple_Udt")
        assert "Simple_Udt" in project.data_types

    @pytest.mark.parametrize(
        "new", ["a_udt", "debounce", "timer", "DINT", "1x", "a__b"]
    )
    def test_errors(self, new: str) -> None:
        """Taken or invalid names are rejected and nothing changes."""
        project = _example()
        before = project.to_string()
        with pytest.raises(ValueError):
            project.data_types.rename("simple_udt", new)
        assert project.to_string() == before

    def test_missing(self) -> None:
        """A missing name raises KeyError."""
        with pytest.raises(KeyError):
            _example().data_types.rename("nope", "x")


class TestRemove:
    """remove, with and without users."""

    def test_in_use(self) -> None:
        """A used type is refused and the users are listed."""
        project = _example()
        before = project.to_string()
        with pytest.raises(ValueError) as error:
            project.data_types.remove("simple_udt")
        message = str(error.value)
        assert "data type A_UDT member a_nested_UDT" in message
        assert "program MainProgram tag a_simple_udt_instance" in message
        assert project.to_string() == before

    def test_users_list(self) -> None:
        """users() reports tags, members, AOI parameters and local tags."""
        project = _example()
        assert "controller tag ALLOWABLE_ALARMS" in project.data_types.users(
            "robotAlarmCode"
        )
        users = project.data_types.users("robotAlarmCode")
        assert "AOI FanucAlarmLookup parameter allowableAlarms" in users
        assert "AOI FanucAlarmLookup local tag robotAlarmCode" in users

    def test_force(self) -> None:
        """force removes a used type."""
        project = _example()
        project.data_types.remove("simple_udt", force=True)
        assert "simple_udt" not in project.data_types

    def test_unused(self) -> None:
        """An unused type is removed without force."""
        project = _example()
        project.data_types.add(DataTypeSpec("Temp", [MemberSpec("a", "DINT")]))
        project.data_types.remove("Temp")
        assert "Temp" not in project.data_types
        assert "Temp" not in loads(project.to_string()).data_types

    def test_missing(self) -> None:
        """A missing name raises KeyError."""
        with pytest.raises(KeyError):
            _example().data_types.remove("nope")

"""Tests for UDT specs, ``build_datatype`` and ``DataType.to_spec``."""

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_layout import first_difference

from py_l5x import DataTypeSpec, MemberSpec, Project, build_datatype, load
from py_l5x.parsers import layout
from py_l5x.parsers.schema import insert_child_at

FIXTURES = Path(__file__).parent / "fixtures"

#: UDTs whose hidden host names in the fixtures are left over from an older
#: UDT name (``ZZZZZZZZZZrobotUIns0`` instead of ``ZZZZZZZZZZrobotUI0``).
STALE_HOST_UDTS = {"robotUI", "robotUO"}

#: User UDTs whose example.L5X / simple_example.L5X export lacks the
#: <Dependencies> element Studio writes when asked for dependencies.
NO_DEPENDENCIES_IN_EXPORT = {
    "A_UDT",
    "GenericRobotInputs",
    "GenericRobotIO",
    "GenericRobotOutputs",
}


def _user_types(file: str) -> list[str]:
    """List the user UDT names in a fixture.

    Args:
        file: Fixture file name.

    Returns:
        The names of data types with ``Class="User"``.
    """
    project = load(str(FIXTURES / file))
    return [n for n, dt in project.data_types.items() if dt.class_ == "User"]


def _rebuild(project: Project, name: str) -> ET.Element:
    """Rebuild a loaded UDT from its spec.

    Args:
        project: The project.
        name: The UDT name.

    Returns:
        The element built from ``to_spec()``.
    """
    return build_datatype(project.data_types[name].to_spec(), project._type_registry)


def _hidden_names(element: ET.Element) -> list[str]:
    """List the names of a UDT element's hidden members.

    Args:
        element: A ``<DataType>``.

    Returns:
        The host names in order.
    """
    return [
        m.get("Name", "")
        for m in element.findall("Members/Member")
        if m.get("Hidden") == "true"
    ]


def _fix_stale_hosts(built: ET.Element, studio: ET.Element) -> None:
    """Rename built hosts to the stale names Studio's fixture holds.

    Only the text before the trailing member index may differ.

    Args:
        built: The built element, modified in place.
        studio: The loaded element.
    """
    ours, theirs = _hidden_names(built), _hidden_names(studio)
    assert len(ours) == len(theirs)
    rename = dict(zip(ours, theirs, strict=True))
    for ours_name, theirs_name in rename.items():
        assert ours_name.rstrip("0123456789") != theirs_name.rstrip("0123456789")
        assert (
            ours_name[len(ours_name.rstrip("0123456789")) :]
            == (theirs_name[len(theirs_name.rstrip("0123456789")) :])
        )
    for member in built.iter("Member"):
        for attribute in ("Name", "Target"):
            if member.get(attribute) in rename:
                member.set(attribute, rename[member.get(attribute)])


class TestGoldenRebuild:
    """Specs from loaded UDTs rebuild Studio's elements exactly."""

    @pytest.mark.parametrize("name", _user_types("type_defaults_Tags.L5X"))
    def test_type_defaults(self, name: str) -> None:
        """Every user UDT in type_defaults_Tags.L5X rebuilds identically."""
        project = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        built = _rebuild(project, name)
        if name in STALE_HOST_UDTS:
            _fix_stale_hosts(built, project.data_types[name]._element)
        assert first_difference(built, project.data_types[name]._element) is None

    @pytest.mark.parametrize("name", _user_types("example.L5X"))
    def test_example(self, name: str) -> None:
        """Every user UDT in example.L5X rebuilds identically (see exceptions)."""
        project = load(str(FIXTURES / "example.L5X"))
        built = _rebuild(project, name)
        if name in STALE_HOST_UDTS:
            _fix_stale_hosts(built, project.data_types[name]._element)
        if name in NO_DEPENDENCIES_IN_EXPORT:
            dependencies = built.find("Dependencies")
            assert dependencies is not None
            built.remove(dependencies)
            built[-1].tail = "\n"
        assert first_difference(built, project.data_types[name]._element) is None

    def test_dependencies_match_studio_export(self) -> None:
        """The dependencies we add to example.L5X types match type_defaults'."""
        example = load(str(FIXTURES / "example.L5X"))
        golden = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        for name in NO_DEPENDENCIES_IN_EXPORT:
            built = _rebuild(example, name).find("Dependencies")
            studio = golden.data_types[name]._element.find("Dependencies")
            assert first_difference(built, studio) is None

    def test_dependency_repeats_per_member(self) -> None:
        """GenericRobotIO lists robotString once per member, as Studio does."""
        golden = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        built = _rebuild(golden, "GenericRobotIO")
        names = [d.get("Name") for d in built.findall("Dependencies/Dependency")]
        assert names == [
            "GenericRobotInputs",
            "GenericRobotOutputs",
            "robotString",
            "robotString",
        ]

    def test_defmix_dependencies_order(self) -> None:
        """Built-ins are skipped; UDT then AOI in member order."""
        golden = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        built = _rebuild(golden, "DefMix")
        assert [
            (d.get("Type"), d.get("Name"))
            for d in built.findall("Dependencies/Dependency")
        ] == [
            ("DataType", "robotString"),
            ("DataType", "simple_udt"),
            ("AddOnInstructionDefinition", "Debounce"),
        ]


def _hosts(element: ET.Element) -> list[tuple[int, str]]:
    """List the hidden hosts of a built UDT with their member positions.

    Args:
        element: A built ``<DataType>``.

    Returns:
        ``(index, name)`` per hidden member.
    """
    return [
        (i, m.get("Name"))
        for i, m in enumerate(element.findall("Members/Member"))
        if m.get("Hidden") == "true"
    ]


def _bools(count: int, prefix: str = "b") -> list[MemberSpec]:
    """Create plain BOOL members.

    Args:
        count: How many.
        prefix: Name prefix.

    Returns:
        The members.
    """
    return [MemberSpec(f"{prefix}{i}", "BOOL") for i in range(count)]


class TestPacking:
    """BOOL packing rules."""

    def test_ten_bools(self) -> None:
        """Ten BOOLs need two hosts, at positions 0 and 9."""
        built = build_datatype(DataTypeSpec("Ten", _bools(10)))
        assert _hosts(built) == [(0, "ZZZZZZZZZZTen0"), (9, "ZZZZZZZZZZTen9")]
        members = built.findall("Members/Member")
        assert len(members) == 12
        assert [m.get("BitNumber") for m in members if m.get("DataType") == "BIT"] == [
            "0", "1", "2", "3", "4", "5", "6", "7", "0", "1",
        ]  # fmt: skip
        assert members[1].get("Target") == "ZZZZZZZZZZTen0"
        assert members[10].get("Target") == "ZZZZZZZZZZTen9"

    def test_split_by_other_members(self) -> None:
        """A non-BOOL member ends the run and a new host starts."""
        spec = DataTypeSpec(
            "Split",
            [*_bools(2, "a"), MemberSpec("d", "DINT"), *_bools(2, "c")],
        )
        built = build_datatype(spec)
        assert _hosts(built) == [(0, "ZZZZZZZZZZSplit0"), (4, "ZZZZZZZZZZSplit4")]
        assert [m.get("Name") for m in built.findall("Members/Member")] == [
            "ZZZZZZZZZZSplit0", "a0", "a1", "d", "ZZZZZZZZZZSplit4", "c0", "c1",
        ]  # fmt: skip

    def test_seventeen_after_dint(self) -> None:
        """17 BOOLs after a DINT need three hosts at 1, 10 and 19."""
        spec = DataTypeSpec("Seventeen", [MemberSpec("d", "DINT"), *_bools(17)])
        built = build_datatype(spec)
        assert [i for i, _ in _hosts(built)] == [1, 10, 19]
        assert _hosts(built)[0][1] == "ZZZZZZZZZZSeventeen1"

    def test_bool_array_rounds_and_breaks_run(self) -> None:
        """A BOOL array is rounded to 32 and ends the run."""
        spec = DataTypeSpec(
            "Arr",
            [
                *_bools(1, "a"),
                MemberSpec("flags", "BOOL", dimension=10),
                *_bools(1, "c"),
            ],
        )
        built = build_datatype(spec)
        members = built.findall("Members/Member")
        flags = next(m for m in members if m.get("Name") == "flags")
        assert (flags.get("DataType"), flags.get("Dimension")) == ("BOOL", "32")
        assert flags.get("Radix") == "Decimal"
        assert _hosts(built) == [(0, "ZZZZZZZZZZArr0"), (3, "ZZZZZZZZZZArr3")]
        assert members[4].get("BitNumber") == "0"

    @pytest.mark.parametrize(("size", "stored"), [(1, 32), (32, 32), (33, 64)])
    def test_bool_array_sizes(self, size: int, stored: int) -> None:
        """BOOL arrays round up to a multiple of 32."""
        built = build_datatype(
            DataTypeSpec("T", [MemberSpec("f", "BOOL", dimension=size)])
        )
        assert built.find("Members/Member").get("Dimension") == str(stored)

    def test_long_name_truncated(self) -> None:
        """Host names use the first ten characters of the UDT name."""
        built = build_datatype(DataTypeSpec("AVeryLongUdtName", _bools(2)))
        assert _hosts(built) == [(0, "ZZZZZZZZZZAVeryLongU0")]

    def test_short_name(self) -> None:
        """Short names are used whole."""
        built = build_datatype(DataTypeSpec("A_UDT", _bools(1)))
        assert _hosts(built)[0][1] == "ZZZZZZZZZZA_UDT0"

    def test_no_bools_no_hosts(self) -> None:
        """Without BOOLs there are no hidden members."""
        built = build_datatype(DataTypeSpec("T", [MemberSpec("a", "DINT")]))
        assert _hosts(built) == []


class TestAttributesAndChildren:
    """Member attributes, defaults and children."""

    def test_defaults(self) -> None:
        """Radix defaults follow the type; attribute order is Studio's."""
        spec = DataTypeSpec(
            "T",
            [
                MemberSpec("d", "DINT"),
                MemberSpec("r", "REAL"),
                MemberSpec("t", "TIMER"),
                MemberSpec("s", "STRING"),
                MemberSpec("h", "DINT", radix="Hex"),
            ],
        )
        members = build_datatype(spec).findall("Members/Member")
        assert [m.get("Radix") for m in members] == [
            "Decimal", "Float", "NullType", "NullType", "Hex",
        ]  # fmt: skip
        assert list(members[0].attrib) == [
            "Name", "DataType", "Dimension", "Radix", "Hidden", "ExternalAccess",
        ]  # fmt: skip

    def test_extended_properties(self) -> None:
        """Max/Min/ExternalLogging go between Hidden and ExternalAccess."""
        member = MemberSpec(
            "a",
            "SINT",
            description="d",
            engineering_unit="mm",
            min=0,
            max=25.5,
            external_logging=False,
            external_access="Read Only",
        )
        element = build_datatype(DataTypeSpec("T", [member])).find("Members/Member")
        assert list(element.attrib) == [
            "Name", "DataType", "Dimension", "Radix", "Hidden", "Max", "Min",
            "ExternalLogging", "ExternalAccess",
        ]  # fmt: skip
        assert element.get("Max") == "25.5"
        assert element.get("ExternalAccess") == "Read Only"
        assert [c.tag for c in element] == ["Description", "EngineeringUnit"]

    def test_bool_properties(self) -> None:
        """BIT members carry state text and logging after BitNumber."""
        member = MemberSpec(
            "b",
            "BOOL",
            description="d",
            state0="Off",
            state1="On",
            external_logging=True,
        )
        built = build_datatype(DataTypeSpec("T", [member]))
        bit = built.findall("Members/Member")[1]
        assert list(bit.attrib) == [
            "Name", "DataType", "Dimension", "Radix", "Hidden", "Target",
            "BitNumber", "ExternalLogging", "ExternalAccess",
        ]  # fmt: skip
        assert [c.tag for c in bit] == ["Description", "State0", "State1"]

    def test_description_and_layout(self) -> None:
        """Description goes before Members; whitespace is Studio's."""
        spec = DataTypeSpec("T", [MemberSpec("a", "DINT")], description="hi")
        built = build_datatype(spec)
        assert [c.tag for c in built] == ["Description", "Members"]
        assert built.text == "\n"
        assert built.tail is None
        assert all(child.tail == "\n" for child in built)
        assert list(built.attrib.items()) == [
            ("Name", "T"), ("Family", "NoFamily"), ("Class", "User"),
        ]  # fmt: skip

    def test_string_helper(self) -> None:
        """DataTypeSpec.string builds LEN and DATA."""
        spec = DataTypeSpec.string("Str20", 20, "twenty")
        assert spec.family == "StringFamily"
        built = build_datatype(spec)
        members = built.findall("Members/Member")
        assert [
            (m.get("Name"), m.get("DataType"), m.get("Dimension"), m.get("Radix"))
            for m in members
        ] == [
            ("LEN", "DINT", "0", "Decimal"),
            ("DATA", "SINT", "20", "ASCII"),
        ]
        assert built.get("Family") == "StringFamily"

    def test_dependencies_without_registry(self) -> None:
        """Without a registry non-atomic, non-built-in types are DataTypes."""
        spec = DataTypeSpec(
            "T",
            [
                MemberSpec("a", "Other"),
                MemberSpec("t", "TIMER"),
                MemberSpec("d", "DINT"),
                MemberSpec("o", "Other", dimension=3),
            ],
        )
        deps = build_datatype(spec).findall("Dependencies/Dependency")
        assert [(d.get("Type"), d.get("Name")) for d in deps] == [
            ("DataType", "Other"),
            ("DataType", "Other"),
        ]

    def test_aoi_with_registry(self) -> None:
        """A registry marks AOI members as AddOnInstructionDefinition."""
        project = load(str(FIXTURES / "example.L5X"))
        spec = DataTypeSpec(
            "T", [MemberSpec("d", "Debounce"), MemberSpec("u", "simple_udt")]
        )
        deps = build_datatype(spec, project._type_registry).findall(
            "Dependencies/Dependency"
        )
        assert [(d.get("Type"), d.get("Name")) for d in deps] == [
            ("AddOnInstructionDefinition", "Debounce"),
            ("DataType", "simple_udt"),
        ]

    def test_no_dependencies_for_builtins(self) -> None:
        """Atomic and built-in members give no Dependencies element."""
        spec = DataTypeSpec(
            "T", [MemberSpec("t", "TIMER"), MemberSpec("s", "STRING"), *_bools(2)]
        )
        assert build_datatype(spec).find("Dependencies") is None


class TestValidation:
    """Spec validation."""

    @pytest.mark.parametrize("name", ["1abc", "a__b", "a_", "x" * 41, "a b", ""])
    def test_bad_udt_name(self, name: str) -> None:
        """Invalid UDT names are rejected."""
        with pytest.raises(ValueError, match="data type name"):
            build_datatype(DataTypeSpec(name, [MemberSpec("a", "DINT")]))

    @pytest.mark.parametrize("name", ["1abc", "a__b", "a_", "x" * 41, "a b", ""])
    def test_bad_member_name(self, name: str) -> None:
        """Invalid member names are rejected."""
        with pytest.raises(ValueError, match="member name"):
            build_datatype(DataTypeSpec("T", [MemberSpec(name, "DINT")]))

    def test_duplicate_member_ignoring_case(self) -> None:
        """Duplicate member names are rejected case-insensitively."""
        spec = DataTypeSpec("T", [MemberSpec("a", "DINT"), MemberSpec("A", "INT")])
        with pytest.raises(ValueError, match="already exists"):
            build_datatype(spec)

    @pytest.mark.parametrize("dimension", [-1, 2.5, "3", True, (2, 3)])
    def test_bad_dimension(self, dimension: object) -> None:
        """Negative and non-integer (multi-dimensional) sizes are rejected."""
        spec = DataTypeSpec("T", [MemberSpec("a", "DINT", dimension=dimension)])
        with pytest.raises(ValueError, match="dimension"):
            build_datatype(spec)

    def test_self_typed_member(self) -> None:
        """A member of the UDT's own type is rejected."""
        with pytest.raises(ValueError, match="own type"):
            build_datatype(DataTypeSpec("T", [MemberSpec("a", "T")]))

    def test_bit_and_family_and_minmax(self) -> None:
        """BIT, an unknown family, and BOOL min/max are rejected."""
        with pytest.raises(ValueError, match="BOOL, not BIT"):
            build_datatype(DataTypeSpec("T", [MemberSpec("a", "BIT")]))
        with pytest.raises(ValueError, match="family"):
            build_datatype(DataTypeSpec("T", [MemberSpec("a", "DINT")], family="x"))
        with pytest.raises(ValueError, match="min/max"):
            build_datatype(DataTypeSpec("T", [MemberSpec("a", "BOOL", min=0)]))


class TestWithReader:
    """Built elements work with the reader and the layout module."""

    @pytest.fixture
    def project(self) -> Project:
        """An example project with a UDT added by hand."""
        project = load(str(FIXTURES / "example.L5X"))
        spec = DataTypeSpec(
            "NewUdt",
            [
                MemberSpec("a", "BOOL", description="first"),
                MemberSpec("b", "BOOL"),
                MemberSpec("n", "DINT", radix="Hex"),
                *_bools(8, "c"),
                MemberSpec("t", "TIMER"),
                MemberSpec("arr", "REAL", dimension=2),
            ],
            description="new",
        )
        container = project.controller_element.find("DataTypes")
        insert_child_at(
            container, len(container), build_datatype(spec, project._type_registry)
        )
        return project

    def test_reads_back(self, project: Project) -> None:
        """Members, descriptions, visible members and bit groups read back."""
        udt = project.data_types["NewUdt"]
        assert udt.description == "new"
        assert udt.class_ == "User"
        names = list(udt.members)
        assert names[:4] == ["ZZZZZZZZZZNewUdt0", "a", "b", "n"]
        assert udt.members["a"].data_type == "BIT"
        assert udt.members["a"].description == "first"
        assert list(udt.visible_members)[:3] == ["a", "b", "n"]
        assert "ZZZZZZZZZZNewUdt0" not in udt.visible_members
        groups = udt.bit_groups
        assert [len(v) for v in groups.values()] == [2, 8]
        assert list(groups)[0] == "ZZZZZZZZZZNewUdt0"

    def test_default_value_tree(self, project: Project) -> None:
        """The layout module sees BOOL members in order after the host is hidden."""
        element = layout.default_value_element("NewUdt", project._type_registry)
        children = [(c.tag, c.get("Name")) for c in element]
        assert children[:3] == [
            ("DataValueMember", "a"),
            ("DataValueMember", "b"),
            ("DataValueMember", "n"),
        ]
        assert [c.get("Name") for c in element][3:11] == [f"c{i}" for i in range(8)]
        assert children[-2:] == [("StructureMember", "t"), ("ArrayMember", "arr")]
        assert element.find("DataValueMember[@Name='n']").get("Value") == "16#0000_0000"
        assert element.find("DataValueMember[@Name='a']").get("DataType") == "BOOL"

    def test_serialized_round_trip(self, project: Project) -> None:
        """Serialize and reload; to_spec gives the same spec again."""
        from py_l5x import loads

        again = loads(project.to_string())
        assert (
            again.data_types["NewUdt"].to_spec()
            == project.data_types["NewUdt"].to_spec()
        )


class TestToSpec:
    """DataType.to_spec."""

    def test_drops_hosts_and_unpacks_bits(self) -> None:
        """Hosts disappear and BIT members become BOOL."""
        project = load(str(FIXTURES / "example.L5X"))
        spec = project.data_types["A_UDT"].to_spec()
        assert [m.name for m in spec.members][:3] == ["a_Bool", "on_off_bool", "a_sint"]
        assert spec.members[0].data_type == "BOOL"
        assert all(not m.name.startswith("ZZZZ") for m in spec.members)

    def test_extended_properties_kept(self) -> None:
        """Descriptions, units, states, min/max and logging are kept."""
        project = load(str(FIXTURES / "example.L5X"))
        members = {m.name: m for m in project.data_types["A_UDT"].to_spec().members}
        assert members["a_Bool"].description == "This is a bool"
        flag = members["on_off_bool"]
        assert (flag.engineering_unit, flag.state0, flag.state1) == (
            "Boolean",
            "Off",
            "On",
        )
        assert flag.external_logging is True
        props = members["a_sint_with_props"]
        assert (props.min, props.max, props.external_logging) == ("0", "25", False)
        assert props.engineering_unit == "mm"

    def test_radix_none_when_default(self) -> None:
        """Default radixes become None; others are kept."""
        project = load(str(FIXTURES / "example.L5X"))
        members = {m.name: m for m in project.data_types["A_UDT"].to_spec().members}
        assert members["a_dint"].radix is None
        assert members["a_nested_UDT"].radix is None
        assert members["a_real"].radix is None
        golden = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        data = {m.name: m for m in golden.data_types["robotString"].to_spec().members}
        assert data["DATA"].radix == "ASCII"
        assert data["DATA"].dimension == 100
        assert golden.data_types["robotString"].to_spec().family == "StringFamily"

    def test_json_round_trip(self) -> None:
        """A spec survives asdict -> JSON -> reconstruction and rebuilds the same."""
        project = load(str(FIXTURES / "type_defaults_Tags.L5X"))
        spec = project.data_types["A_UDT"].to_spec()
        loaded = DataTypeSpec.from_dict(json.loads(json.dumps(spec.to_dict())))
        assert loaded == spec
        assert (
            first_difference(
                build_datatype(loaded, project._type_registry),
                build_datatype(spec, project._type_registry),
            )
            is None
        )

    def test_spec_uses_only_plain_types(self) -> None:
        """Every spec field is str, int, float, bool, None or list."""
        project = load(str(FIXTURES / "example.L5X"))
        data = project.data_types["A_UDT"].to_spec().to_dict()
        assert json.loads(json.dumps(data)) == data

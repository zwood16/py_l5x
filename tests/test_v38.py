"""Studio 5000 v38 support: the cumulative type table and TIMER_T."""

import copy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_layout import first_difference

from py_l5x import (
    AOISpec,
    DataTypeSpec,
    LocalTagSpec,
    MemberSpec,
    Project,
    RoutineSpec,
    TagSpec,
    build_aoi,
    build_datatype,
    build_tag,
    export_component,
    load,
    loads,
)
from py_l5x.parsers import layout
from py_l5x.parsers.layout import builtin_table, default_data_element
from py_l5x.parsers.tag import BoolNode, TimeNode

FIXTURES = Path(__file__).parent / "fixtures"


def _v38() -> Project:
    """Load Studio's v38 TIMER_T export.

    Returns:
        The parsed project.
    """
    return load(str(FIXTURES / "v38_timer_t_Tags.L5X"))


def _comparable(element: ET.Element) -> ET.Element:
    """Strip L5K data and the component ``Use`` marker.

    Args:
        element: An exported element.

    Returns:
        A stripped copy.
    """
    copy_ = copy.deepcopy(element)
    for parent in copy_.iter():
        for child in list(parent):
            if child.tag in ("Data", "DefaultData") and child.get("Format") == "L5K":
                parent.remove(child)
    copy_.attrib.pop("Use", None)
    return copy_


def _default_for(project: Project, name: str) -> ET.Element:
    """Generate the default ``<Data>`` for a fixture tag from its attributes.

    Args:
        project: The v38 project.
        name: The tag name.

    Returns:
        The generated element.
    """
    element = project.controller_tags[name]._element
    dims = tuple(int(n) for n in element.get("Dimensions", "").split()) or None
    return default_data_element(
        element.get("DataType", ""),
        project._type_registry,
        dimensions=dims,
        radix=element.get("Radix"),
    )


class TestCumulativeTable:
    """The package table holds v37 plus v38 types."""

    def test_size_and_resource(self) -> None:
        """207 types: the 206 of v37 plus TIMER_T, from the renamed resource."""
        assert layout.BUILTIN_TABLE_RESOURCE == "data/builtin_types.L5X.gz"
        table = builtin_table()
        assert len(table) == 207
        assert {"TIMER", "TIMER_T", "COUNTER", "STRING", "DINT"} <= set(table)

    def test_old_resource_is_gone(self) -> None:
        """Nothing refers to the v37-only file any more."""
        root = Path(__file__).parent.parent
        assert not (root / "py_l5x" / "data" / "builtin_types_v37.L5X.gz").exists()
        assert (
            "builtin_types_v37" not in (root / "py_l5x/parsers/layout.py").read_text()
        )

    def test_timer_t_member_order(self) -> None:
        """TIMER_T is ACC, PRE, EN, TT, DN (ACC before PRE, unlike TIMER)."""
        names = [c.get("Name") for c in builtin_table()["TIMER_T"][0]]
        assert names == ["ACC", "PRE", "EN", "TT", "DN"]
        timer = [c.get("Name") for c in builtin_table()["TIMER"][0]]
        assert timer == ["PRE", "ACC", "EN", "TT", "DN"]

    def test_timer_t_default_matches_studio(self) -> None:
        """The generated default equals d_TIMER_T in Studio's export."""
        project = _v38()
        generated = default_data_element("TIMER_T", project._type_registry)
        studio = project.controller_tags["d_TIMER_T"]._element.find("Data")
        assert first_difference(generated, studio) is None
        members = {m.get("Name"): m for m in generated[0]}
        assert members["ACC"].attrib == {
            "Name": "ACC",
            "DataType": "TIME",
            "Radix": "Time (us)",
            "Value": "T#0us",
        }


class TestTimerTUse:
    """Using TIMER_T through the write API."""

    def test_add_with_value(self) -> None:
        """add() with a dict value sets PRE and round trips."""
        project = _v38()
        tag = project.controller_tags.add("t", "TIMER_T", value={"PRE": "T#5s"})
        assert tag.to_python() == {
            "ACC": "T#0us",
            "PRE": "T#5s",
            "EN": False,
            "TT": False,
            "DN": False,
        }
        again = loads(project.to_string()).controller_tags["t"].to_python()
        assert again == tag.to_python()

    def test_add_with_value_without_project_types(self) -> None:
        """TIMER_T needs no project definition."""
        project = loads(
            '<RSLogix5000Content><Controller Name="C"><Tags/></Controller>'
            "</RSLogix5000Content>"
        )
        tag = project.controller_tags.add("t", "TIMER_T", value={"PRE": 5000000})
        assert tag.to_python()["PRE"] == "T#5s"

    def test_initialize_data(self) -> None:
        """initialize_data on a data-less TIMER_T tag gives the default tree."""
        project = _v38()
        element = project.controller_tags["d_TIMER_T"]._element
        element.remove(element.find("Data"))
        tag = project.controller_tags["d_TIMER_T"]
        assert tag.value_element is None
        tag.initialize_data()
        assert tag.to_python()["ACC"] == "T#0us"
        assert isinstance(tag.members["PRE"], TimeNode)
        assert isinstance(tag.members["EN"], BoolNode)

    def test_array_and_dict_values(self) -> None:
        """TIMER_T arrays take lists and index dicts of dicts."""
        project = _v38()
        tag = project.controller_tags["a_TIMER_T_3"]
        tag.value = [{"PRE": "T#1m"}, {}, {"ACC": "T#2s"}]
        data = tag.to_python()
        assert data[0]["PRE"] == "T#1m"
        assert data[2]["ACC"] == "T#2s"
        tag.value = {1: {"PRE": "T#1h30m"}}
        assert tag.to_python()[1]["PRE"] == "T#1h_30m"

    def test_data_types_add_accepts_timer_t(self) -> None:
        """A UDT with a TIMER_T member is accepted and lists no Dependency."""
        project = _v38()
        added = project.data_types.add(
            DataTypeSpec(
                "HasTT", [MemberSpec("t", "TIMER_T"), MemberSpec("u", "UdtTT")]
            )
        )
        deps = [
            d.get("Name") for d in added._element.findall("Dependencies/Dependency")
        ]
        assert deps == ["UdtTT"]
        assert "TIMER_T" not in deps

    def test_build_datatype_has_no_timer_t_dependency(self) -> None:
        """TIMER_T is built in, so it is never a Dependency."""
        element = build_datatype(
            DataTypeSpec("OnlyTT", [MemberSpec("t", "TIMER_T", dimension=2)])
        )
        assert element.find("Dependencies") is None

    def test_build_aoi_local(self) -> None:
        """A TIMER_T local gets a default tree, a value and no Dependency."""
        spec = AOISpec(
            "UsesTT",
            [],
            [LocalTagSpec("t", "TIMER_T", default={"PRE": "T#1m"})],
            [RoutineSpec("Logic")],
        )
        element = build_aoi(spec, _v38()._type_registry)
        pre = element.find("LocalTags/LocalTag/DefaultData/Structure/*[@Name='PRE']")
        assert pre.get("Value") == "T#1m"
        assert element.find("Dependencies") is None

    def test_tag_spec_round_trip(self) -> None:
        """build_tag of a TIMER_T spec equals what add produces."""
        project = _v38()
        spec = TagSpec("t", "TIMER_T", value={"ACC": "T#1s_250ms", "PRE": "T#1h30m"})
        built = build_tag(spec, project._type_registry)
        added = project.controller_tags.add(
            "t", "TIMER_T", value={"ACC": "T#1s_250ms", "PRE": "T#1h30m"}
        )
        assert first_difference(built, added._element) is None


class TestV38Fixture:
    """Studio's own v38 export."""

    def test_reader(self) -> None:
        """tt_values reads as strings and bools; members are typed nodes."""
        tag = _v38().controller_tags["tt_values"]
        assert tag.to_python() == {
            "ACC": "T#1s_250ms",
            "PRE": "T#1h_30m",
            "EN": True,
            "TT": True,
            "DN": False,
        }
        assert isinstance(tag.members["ACC"], TimeNode)
        assert isinstance(tag.members["PRE"], TimeNode)
        assert all(isinstance(tag.members[n], BoolNode) for n in ("EN", "TT", "DN"))
        assert tag.members["ACC"].count == 1_250_000
        assert tag.members["PRE"].count == 5_400_000_000

    def test_every_tag_rebuilds_from_its_spec(self) -> None:
        """Every fixture tag's spec rebuilds the tag identically."""
        project = _v38()
        for name, tag in project.controller_tags.items():
            built = build_tag(tag.to_spec(), project._type_registry)
            assert first_difference(built, _comparable(tag._element)) is None, name

    def test_udt_rebuilds_identically(self) -> None:
        """UdtTT rebuilds from its spec exactly (hidden-host BOOL included)."""
        project = _v38()
        data_type = project.data_types["UdtTT"]
        built = build_datatype(data_type.to_spec(), project._type_registry)
        assert first_difference(built, _comparable(data_type._element)) is None
        names = [m.get("Name") for m in built.findall("Members/Member")]
        assert names[1] == "run"
        assert [d.get("Name") for d in built.findall("Dependencies/Dependency")] == []
        member = project.data_types["UdtTT"].members["t"]
        assert member.description

    def test_aoi_rebuilds_identically(self) -> None:
        """AoiTT rebuilds from its spec exactly.

        Studio's export of this AOI has no Description on EnableIn/EnableOut
        (it echoes the SDK import, which had none), while the builder always
        writes the system descriptions; those two are removed before comparing.
        """
        project = _v38()
        aoi = project.aois["AoiTT"]
        built = build_aoi(aoi.to_spec(), project._type_registry)
        for parameter in built.findall("Parameters/Parameter"):
            if parameter.get("Name") in ("EnableIn", "EnableOut"):
                for description in parameter.findall("Description"):
                    parameter.remove(description)
                parameter.text = None
        assert first_difference(built, _comparable(aoi._element)) is None
        local = aoi.local_tags["t"]
        assert local.data_type == "TIMER_T"

    @pytest.mark.parametrize("name", ["d_TIMER_T", "a_TIMER_T_3", "d_UdtTT", "d_AoiTT"])
    def test_layout_defaults_match_studio(self, name: str) -> None:
        """Generated defaults equal Studio's trees exactly."""
        project = _v38()
        studio = project.controller_tags[name]._element.find(
            "Data[@Format='Decorated']"
        )
        assert first_difference(_default_for(project, name), studio) is None


class TestExportHeader:
    """SoftwareRevision of component exports."""

    def test_source_revision_is_written(self) -> None:
        """A v38 project exports 38.03."""
        project = _v38()
        exported = project.export(project.data_types["UdtTT"])
        assert exported.root.get("SoftwareRevision") == "38.03"
        example = load(str(FIXTURES / "example.L5X"))
        assert (
            example.export(example.data_types["A_UDT"]).root.get("SoftwareRevision")
            == "37.00"
        )

    def test_fallback_without_revision_or_project(self) -> None:
        """Without a revision on the project, or without a project, it is 37.00."""
        assert export_component(TagSpec("n", "DINT")).root.get("SoftwareRevision") == (
            "37.00"
        )
        project = _v38()
        del project.root.attrib["SoftwareRevision"]
        exported = project.export(project.data_types["UdtTT"])
        assert exported.root.get("SoftwareRevision") == "37.00"

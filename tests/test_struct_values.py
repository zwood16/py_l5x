"""Tests for tag initialization, structured assignment and ``to_python``."""

import copy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_layout import first_difference

from py_l5x import Project, load, loads
from py_l5x.parsers.layout import LayoutError

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "type_defaults_Tags.L5X"


def _example() -> Project:
    """Load the main example project.

    Returns:
        The parsed ``example.L5X``.
    """
    return load(str(FIXTURES / "example.L5X"))


def _main(project: Project, name: str):
    """Return a ``MainProgram`` tag.

    Args:
        project: The project.
        name: Tag name.

    Returns:
        The tag.
    """
    return project.programs["MainProgram"].tags[name]


def _stripped() -> tuple[Project, dict]:
    """Load the golden file with every tag's ``Data`` removed.

    Returns:
        The data-less project and each tag's original ``Data`` elements.
    """
    project = load(str(GOLDEN))
    originals = {}
    for tag in project.root.iter("Tag"):
        originals[tag.get("Name")] = [copy.deepcopy(d) for d in tag.findall("Data")]
        for data in tag.findall("Data"):
            tag.remove(data)
    return project, originals


def _golden_names() -> list[str]:
    """List the golden tag names.

    Returns:
        The names.
    """
    return list(load(str(GOLDEN)).controller_tags)


class TestInitializeData:
    """initialize_data materializes Studio's default tree."""

    @pytest.mark.parametrize("name", _golden_names())
    def test_matches_golden(self, name: str) -> None:
        """The created Data equals Studio's, for every golden tag."""
        project, originals = _stripped()
        tag = project.controller_tags[name]
        assert tag.value_element is None
        assert tag.initialize_data() is tag
        created = tag._element.find("Data")
        decorated = [d for d in originals[name] if d.get("Format") != "L5K"]
        assert first_difference(created, decorated[0]) is None
        assert [c.tag for c in tag._element] == ["Data"]

    def test_idempotent(self) -> None:
        """A second call changes nothing."""
        project, _ = _stripped()
        tag = project.controller_tags["d_DefMix"]
        tag.initialize_data()
        before = project.to_string()
        tag.initialize_data()
        assert project.to_string() == before

    def test_same_object_members_and_elements(self) -> None:
        """members/elements work on the object that was initialized."""
        project, _ = _stripped()
        timer = project.controller_tags["a_TIMER_2"]
        assert len(timer) == 0
        timer.initialize_data()
        assert len(timer) == 2
        assert timer[1].members["PRE"].value == 0
        deb = project.controller_tags["d_Debounce"]
        deb.initialize_data()
        assert deb.members["EnableIn"].value is True
        string = project.controller_tags["d_robotString"]
        string.initialize_data()
        assert string.value == ""
        assert string.len == 0
        grid = project.controller_tags["a_DINT_2x3"]
        assert grid.dimensions == (2, 3)
        grid.initialize_data()
        assert len(grid) == 6

    def test_reads_do_not_mutate(self) -> None:
        """Reading members, elements and values never creates data."""
        project, _ = _stripped()
        before = project.to_string()
        for name in project.controller_tags:
            tag = project.controller_tags[name]
            for attribute in ("members", "elements", "dimensions"):
                getattr(tag, attribute, None)
            tag.to_python() if hasattr(tag, "to_python") else None
        assert project.to_string() == before

    def test_builtin_scalars(self) -> None:
        """A built-in structure and STRING initialize from the table."""
        project = loads(
            '<RSLogix5000Content><Controller Name="C"><Tags>'
            '<Tag Name="t" TagType="Base" DataType="TIMER"/>'
            '<Tag Name="s" TagType="Base" DataType="STRING"/>'
            "</Tags></Controller></RSLogix5000Content>"
        )
        project.controller_tags["t"].initialize_data()
        project.controller_tags["s"].initialize_data()
        text = project.to_string()
        assert (
            '<DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="0"/>'
            in text
        )
        assert (
            '<Data Format="String" Length="0">\r\n<![CDATA[\'\']]>\r\n</Data>' in text
        )

    def test_drops_stale_l5k(self) -> None:
        """An existing L5K Data is replaced."""
        project = loads(
            '<RSLogix5000Content><Controller Name="C"><Tags>'
            '<Tag Name="t" TagType="Base" DataType="TIMER">'
            '<Data Format="L5K"><![CDATA[[0,0,0]]]></Data>'
            "</Tag></Tags></Controller></RSLogix5000Content>"
        )
        tag = project.controller_tags["t"]
        tag.initialize_data()
        assert [d.get("Format") for d in tag._element.findall("Data")] == ["Decorated"]

    def test_layout_error(self) -> None:
        """A type without a layout raises LayoutError and changes nothing."""
        project = loads(
            '<RSLogix5000Content><Controller Name="C"><Tags>'
            '<Tag Name="m" TagType="Base" DataType="MESSAGE"/>'
            '<Tag Name="u" TagType="Base" DataType="Unknown"/>'
            "</Tags></Controller></RSLogix5000Content>"
        )
        before = project.to_string()
        with pytest.raises(LayoutError, match="Unknown"):
            project.controller_tags["u"].initialize_data()
        assert project.to_string() == before


class TestAssignment:
    """Dict and list assignment on loaded tags."""

    def test_partial_dict(self) -> None:
        """Only the given members change."""
        project = _example()
        tag = _main(project, "a_udt_instance")
        before = tag.to_python()
        tag.value = {"a_dint": 5, "a_nested_UDT": {"Dint": 7}}
        after = tag.to_python()
        assert after["a_dint"] == 5
        assert after["a_nested_UDT"]["Dint"] == 7
        expected = copy.deepcopy(before)
        expected["a_dint"] = 5
        expected["a_nested_UDT"]["Dint"] = 7
        assert after == expected

    def test_case_insensitive_keeps_spelling(self) -> None:
        """Names match ignoring case; the XML keeps its own spelling."""
        project = _example()
        tag = _main(project, "a_udt_instance")
        tag.value = {"A_DINT": 9, "AN_AOI": {"ondelay": 3}}
        names = [c.get("Name") for c in tag.value_element]
        assert "a_dint" in names
        assert "A_DINT" not in names
        assert tag.members["a_dint"].value == 9
        assert tag.members["an_aoi"].members["onDelay"].value == 3

    def test_array_member_list_and_dict(self) -> None:
        """Array members take a list or an index dict."""
        project = _example()
        tag = _main(project, "a_udt_instance")
        tag.value = {"an_array": [1.5, 2.5, 3.5, 4.5]}
        assert tag.members["an_array"].to_python() == [1.5, 2.5, 3.5, 4.5]
        tag.value = {"an_array": {0: 9.0, -1: 8.0}}
        assert tag.members["an_array"].to_python() == [9.0, 2.5, 3.5, 8.0]

    def test_array_nested_flat_and_index_dict(self) -> None:
        """A 2-D array takes nested lists, a flat list and subscripts."""
        project = _example()
        grid = _main(project, "a_2d_array")
        grid.value = [[1, 2, 3], [4, 5, 6]]
        assert grid.to_python() == [[1, 2, 3], [4, 5, 6]]
        grid.value = [6, 5, 4, 3, 2, 1]
        assert grid.to_python() == [[6, 5, 4], [3, 2, 1]]
        grid.value = {(1, 2): 99, 0: 7}
        assert grid.to_python() == [[7, 5, 4], [3, 2, 99]]

    def test_string_array_elements(self) -> None:
        """String elements take str values."""
        project = _example()
        alarms = project.controller_tags["ALLOWABLE_ALARMS"]
        alarms.value = {0: "AAA", 1: "BBB"}
        assert alarms[0].value == "AAA"
        assert alarms[1].len == 3
        assert alarms.to_python()[2] == "SYST-043"

    def test_l5k_dropped_and_round_trip(self) -> None:
        """A tag without AOI data loses its L5K; values survive a reload."""
        project = _example()
        tag = _main(project, "a_2d_array")
        assert tag._element.find("Data[@Format='L5K']") is not None
        before = project.to_string().count('Format="L5K"')
        tag.value = {(0, 1): 11}
        assert tag._element.find("Data[@Format='L5K']") is None
        text = project.to_string()
        assert text.count('Format="L5K"') == before - 1
        again = loads(text).programs["MainProgram"].tags["a_2d_array"]
        assert again.to_python() == tag.to_python()

    def test_l5k_kept_for_tags_containing_aoi_instances(self) -> None:
        """A UDT with an AOI member keeps its L5K block through a write."""
        project = _example()
        tag = _main(project, "a_udt_instance")
        l5k = ET.tostring(tag._element.find("Data[@Format='L5K']"))
        tag.value = {"a_dint": 11, "an_aoi": {"onDelay": 3}}
        assert ET.tostring(tag._element.find("Data[@Format='L5K']")) == l5k
        again = (
            loads(project.to_string()).programs["MainProgram"].tags["a_udt_instance"]
        )
        assert again.to_python() == tag.to_python()

    def test_mixed_defaults_on_dataless(self) -> None:
        """A data-less UDT is initialized and then assigned."""
        project, _ = _stripped()
        tag = project.controller_tags["d_DefMix"]
        tag.value = {
            "s": "hi",
            "rs": "yo",
            "t": {"PRE": 100},
            "ta": [{"PRE": 1}, {"ACC": 2}],
            "flags": {3: True},
            "x": [1.0, 2.0, 3.0],
            "deb": {"onDelay": 5},
            "b1": 1,
        }
        data = tag.to_python()
        assert data["s"] == "hi"
        assert data["rs"] == "yo"
        assert data["t"]["PRE"] == 100
        assert data["ta"][0]["PRE"] == 1
        assert data["ta"][1]["ACC"] == 2
        assert data["flags"][3] is True
        assert data["flags"][4] is False
        assert data["x"] == [1.0, 2.0, 3.0]
        assert data["deb"]["onDelay"] == 5
        assert data["deb"]["EnableIn"] is True
        assert data["b1"] is True
        again = loads(project.to_string()).controller_tags["d_DefMix"]
        assert again.to_python() == data

    def test_dataless_array_list(self) -> None:
        """A data-less array takes a list and materializes."""
        project, _ = _stripped()
        grid = project.controller_tags["a_DINT_2x3"]
        grid.value = [[1, 2, 3], [4, 5, 6]]
        assert grid.to_python() == [[1, 2, 3], [4, 5, 6]]
        timers = project.controller_tags["a_TIMER_2"]
        timers.value = [{"PRE": 1}, {"PRE": 2}]
        assert [t["PRE"] for t in timers.to_python()] == [1, 2]

    def test_aoi_local_tag_default(self) -> None:
        """AOI local tags with DefaultData accept dict assignment."""
        project = _example()
        local = project.aois["Debounce"].local_tags["debounceOnTimer"]
        assert local._element.find("DefaultData[@Format='L5K']") is not None
        local.value = {"PRE": 12}
        assert local.members["PRE"].value == 12
        assert local._element.find("DefaultData[@Format='L5K']") is None


class TestAtomicity:
    """A failed assignment changes nothing."""

    def test_bad_leaf_deep_in_dict(self) -> None:
        """One bad leaf leaves the document byte-identical."""
        project = _example()
        tag = _main(project, "a_udt_instance")
        before = project.to_string()
        with pytest.raises(TypeError):
            tag.value = {
                "a_dint": 5,
                "a_real": 2.5,
                "a_nested_UDT": {"bool1": True, "Dint": "oops"},
            }
        assert project.to_string() == before

    def test_out_of_range_in_array(self) -> None:
        """A bad element in a list changes none of them."""
        project = _example()
        grid = _main(project, "a_2d_array")
        before = project.to_string()
        with pytest.raises(ValueError):
            grid.value = [1, 2, 3, 4, 5, 500]
        assert project.to_string() == before

    def test_dataless_failure_creates_no_data(self) -> None:
        """A failed assignment on a data-less tag leaves it data-less."""
        project, _ = _stripped()
        tag = project.controller_tags["d_DefMix"]
        before = project.to_string()
        with pytest.raises(TypeError):
            tag.value = {"t": {"PRE": 1}, "deb": {"onDelay": "bad"}}
        assert project.to_string() == before
        assert tag._element.find("Data") is None

    def test_string_too_long_leaf(self) -> None:
        """A too-long string member aborts the whole assignment."""
        project, _ = _stripped()
        tag = project.controller_tags["d_DefMix"]
        before = project.to_string()
        with pytest.raises(ValueError):
            tag.value = {"t": {"PRE": 1}, "s": "x" * 100}
        assert project.to_string() == before

    def test_bad_member_name_first(self) -> None:
        """An unknown name aborts even after valid ones."""
        project = _example()
        tag = _main(project, "a_udt_instance")
        before = project.to_string()
        with pytest.raises(KeyError):
            tag.value = {"a_dint": 1, "nope": 2}
        assert project.to_string() == before


class TestErrors:
    """Error cases."""

    def test_unknown_member(self) -> None:
        """An unknown member raises KeyError."""
        with pytest.raises(KeyError, match="nope"):
            _main(_example(), "a_udt_instance").value = {"nope": 1}

    def test_duplicate_member_ignoring_case(self) -> None:
        """Names repeating ignoring case raise ValueError."""
        with pytest.raises(ValueError, match="more than once"):
            _main(_example(), "a_udt_instance").value = {"a_dint": 1, "A_DINT": 2}

    @pytest.mark.parametrize("bad", [[1, 2], [1, 2, 3, 4, 5, 6, 7], [[1, 2], [3, 4]]])
    def test_wrong_list_length(self, bad: list) -> None:
        """A list that doesn't match the element count raises ValueError."""
        with pytest.raises(ValueError):
            _main(_example(), "a_2d_array").value = bad

    @pytest.mark.parametrize("key", [6, -7, (2, 0), (0, 3)])
    def test_bad_index(self, key: object) -> None:
        """Out of range indexes raise IndexError."""
        with pytest.raises(IndexError):
            _main(_example(), "a_2d_array").value = {key: 1}

    @pytest.mark.parametrize("key", ["a", 1.5, True, None])
    def test_bad_index_type(self, key: object) -> None:
        """Index keys must be int or tuple."""
        with pytest.raises(TypeError):
            _main(_example(), "a_2d_array").value = {key: 1}

    def test_wrong_container_types(self) -> None:
        """Lists for structures and scalars for aggregates are rejected."""
        project = _example()
        with pytest.raises(TypeError):
            _main(project, "a_udt_instance").value = [1, 2]
        with pytest.raises(TypeError):
            _main(project, "a_2d_array").value = 5
        with pytest.raises(TypeError):
            _main(project, "a_udt_instance").value = {"a_nested_UDT": 5}
        with pytest.raises(TypeError):
            _main(project, "a_udt_instance").value = {"an_array": "text"}

    def test_wrong_leaf_types(self) -> None:
        """Leaf validation reuses the scalar setters."""
        project = _example()
        tag = _main(project, "a_udt_instance")
        with pytest.raises(TypeError):
            tag.value = {"a_dint": "5"}
        with pytest.raises(ValueError):
            tag.value = {"a_sint": 300}
        with pytest.raises(TypeError):
            tag.value = {"a_Bool": "yes"}

    def test_non_string_key(self) -> None:
        """Member names must be str."""
        with pytest.raises(TypeError):
            _main(_example(), "a_udt_instance").value = {1: 2}

    def test_value_read_still_raises(self) -> None:
        """Structures and arrays keep raising on a value read."""
        project = _example()
        assert not hasattr(_main(project, "a_udt_instance"), "value")
        assert not hasattr(_main(project, "a_2d_array"), "value")

    def test_bit_nodes_not_assignable(self) -> None:
        """Assigning into a bit via a dict is a TypeError (no backing element)."""
        project = _example()
        with pytest.raises(TypeError):
            _main(project, "a_dint").bit(1).value = True


class TestToPython:
    """to_python on fixture tags."""

    def test_struct(self) -> None:
        """A TIMER becomes a dict in member order."""
        timer = _main(_example(), "a_timer").to_python()
        assert timer == {"PRE": 0, "ACC": 0, "EN": False, "TT": False, "DN": False}
        assert list(timer) == ["PRE", "ACC", "EN", "TT", "DN"]

    def test_nested(self) -> None:
        """Nested structures, arrays and AOI members convert recursively."""
        data = _main(_example(), "a_udt_instance").to_python()
        assert data["a_nested_UDT"]["Dint"] == 0
        assert data["an_array"] == [0.0, 0.0, 0.0, 0.0]
        assert data["an_aoi"]["holdTime"] == 500
        assert data["an_aoi"]["EnableIn"] is True
        assert data["a_real"] == 0.0

    def test_arrays(self) -> None:
        """Arrays nest per dimension."""
        project = _example()
        assert _main(project, "a_2d_array").to_python() == [[0, 0, 0], [0, 0, 0]]
        cube = _main(project, "a_3d_array").to_python()
        assert len(cube) == 2
        assert len(cube[0]) == 3
        assert len(cube[0][0]) == 4

    def test_strings(self) -> None:
        """Strings convert to str, in arrays too."""
        project = _example()
        assert _main(project, "a_string").to_python() == ""
        alarms = project.controller_tags["ALLOWABLE_ALARMS"].to_python()
        assert len(alarms) == 20
        assert alarms[1] == "SRVO-003"

    def test_atomics(self) -> None:
        """Atomic tags return their scalar."""
        project = _example()
        assert _main(project, "a_dint").to_python() == 0
        assert _main(project, "a_real").to_python() == 0.0
        assert _main(project, "a_bool").to_python() is False
        assert _main(project, "duration").to_python() == "T#0us"
        assert (
            _main(project, "datetime").to_python() == "DT#1970-01-01-00:00:00.000_000Z"
        )

    def test_every_radix_golden_tag(self) -> None:
        """to_python equals value for all golden atomic tags."""
        project = load(str(FIXTURES / "radix_values_Tags.L5X"))
        for tag in project.controller_tags.values():
            assert tag.to_python() == tag.value

    def test_dataless_empty(self) -> None:
        """Data-less tags convert to empty values without creating data."""
        project, _ = _stripped()
        before = project.to_string()
        assert project.controller_tags["d_DefMix"].to_python() == {}
        assert project.controller_tags["a_TIMER_2"].to_python() == []
        assert project.controller_tags["d_robotString"].to_python() == ""
        assert project.to_string() == before

    def test_round_trip_through_assignment(self) -> None:
        """Assigning a tag's own to_python() back changes nothing semantically."""
        project = _example()
        tag = _main(project, "a_udt_instance")
        data = tag.to_python()
        tag.value = data
        assert tag.to_python() == data


_DOC = """<RSLogix5000Content><Controller Name="C">
<Tags/>
</Controller></RSLogix5000Content>"""


class TestAddWithValue:
    """TagsCollection.add(value=...)."""

    @pytest.fixture
    def tags(self):
        """The golden project's controller tags (UDTs and AOIs defined)."""
        return load(str(GOLDEN)).controller_tags

    def test_atomic_and_string(self, tags) -> None:
        """Scalars and strings are set on creation."""
        assert tags.add("n1", "DINT", value=5).value == 5
        assert tags.add("r1", "REAL", value=1.5).value == 1.5
        assert tags.add("s1", "STRING", value="hi").value == "hi"
        assert tags["n1"].value == 5
        assert tags["s1"].len == 2

    def test_struct(self, tags) -> None:
        """Structures take a dict."""
        timer = tags.add("t1", "TIMER", value={"PRE": 10})
        assert timer.to_python()["PRE"] == 10
        mix = tags.add("m1", "DefMix", value={"s": "x", "deb": {"offDelay": 3}})
        assert mix.to_python()["s"] == "x"
        assert mix.to_python()["deb"]["offDelay"] == 3

    def test_arrays(self, tags) -> None:
        """Arrays take lists or index dicts."""
        assert tags.add("a1", "DINT", dimensions=3, value=[1, 2, 3]).to_python() == [
            1,
            2,
            3,
        ]
        grid = tags.add("a2", "DINT", dimensions=(2, 2), value={(1, 1): 4})
        assert grid.to_python() == [[0, 0], [0, 4]]
        timers = tags.add("a3", "TIMER", dimensions=2, value=[{"PRE": 1}, {}])
        assert timers.to_python()[0]["PRE"] == 1

    def test_without_value_has_no_data(self, tags) -> None:
        """No value means no Data, as before."""
        assert tags.add("plain", "TIMER")._element.find("Data") is None

    def test_failed_value_removes_tag(self, tags) -> None:
        """A bad value leaves no tag behind."""
        before = len(tags)
        with pytest.raises(TypeError):
            tags.add("bad", "DINT", value="x")
        with pytest.raises(KeyError):
            tags.add("bad", "TIMER", value={"nope": 1})
        with pytest.raises(LayoutError):
            tags.add("bad", "NoSuchType", value={})
        assert len(tags) == before
        assert "bad" not in tags

    def test_round_trip(self) -> None:
        """Created tags survive serialization."""
        project = load(str(GOLDEN))
        project.controller_tags.add("t1", "TIMER", value={"PRE": 10, "EN": True})
        again = loads(project.to_string()).controller_tags["t1"]
        assert again.to_python() == {
            "PRE": 10,
            "ACC": 0,
            "EN": True,
            "TT": False,
            "DN": False,
        }

    @pytest.mark.parametrize(
        ("requested", "stored"), [(1, 32), (32, 32), (33, 64), (40, 64), (64, 64)]
    )
    def test_bool_rounding(self, tags, requested: int, stored: int) -> None:
        """1-D BOOL sizes round up to a multiple of 32."""
        tag = tags.add("flags", "BOOL", dimensions=requested)
        assert tag._element.get("Dimensions") == str(stored)
        assert tag.dimensions == (stored,)

    def test_bool_array_value_uses_rounded_size(self, tags) -> None:
        """A value list must match the rounded size."""
        with pytest.raises(ValueError):
            tags.add("flags", "BOOL", dimensions=40, value=[False] * 40)
        assert "flags" not in tags
        tag = tags.add("flags", "BOOL", dimensions=40, value={39: True})
        assert tag.to_python()[39] is True
        assert len(tag.to_python()) == 64

    def test_multi_dimensional_bool(self, tags) -> None:
        """Multi-dimensional BOOL arrays are refused."""
        with pytest.raises(ValueError, match="multi-dimensional BOOL"):
            tags.add("flags", "BOOL", dimensions=(2, 3))
        assert "flags" not in tags

    def test_non_bool_dimensions_untouched(self, tags) -> None:
        """Other types keep the requested size."""
        assert tags.add("d", "DINT", dimensions=40)._element.get("Dimensions") == "40"

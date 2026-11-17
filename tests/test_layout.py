"""Tests for default value tree generation (``py_l5x.parsers.layout``)."""

import gzip
from importlib import resources
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x import Project, load
from py_l5x.parsers import layout
from py_l5x.parsers.layout import (
    LayoutError,
    builtin_table,
    default_data_element,
    default_value_element,
    members,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def golden() -> Project:
    """The project holding Studio's default trees for user types."""
    return load(str(FIXTURES / "type_defaults_Tags.L5X"))


def _text(value: str | None) -> str:
    """Normalize ``None`` text to an empty string.

    Args:
        value: Element text or tail.

    Returns:
        The text, ``""`` if ``None``.
    """
    return value or ""


def first_difference(a: ET.Element, b: ET.Element, path: str = "") -> str | None:
    """Find the first difference between two trees, comparing everything.

    Compares tag, ordered attributes, text, children and tails (the top
    element's tail is ignored).

    Args:
        a: The generated element.
        b: Studio's element.
        path: The path so far, for the message.

    Returns:
        A description of the first difference, or ``None`` if identical.
    """
    here = f"{path}/{a.tag}"
    if a.tag != b.tag:
        return f"{here}: tag {a.tag!r} != {b.tag!r}"
    if list(a.attrib.items()) != list(b.attrib.items()):
        return (
            f"{here}: attributes {list(a.attrib.items())} != {list(b.attrib.items())}"
        )
    if _text(a.text) != _text(b.text):
        return f"{here}: text {a.text!r} != {b.text!r}"
    if len(a) != len(b):
        return f"{here}: {len(a)} children != {len(b)}"
    for index, (ca, cb) in enumerate(zip(a, b, strict=True)):
        if _text(ca.tail) != _text(cb.tail):
            return f"{here}/[{index}]: tail {ca.tail!r} != {cb.tail!r}"
        diff = first_difference(ca, cb, f"{here}[{index}]")
        if diff:
            return diff
    return None


def _golden_tags() -> list[str]:
    """List the tag names in the golden file.

    Returns:
        The controller tag names.
    """
    return list(load(str(FIXTURES / "type_defaults_Tags.L5X")).controller_tags)


def _generate(project: Project, tag) -> ET.Element:
    """Generate the ``<Data>`` for a golden tag from its attributes.

    Args:
        project: The project providing the type definitions.
        tag: The golden tag.

    Returns:
        The generated ``<Data>`` element.
    """
    element = tag._element
    dims = tuple(int(n) for n in element.get("Dimensions", "").split()) or None
    return default_data_element(
        element.get("DataType", ""),
        project._type_registry,
        dimensions=dims,
        radix=element.get("Radix"),
    )


class TestGolden:
    """Generated data equals Studio's exactly."""

    @pytest.mark.parametrize("name", _golden_tags())
    def test_identical(self, golden: Project, name: str) -> None:
        """The generated Data matches Studio's, including whitespace."""
        tag = golden.controller_tags[name]
        studio = tag._element.find("Data[@Format='Decorated']")
        if studio is None:
            studio = tag._element.find("Data[@Format='String']")
        assert studio is not None
        assert first_difference(_generate(golden, tag), studio) is None

    def test_all_tags_covered(self, golden: Project) -> None:
        """The golden file has the expected 25 tags."""
        assert len(golden.controller_tags) == 25

    def test_serialized_identical(self, golden: Project) -> None:
        """Serialized with the writer, a tag's Data text equals Studio's."""
        from py_l5x.writer import to_string

        tag = golden.controller_tags["d_DefMix"]
        wrapper_a = ET.Element("W")
        wrapper_a.text = "\n"
        generated = _generate(golden, tag)
        generated.tail = "\n"
        wrapper_a.append(generated)
        wrapper_b = ET.Element("W")
        wrapper_b.text = "\n"
        studio = tag._element.find("Data[@Format='Decorated']")
        wrapper_b.append(studio)
        assert to_string(wrapper_a) == to_string(wrapper_b)


class TestBuiltins:
    """Built-in structure types come from the package table."""

    @pytest.mark.parametrize(
        "name",
        ["TIMER", "COUNTER", "CONTROL", "PID", "MMC", "P_PID", "P_MOTOR_DISCRETE"],
    )
    def test_root_equals_table(self, golden: Project, name: str) -> None:
        """A root built-in equals the table's tree."""
        table = builtin_table()[name]
        generated = default_data_element(name, golden._type_registry)
        assert first_difference(generated, table) is None

    def test_table_size(self) -> None:
        """The table holds all 207 built-in types."""
        assert len(builtin_table()) == 207

    @pytest.mark.parametrize("name", ["STRING", "STRING_16", "STRING_32"])
    def test_builtin_strings(self, golden: Project, name: str) -> None:
        """Built-in string types give the String format at a root."""
        table = builtin_table()[name]
        assert (
            first_difference(default_data_element(name, golden._type_registry), table)
            is None
        )

    def test_member_context(self, golden: Project) -> None:
        """A built-in as a member is a StructureMember with a Name first."""
        element = default_value_element(
            "TIMER", golden._type_registry, context="member", name="t"
        )
        assert element.tag == "StructureMember"
        assert list(element.attrib.items()) == [("Name", "t"), ("DataType", "TIMER")]
        assert [c.get("Name") for c in element] == ["PRE", "ACC", "EN", "TT", "DN"]

    def test_defmix_members(self, golden: Project) -> None:
        """DefMix's t, ta and s match the built-in trees in member/element form."""
        tag = golden.controller_tags["d_DefMix"]
        structure = tag._element.find("Data/Structure")
        by_name = {c.get("Name"): c for c in structure if c.get("Name")}
        registry = golden._type_registry
        assert (
            first_difference(
                default_value_element("TIMER", registry, context="member", name="t"),
                by_name["t"],
            )
            is None
        )
        assert (
            first_difference(
                default_value_element(
                    "TIMER", registry, dimensions=(2,), context="member", name="ta"
                ),
                by_name["ta"],
            )
            is None
        )
        assert (
            first_difference(
                default_value_element("STRING", registry, context="member", name="s"),
                by_name["s"],
            )
            is None
        )

    def test_table_is_not_mutated(self, golden: Project) -> None:
        """Building never alters the cached table."""
        before = ET.tostring(builtin_table()["TIMER"])
        element = default_value_element("TIMER", golden._type_registry)
        element[0].set("Value", "9")
        assert ET.tostring(builtin_table()["TIMER"]) == before


class TestAtomicDefaults:
    """Atomic defaults per radix."""

    @pytest.mark.parametrize(
        ("data_type", "radix", "text"),
        [
            ("DINT", None, "0"),
            ("DINT", "Hex", "16#0000_0000"),
            ("SINT", "Binary", "2#0000_0000"),
            ("INT", "Octal", "8#000_000"),
            ("SINT", "ASCII", "'$00'"),
            ("REAL", None, "0.0"),
            ("REAL", "Exponential", "0.00000000e+000"),
            ("LREAL", "Float", "0.0"),
            ("BOOL", None, "0"),
            ("TIME", None, "T#0us"),
            ("TIME32", None, "T32#0us"),
            ("LTIME", None, "LT#0ns"),
            ("DT", None, "DT#1970-01-01-00:00:00.000_000Z"),
            ("LDT", None, "LDT#1970-01-01-00:00:00.000_000_000Z"),
        ],
    )
    def test_root(self, golden: Project, data_type: str, radix: str, text: str) -> None:
        """Root DataValue carries the default text for its radix."""
        element = default_value_element(data_type, golden._type_registry, radix=radix)
        assert element.tag == "DataValue"
        assert element.get("Value") == text

    @pytest.mark.parametrize(
        "data_type", ["DINT", "SINT", "INT", "LINT", "REAL", "LREAL", "TIME", "BOOL"]
    )
    def test_matches_builtin_table(self, golden: Project, data_type: str) -> None:
        """Atomic roots equal Studio's table entries (BOOL has Radix at a root)."""
        table = builtin_table()[data_type]
        generated = default_data_element(data_type, golden._type_registry)
        assert first_difference(generated, table) is None

    def test_bool_member_has_no_radix(self, golden: Project) -> None:
        """A BOOL member omits Radix; a DINT member has it."""
        registry = golden._type_registry
        bool_member = default_value_element(
            "BOOL", registry, context="member", name="b"
        )
        dint_member = default_value_element(
            "DINT", registry, context="member", name="d"
        )
        assert list(bool_member.attrib) == ["Name", "DataType", "Value"]
        assert list(dint_member.attrib) == ["Name", "DataType", "Radix", "Value"]

    def test_array_shapes(self, golden: Project) -> None:
        """Arrays use comma dimensions, row-major indexes and element values."""
        array = default_value_element(
            "DINT", golden._type_registry, dimensions=(2, 3), radix="Hex"
        )
        assert array.tag == "Array"
        assert array.get("Dimensions") == "2,3"
        assert array.get("Radix") == "Hex"
        assert [e.get("Index") for e in array] == [
            "[0,0]", "[0,1]", "[0,2]", "[1,0]", "[1,1]", "[1,2]",
        ]  # fmt: skip
        assert array[0].get("Value") == "16#0000_0000"


class TestMembers:
    """The members() API and AOI/UDT rules."""

    def test_udt_members(self, golden: Project) -> None:
        """Hidden members are skipped and BIT members become BOOL."""
        info = members("DefMix", golden._type_registry)
        assert [m.name for m in info][:3] == ["b0", "b1", "t"]
        assert info[0].data_type == "BOOL"
        assert info[0].dimensions == ()
        ta = next(m for m in info if m.name == "ta")
        assert ta.dimensions == (2,)
        flags = next(m for m in info if m.name == "flags")
        assert (flags.data_type, flags.dimensions, flags.radix) == (
            "BOOL",
            (32,),
            "Decimal",
        )

    def test_aoi_members(self, golden: Project) -> None:
        """AOI members skip InOut and default EnableIn to 1."""
        info = members("Debounce", golden._type_registry)
        assert [m.name for m in info] == [
            "EnableIn", "EnableOut", "state", "onDelay", "offDelay",
        ]  # fmt: skip
        assert info[0].default == "1"
        assert info[1].default is None
        generic = members("GenericInput", golden._type_registry)
        assert next(m for m in generic if m.name == "onDelay").default == "25"
        assert "UI" not in [
            m.name for m in members("FanucRobot", golden._type_registry)
        ]

    def test_members_of_builtin_fails(self, golden: Project) -> None:
        """Built-in structures have no member list here."""
        with pytest.raises(LayoutError):
            members("TIMER", golden._type_registry)


class TestErrors:
    """Types without a layout."""

    @pytest.mark.parametrize(
        "name", ["NoSuchType", "MESSAGE", "AXIS_CIP_DRIVE", "MOTION_GROUP"]
    )
    def test_raises(self, golden: Project, name: str) -> None:
        """Unknown and special-format types raise LayoutError."""
        with pytest.raises(LayoutError):
            default_data_element(name, golden._type_registry)
        with pytest.raises(LayoutError):
            default_value_element(name, golden._type_registry, dimensions=(2,))

    def test_member_of_unknown_type(self, golden: Project) -> None:
        """LayoutError is a ValueError."""
        assert issubclass(LayoutError, ValueError)

    def test_bad_context(self, golden: Project) -> None:
        """Bad context and nameless member raise ValueError."""
        with pytest.raises(ValueError):
            default_value_element("DINT", golden._type_registry, context="element")
        with pytest.raises(ValueError):
            default_value_element("DINT", golden._type_registry, context="member")


class TestPackageData:
    """The table loads through importlib.resources, as in an installed wheel."""

    def test_resource_readable(self) -> None:
        """The resource is found by package name and decompresses."""
        data = (resources.files("py_l5x") / layout.BUILTIN_TABLE_RESOURCE).read_bytes()
        text = gzip.decompress(data).decode("utf-8-sig")
        assert 'TargetName="builtin_types"' in text

    def test_declared_as_package_data(self) -> None:
        """pyproject lists the data file so the wheel includes it."""
        root = Path(__file__).parent.parent
        assert "data/*.gz" in (root / "pyproject.toml").read_text()

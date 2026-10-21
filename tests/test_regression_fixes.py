"""Regression tests for fixes made during the tag-types refactor review."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x import load
from py_l5x.parsers.aoi import (
    AOIDataTypesCollection,
    AOIDefinition,
    AOILocalTag,
    AOIParameter,
    _make_aoi_local_tag,
)
from py_l5x.parsers.controller import ControllerInfo
from py_l5x.parsers.datatype import DataTypesCollection
from py_l5x.parsers.tag import (
    ArrayTag,
    AtomicNode,
    FloatTag,
    IntegerNode,
    IntegerTag,
    Tag,
    TagNode,
    TypeRegistry,
    UnknownTag,
    _build_node,
    _find_special_data_element,
    _make_tag,
    _RootMetadataMixin,
    _TagOverrides,
)

EXAMPLE_L5X = Path(__file__).parent / "fixtures" / "example.L5X"


def _count_field_lines(text: str, name: str) -> int:
    """Count describe() lines for ``name`` (``name = ...`` or ``name: ...``)."""
    return sum(
        1
        for line in text.splitlines()
        if line.strip().startswith((f"{name} =", f"{name}:"))
    )


@pytest.fixture
def controller_element() -> ET.Element:
    """Extract the <Controller> element from the example L5X."""
    el = ET.parse(str(EXAMPLE_L5X)).getroot().find("Controller")
    assert el is not None
    return el


@pytest.fixture
def type_registry(controller_element: ET.Element) -> TypeRegistry:
    """Build a TypeRegistry from the example L5X."""
    return TypeRegistry(
        DataTypesCollection(controller_element),
        AOIDataTypesCollection(controller_element),
    )


_REAL_WITH_ROOT_META = (
    '<{tag} Name="x" DataType="REAL" Min="0.0" Max="10.0" '
    'ExternalLogging="true"><{data} Format="Decorated">'
    '<DataValue DataType="REAL" Radix="Float" Value="1.0"/>'
    "</{data}></{tag}>"
)


class TestAOILocalRootMetadata:
    """AOI local tags read root Min/Max/ExternalLogging like regular tags."""

    def test_local_tag_matches_tag(self, type_registry: TypeRegistry) -> None:
        """A REAL local tag exposes the same root metadata as a REAL tag."""
        local = _make_aoi_local_tag(
            ET.fromstring(
                _REAL_WITH_ROOT_META.format(tag="LocalTag", data="DefaultData")
            ),
            type_registry,
        )
        tag = _make_tag(
            ET.fromstring(_REAL_WITH_ROOT_META.format(tag="Tag", data="Data")),
            type_registry,
        )
        assert isinstance(tag, FloatTag)
        assert (local.min, local.max, local.external_logging) == (0.0, 10.0, True)
        assert (tag.min, tag.max, tag.external_logging) == (0.0, 10.0, True)

    def test_description_attr_fallback_matches_tag(
        self, type_registry: TypeRegistry
    ) -> None:
        """A Description attribute is read by both AOI local tags and tags."""
        xml = (
            '<{tag} Name="x" DataType="REAL" Description="from attr">'
            '<{data} Format="Decorated">'
            '<DataValue DataType="REAL" Radix="Float" Value="1.0"/>'
            "</{data}></{tag}>"
        )
        local = _make_aoi_local_tag(
            ET.fromstring(xml.format(tag="LocalTag", data="DefaultData")),
            type_registry,
        )
        tag = _make_tag(
            ET.fromstring(xml.format(tag="Tag", data="Data")),
            type_registry,
        )
        assert local.description == "from attr"
        assert local.description == tag.description
        assert "Description" not in local.extra_attributes

    def test_dynamic_keys_shared_with_tag(self) -> None:
        """AOILocalTag and Tag share the root-metadata keys; Tag adds AliasFor."""
        assert AOILocalTag._DYNAMIC_KEYS == _RootMetadataMixin._DYNAMIC_KEYS
        assert _RootMetadataMixin._DYNAMIC_KEYS | {"AliasFor"} == Tag._DYNAMIC_KEYS
        assert (
            frozenset({"Min", "Max", "ExternalLogging", "Radix", "Dimensions"})
            == _RootMetadataMixin._DYNAMIC_KEYS
        )


class TestAOIParameterOperandMetadata:
    """Parameter EU/State text comes only from un-operanded entries."""

    _PARAM = '<Parameter Name="p" DataType="BOOL" Usage="Input">{body}</Parameter>'

    def _param(self, body: str) -> AOIParameter:
        return AOIParameter(ET.fromstring(self._PARAM.format(body=body)))

    def test_unoperanded_entries_win_over_operanded_first(self) -> None:
        """An Operand=".0" entry before the plain entry is skipped."""
        param = self._param(
            "<EngineeringUnits>"
            '<EngineeringUnit Operand=".0"><CDataContent>bad</CDataContent>'
            "</EngineeringUnit>"
            "<EngineeringUnit><CDataContent>ms</CDataContent></EngineeringUnit>"
            "</EngineeringUnits>"
            "<State0s>"
            '<State0 Operand=".0"><CDataContent>wrong0</CDataContent></State0>'
            "<State0><CDataContent>off</CDataContent></State0>"
            "</State0s>"
            "<State1s>"
            '<State1 Operand=".0"><CDataContent>wrong1</CDataContent></State1>'
            "<State1><CDataContent>on</CDataContent></State1>"
            "</State1s>"
        )
        assert param.engineering_unit == "ms"
        assert param.state0 == "off"
        assert param.state1 == "on"

    def test_only_operanded_entries_return_empty(self) -> None:
        """With only per-bit entries, the parameter-level text is empty."""
        param = self._param(
            "<EngineeringUnits>"
            '<EngineeringUnit Operand=".0"><CDataContent>bad</CDataContent>'
            "</EngineeringUnit>"
            "</EngineeringUnits>"
            "<State0s>"
            '<State0 Operand=".0"><CDataContent>wrong0</CDataContent></State0>'
            "</State0s>"
            "<State1s>"
            '<State1 Operand=".0"><CDataContent>wrong1</CDataContent></State1>'
            "</State1s>"
        )
        assert param.engineering_unit == ""
        assert param.state0 == ""
        assert param.state1 == ""
        assert "engineering_unit" not in param.describe()

    def test_operand_override_still_in_overrides(self) -> None:
        """The operanded per-bit state text is kept as a path override."""
        param = self._param(
            "<State0s>"
            '<State0 Operand=".0"><CDataContent>wrong0</CDataContent></State0>'
            "</State0s>"
        )
        assert param._overrides.get(".0") == {"state0": "wrong0"}

    def test_min_max_and_absent_metadata(self) -> None:
        """Min/Max convert by DataType; absent Min/Max are None."""
        param = AOIParameter(
            ET.fromstring(
                '<Parameter Name="p" DataType="DINT" Usage="Input" Min="-5" Max="7"/>'
            )
        )
        assert (param.min, param.max) == (-5, 7)
        bare = AOIParameter(ET.fromstring('<Parameter Name="q" DataType="DINT"/>'))
        assert (bare.min, bare.max) == (None, None)


class TestNodeRepr:
    """Node reprs omit empty-string metadata."""

    def test_empty_strings_omitted(self) -> None:
        """A BOOL member with no units/state text doesn't print them."""
        el = ET.fromstring(
            '<DataValueMember Name="B" DataType="BOOL" Radix="Decimal" Value="1"/>'
        )
        node = _build_node(el, None, _TagOverrides(ET.Element("Tag")), ".B")
        text = repr(node)
        assert "value: True" in text
        assert "engineering_unit" not in text
        assert "state0" not in text
        assert "''" not in text


class TestScalarWithoutValue:
    """Known atomic scalars keep their typed class without a Value attribute."""

    def test_dint_without_value_is_integer_tag(
        self, type_registry: TypeRegistry
    ) -> None:
        """A DINT DataValue with no Value is an IntegerTag with bit access."""
        tag = _make_tag(
            ET.fromstring(
                '<Tag Name="y" TagType="Base" DataType="DINT">'
                '<Data Format="Decorated">'
                '<DataValue DataType="DINT" Radix="Decimal"/>'
                "</Data></Tag>"
            ),
            type_registry,
        )
        assert isinstance(tag, IntegerTag)
        assert tag.value is None
        assert tag.signed is True
        assert tag.bit(0).value is None

    def test_cdata_scalar_is_unquoted_atomic_node(self) -> None:
        """A no-Value scalar with CDATA text stays an AtomicNode, unquoted."""
        el = ET.fromstring(
            '<DataValueMember Name="DATA" DataType="SINT" Radix="ASCII">'
            "<CDataContent>'abc'</CDataContent></DataValueMember>"
        )
        node = _build_node(el, None, _TagOverrides(ET.Element("Tag")), ".DATA")
        assert type(node) is AtomicNode
        assert node.value == "abc"

    def test_member_without_value_or_text_is_typed(self) -> None:
        """A no-Value, no-text DINT member is an IntegerNode."""
        el = ET.fromstring('<DataValueMember Name="D" DataType="DINT"/>')
        node = _build_node(el, None, _TagOverrides(ET.Element("Tag")), ".D")
        assert isinstance(node, IntegerNode)
        assert node.value is None


class TestTagNodeBase:
    """TagNode no longer exposes XmlAttrMixin helpers it can't support."""

    def test_no_cdata_helper(self) -> None:
        """Member nodes don't have the broken _get_cdata_child helper."""
        assert not hasattr(TagNode, "_get_cdata_child")


class TestSpecialData:
    """The shared special-<Data> lookup helper."""

    def test_finds_message_format(self) -> None:
        """A Message-format <Data> element is found."""
        el = ET.fromstring('<Tag><Data Format="Message"/></Tag>')
        found = _find_special_data_element(el)
        assert found is not None
        assert found.get("Format") == "Message"

    def test_ignores_value_formats(self) -> None:
        """Decorated/L5K/String formats are not special."""
        el = ET.fromstring('<Tag><Data Format="L5K"/><Data Format="Decorated"/></Tag>')
        assert _find_special_data_element(el) is None

    def test_tag_without_data_is_unknown(self, type_registry: TypeRegistry) -> None:
        """A tag with no data at all falls back to UnknownTag."""
        tag = _make_tag(
            ET.fromstring('<Tag Name="io" TagType="Base" DataType="DINT"/>'),
            type_registry,
        )
        assert isinstance(tag, UnknownTag)
        assert tag.special_data_format is None


class TestReprs:
    """AOI-related reprs use real class names and describe()."""

    def test_aoi_definition_repr(
        self, controller_element: ET.Element, type_registry: TypeRegistry
    ) -> None:
        """AOIDefinition repr uses the actual class name."""
        el = controller_element.find(
            "AddOnInstructionDefinitions/AddOnInstructionDefinition"
        )
        assert el is not None
        aoi = AOIDefinition(el, type_registry)
        assert repr(aoi) == f"AOIDefinition({aoi.name!r})"

    def test_aoi_local_tag_repr_is_describe(self, type_registry: TypeRegistry) -> None:
        """AOILocalTag repr matches describe(), like Tag."""
        local = _make_aoi_local_tag(
            ET.fromstring(
                _REAL_WITH_ROOT_META.format(tag="LocalTag", data="DefaultData")
            ),
            type_registry,
        )
        assert repr(local) == local.describe()
        assert "min: 0.0" in repr(local)


class TestDescribeNoDuplicateFields:
    """describe() emits external_access/description once, not twice."""

    def test_value_tag(self) -> None:
        """A value Tag lists each declared field exactly once."""
        tag = load(EXAMPLE_L5X).programs["MainProgram"].tags["a_commented_dint"]
        text = tag.describe()
        assert _count_field_lines(text, "external_access") == 1
        assert _count_field_lines(text, "description") == 1
        assert repr(tag) == text

    def test_aoi_local_tag(self, type_registry: TypeRegistry) -> None:
        """An AOI local tag lists each declared field exactly once."""
        local = _make_aoi_local_tag(
            ET.fromstring(
                '<LocalTag Name="x" DataType="REAL" ExternalAccess="Read/Write">'
                "<Description><CDataContent>d</CDataContent></Description>"
                '<DefaultData Format="Decorated">'
                '<DataValue DataType="REAL" Radix="Float" Value="1.0"/>'
                "</DefaultData></LocalTag>"
            ),
            type_registry,
        )
        text = local.describe()
        assert _count_field_lines(text, "external_access") == 1
        assert _count_field_lines(text, "description") == 1
        assert repr(local) == text

    def test_message_tag(self) -> None:
        """A MessageTag lists each declared field exactly once."""
        tag = load(EXAMPLE_L5X).tags["message_tag"]
        text = tag.describe()
        assert _count_field_lines(text, "external_access") == 1
        assert _count_field_lines(text, "description") == 1


class TestDescribeArrayElements:
    """Array describe() uses the same ``elements: len=`` format as repr."""

    def test_elements_len_format(self) -> None:
        """An array tag reports ``elements: len=<n>`` and no 'items' wording."""
        tag = load(EXAMPLE_L5X).programs["MainProgram"].tags["a_2d_array"]
        assert isinstance(tag, ArrayTag)
        text = tag.describe()
        assert f"  elements: len={len(tag)}" in text
        assert "items" not in text
        assert f"  elements: len={len(tag)}" in repr(tag)


def _assert_extras_block_last(text: str) -> None:
    """Assert the ``Extra Attributes:`` block is the final section of ``text``.

    Every line after the header must be a four-space-indented extra attribute,
    so no other summary line can appear to belong to the extras block.
    """
    lines = text.splitlines()
    header_idx = lines.index("  Extra Attributes:")
    assert header_idx > 0
    for line in lines[header_idx + 1 :]:
        assert line.startswith("    "), line


class TestDescribeExtrasLast:
    """Lines from ``_describe_lines`` precede the ``Extra Attributes:`` block."""

    def test_controller_extras_block_is_last(self) -> None:
        """ControllerInfo child summaries come before the extras block."""
        ctrl_el = ET.parse(str(EXAMPLE_L5X)).getroot().find("Controller")
        assert ctrl_el is not None
        ctrl = ControllerInfo(ctrl_el)
        text = repr(ctrl)
        _assert_extras_block_last(text)
        lines = text.splitlines()
        extras_idx = lines.index("  Extra Attributes:")
        for prefix in ("  safety_info:", "  ethernet_ports:"):
            idx = next(i for i, line in enumerate(lines) if line.startswith(prefix))
            assert idx < extras_idx

    def test_tag_extras_block_is_last(self, type_registry: TypeRegistry) -> None:
        """A Tag with an unknown attribute lists it after the value lines."""
        tag = _make_tag(
            ET.fromstring(
                '<Tag Name="y" TagType="Base" DataType="DINT" Foo="1">'
                '<Data Format="Decorated">'
                '<DataValue DataType="DINT" Radix="Decimal" Value="5"/>'
                "</Data></Tag>"
            ),
            type_registry,
        )
        text = tag.describe()
        _assert_extras_block_last(text)
        assert "    Foo = '1'" in text.splitlines()
        assert text.splitlines().index("  value: 5") < text.splitlines().index(
            "  Extra Attributes:"
        )

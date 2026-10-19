"""Regression tests for fixes made during the tag-types refactor review."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.aoi import AOIDefinition, _make_aoi_local_tag
from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.tag import (
    AtomicNode,
    FloatTag,
    IntegerNode,
    IntegerTag,
    TagNode,
    TypeRegistry,
    UnknownTag,
    _build_node,
    _find_special_data_element,
    _make_tag,
    _TagOverrides,
)

EXAMPLE_L5X = Path(__file__).parent / "fixtures" / "example.L5X"


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
        AddOnDataTypeCollection(controller_element),
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

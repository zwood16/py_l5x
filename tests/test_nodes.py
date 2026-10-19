"""Tests for py_l5x.parsers.tag node classes."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.module import ModulesCollection
from py_l5x.parsers.program import ProgramsCollection
from py_l5x.parsers.tag import (
    ArrayNode,
    AtomicNode,
    BoolNode,
    DateTimeNode,
    FloatNode,
    IntegerNode,
    StringNode,
    StructNode,
    TagsCollection,
    TimeNode,
    TypeRegistry,
    _build_node,
    _TagOverrides,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLE_L5X = FIXTURES_DIR / "example.L5X"


@pytest.fixture
def example_tree() -> ET.ElementTree:
    """Load the example L5X file."""
    return ET.parse(str(EXAMPLE_L5X))


@pytest.fixture
def controller_element(example_tree: ET.ElementTree) -> ET.Element:
    """Extract the <Controller> element from the example L5X."""
    el = example_tree.getroot().find("Controller")
    assert el is not None, "Controller element not found in example.L5X"
    return el


@pytest.fixture
def type_registry(controller_element: ET.Element) -> TypeRegistry:
    """Build a TypeRegistry from the example L5X."""
    return TypeRegistry(
        DataTypesCollection(controller_element),
        AddOnDataTypeCollection(controller_element),
    )


@pytest.fixture
def controller_tags(
    controller_element: ET.Element, type_registry: TypeRegistry
) -> TagsCollection:
    """Controller-scoped tags collection."""
    return TagsCollection(controller_element, type_registry)


@pytest.fixture
def programs(
    controller_element: ET.Element, type_registry: TypeRegistry
) -> ProgramsCollection:
    """Programs collection."""
    return ProgramsCollection(controller_element, type_registry)


@pytest.fixture
def main_program_tags(programs: ProgramsCollection) -> TagsCollection:
    """MainProgram's tags collection."""
    return programs["MainProgram"].tags


# ============================================================================
# 1. DISPATCH FROM EXAMPLE.L5X
# ============================================================================


class TestDispatchBasicTypes:
    """Test that tags dispatch to the correct node classes."""

    def test_a_dint_is_integer_node(self, main_program_tags: TagsCollection) -> None:
        """a_dint dispatches to IntegerNode."""
        node = main_program_tags["a_dint"]
        assert isinstance(node, IntegerNode)
        assert node.data_type == "DINT"

    def test_a_real_is_float_node(self, main_program_tags: TagsCollection) -> None:
        """a_real dispatches to FloatNode."""
        node = main_program_tags["a_real"]
        assert isinstance(node, FloatNode)
        assert node.data_type == "REAL"

    def test_a_long_real_is_float_node(self, main_program_tags: TagsCollection) -> None:
        """a_long_real dispatches to FloatNode."""
        node = main_program_tags["a_long_real"]
        assert isinstance(node, FloatNode)
        assert node.data_type == "LREAL"

    def test_a_lint_is_integer_node(self, main_program_tags: TagsCollection) -> None:
        """a_lint dispatches to IntegerNode."""
        node = main_program_tags["a_lint"]
        assert isinstance(node, IntegerNode)
        assert node.data_type == "LINT"

    def test_a_bool_is_bool_node(self, main_program_tags: TagsCollection) -> None:
        """a_bool dispatches to BoolNode."""
        node = main_program_tags["a_bool"]
        assert isinstance(node, BoolNode)
        assert node.data_type == "BOOL"

    def test_a_string_is_string_node(self, main_program_tags: TagsCollection) -> None:
        """a_string dispatches to StringNode."""
        node = main_program_tags["a_string"]
        assert isinstance(node, StringNode)
        assert node.data_type == "STRING"

    def test_a_udt_instance_is_struct_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_udt_instance dispatches to StructNode."""
        node = main_program_tags["a_udt_instance"]
        assert isinstance(node, StructNode)
        assert node.data_type == "A_UDT"


class TestV37TimeTypes:
    """Test TIME/TIME32/LTIME and DT/LDT types."""

    def test_duration_is_time_node(self, main_program_tags: TagsCollection) -> None:
        """duration tag is a TimeNode with TIME data type."""
        node = main_program_tags["duration"]
        assert isinstance(node, TimeNode)
        assert node.data_type == "TIME"
        assert node.value == "T#0us"
        assert node.unit == "us"

    def test_short_duration_is_time_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """short_duration tag is a TimeNode with TIME32 data type."""
        node = main_program_tags["short_duration"]
        assert isinstance(node, TimeNode)
        assert node.data_type == "TIME32"
        assert node.value == "T32#0us"
        assert node.unit == "us"

    def test_long_duration_is_time_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """long_duration tag is a TimeNode with LTIME data type."""
        node = main_program_tags["long_duration"]
        assert isinstance(node, TimeNode)
        assert node.data_type == "LTIME"
        assert node.value == "LT#0ns"
        assert node.unit == "ns"

    def test_datetime_is_datetime_node(self, main_program_tags: TagsCollection) -> None:
        """datetime tag is a DateTimeNode with DT data type."""
        node = main_program_tags["datetime"]
        assert isinstance(node, DateTimeNode)
        assert node.data_type == "DT"
        assert node.value == "DT#1970-01-01-00:00:00.000_000Z"
        assert node.unit == "us"

    def test_long_datetime_is_datetime_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """long_datetime tag is a DateTimeNode with LDT data type."""
        node = main_program_tags["long_datetime"]
        assert isinstance(node, DateTimeNode)
        assert node.data_type == "LDT"
        assert node.value == "LDT#1970-01-01-00:00:00.000_000_000Z"
        assert node.unit == "ns"


class TestNestedStructMembers:
    """Test nested members of a_udt_instance."""

    def test_a_nested_udt_is_struct_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_udt_instance.a_nested_UDT is a StructNode."""
        udt = main_program_tags["a_udt_instance"]
        node = udt.members["a_nested_UDT"]
        assert isinstance(node, StructNode)

    def test_an_array_is_array_node(self, main_program_tags: TagsCollection) -> None:
        """a_udt_instance.an_array is an ArrayNode."""
        udt = main_program_tags["a_udt_instance"]
        node = udt.members["an_array"]
        assert isinstance(node, ArrayNode)

    def test_a_sint_with_props_is_integer_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_udt_instance.a_sint_with_props is an IntegerNode."""
        udt = main_program_tags["a_udt_instance"]
        node = udt.members["a_sint_with_props"]
        assert isinstance(node, IntegerNode)
        assert node.data_type == "SINT"

    def test_nested_a_real_is_float_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_udt_instance.a_real is a FloatNode."""
        udt = main_program_tags["a_udt_instance"]
        node = udt.members["a_real"]
        assert isinstance(node, FloatNode)

    def test_nested_a_bool_is_bool_node(
        self, main_program_tags: TagsCollection
    ) -> None:
        """a_udt_instance.a_Bool is a BoolNode."""
        udt = main_program_tags["a_udt_instance"]
        node = udt.members["a_Bool"]
        assert isinstance(node, BoolNode)


class TestAllowableAlarmsArray:
    """Test the ALLOWABLE_ALARMS controller tag."""

    def test_allowable_alarms_is_array_node(
        self, controller_tags: TagsCollection
    ) -> None:
        """ALLOWABLE_ALARMS is an ArrayNode."""
        node = controller_tags["ALLOWABLE_ALARMS"]
        assert isinstance(node, ArrayNode)

    def test_allowable_alarms_elements_are_string_nodes(
        self, controller_tags: TagsCollection
    ) -> None:
        """ALLOWABLE_ALARMS elements are StringNodes."""
        node = controller_tags["ALLOWABLE_ALARMS"]
        for elem in node.elements:
            assert isinstance(elem, StringNode)


# ============================================================================
# 2. RESTRICTED SURFACE
# ============================================================================


class TestRestrictedSurfaceBoolNode:
    def test_bool_node_lacks_bits_min_max(self, main_program_tags):
        # BoolTag is both Tag and BoolNode, but BoolNode doesn't have min/max.
        # BoolTag won't have min/max either since they're not defined on BoolNode.
        node = main_program_tags["a_bool"]
        # node is a BoolTag (both Tag and BoolNode)
        # BoolNode has no bit/bits (only integer nodes do)
        assert not hasattr(node, "bit")
        assert not hasattr(node, "bits")
        # BoolNode/BoolTag don't have min/max (only IntegerNode/FloatNode do)
        assert not hasattr(node, "min")
        assert not hasattr(node, "max")


# ============================================================================
# 3. INTEGER NODE TESTS
# ============================================================================


class TestIntegerNodeBitValues:
    def test_bits_for_value_5(self):
        xml_str = '<DataValue DataType="SINT" Radix="Decimal" Value="5"/>'
        el = ET.fromstring(xml_str)
        overrides = _TagOverrides(ET.fromstring("<Tag/>"))
        node = _build_node(el, None, overrides, "", None)
        assert node.bit(0).value is True
        assert node.bit(1).value is False
        assert node.bit(2).value is True

    def test_bit_negative_raises(self, main_program_tags):
        node = main_program_tags["a_dint"]
        with pytest.raises(IndexError):
            node.bit(-1)


class TestIntegerNodeRadix:
    def test_hex_ff_sint(self):
        xml_str = '<DataValue DataType="SINT" Radix="Hex" Value="16#FF"/>'
        el = ET.fromstring(xml_str)
        overrides = _TagOverrides(ET.fromstring("<Tag/>"))
        node = _build_node(el, None, overrides, "", None)
        assert node.value == -1

    def test_hex_ff_usint(self):
        xml_str = '<DataValue DataType="USINT" Radix="Hex" Value="16#FF"/>'
        el = ET.fromstring(xml_str)
        overrides = _TagOverrides(ET.fromstring("<Tag/>"))
        node = _build_node(el, None, overrides, "", None)
        assert node.value == 255

    def test_binary(self):
        xml_str = '<DataValue DataType="DINT" Radix="Binary" Value="2#0000_0101"/>'
        el = ET.fromstring(xml_str)
        overrides = _TagOverrides(ET.fromstring("<Tag/>"))
        node = _build_node(el, None, overrides, "", None)
        assert node.value == 5


# ============================================================================
# 4. OPERAND OVERRIDES
# ============================================================================


class TestBitOverrides:
    def test_a_commented_dint_bit_1_description(self, main_program_tags):
        node = main_program_tags["a_commented_dint"]
        bit_node = node.bit(1)
        assert bit_node.description == "this is bit 1"


# ============================================================================
# 5. FLOAT NODE
# ============================================================================


class TestFloatNode:
    def test_qnan(self):
        import math

        xml_str = '<DataValue DataType="REAL" Value="1.#QNAN"/>'
        el = ET.fromstring(xml_str)
        overrides = _TagOverrides(ET.fromstring("<Tag/>"))
        node = _build_node(el, None, overrides, "", None)
        assert math.isnan(node.value)


# ============================================================================
# 6. STRING NODE
# ============================================================================


class TestStringNode:
    def test_a_string_value(self, main_program_tags):
        node = main_program_tags["a_string"]
        assert node.value == ""
        assert node.len == 0
        assert node.max_length == 82

    def test_allowable_alarms_element(self, controller_tags):
        node = controller_tags["ALLOWABLE_ALARMS"]
        elem = node.elements[1]
        assert elem.value == "SRVO-003"
        assert elem.len == 8
        assert elem.max_length == 8
        assert elem.operand_path == "[1]"


# ============================================================================
# 7. ARRAY NODE
# ============================================================================


class TestArrayNode2D:
    def test_dimensions(self, main_program_tags):
        node = main_program_tags["a_2d_array"]
        assert node.dimensions == (2, 3)
        assert len(node) == 6

    def test_subscript(self, main_program_tags):
        node = main_program_tags["a_2d_array"]
        elem = node[0, 1]
        assert elem.operand_path == "[0,1]"

    def test_negative_index(self, main_program_tags):
        node = main_program_tags["a_2d_array"]
        elem = node[-1]
        assert elem.operand_path == "[1,2]"

    def test_out_of_bounds(self, main_program_tags):
        node = main_program_tags["a_2d_array"]
        with pytest.raises(IndexError):
            node[5, 5]


class TestArrayNode3D:
    def test_dimensions(self, main_program_tags):
        node = main_program_tags["a_3d_array"]
        assert node.dimensions == (2, 3, 4)
        assert len(node) == 24

    def test_subscript(self, main_program_tags):
        node = main_program_tags["a_3d_array"]
        elem = node[1, 2, 3]
        assert elem.operand_path == "[1,2,3]"


# ============================================================================
# 8. REPR
# ============================================================================


class TestRepr:
    def test_integer_repr(self, main_program_tags):
        node = main_program_tags["a_dint"]
        repr_str = repr(node)
        # Now root tags show their tag type, not node type
        assert repr_str.startswith("IntegerTag(")
        assert "'a_dint'" in repr_str
        assert "'DINT'" in repr_str


# ============================================================================
# ADDITIONAL COMPREHENSIVE TESTS
# ============================================================================


class TestRestrictedSurfaceIntegerNode:
    """IntegerNode must lack members and elements."""

    def test_integer_node_lacks_members_elements(self, main_program_tags):
        node = main_program_tags["a_dint"]
        assert not hasattr(node, "members")
        assert not hasattr(node, "elements")


class TestRestrictedSurfaceFloatNode:
    """FloatNode must lack bit/bits attributes."""

    def test_float_node_lacks_bits(self, main_program_tags):
        node = main_program_tags["a_real"]
        assert not hasattr(node, "bit")
        assert not hasattr(node, "bits")


class TestRestrictedSurfaceStringNode:
    """StringNode must lack value/elements but has members."""

    def test_string_node_lacks_elements_bit(self, main_program_tags):
        node = main_program_tags["a_string"]
        assert not hasattr(node, "elements")
        assert not hasattr(node, "bit")


class TestRestrictedSurfaceStructNode:
    """StructNode must lack value and elements."""

    def test_struct_node_lacks_value_elements(self, main_program_tags):
        node = main_program_tags["a_udt_instance"]
        assert not hasattr(node, "value")
        assert not hasattr(node, "elements")


class TestRestrictedSurfaceArrayNode:
    """ArrayNode must lack value and members."""

    def test_array_node_lacks_value_members(self, main_program_tags):
        node = main_program_tags["a_2d_array"]
        assert not hasattr(node, "value")
        assert not hasattr(node, "members")


class TestNoKindAttribute:
    """No node class should have a 'kind' attribute."""

    def test_integer_lacks_kind(self, main_program_tags):
        node = main_program_tags["a_dint"]
        assert not hasattr(node, "kind")

    def test_bool_lacks_kind(self, main_program_tags):
        node = main_program_tags["a_bool"]
        assert not hasattr(node, "kind")

    def test_string_lacks_kind(self, main_program_tags):
        node = main_program_tags["a_string"]
        assert not hasattr(node, "kind")

    def test_array_lacks_kind(self, main_program_tags):
        node = main_program_tags["a_2d_array"]
        assert not hasattr(node, "kind")


class TestIntegerNodeBitWidth:
    """Test bit width calculations for various integer types."""

    def test_sint_bit_width(self):
        xml_str = '<DataValue DataType="SINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.bit_width == 8

    def test_dint_bit_width(self):
        xml_str = '<DataValue DataType="DINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.bit_width == 32

    def test_int_bit_width(self):
        xml_str = '<DataValue DataType="INT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.bit_width == 16


class TestIntegerNodeMinMax:
    """Test min/max for integer types with no declared bounds."""

    def test_sint_undeclared_min_max(self):
        xml_str = '<DataValue DataType="SINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.min is None
        assert node.max is None

    def test_usint_undeclared_min_max(self):
        xml_str = '<DataValue DataType="USINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.min is None
        assert node.max is None

    def test_dint_undeclared_min_max(self):
        xml_str = '<DataValue DataType="DINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.min is None
        assert node.max is None


class TestIntegerNodeSigned:
    """Test signed property of integer nodes."""

    def test_sint_is_signed(self):
        xml_str = '<DataValue DataType="SINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.signed is True

    def test_usint_is_unsigned(self):
        xml_str = '<DataValue DataType="USINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.signed is False


class TestIntegerNodeBitAccess:
    """Test bit access with valid ranges."""

    def test_bit_raises_on_high_index(self, main_program_tags):
        node = main_program_tags["a_dint"]
        with pytest.raises(IndexError):
            node.bit(32)  # DINT has 32 bits (0-31)

    def test_bit_returns_bool_node(self, main_program_tags):
        node = main_program_tags["a_dint"]
        bit_node = node.bit(0)
        assert isinstance(bit_node, BoolNode)

    def test_bit_path_format(self, main_program_tags):
        node = main_program_tags["a_dint"]
        bit_node = node.bit(3)
        assert ".3" in bit_node.operand_path


class TestIntegerNodeBitsProperty:
    """Test the bits property returns correct list."""

    def test_bits_list_length_sint(self):
        xml_str = '<DataValue DataType="SINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert len(node.bits) == 8

    def test_bits_list_length_dint(self):
        xml_str = '<DataValue DataType="DINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert len(node.bits) == 32

    def test_bits_are_bool_nodes(self):
        xml_str = '<DataValue DataType="SINT" Radix="Decimal" Value="0"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        for bit in node.bits:
            assert isinstance(bit, BoolNode)


class TestIntegerNodeNegativeValue:
    """Test bit values for negative integers."""

    def test_negative_sint_all_bits_true(self):
        xml_str = '<DataValue DataType="SINT" Radix="Decimal" Value="-1"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        for bit in node.bits:
            assert bit.value is True


class TestIntegerNodeRadixParsingEdgeCases:
    """Test radix parsing for various formats."""

    def test_ascii_dollar_format(self):
        xml_str = '<DataValue DataType="SINT" Radix="ASCII" Value="\'$41\'"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.value == 65

    def test_octal_format(self):
        xml_str = '<DataValue DataType="DINT" Radix="Octal" Value="8#123"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.value == 83  # 8#123 in octal = 83 decimal

    def test_unparseable_fallback_to_string(self):
        xml_str = '<DataValue DataType="DINT" Radix="Decimal" Value="garbage"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.value == "garbage"
        assert isinstance(node.value, str)


class TestFloatNodeSpecialValues:
    """Test special float value parsing."""

    def test_positive_inf(self):
        xml_str = '<DataValue DataType="REAL" Value="1.#INF"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.value == float("inf")

    def test_negative_inf(self):
        xml_str = '<DataValue DataType="REAL" Value="-1.#INF"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.value == float("-inf")

    def test_unparseable_float_fallback(self):
        xml_str = '<DataValue DataType="REAL" Value="bogus"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert node.value == "bogus"


class TestStringNodeMembers:
    """Test StringNode members structure."""

    def test_members_has_len_and_data(self, main_program_tags):
        node = main_program_tags["a_string"]
        assert "LEN" in node.members
        assert "DATA" in node.members

    def test_len_member_is_integer_node(self, main_program_tags):
        node = main_program_tags["a_string"]
        len_node = node.members["LEN"]
        assert isinstance(len_node, IntegerNode)

    def test_data_member_is_atomic_node(self, main_program_tags):
        node = main_program_tags["a_string"]
        data_node = node.members["DATA"]
        # DATA should be an AtomicNode; check it's not a struct/array
        assert not isinstance(data_node, StructNode)
        assert not isinstance(data_node, ArrayNode)


class TestStringNodeMaxLength:
    """Test max_length property."""

    def test_string_node_max_length(self, main_program_tags):
        node = main_program_tags["a_string"]
        assert node.max_length == 82


class TestArrayNode1D:
    """Test 1D array properties."""

    def test_1d_dimensions(self, main_program_tags):
        node = main_program_tags["a_udt_instance"]
        arr = node.members["an_array"]
        assert arr.dimensions == (4,)

    def test_1d_length(self, main_program_tags):
        node = main_program_tags["a_udt_instance"]
        arr = node.members["an_array"]
        assert len(arr) == 4

    def test_1d_element_path(self, main_program_tags):
        node = main_program_tags["a_udt_instance"]
        arr = node.members["an_array"]
        elem = arr[0]
        assert "[0]" in elem.operand_path


class TestArrayNodeNegativeIndexing:
    """Test negative indexing works correctly."""

    def test_2d_negative_index_equals_last(self, main_program_tags):
        node = main_program_tags["a_2d_array"]
        last_elem = node[-1]
        last_subscript = node[1, 2]
        assert last_elem.operand_path == last_subscript.operand_path

    def test_3d_negative_index_equals_last(self, main_program_tags):
        node = main_program_tags["a_3d_array"]
        last_elem = node[-1]
        last_subscript = node[1, 2, 3]
        assert last_elem.operand_path == last_subscript.operand_path


class TestArrayNodeIteration:
    """Test array iteration and slicing."""

    def test_2d_array_iteration_count(self, main_program_tags):
        node = main_program_tags["a_2d_array"]
        count = sum(1 for _ in node)
        assert count == 6

    def test_3d_array_iteration_count(self, main_program_tags):
        node = main_program_tags["a_3d_array"]
        count = sum(1 for _ in node)
        assert count == 24


class TestUnknownAtomicType:
    """Test that unknown atomic types create AtomicNode instances."""

    def test_unknown_type_is_atomic_node(self):
        xml_str = '<DataValue DataType="MYSTERY" Value="x"/>'
        el = ET.fromstring(xml_str)
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert type(node) is AtomicNode
        assert node.value == "x"
        assert node.raw_value == "x"


class TestSpecGaps:
    """Spec cases not covered by the generated suites above."""

    def test_subscript_bit_override(self, main_program_tags):
        node = main_program_tags["a_2d_array"]
        elem = node[0, 1]
        assert elem.operand_path == "[0,1]"
        assert elem.bit(1).description == "different element bit comment"

    def test_ascii_radix_tag(self, main_program_tags):
        node = main_program_tags["a_character"]
        assert isinstance(node, IntegerNode)
        assert node.radix == "ASCII"
        assert node.raw_value == "'$00'"
        assert node.value == 0

    def test_binary_radix_module_member(self, controller_element, type_registry):
        modules = ModulesCollection(controller_element, type_registry)
        comms = modules["Test_Servo_Drive"].communications
        found = []
        for conn in comms.connections.values():
            for io in (conn.input_tag, conn.output_tag):
                if io is None:
                    continue
                # ModuleDataTag wraps a node, check .data
                data_node = io.data
                if data_node is None or not isinstance(data_node, StructNode):
                    continue
                for name in ("Command", "Status"):
                    if name in data_node.members:
                        found.append(data_node.members[name])
        assert found
        for member in found:
            assert isinstance(member, IntegerNode)
            assert member.radix == "Binary"
            assert member.value == 0

    def test_lint_bits(self):
        el = ET.fromstring('<DataValue DataType="LINT" Value="1"/>')
        node = _build_node(el, None, _TagOverrides(ET.fromstring("<Tag/>")), "", None)
        assert len(node.bits) == 64
        assert node.bits[0].value is True

    def test_commented_dint_bit1_metadata(self, main_program_tags):
        bit1 = main_program_tags["a_commented_dint"].bit(1)
        assert bit1.operand_path == ".1"
        assert bit1.description == "this is bit 1"
        assert bit1.engineering_unit == "mm"
        assert bit1.state0 == "off"
        assert bit1.state1 == "on"
        assert bit1.external_logging is False

    def test_string_root_hand_built(self):
        el = ET.fromstring(
            '<Data Format="String" Length="3">'
            "<CDataContent>'abc'</CDataContent></Data>"
        )
        node = StringNode(
            el,
            None,
            _TagOverrides(ET.fromstring("<Tag/>")),
            "",
            None,
            data_type="STRING",
        )
        assert isinstance(node, StringNode)
        assert node.value == "abc"
        assert node.len == 3
        assert node.max_length == 82
        assert node.members["LEN"].value == 3
        assert node.members["DATA"].value == "abc"

    def test_nested_string_member_paths(self, controller_tags):
        elem = controller_tags["ALLOWABLE_ALARMS"][1]
        assert elem.operand_path == "[1]"
        assert elem.members["DATA"].operand_path == "[1].DATA"
        assert elem.members["LEN"].operand_path == "[1].LEN"
        assert type(elem.members["DATA"]) is AtomicNode

    def test_array_slice_and_negative(self, main_program_tags):
        arr = main_program_tags["a_udt_instance"].members["an_array"]
        assert [e.operand_path for e in arr.elements[1:3]] == [
            ".AN_ARRAY[1]",
            ".AN_ARRAY[2]",
        ]
        assert arr[-1].operand_path == ".AN_ARRAY[3]"
        assert arr.elements[0].data_type == "REAL"

    def test_struct_and_array_repr(self, main_program_tags):
        udt = main_program_tags["a_udt_instance"]
        # Root tags now repr as their full describe() text; the first line is
        # the rich identity header (tag type, name, data type).
        assert repr(udt) == udt.describe()
        assert repr(udt).splitlines()[0] == "StructTag('a_udt_instance', 'A_UDT')"
        # Full Node repr is for nested nodes; here just check member access
        assert "a_nested_UDT" in list(udt.members)

        arr = udt.members["an_array"]
        # Nested nodes still show full Node-style repr
        assert repr(arr).startswith("ArrayNode('REAL'")
        assert "elements: len=4" in repr(arr)

"""Tests for py_l5x.parsers.aoi."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.aoi import AOICollection, AOIDefinition, AOILocalTag
from py_l5x.parsers.datatype import (
    AddOnDataTypeCollection,
    AddOnParameters,
    DataTypesCollection,
)
from py_l5x.parsers.routine import Routine
from py_l5x.parsers.tag import (
    BoolNode,
    IntegerNode,
    StringNode,
    StructNode,
    TypeRegistry,
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
    """Build a TypeRegistry from the example L5X's UDT and AOI collections."""
    return TypeRegistry(
        DataTypesCollection(controller_element),
        AddOnDataTypeCollection(controller_element),
    )


@pytest.fixture
def aoi_definitions(
    controller_element: ET.Element, type_registry: TypeRegistry
) -> AOICollection:
    """AOI definitions collection."""
    return AOICollection(controller_element, type_registry)


class TestAoiCollection:
    """Tests for AOI collection mapping behavior."""

    def test_contains_known_aois(self, aoi_definitions: AOICollection) -> None:
        """Debounce and FanucRobot are present."""
        assert "Debounce" in aoi_definitions
        assert "FanucRobot" in aoi_definitions

    def test_getitem_returns_definition(self, aoi_definitions: AOICollection) -> None:
        """Indexing returns an AOI definition wrapper."""
        assert isinstance(aoi_definitions["Debounce"], AOIDefinition)


class TestAoiIdentity:
    """Tests for AOI identity metadata."""

    def test_identity_fields(self, aoi_definitions: AOICollection) -> None:
        """Key AOI attributes are exposed as typed properties."""
        debounce = aoi_definitions["Debounce"]
        assert debounce.name == "Debounce"
        assert debounce.revision == "1.2"
        assert debounce.execute_enable_in_false is True
        assert debounce.execute_prescan is False
        assert debounce.execute_postscan is False
        assert debounce.software_revision == "v37.00"


class TestAoiParametersAndRoutines:
    """Tests for reused parameter and routine parser surfaces."""

    def test_parameters_property_reuses_addonparameters(
        self, aoi_definitions: AOICollection
    ) -> None:
        """AOI.parameters returns AddOnParameters."""
        debounce = aoi_definitions["Debounce"]
        assert isinstance(debounce.parameters, AddOnParameters)
        assert debounce.parameters["onDelay"].data_type == "DINT"

    def test_routines_property_reuses_shared_routine_parser(
        self, aoi_definitions: AOICollection
    ) -> None:
        """AOI.routines returns Routine wrappers."""
        debounce = aoi_definitions["Debounce"]
        assert "Logic" in debounce.routines
        assert isinstance(debounce.routines["Logic"], Routine)
        assert debounce.routines["Logic"].type_ == "RLL"

    def test_st_routine_is_exposed(self, aoi_definitions: AOICollection) -> None:
        """FanucAlarmLookup has an ST logic routine."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        logic = lookup.routines["Logic"]
        assert logic.type_ == "ST"
        assert "recoverableAlarm := 0;" in logic.st_code


class TestAoiLocalTags:
    """Tests for AOI LocalTag metadata and value parsing."""

    def test_local_tags_collection(self, aoi_definitions: AOICollection) -> None:
        """AOI.local_tags maps local tag names to AOILocalTag wrappers."""
        debounce = aoi_definitions["Debounce"]
        assert "debounceOnTimer" in debounce.local_tags
        assert isinstance(debounce.local_tags["debounceOnTimer"], AOILocalTag)

    def test_local_tag_structure_drilldown(
        self, aoi_definitions: AOICollection
    ) -> None:
        """Structured local tags expose member drill-down."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        assert isinstance(timer, StructNode)
        assert timer.members["PRE"].value == 0
        assert timer.members["DN"].value == 0

    def test_local_tag_aoi_datatype_drilldown_uses_registry(
        self, aoi_definitions: AOICollection
    ) -> None:
        """AOI-typed local tags resolve nested members from AOI parameter defs."""
        generic_input = aoi_definitions["GenericInput"]
        nested = generic_input.local_tags["debounce"]
        assert isinstance(nested, StructNode)
        assert nested.members["EnableIn"].value == 1
        assert nested.members["state"].data_type == "BOOL"

    def test_local_tag_string_fallback(self, aoi_definitions: AOICollection) -> None:
        """String-format local tags fall back to DefaultData Format=String."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        robot_alarm_code = lookup.local_tags["robotAlarmCode"]
        assert robot_alarm_code.value == ""


class TestAOILocalTagTyping:
    """Tests for AOI local tag node typing and class caching."""

    def test_struct_local_tag_isinstance_node(
        self, aoi_definitions: AOICollection
    ) -> None:
        """A TIMER local tag is both an AOILocalTag and a StructNode."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        assert isinstance(timer, AOILocalTag)
        assert isinstance(timer, StructNode)
        assert type(timer).__name__ == "AOILocalStructTag"

    def test_struct_local_tag_class_caching(
        self, aoi_definitions: AOICollection
    ) -> None:
        """Multiple TIMER locals share the same class object (cached)."""
        debounce = aoi_definitions["Debounce"]
        timer1 = debounce.local_tags["debounceOnTimer"]
        generic_input = aoi_definitions["GenericInput"]
        timer2 = generic_input.local_tags["debounce"]
        # Both are StructNode-based local tags, so should have the same type
        assert type(timer1) is type(timer2)

    def test_integer_local_tag_with_properties(
        self, aoi_definitions: AOICollection
    ) -> None:
        """An integer local tag exposes its value, radix, and constraints."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        length = lookup.local_tags["length"]
        assert isinstance(length, IntegerNode)
        assert type(length).__name__ == "AOILocalIntegerTag"
        assert length.value == 0
        assert length.radix == "Decimal"
        assert length.min is None
        assert length.max is None
        assert length.bit_width == 32

    def test_integer_local_tag_describe(self, aoi_definitions: AOICollection) -> None:
        """describe() of integer local tag includes value and radix."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        length = lookup.local_tags["length"]
        desc = length.describe()
        assert "value: 0" in desc
        assert "radix: 'Decimal'" in desc

    def test_bool_local_tag(self, aoi_definitions: AOICollection) -> None:
        """A BOOL local tag is a BoolNode."""
        generic_input = aoi_definitions["GenericInput"]
        rising_ons = generic_input.local_tags["risingOns"]
        assert isinstance(rising_ons, BoolNode)
        assert rising_ons.data_type == "BOOL"
        assert rising_ons.value is False
        assert not hasattr(rising_ons, "min")

    def test_string_local_tag(self, aoi_definitions: AOICollection) -> None:
        """A STRING local tag is a StringNode."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        robot_alarm_code = lookup.local_tags["robotAlarmCode"]
        assert isinstance(robot_alarm_code, StringNode)
        assert robot_alarm_code.value == ""

    def test_local_tag_has_no_data_attribute(
        self, aoi_definitions: AOICollection
    ) -> None:
        """Typed local tags do not have a .data property (they ARE the node)."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        assert not hasattr(timer, "data")

    def test_local_tag_extra_attributes_excludes_radix_etc(
        self, aoi_definitions: AOICollection
    ) -> None:
        """Local tag.extra_attributes excludes Radix/Dimensions/Min/Max/ExternalLogging."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        length = lookup.local_tags["length"]
        assert length.element.get("Radix") == "Decimal"
        assert "Radix" not in length.extra_attributes

    def test_local_tag_element_property(self, aoi_definitions: AOICollection) -> None:
        """Local tag.element returns the raw <LocalTag> element."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        assert timer.element is not None
        assert timer.element.tag == "LocalTag"

    def test_local_tag_value_element_differs(
        self, aoi_definitions: AOICollection
    ) -> None:
        """For typed local tags, value_element is not the same as element."""
        debounce = aoi_definitions["Debounce"]
        timer = debounce.local_tags["debounceOnTimer"]
        # The typed local tag IS a StructNode, so it has a value_element
        assert timer.value_element is not timer.element


class TestAoiLogicText:
    """Tests for AOI-level logic rendering helpers."""

    def test_logic_text_contains_headers_and_code(
        self, aoi_definitions: AOICollection
    ) -> None:
        """AOI.logic_text emits AOI/routine headers and routine text."""
        lookup = aoi_definitions["FanucAlarmLookup"]
        text = lookup.logic_text()
        assert text.startswith("AOI: FanucAlarmLookup")
        assert "Routine: Logic (ST)" in text
        assert "recoverableAlarm := 0;" in text

    def test_print_logic_text_prints_and_returns(
        self,
        aoi_definitions: AOICollection,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """AOI.print_logic_text prints and returns the same content."""
        debounce = aoi_definitions["Debounce"]
        returned = debounce.print_logic_text()
        out = capsys.readouterr().out
        assert returned in out

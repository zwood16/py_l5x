"""Tests for py_l5x.parsers.module."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.module import (
    Communications,
    ConfigTag,
    Connection,
    InputTag,
    Module,
    ModulesCollection,
    OutputTag,
    Port,
)
from py_l5x.parsers.tag import ArrayNode, StructNode, TypeRegistry

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLE_L5X = FIXTURES_DIR / "example.L5X"


@pytest.fixture
def example_tree() -> ET.ElementTree:
    """Load the example L5X file."""
    return ET.parse(str(EXAMPLE_L5X))


@pytest.fixture
def controller_element(example_tree: ET.ElementTree) -> ET.Element:
    """Extract the <Controller> element from the example L5X."""
    controller = example_tree.getroot().find("Controller")
    assert controller is not None, "Controller element not found in example.L5X"
    return controller


@pytest.fixture
def type_registry(controller_element: ET.Element) -> TypeRegistry:
    """Build a TypeRegistry from the example L5X's UDT and AOI collections."""
    return TypeRegistry(
        DataTypesCollection(controller_element),
        AddOnDataTypeCollection(controller_element),
    )


@pytest.fixture
def modules(
    controller_element: ET.Element, type_registry: TypeRegistry
) -> ModulesCollection:
    """Modules collection."""
    return ModulesCollection(controller_element, type_registry)


class TestModulesCollection:
    """Tests for ModulesCollection mapping behavior."""

    def test_contains_expected_modules(self, modules: ModulesCollection) -> None:
        """Fixture exposes expected module names."""
        assert len(modules) == 7
        assert "Local" in modules
        assert "Test_Input_Module" in modules
        assert "Test_Safety_Input" in modules
        assert "ShopRobot" in modules
        assert "AnotherPLC" in modules
        assert "ValveBank" in modules
        assert "Test_Servo_Drive" in modules

    def test_getitem_returns_module(self, modules: ModulesCollection) -> None:
        """Indexing returns a Module wrapper."""
        assert isinstance(modules["Local"], Module)

    def test_missing_key_raises(self, modules: ModulesCollection) -> None:
        """Missing module name raises KeyError."""
        with pytest.raises(KeyError):
            modules["NoSuchModule"]


class TestLocalModule:
    """Tests for a local controller module with multiple ports and no comms."""

    def test_identity(self, modules: ModulesCollection) -> None:
        """Core identity properties map from XML attributes."""
        local = modules["Local"]
        assert local.catalog_number == "5069-L310ERMS3"
        assert local.vendor == "1"
        assert local.product_type == "14"
        assert local.product_code == "244"
        assert local.major == "37"
        assert local.minor == "11"
        assert local.inhibited is False
        assert local.major_fault is True
        assert local.ekey_state == "Disabled"

    def test_ports_view(self, modules: ModulesCollection) -> None:
        """Ports mapping supports membership, indexing, and typed fields."""
        local = modules["Local"]
        assert list(local.ports) == [1, 3, 4]

        port_1 = local.ports[1]
        assert isinstance(port_1, Port)
        assert port_1.address == "0"
        assert port_1.type == "5069"
        assert port_1.upstream is False
        assert port_1.bus_size == 9

        port_3 = local.ports[3]
        assert port_3.address == ""
        assert port_3.bus_size is None

    def test_communications_with_no_connections(
        self, modules: ModulesCollection
    ) -> None:
        """Local module's Communications block has no connections configured."""
        local = modules["Local"]
        comms = local.communications
        assert isinstance(comms, Communications)
        assert comms.comm_method == ""
        assert len(comms.connections) == 0


class TestTestInputModule:
    """Tests for a 5069 input module with ConfigTag and InputTag payloads."""

    def test_metadata_and_description(self, modules: ModulesCollection) -> None:
        """Identity, optional booleans, and description are exposed."""
        mod = modules["Test_Input_Module"]
        assert mod.description == "An example of a IB16 Input modele"
        assert mod.safety_enabled is False
        assert mod.auto_diags_enabled is True
        assert mod.data_exchange_id == "{4BD11653-8FB3-44A6-9DFA-05BD9D6EF443}"
        assert mod.extended_properties_xml is not None
        assert "Rockwell Automation/Allen-Bradley" in mod.extended_properties_xml

    def test_comms_config_tag(self, modules: ModulesCollection) -> None:
        """ConfigTag parses as a structure for this module type."""
        mod = modules["Test_Input_Module"]
        comms = mod.communications
        assert isinstance(comms, Communications)
        assert comms.comm_method == ""
        assert comms.prim_cxn_input_size is None
        assert comms.prim_cxn_output_size is None

        config = comms.config_tag
        assert isinstance(config, ConfigTag)
        assert config.external_access == "Read/Write"
        assert config.config_size == 64

        data = config.data
        assert isinstance(data, StructNode)
        assert data.members["Pt00"].members["InputOffOnFilter"].value == 13
        assert data.members["Pt15"].members["InputOnOffFilter"].value == 13

    def test_single_input_connection(self, modules: ModulesCollection) -> None:
        """InputData connection fields and InputTag payload are parsed."""
        mod = modules["Test_Input_Module"]
        comms = mod.communications
        assert isinstance(comms, Communications)

        assert list(comms.connections) == ["InputData"]
        conn = comms.connections["InputData"]
        assert isinstance(conn, Connection)

        assert conn.rpi == 5000
        assert conn.type == "StandardDataDriven"
        assert conn.input_size == 68
        assert conn.output_size == 0
        assert conn.priority == "Scheduled"
        assert conn.input_connection_type == "Multicast"
        assert conn.input_production_trigger == "Cyclic"
        assert conn.input_tag_suffix == "I"
        assert conn.output_tag_suffix == ""
        assert conn.unicast is None

        input_tag = conn.input_tag
        assert isinstance(input_tag, InputTag)
        assert input_tag.external_access == "Read/Write"
        assert input_tag.value is None
        assert input_tag.members["RunMode"].value == 0
        assert input_tag.members["Pt00"].members["Data"].value == 0


class TestEthernetAndValveBankModules:
    """Tests for ethernet modules with array-based module data payloads."""

    def test_shoprobot_config_data_array(self, modules: ModulesCollection) -> None:
        """ShopRobot ConfigTag exposes the Data array as the logical root."""
        shop = modules["ShopRobot"]
        comms = shop.communications
        assert isinstance(comms, Communications)
        assert comms.comm_method == "536870916"
        assert comms.prim_cxn_input_size == 260
        assert comms.prim_cxn_output_size == 52

        config = comms.config_tag
        assert isinstance(config, ConfigTag)
        data = config.data
        assert isinstance(data, ArrayNode)
        assert len(data.elements) == 400
        assert data.elements[0].value == 0
        assert data.elements[0].raw_value == "16#00"
        assert data.elements[0].radix == "Hex"

        standard = comms.connections["Standard"]
        assert standard.unicast is True
        assert standard.input_cxn_point == 100
        assert standard.output_cxn_point == 101
        assert isinstance(standard.input_tag, InputTag)
        assert isinstance(standard.output_tag, OutputTag)

        input_tag = standard.input_tag
        assert isinstance(input_tag, InputTag)
        assert len(input_tag.elements) == 260

        output_tag = standard.output_tag
        assert isinstance(output_tag, OutputTag)
        assert len(output_tag.elements) == 52

    def test_valvebank_connection_and_payload(self, modules: ModulesCollection) -> None:
        """ValveBank parses both InputTag and OutputTag Data arrays."""
        valve = modules["ValveBank"]
        comms = valve.communications
        assert isinstance(comms, Communications)
        assert comms.config_tag is None

        conn = comms.connections["_200424692C962C64"]
        assert conn.type == "StandardDataDriven"
        assert conn.input_size == 8
        assert conn.output_size == 4
        assert conn.input_tag_suffix == "I"
        assert conn.output_tag_suffix == "O"
        assert conn.unicast is None

        input_tag = conn.input_tag
        assert isinstance(input_tag, InputTag)
        assert input_tag.members["ConnectionFaulted"].value == 0
        assert len(input_tag.elements) == 4

        output_tag = conn.output_tag
        assert isinstance(output_tag, OutputTag)
        assert len(output_tag.elements) == 4
        assert output_tag.elements[3].value == 0

"""Tests for py_l5x.parsers.module."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.aoi import AOIDataTypesCollection
from py_l5x.parsers.datatype import DataTypesCollection
from py_l5x.parsers.module import (
    Communications,
    ConfigTag,
    Connection,
    InputTag,
    Module,
    ModulesCollection,
    ModuleTagRef,
    ModuleTagsView,
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
        AOIDataTypesCollection(controller_element),
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
        expected = [
            "Local",
            "Test_Input_Module",
            "Test_Safety_Input",
            "Fast_Local_Input",
            "ShopRobot",
            "AnotherPLC",
            "ValveBank",
            "Test_Servo_Drive",
            "PointIO",
            "PointIO_Input",
            "PointIO_Output",
            "PointIO_AnalogInput",
            "PointIO_AnalogOutput",
            "PointIO_SafetyInput",
            "PointIO_SafetyOutput",
            "Compact5000_IO_Adapter",
            "Remote_Output",
        ]
        assert len(modules) == 17
        assert sorted(modules) == sorted(expected)

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
        assert input_tag.data is not None
        assert isinstance(input_tag.data, StructNode)
        assert input_tag.data.members["RunMode"].value == 0
        assert input_tag.data.members["Pt00"].members["Data"].value == 0


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
        assert input_tag.data is not None
        # ShopRobot input is a Structure with a Data member (which is an array)
        assert isinstance(input_tag.data, StructNode)
        assert isinstance(input_tag.data.members["Data"], ArrayNode)
        assert len(input_tag.data.members["Data"].elements) == 260

        output_tag = standard.output_tag
        assert isinstance(output_tag, OutputTag)
        assert output_tag.data is not None
        # ShopRobot output is a Structure with a Data member (which is an array)
        assert isinstance(output_tag.data, StructNode)
        assert isinstance(output_tag.data.members["Data"], ArrayNode)
        assert len(output_tag.data.members["Data"].elements) == 52

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
        assert input_tag.data is not None
        assert isinstance(input_tag.data, StructNode)
        assert input_tag.data.members["ConnectionFaulted"].value == 0
        assert len(input_tag.data.members["Data"].elements) == 4

        output_tag = conn.output_tag
        assert isinstance(output_tag, OutputTag)
        assert output_tag.data is not None
        # ValveBank output is a Structure with a Data member (which is an array)
        assert isinstance(output_tag.data, StructNode)
        assert isinstance(output_tag.data.members["Data"], ArrayNode)
        assert len(output_tag.data.members["Data"].elements) == 4
        assert output_tag.data.members["Data"].elements[3].value == 0


class TestModuleDataTagProperties:
    """Tests for ModuleDataTag property deletion."""

    def test_module_input_tag_no_value_shortcut(
        self, modules: ModulesCollection
    ) -> None:
        """ModuleDataTag no longer exposes .value shortcut."""
        mod = modules["Test_Input_Module"]
        input_tag = mod.communications.connections["InputData"].input_tag
        assert not hasattr(input_tag, "value")

    def test_module_input_tag_no_members_shortcut(
        self, modules: ModulesCollection
    ) -> None:
        """ModuleDataTag no longer exposes .members shortcut."""
        mod = modules["Test_Input_Module"]
        input_tag = mod.communications.connections["InputData"].input_tag
        assert not hasattr(input_tag, "members")

    def test_module_input_tag_no_elements_shortcut(
        self, modules: ModulesCollection
    ) -> None:
        """ModuleDataTag no longer exposes .elements shortcut."""
        mod = modules["Test_Input_Module"]
        input_tag = mod.communications.connections["InputData"].input_tag
        assert not hasattr(input_tag, "elements")


class TestModuleTagsView:
    """Tests for Module.tags / ModuleTagsView global-name exposure."""

    def test_remote_module_uses_module_name_prefix(
        self, modules: ModulesCollection
    ) -> None:
        """Remote module tag names use <ModuleName>:<suffix>."""
        mod = modules["ValveBank"]
        assert mod.tag_prefix == "ValveBank"
        assert list(mod.tags) == ["ValveBank:I", "ValveBank:O"]

    def test_remote_module_tag_data_and_backrefs(
        self, modules: ModulesCollection
    ) -> None:
        """A module tag ref exposes .data and back-references to its module."""
        mod = modules["ValveBank"]
        ref = mod.tags["ValveBank:I"]
        assert isinstance(ref, ModuleTagRef)
        assert isinstance(ref.data, StructNode)
        assert "ConnectionFaulted" in ref.data.members
        assert ref.module is mod
        assert ref.module_name == "ValveBank"
        assert ref.kind == "I"
        # Back-reference to the owning connection (matched by name, since the
        # connections collection builds a fresh wrapper on each access).
        assert ref.connection is not None
        assert ref.connection.name == "_200424692C962C64"

    def test_config_tag_and_default_suffixes(self, modules: ModulesCollection) -> None:
        """Config tag gets :C; missing suffixes derive from the data type."""
        mod = modules["ShopRobot"]
        assert list(mod.tags) == ["ShopRobot:C", "ShopRobot:I", "ShopRobot:O"]
        config_ref = mod.tags["ShopRobot:C"]
        # Config tags are not owned by a connection.
        assert config_ref.connection is None
        assert config_ref.kind == "C"

    def test_local_backplane_module_uses_position_prefix(
        self, modules: ModulesCollection
    ) -> None:
        """Local backplane modules are addressed as Local:<position>:<suffix>."""
        input_mod = modules["Test_Input_Module"]
        assert input_mod.tag_prefix == "Local:1"
        assert list(input_mod.tags) == ["Local:1:C", "Local:1:I"]

        safety_mod = modules["Test_Safety_Input"]
        assert safety_mod.tag_prefix == "Local:2"
        assert list(safety_mod.tags) == ["Local:2:I"]

    def test_servo_drive_suffixes_derived_from_data_type(
        self, modules: ModulesCollection
    ) -> None:
        """Servo drive tag suffixes (S/SI/SO) come from the data type.

        Studio 5000 creates tags only where the L5X has tag elements; this
        servo's diagnostic connection has them, so ``S`` is exposed as well.
        """
        mod = modules["Test_Servo_Drive"]
        names = list(mod.tags)
        assert "Test_Servo_Drive:S" in names  # diagnostics (non-safety)
        assert "Test_Servo_Drive:SI" in names  # safety input
        assert "Test_Servo_Drive:SO" in names  # safety output

    def test_local_chassis_has_no_tags(self, modules: ModulesCollection) -> None:
        """The Local chassis module exposes no tag-bearing communication."""
        local = modules["Local"]
        assert len(local.tags) == 0
        assert list(local.tags) == []

    def test_tag_ref_getattr_forwards_unknown_attributes(
        self, modules: ModulesCollection
    ) -> None:
        """Unknown attributes forward to the wrapped tag; absent ones raise."""
        ref = modules["ValveBank"].tags["ValveBank:I"]
        # Forwarded attribute that exists on the wrapped InputTag.
        assert ref.external_access == "Read/Write"
        # Attribute that does not exist anywhere -> AttributeError, not a
        # forwarded value.
        with pytest.raises(AttributeError):
            _ = ref.does_not_exist  # type: ignore[attr-defined]

    def test_module_tags_view_is_mapping(self, modules: ModulesCollection) -> None:
        """Module.tags supports the Mapping protocol."""
        view: ModuleTagsView = modules["ValveBank"].tags
        assert "ValveBank:I" in view
        assert "ValveBank:X" not in view
        assert len(view) == 2
        with pytest.raises(KeyError):
            _ = view["ValveBank:X"]


#: Ground truth from a Studio 5000 tag export of example.L5X:
#: global name -> (data type, class).
EXPECTED_MODULE_TAGS: dict[str, tuple[str, str]] = {
    "ValveBank:I": ("_0007:EX600_SEN78_85D36DB4:I:0", "Standard"),
    "ValveBank:O": ("_0007:EX600_SEN78_AAB94180:O:0", "Standard"),
    "Test_Servo_Drive:S": ("AB:Motion_Diagnostics:S:1", "Standard"),
    "Test_Servo_Drive:SI": ("AB:CIP_Drive_Safety1:SI:0", "Safety"),
    "Test_Servo_Drive:SO": ("AB:CIP_Drive_Safety1:SO:0", "Safety"),
    "Local:1:C": ("AB:5000_DI16:C:0", "Standard"),
    "Local:1:I": ("AB:5000_DI16:I:0", "Standard"),
    "Local:2:I": ("AB:5000_SDI8:I:0", "Safety"),
    "Local:3:C": ("AB:5000_DI16_Timestamp:C:0", "Standard"),
    "Local:3:EI": ("AB:5000_DI16_Event4:EI:0", "Standard"),
    "Local:3:EO": ("AB:5000_DI16_Event4:EO:0", "Standard"),
    "Local:3:I": ("AB:5000_DI16_Timestamp_Event4:I:0", "Standard"),
    "Local:3:O": ("AB:5000_DI16_Timestamp:O:0", "Standard"),
    "PointIO:1:C": ("AB:1734_DI8:C:0", "Standard"),
    "PointIO:2:C": ("AB:1734_DO8_NoDiag:C:0", "Standard"),
    "PointIO:3:C": ("AB:1734_IE2:C:0", "Standard"),
    "PointIO:3:I": ("AB:1734_IE2:I:0", "Standard"),
    "PointIO:4:C": ("AB:1734_OE2:C:0", "Standard"),
    "PointIO:4:I": ("AB:1734_OE2:I:0", "Standard"),
    "PointIO:4:O": ("AB:1734_OE2:O:0", "Standard"),
    "PointIO:5:I": ("AB:1734_IB8S_Safety2:I:0", "Safety"),
    "PointIO:5:O": ("AB:1734_IB8S:O:0", "Safety"),
    "PointIO:6:I": ("AB:1734_OB8S_Safety1:I:0", "Safety"),
    "PointIO:6:O": ("AB:1734_OB8S:O:0", "Safety"),
    "PointIO:I": ("AB:1734_7SLOT:I:0", "Standard"),
    "PointIO:O": ("AB:1734_7SLOT:O:0", "Standard"),
    "Compact5000_IO_Adapter:1:C": ("AB:5000_DO16_Diag:C:0", "Standard"),
    "Compact5000_IO_Adapter:1:I": ("AB:5000_DO16_Diag:I:0", "Standard"),
    "Compact5000_IO_Adapter:1:O": ("AB:5000_DO16:O:0", "Standard"),
    "ShopRobot:C": ("AB:ETHERNET_MODULE:C:0", "Standard"),
    "ShopRobot:I": ("AB:ETHERNET_MODULE_SINT_260Bytes:I:0", "Standard"),
    "ShopRobot:O": ("AB:ETHERNET_MODULE_SINT_52Bytes:O:0", "Standard"),
}


class TestExampleModuleTagsGroundTruth:
    """Module tag names, data types, and classes match Studio 5000 exports."""

    def test_union_of_module_tags_matches_studio(
        self, modules: ModulesCollection
    ) -> None:
        """All module tag names, types, and classes match the Studio export."""
        refs = {
            ref.name: ref for module in modules.values() for ref in module.tags.values()
        }
        assert set(refs) == set(EXPECTED_MODULE_TAGS)
        for name, (data_type, class_) in EXPECTED_MODULE_TAGS.items():
            assert refs[name].data_type == data_type, name
            assert refs[name].class_ == class_, name
            assert refs[name].is_safety == (class_ == "Safety"), name

    def test_direct_value_access_matches_data(self, modules: ModulesCollection) -> None:
        """Value-node attributes work directly on the ref, matching ``.data``."""
        valve = modules["ValveBank"].tags["ValveBank:I"]
        assert "ConnectionFaulted" in valve.members
        assert list(valve.members) == list(valve.data.members)

        config = modules["ShopRobot"].tags["ShopRobot:C"]
        assert config.data is not None
        assert len(config.elements) == len(config.data.elements)

    def test_safety_repr_shows_class(self, modules: ModulesCollection) -> None:
        """Safety tags show their class in the repr; standard tags do not."""
        safety = modules["Test_Safety_Input"].tags["Local:2:I"]
        assert safety.class_ == "Safety"
        assert "class_: 'Safety'" in repr(safety)
        standard = modules["Test_Input_Module"].tags["Local:1:I"]
        assert "class_" not in repr(standard)


def _build_modules(modules_xml: str) -> ModulesCollection:
    """Build a ModulesCollection from synthetic ``<Module>`` XML."""
    controller = ET.fromstring(
        "<Controller Name='Synthetic'><DataTypes/>"
        "<AddOnInstructionDefinitions/>"
        f"<Modules>{modules_xml}</Modules></Controller>"
    )
    registry = TypeRegistry(
        DataTypesCollection(controller), AOIDataTypesCollection(controller)
    )
    return ModulesCollection(controller, registry)


_LOCAL_CHASSIS_XML = (
    '<Module Name="Local" ParentModule="Local" ParentModPortId="1">'
    '<Ports><Port Id="1" Address="0" Type="5069" Upstream="false"/></Ports>'
    "</Module>"
)


class TestTagPrefixRules:
    """Module.tag_prefix addresses backplane modules by parent and slot."""

    def test_local_backplane_slot_uses_upstream_address(self) -> None:
        """A local-chassis 5069 module is ``Local:<upstream address>``.

        ParentModPortId is the parent's port number and must not be used.
        """
        modules = _build_modules(
            _LOCAL_CHASSIS_XML
            + '<Module Name="Slot_Module" ParentModule="Local" ParentModPortId="1">'
            '<Ports><Port Id="1" Address="4" Type="5069" Upstream="true"/></Ports>'
            "</Module>"
        )
        assert modules["Slot_Module"].tag_prefix == "Local:4"
        assert modules["Local"].tag_prefix == "Local"

    def test_module_in_remote_rack_uses_adapter_name(self) -> None:
        """A module behind a remote adapter is ``<Adapter>:<slot>``."""
        modules = _build_modules(
            _LOCAL_CHASSIS_XML
            + '<Module Name="Adapter" ParentModule="Local" ParentModPortId="3">'
            '<Ports><Port Id="1" Address="0" Type="5069" Upstream="false"/>'
            '<Port Id="2" Address="10.0.0.5" Type="Ethernet" Upstream="true"/>'
            "</Ports></Module>"
            '<Module Name="Remote_Slot" ParentModule="Adapter" ParentModPortId="1">'
            '<Ports><Port Id="1" Address="2" Type="5069" Upstream="true"/></Ports>'
            "</Module>"
        )
        assert modules["Adapter"].tag_prefix == "Adapter"
        assert modules["Remote_Slot"].tag_prefix == "Adapter:2"

    def test_1756_icp_local_module_uses_local_prefix(self) -> None:
        """A ControlLogix ICP upstream port is a backplane slot on the chassis."""
        modules = _build_modules(
            '<Module Name="Local" ParentModule="Local" ParentModPortId="1">'
            '<Ports><Port Id="1" Address="0" Type="ICP" Upstream="false"/></Ports>'
            "</Module>"
            '<Module Name="ICP_Module" ParentModule="Local" ParentModPortId="1">'
            '<Ports><Port Id="1" Address="2" Type="ICP" Upstream="true"/></Ports>'
            "</Module>"
        )
        assert modules["ICP_Module"].tag_prefix == "Local:2"

    @pytest.mark.parametrize("port_type", ["Ethernet", "ControlNet", "DeviceNet"])
    def test_network_upstream_uses_own_name(self, port_type: str) -> None:
        """Modules on a network upstream port are named after themselves."""
        modules = _build_modules(
            _LOCAL_CHASSIS_XML
            + '<Module Name="Net_Module" ParentModule="Local" ParentModPortId="3">'
            f'<Ports><Port Id="2" Address="192.168.1.10" Type="{port_type}" '
            'Upstream="true"/></Ports>'
            "</Module>"
        )
        assert modules["Net_Module"].tag_prefix == "Net_Module"

    def test_upstream_without_address_uses_own_name(self) -> None:
        """A backplane upstream port with no address gives no slot; use the name."""
        modules = _build_modules(
            _LOCAL_CHASSIS_XML
            + '<Module Name="No_Addr" ParentModule="Local" ParentModPortId="1">'
            '<Ports><Port Id="1" Type="5069" Upstream="true"/></Ports>'
            "</Module>"
        )
        assert modules["No_Addr"].tag_prefix == "No_Addr"


class TestModuleTagsDedup:
    """Duplicate global names collapse to the first tag, consistently."""

    def test_first_duplicate_wins(self) -> None:
        """Iteration, indexing, and length all agree on the first tag per name."""
        tag_xml = (
            '<InputTag ExternalAccess="{access}"><Data Format="Decorated">'
            '<Structure DataType="AB:Dup:I:0"/></Data></InputTag>'
        )
        modules = _build_modules(
            '<Module Name="Dup" ParentModule="Local">'
            '<Ports><Port Id="2" Address="10.0.0.9" Type="Ethernet" '
            'Upstream="true"/></Ports>'
            "<Communications><Connections>"
            '<Connection Name="First" Type="Input" InputTagSuffix="I">'
            + tag_xml.format(access="Read/Write")
            + "</Connection>"
            '<Connection Name="Second" Type="Input" InputTagSuffix="I">'
            + tag_xml.format(access="Read Only")
            + "</Connection>"
            "</Connections></Communications></Module>"
        )
        view = modules["Dup"].tags
        assert list(view) == ["Dup:I"]
        assert len(view) == 1
        ref = view["Dup:I"]
        assert ref.connection is not None
        assert ref.connection.name == "First"
        assert ref.external_access == "Read/Write"


class TestRealWorldModuleFixtures:
    """Fixture checks for Point I/O, Compact 5000, and multi-connection modules."""

    @pytest.mark.parametrize(
        ("module_name", "expected_prefix"),
        [
            ("PointIO", "PointIO"),
            ("PointIO_Input", "PointIO:1"),
            ("PointIO_SafetyOutput", "PointIO:6"),
            ("Compact5000_IO_Adapter", "Compact5000_IO_Adapter"),
            ("Remote_Output", "Compact5000_IO_Adapter:1"),
            ("Fast_Local_Input", "Local:3"),
        ],
    )
    def test_tag_prefix_for_real_modules(
        self, modules: ModulesCollection, module_name: str, expected_prefix: str
    ) -> None:
        """Parent/slot rule matches the prefixes Studio 5000 uses in the export."""
        assert modules[module_name].tag_prefix == expected_prefix

    @pytest.mark.parametrize(
        "module_name", ["Local", "AnotherPLC", "Compact5000_IO_Adapter"]
    )
    def test_adapters_and_controllers_have_no_tags(
        self, modules: ModulesCollection, module_name: str
    ) -> None:
        """Controllers and adapters without tag elements expose no module tags."""
        assert len(modules[module_name].tags) == 0

    def test_point_io_adapter_rack_optimized_tags(
        self, modules: ModulesCollection
    ) -> None:
        """The Point I/O adapter exposes its own Output connection as I/O tags."""
        assert list(modules["PointIO"].tags) == ["PointIO:I", "PointIO:O"]

    @pytest.mark.parametrize(
        ("module_name", "tag_name"),
        [("PointIO_Input", "PointIO:1:C"), ("PointIO_Output", "PointIO:2:C")],
    )
    def test_config_only_slots_expose_only_config_tag(
        self, modules: ModulesCollection, module_name: str, tag_name: str
    ) -> None:
        """Config-only Point I/O slots expose just the :C tag, with no connection."""
        mod = modules[module_name]
        assert list(mod.tags) == [tag_name]
        ref = mod.tags[tag_name]
        assert ref.kind == "C"
        assert ref.connection is None

    def test_multi_connection_module_tags_in_order(
        self, modules: ModulesCollection
    ) -> None:
        """Fast_Local_Input exposes C, I, O, and event tags with explicit suffixes."""
        tags = modules["Fast_Local_Input"].tags
        assert list(tags) == [
            "Local:3:C",
            "Local:3:I",
            "Local:3:O",
            "Local:3:EI",
            "Local:3:EO",
        ]
        ei = tags["Local:3:EI"]
        eo = tags["Local:3:EO"]
        assert ei.kind == "EI"
        assert eo.kind == "EO"
        assert ei.connection is not None
        assert eo.connection is not None
        assert ei.connection.name == "InputDataEvent"
        assert eo.connection.name == "InputDataEvent"

    def test_point_io_safety_split_connections(
        self, modules: ModulesCollection
    ) -> None:
        """Safety Point I/O modules split I and O across SafetyInput/SafetyOutput."""
        mod = modules["PointIO_SafetyInput"]
        tag_in = mod.tags["PointIO:5:I"]
        tag_out = mod.tags["PointIO:5:O"]
        assert tag_in.connection is not None
        assert tag_out.connection is not None
        assert tag_in.connection.type == "SafetyInput"
        assert tag_out.connection.type == "SafetyOutput"
        for ref in (tag_in, tag_out):
            assert ref.class_ == "Safety"
            assert ref.is_safety is True

    def test_point_io_standard_connection_is_standard(
        self, modules: ModulesCollection
    ) -> None:
        """A standard Point I/O input tag is classed Standard, not Safety."""
        ref = modules["PointIO_AnalogInput"].tags["PointIO:3:I"]
        assert ref.class_ == "Standard"
        assert ref.is_safety is False

    def test_value_access_on_point_io_ref(self, modules: ModulesCollection) -> None:
        """Member access on a Point I/O ref matches its underlying data."""
        ref = modules["PointIO_AnalogInput"].tags["PointIO:3:I"]
        assert len(ref.members) > 0
        assert list(ref.members) == list(ref.data.members)


class TestModuleTagValueForwarding:
    """Value-node attributes forward from the ref to its root node."""

    def test_struct_ref_forwards_members(self, modules: ModulesCollection) -> None:
        """A struct-rooted ref exposes ``members``, not ``elements``/``value``."""
        ref = modules["ValveBank"].tags["ValveBank:I"]
        assert "ConnectionFaulted" in ref.members
        assert list(ref.members) == list(ref.data.members)
        with pytest.raises(AttributeError, match="ModuleTagRef"):
            _ = ref.elements  # type: ignore[attr-defined]
        with pytest.raises(AttributeError, match="ModuleTagRef"):
            _ = ref.value  # type: ignore[attr-defined]

    def test_config_array_ref_forwards_elements(
        self, modules: ModulesCollection
    ) -> None:
        """A ConfigTag whose data unwraps to an array exposes ``elements``."""
        ref = modules["ShopRobot"].tags["ShopRobot:C"]
        assert isinstance(ref.data, ArrayNode)
        assert len(ref.elements) == len(ref.data.elements) == 400
        with pytest.raises(AttributeError, match="ModuleTagRef"):
            _ = ref.members  # type: ignore[attr-defined]

    def test_scalar_ref_forwards_value(self) -> None:
        """A scalar-rooted ref exposes ``value``; members/elements do not apply."""
        modules = _build_modules(
            _LOCAL_CHASSIS_XML
            + '<Module Name="Scalar" ParentModule="Local" ParentModPortId="1">'
            '<Ports><Port Id="1" Address="0" Type="5069" Upstream="false"/></Ports>'
            '<Communications CommMethod="4"><Connections>'
            '<Connection Name="Cxn" Type="Standard">'
            '<InputTag ExternalAccess="Read Only">'
            '<Data Format="Decorated">'
            '<DataValue DataType="BOOL" Radix="Decimal" Value="1"/>'
            "</Data></InputTag></Connection></Connections></Communications>"
            "</Module>"
        )
        ref = modules["Scalar"].tags["Scalar:I"]
        assert ref.value is True
        assert ref.value == ref.data.value
        with pytest.raises(AttributeError, match="ModuleTagRef"):
            _ = ref.members  # type: ignore[attr-defined]

    def test_non_applicable_attribute_error_names_module_tag_ref(
        self, modules: ModulesCollection
    ) -> None:
        """Accessing ``elements`` on a struct-rooted ConfigTag ref reports ModuleTagRef.

        The message must name the ref type, not the wrapped ConfigTag.
        """
        ref = modules["Test_Input_Module"].tags["Local:1:C"]
        assert isinstance(ref.data, StructNode)
        with pytest.raises(AttributeError) as excinfo:
            _ = ref.elements  # type: ignore[attr-defined]
        message = str(excinfo.value)
        assert "ModuleTagRef" in message
        assert "ConfigTag" not in message
        assert "'elements'" in message

    def test_unknown_attribute_error_names_module_tag_ref(
        self, modules: ModulesCollection
    ) -> None:
        """Unknown attributes on a ref raise AttributeError naming ModuleTagRef."""
        ref = modules["Test_Input_Module"].tags["Local:1:C"]
        with pytest.raises(AttributeError) as excinfo:
            _ = ref.does_not_exist  # type: ignore[attr-defined]
        assert str(excinfo.value) == (
            "'ModuleTagRef' object has no attribute 'does_not_exist'"
        )

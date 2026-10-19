"""Tests for py_l5x.parsers.controller."""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.controller import (
    ControllerInfo,
    EthernetPort,
    SafetyInfo,
    TimeSynchronize,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLE_L5X = FIXTURES_DIR / "example.L5X"

#: Matches Logix's exported date format, e.g. "Tue Jun 30 10:14:37 2026".
_DATE_RE = re.compile(r"^[A-Z][a-z]{2} [A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4}$")


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
def controller(controller_element: ET.Element) -> ControllerInfo:
    """Create a ControllerInfo instance from the example L5X."""
    return ControllerInfo(controller_element)


# ---------------------------------------------------------------------------
# Identity properties
# ---------------------------------------------------------------------------


class TestControllerIdentity:
    """Tests for controller identity properties."""

    def test_name(self, controller: ControllerInfo) -> None:
        """Controller name matches the Name attribute."""
        assert controller.name == "Example_PLC"

    def test_use(self, controller: ControllerInfo) -> None:
        """Use attribute returns the export target role."""
        assert controller.use == "Target"

    def test_processor_type(self, controller: ControllerInfo) -> None:
        """Processor type returns the catalog number."""
        assert controller.processor_type == "5069-L310ERMS3"


# ---------------------------------------------------------------------------
# Revision properties
# ---------------------------------------------------------------------------


class TestControllerRevision:
    """Tests for controller revision properties."""

    def test_major_rev(self, controller: ControllerInfo) -> None:
        """Major revision matches MajorRev attribute."""
        assert controller.major_rev == "37"

    def test_minor_rev(self, controller: ControllerInfo) -> None:
        """Minor revision matches MinorRev attribute."""
        assert controller.minor_rev == "11"


# ---------------------------------------------------------------------------
# Date / identifier properties
# ---------------------------------------------------------------------------


class TestControllerDates:
    """Tests for controller date and identifier properties."""

    def test_project_creation_date(self, controller: ControllerInfo) -> None:
        """Project creation date matches the Logix export date format."""
        assert _DATE_RE.match(controller.project_creation_date)

    def test_last_modified_date(self, controller: ControllerInfo) -> None:
        """Last modified date matches the Logix export date format."""
        assert _DATE_RE.match(controller.last_modified_date)

    def test_project_sn(self, controller: ControllerInfo) -> None:
        """Project serial number matches ProjectSN attribute."""
        assert controller.project_sn == "16#0000_0000"


# ---------------------------------------------------------------------------
# Extra attributes
# ---------------------------------------------------------------------------


class TestControllerExtraAttributes:
    """Tests for the extra_attributes property."""

    def test_extra_attributes_contains_unknown_keys(
        self, controller: ControllerInfo
    ) -> None:
        """Extra attributes include keys not covered by explicit properties."""
        extras = controller.extra_attributes
        assert "SFCExecutionControl" in extras

    def test_extra_attributes_excludes_known_keys(
        self, controller: ControllerInfo
    ) -> None:
        """Known keys are excluded from extra_attributes."""
        extras = controller.extra_attributes
        for key in ("Name", "Use", "ProcessorType", "MajorRev", "MinorRev"):
            assert key not in extras

    def test_extra_attributes_values(self, controller: ControllerInfo) -> None:
        """Extra attribute values match the XML."""
        extras = controller.extra_attributes
        assert extras["SFCExecutionControl"] == "CurrentActive"
        assert extras["SFCRestartPosition"] == "MostRecent"

    def test_extra_attributes_is_dict(self, controller: ControllerInfo) -> None:
        """Extra attributes returns a dictionary."""
        assert isinstance(controller.extra_attributes, dict)


# ---------------------------------------------------------------------------
# All attributes
# ---------------------------------------------------------------------------


class TestControllerAttributes:
    """Tests for the attributes property."""

    def test_attributes_contains_all_keys(self, controller: ControllerInfo) -> None:
        """Attributes includes both known and unknown keys."""
        attrs = controller.attributes
        assert "Name" in attrs
        assert "Use" in attrs
        assert "ProcessorType" in attrs
        assert "SFCExecutionControl" in attrs

    def test_attributes_values(self, controller: ControllerInfo) -> None:
        """Attribute values match the XML."""
        attrs = controller.attributes
        assert attrs["Name"] == "Example_PLC"
        assert attrs["Use"] == "Target"
        assert attrs["ProcessorType"] == "5069-L310ERMS3"

    def test_attributes_is_dict(self, controller: ControllerInfo) -> None:
        """Attributes returns a dictionary."""
        assert isinstance(controller.attributes, dict)

    def test_attributes_superset_of_extra(self, controller: ControllerInfo) -> None:
        """Attributes contains everything in extra_attributes plus known keys."""
        attrs = controller.attributes
        extras = controller.extra_attributes
        for k, v in extras.items():
            assert attrs[k] == v


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------


class TestControllerRepr:
    """Tests for the __repr__ method."""

    def test_repr_contains_name(self, controller: ControllerInfo) -> None:
        """Repr string contains the controller name."""
        assert "Example_PLC" in repr(controller)

    def test_repr_contains_processor_type(self, controller: ControllerInfo) -> None:
        """Repr string contains the processor type."""
        assert "5069-L310ERMS3" in repr(controller)

    def test_repr_contains_firmware(self, controller: ControllerInfo) -> None:
        """Repr string contains the firmware version."""
        assert "37.11" in repr(controller)

    def test_repr_contains_extra_attributes_header(
        self, controller: ControllerInfo
    ) -> None:
        """Repr includes 'Extra Attributes' header when extras exist."""
        assert "Extra Attributes:" in repr(controller)

    def test_repr_is_multiline(self, controller: ControllerInfo) -> None:
        """Repr string contains multiple lines."""
        lines = repr(controller).splitlines()
        assert len(lines) > 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestControllerEdgeCases:
    """Tests for edge cases with minimal or missing attributes."""

    def test_minimal_controller(self) -> None:
        """Controller with only required attrs returns None for missing metadata."""
        el = ET.Element("Controller", Name="Minimal", Use="Target")
        ctrl = ControllerInfo(el)
        assert ctrl.name == "Minimal"
        assert ctrl.use == "Target"
        assert ctrl.processor_type is None
        assert ctrl.major_rev is None
        assert ctrl.minor_rev is None
        assert not ctrl.is_context

    def test_context_controller(self) -> None:
        """Context controllers (component exports) report is_context, no metadata."""
        el = ET.Element("Controller", Name="Example_PLC", Use="Context")
        ctrl = ControllerInfo(el)
        assert ctrl.is_context
        assert ctrl.processor_type is None
        assert ctrl.major_rev is None
        assert ctrl.minor_rev is None
        assert ctrl.project_creation_date is None
        assert ctrl.last_modified_date is None
        assert ctrl.project_sn is None

    def test_empty_extra_attributes(self) -> None:
        """Controller with only known keys has empty extra_attributes."""
        el = ET.Element(
            "Controller",
            Name="Test",
            Use="Target",
            ProcessorType="5069-L306ERM",
        )
        ctrl = ControllerInfo(el)
        assert ctrl.extra_attributes == {}

    def test_repr_with_no_extras(self) -> None:
        """Repr does not include 'Extra Attributes' header when none exist."""
        el = ET.Element(
            "Controller",
            Name="Test",
            Use="Target",
            ProcessorType="5069-L306ERM",
            MajorRev="1",
            MinorRev="0",
            ProjectCreationDate="2026-01-01",
            LastModifiedDate="2026-01-02",
        )
        ctrl = ControllerInfo(el)
        assert "Extra Attributes:" not in repr(ctrl)


# ---------------------------------------------------------------------------
# Safety controller
# ---------------------------------------------------------------------------


class TestControllerSafety:
    """Tests for SafetyInfo / is_safety_controller."""

    def test_is_safety_controller(self, controller: ControllerInfo) -> None:
        """Example controller has a SafetyInfo element."""
        assert controller.is_safety_controller is True

    def test_safety_info_type(self, controller: ControllerInfo) -> None:
        """safety_info returns a SafetyInfo instance."""
        assert isinstance(controller.safety_info, SafetyInfo)

    def test_safety_info_fields(self, controller: ControllerInfo) -> None:
        """SafetyInfo exposes the safety partition configuration."""
        info = controller.safety_info
        assert info.safety_locked is False
        assert info.signature_run_mode_protect is False
        assert info.configure_safety_io_always is False
        assert info.safety_level == "SIL3/PLe"

    def test_safety_tag_map(self, controller: ControllerInfo) -> None:
        """safety_tag_map returns the mapping text."""
        assert (
            controller.safety_info.safety_tag_map == "toSafety_reset=fromNormal_reset"
        )

    def test_safety_info_repr(self, controller: ControllerInfo) -> None:
        """SafetyInfo repr includes the safety level."""
        assert "SIL3/PLe" in repr(controller.safety_info)

    def test_no_safety_info_returns_none(self) -> None:
        """Controllers without a SafetyInfo child are not safety controllers."""
        el = ET.Element("Controller", Name="Test", Use="Target")
        ctrl = ControllerInfo(el)
        assert ctrl.safety_info is None
        assert ctrl.is_safety_controller is False


# ---------------------------------------------------------------------------
# Time synchronization / clock
# ---------------------------------------------------------------------------


class TestControllerTimeSync:
    """Tests for TimeSynchronize / CST / WallClockTime."""

    def test_time_synchronize_type(self, controller: ControllerInfo) -> None:
        """time_synchronize returns a TimeSynchronize instance."""
        assert isinstance(controller.time_synchronize, TimeSynchronize)

    def test_time_synchronize_fields(self, controller: ControllerInfo) -> None:
        """TimeSynchronize exposes priority and PTP enable state."""
        ts = controller.time_synchronize
        assert ts.priority1 == 128
        assert ts.priority2 == 128
        assert ts.ptp_enable is True

    def test_time_synchronize_repr(self, controller: ControllerInfo) -> None:
        """TimeSynchronize repr includes the PTP enable state."""
        assert "PTPEnable=True" in repr(controller.time_synchronize)

    def test_cst_master_id(self, controller: ControllerInfo) -> None:
        """cst_master_id matches the <CST MasterID="..."/> attribute."""
        assert controller.cst_master_id == "0"

    def test_wall_clock_time(self, controller: ControllerInfo) -> None:
        """wall_clock_time returns the WallClockTime attribute dict."""
        assert controller.wall_clock_time == {
            "LocalTimeAdjustment": "0",
            "TimeZone": "0",
        }

    def test_missing_time_synchronize_returns_none(self) -> None:
        """Controllers without a TimeSynchronize child return None."""
        el = ET.Element("Controller", Name="Test", Use="Target")
        ctrl = ControllerInfo(el)
        assert ctrl.time_synchronize is None
        assert ctrl.cst_master_id is None
        assert ctrl.wall_clock_time is None


# ---------------------------------------------------------------------------
# Ethernet ports
# ---------------------------------------------------------------------------


class TestControllerEthernetPorts:
    """Tests for the ethernet_ports mapping."""

    def test_ports_mapping_length(self, controller: ControllerInfo) -> None:
        """Two Ethernet ports are exported for the example controller."""
        assert len(controller.ethernet_ports) == 2

    def test_port_1(self, controller: ControllerInfo) -> None:
        """Port 1 (A1) is enabled."""
        port = controller.ethernet_ports[1]
        assert isinstance(port, EthernetPort)
        assert port.port == 1
        assert port.label == "A1"
        assert port.port_enabled is True

    def test_port_2(self, controller: ControllerInfo) -> None:
        """Port 2 (A2) is enabled."""
        port = controller.ethernet_ports[2]
        assert port.label == "A2"
        assert port.port_enabled is True

    def test_missing_port_raises_keyerror(self, controller: ControllerInfo) -> None:
        """Accessing a non-existent port raises KeyError."""
        with pytest.raises(KeyError):
            _ = controller.ethernet_ports[99]

    def test_port_repr(self, controller: ControllerInfo) -> None:
        """EthernetPort repr includes the label and enabled state."""
        assert repr(controller.ethernet_ports[1]) == "EthernetPort('A1', enabled=True)"

    def test_no_ethernet_ports_element(self) -> None:
        """Controllers without an EthernetPorts child expose an empty mapping."""
        el = ET.Element("Controller", Name="Test", Use="Target")
        ctrl = ControllerInfo(el)
        assert len(ctrl.ethernet_ports) == 0


# ---------------------------------------------------------------------------
# OPC UA
# ---------------------------------------------------------------------------


class TestControllerOpcUa:
    """Tests for opc_ua_enabled / opc_ua_enabled_ports."""

    def test_opc_ua_enabled(self, controller: ControllerInfo) -> None:
        """The example controller has OPC UA enabled."""
        assert controller.opc_ua_enabled is True

    def test_opc_ua_enabled_ports(self, controller: ControllerInfo) -> None:
        """opc_ua_enabled_ports returns the EnabledPorts bitmask as an int."""
        assert controller.opc_ua_enabled_ports == 2

    def test_opc_ua_disabled_when_no_element(self) -> None:
        """Controllers without an OpcUaInfo child report OPC UA as disabled."""
        el = ET.Element("Controller", Name="Test", Use="Target")
        ctrl = ControllerInfo(el)
        assert ctrl.opc_ua_enabled is False
        assert ctrl.opc_ua_enabled_ports is None

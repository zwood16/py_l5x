"""Tests for py_l5x.parsers.controller."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from py_l5x.parsers.controller import ControllerInfo

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
        assert controller.processor_type == "5069-L306ERM"


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
        """Project creation date matches ProjectCreationDate attribute."""
        assert controller.project_creation_date == "Tue Jun 30 10:14:37 2026"

    def test_last_modified_date(self, controller: ControllerInfo) -> None:
        """Last modified date matches LastModifiedDate attribute."""
        assert controller.last_modified_date == "Tue Jun 30 11:15:40 2026"

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
        assert attrs["ProcessorType"] == "5069-L306ERM"

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
        assert "5069-L306ERM" in repr(controller)

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
        """Controller with only required attributes returns empty strings for missing."""
        el = ET.Element("Controller", Name="Minimal", Use="Target")
        ctrl = ControllerInfo(el)
        assert ctrl.name == "Minimal"
        assert ctrl.use == "Target"
        assert ctrl.processor_type == ""
        assert ctrl.major_rev == ""
        assert ctrl.minor_rev == ""

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

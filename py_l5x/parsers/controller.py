"""Top-level controller data.

This module provides ``ControllerInfo``, a wrapper around the ``<Controller>``
element in L5X files.  It exposes every known XML attribute as a typed property
and collects any unrecognised attributes in ``extra_attributes`` so they can be
cross-referenced against the Rockwell L5X export manual.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from py_l5x.parsers.base import BaseElement

# XML attribute names that are exposed as explicit properties.
# Everything else ends up in ``extra_attributes``.
_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {
        "Use",
        "Name",
        "ProcessorType",
        "MajorRev",
        "MinorRev",
        "ProjectCreationDate",
        "LastModifiedDate",
        "ProjectSN",
    }
)


class ControllerInfo(BaseElement):
    """Top-level controller metadata from a ``<Controller>`` element.

    Wraps a ``<Controller>`` XML element and exposes its attributes as
    readable properties.  Any attributes not explicitly handled are
    available via :attr:`extra_attributes`.

    Args:
        element: The ``<Controller>`` element from a parsed L5X tree.
            Typically obtained via ``root.find("Controller")``.

    Example:
        >>> from xml.etree import ElementTree as ET
        >>> root = ET.parse("project.L5X").getroot()
        >>> ctrl = ControllerInfo(root.find("Controller"))
        >>> print(ctrl.name)
        MyController
    """

    def __init__(self, element: ET.Element) -> None:
        """Initialise from a ``<Controller>`` XML element.

        Args:
            element: The ``<Controller>`` element from a parsed L5X tree.
                Pass ``root.find("Controller")`` when constructing directly.
        """
        super().__init__(element)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Controller name.

        Returns:
            The value of the ``Name`` XML attribute.
        """
        return self._get("Name")

    @property
    def use(self) -> str:
        """Export target role.

        Common values include ``"Target"`` and ``"Source"``.

        Returns:
            The value of the ``Use`` XML attribute.
        """
        return self._get("Use")

    @property
    def processor_type(self) -> str:
        """Processor catalog number.

        Returns:
            The catalog number string (e.g. ``"5069-L306ERM"``).
        """
        return self._get("ProcessorType")

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------

    @property
    def major_rev(self) -> str:
        """Major firmware revision.

        Returns:
            The value of the ``MajorRev`` XML attribute.
        """
        return self._get("MajorRev")

    @property
    def minor_rev(self) -> str:
        """Minor firmware revision.

        Returns:
            The value of the ``MinorRev`` XML attribute.
        """
        return self._get("MinorRev")

    # ------------------------------------------------------------------
    # Dates / identifiers
    # ------------------------------------------------------------------

    @property
    def project_creation_date(self) -> str:
        """Date string when the project was first created.

        Returns:
            The value of the ``ProjectCreationDate`` XML attribute.
        """
        return self._get("ProjectCreationDate")

    @property
    def last_modified_date(self) -> str:
        """Date string when the project was last saved.

        Returns:
            The value of the ``LastModifiedDate`` XML attribute.
        """
        return self._get("LastModifiedDate")

    @property
    def project_sn(self) -> str:
        """Project serial number.

        Returns:
            The value of the ``ProjectSN`` XML attribute.
        """
        return self._get("ProjectSN")

    # ------------------------------------------------------------------
    # Unrecognised attributes
    # ------------------------------------------------------------------

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Keys are the original XML attribute names (e.g.
        ``"SFCExecutionControl"``) so they can be cross-referenced directly
        against the Rockwell L5X export manual.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v for k, v in self._element.attrib.items() if k not in _KNOWN_XML_KEYS
        }

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a multi-line string representation of the controller.

        Includes the controller name, processor type, firmware version,
        creation and modification dates, and any extra attributes.

        Returns:
            A formatted string suitable for display in debug output.
        """
        lines = [
            f"Controller Name:  {self.name}",
            f"Processor Type:   {self.processor_type}",
            f"Firmware:         {self.major_rev}.{self.minor_rev}",
            f"Created:          {self.project_creation_date}",
            f"Last Modified:    {self.last_modified_date}",
        ]
        extras = self.extra_attributes
        if extras:
            lines.append("Extra Attributes:")
            for k, v in sorted(extras.items()):
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

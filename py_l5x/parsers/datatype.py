"""User-defined data type (UDT) data.

This module provides ``DataType`` and ``DataTypeMember``, wrappers around the
``<DataType>`` and ``<Member>`` elements found in the ``<DataTypes>`` section
of an L5X file, plus ``DataTypesCollection`` for accessing every ``<DataType>``
by name.

Logix Designer stores each packed boolean as a separate ``<Member>`` with
``DataType="BIT"`` that references a hidden ``SINT`` "host" member via the
``Target``/``BitNumber`` attributes. ``DataType.visible_members`` and
``DataType.bit_groups`` are provided to make that pattern easy to work with
without needing to filter or group members by hand.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from py_l5x.parsers.base import BaseCollection, BaseElement
from py_l5x.parsers.utils import convert_numeric

# XML attribute names on <Member> exposed as explicit properties.
_MEMBER_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {
        "Name",
        "DataType",
        "Dimension",
        "Radix",
        "Hidden",
        "ExternalAccess",
        "Target",
        "BitNumber",
        "Max",
        "Min",
        "ExternalLogging",
    }
)

# XML attribute names on <DataType> exposed as explicit properties.
_DATATYPE_KNOWN_XML_KEYS: frozenset[str] = frozenset({"Name", "Family", "Class"})


class DataTypeMember(BaseElement):
    """A single ``<Member>`` element within a ``<DataType>``'s ``<Members>``.

    Args:
        element: The ``<Member>`` element from a parsed L5X tree.
    """

    def __init__(self, element: ET.Element) -> None:
        """Initialise from a ``<Member>`` XML element.

        Args:
            element: The ``<Member>`` element to wrap.
        """
        super().__init__(element)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Member name.

        Returns:
            The value of the ``Name`` XML attribute.
        """
        return self._get("Name")

    @property
    def data_type(self) -> str:
        """Data type of this member.

        This is ``"BIT"`` for packed booleans, an atomic type name (e.g.
        ``"SINT"``, ``"REAL"``), or the name of another UDT or Add-On
        Instruction definition.

        Returns:
            The value of the ``DataType`` XML attribute.
        """
        return self._get("DataType")

    @property
    def radix(self) -> str:
        """Display radix (e.g. ``"Decimal"``, ``"Binary"``, ``"Float"``).

        Returns:
            The value of the ``Radix`` XML attribute.
        """
        return self._get("Radix")

    # ------------------------------------------------------------------
    # Bit packing
    # ------------------------------------------------------------------

    @property
    def hidden(self) -> bool:
        """Whether this member is a hidden host byte for packed booleans.

        Returns:
            ``True`` if the ``Hidden`` XML attribute is ``"true"``.
        """
        return self._get("Hidden") == "true"

    @property
    def target(self) -> str:
        """Name of the hidden host member this bit is packed into.

        Only meaningful when :attr:`is_bit_member` is ``True``.

        Returns:
            The value of the ``Target`` XML attribute, or an empty string
            for non-bit members.
        """
        return self._get("Target")

    @property
    def bit_number(self) -> int | None:
        """Bit position within the host member.

        Only meaningful when :attr:`is_bit_member` is ``True``.

        Returns:
            The ``BitNumber`` XML attribute as an ``int``, or ``None`` if
            the attribute is absent.
        """
        value = self._get("BitNumber", "")
        return int(value) if value else None

    @property
    def is_bit_member(self) -> bool:
        """Whether this member is a packed boolean bit.

        Returns:
            ``True`` if :attr:`data_type` is ``"BIT"``.
        """
        return self.data_type == "BIT"

    # ------------------------------------------------------------------
    # Shape / limits
    # ------------------------------------------------------------------

    @property
    def dimension(self) -> int:
        """Array dimension.

        Returns:
            ``0`` for an atomic (non-array) member, otherwise the array
            length.
        """
        return int(self._get("Dimension", "0"))

    @property
    def is_array(self) -> bool:
        """Whether this member is an array.

        Returns:
            ``True`` if :attr:`dimension` is non-zero.
        """
        return self.dimension != 0

    @property
    def min(self) -> int | float | str | None:
        """User-specified minimum value, if any.

        Returns:
            The ``Min`` XML attribute converted to ``int``/``float``
            based on :attr:`data_type`, or ``None`` if the attribute is
            absent.
        """
        value = self._element.get("Min")
        return None if value is None else convert_numeric(value, self.data_type)

    @property
    def max(self) -> int | float | str | None:
        """User-specified maximum value, if any.

        Returns:
            The ``Max`` XML attribute converted to ``int``/``float``
            based on :attr:`data_type`, or ``None`` if the attribute is
            absent.
        """
        value = self._element.get("Max")
        return None if value is None else convert_numeric(value, self.data_type)

    # ------------------------------------------------------------------
    # Access / logging
    # ------------------------------------------------------------------

    @property
    def external_access(self) -> str:
        """External access level (e.g. ``"Read/Write"``, ``"Read Only"``).

        Returns:
            The value of the ``ExternalAccess`` XML attribute.
        """
        return self._get("ExternalAccess")

    @property
    def external_logging(self) -> bool | None:
        """Whether external logging is enabled for this member.

        Returns:
            ``True``/``False`` if the ``ExternalLogging`` XML attribute is
            present, otherwise ``None``.
        """
        value = self._element.get("ExternalLogging")
        return None if value is None else value == "true"

    # ------------------------------------------------------------------
    # Documentation
    # ------------------------------------------------------------------

    @property
    def description(self) -> str:
        """Member description text.

        Returns:
            The ``Description`` CDATA text, or an empty string if absent.
        """
        return self._get_description()

    @property
    def engineering_unit(self) -> str:
        """User-specified engineering unit (e.g. ``"mm"``).

        Returns:
            The ``EngineeringUnit`` CDATA text, or an empty string if absent.
        """
        return self._get_cdata_child("EngineeringUnit")

    @property
    def state0(self) -> str:
        """Description of the boolean member's zero state.

        Returns:
            The ``State0`` CDATA text, or an empty string if absent.
        """
        return self._get_cdata_child("State0")

    @property
    def state1(self) -> str:
        """Description of the boolean member's one state.

        Returns:
            The ``State1`` CDATA text, or an empty string if absent.
        """
        return self._get_cdata_child("State1")

    # ------------------------------------------------------------------
    # Unrecognised attributes
    # ------------------------------------------------------------------

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _MEMBER_KNOWN_XML_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on the ``<Member>`` element.

        Returns:
            Dictionary mapping every XML attribute name to its string value.
        """
        return dict(self._element.attrib)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a multi-line string representation of the member.

        Includes the member name, data type, dimension, radix, bit-packing
        details, min/max bounds, and any extra attributes.

        Returns:
            A formatted string suitable for display in debug output.
        """
        lines = [
            f"Member Name:      {self.name}",
            f"Data Type:        {self.data_type}",
        ]
        if self.is_array:
            lines.append(f"Dimension:        {self.dimension}")
        if self.radix:
            lines.append(f"Radix:            {self.radix}")
        if self.is_bit_member:
            lines.append(f"Bit Number:       {self.bit_number}")
            lines.append(f"Target:           {self.target}")
        if self.min is not None:
            lines.append(f"Min:              {self.min}")
        if self.max is not None:
            lines.append(f"Max:              {self.max}")
        if self.hidden:
            lines.append(f"Hidden:           {self.hidden}")
        extras = self.extra_attributes
        if extras:
            lines.append("Extra Attributes:")
            for k, v in sorted(extras.items()):
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)


class DataType(BaseElement):
    """A single ``<DataType>`` element from the ``<DataTypes>`` section.

    Args:
        element: The ``<DataType>`` element from a parsed L5X tree.
    """

    def __init__(self, element: ET.Element) -> None:
        """Initialise from a ``<DataType>`` XML element.

        Args:
            element: The ``<DataType>`` element to wrap.
        """
        super().__init__(element)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Data type name.

        Returns:
            The value of the ``Name`` XML attribute.
        """
        return self._get("Name")

    @property
    def family(self) -> str:
        """Data type family.

        ``"StringFamily"`` for STRING-like types, ``"NoFamily"`` otherwise.

        Returns:
            The value of the ``Family`` XML attribute.
        """
        return self._get("Family")

    @property
    def class_(self) -> str:
        """Data type class (always ``"User"`` for user-defined types).

        Returns:
            The value of the ``Class`` XML attribute.
        """
        return self._get("Class")

    @property
    def is_string(self) -> bool:
        """Whether this is a STRING-family data type.

        Returns:
            ``True`` if :attr:`family` is ``"StringFamily"``.
        """
        return self.family == "StringFamily"

    @property
    def max_length(self) -> int | None:
        """Maximum character length, for STRING-family data types.

        Returns:
            The ``Dimension`` of the ``DATA`` member when :attr:`is_string`
            is ``True``, otherwise ``None``.
        """
        if not self.is_string:
            return None
        data_member = self.members.get("DATA")
        return data_member.dimension if data_member is not None else None

    # ------------------------------------------------------------------
    # Documentation
    # ------------------------------------------------------------------

    @property
    def description(self) -> str:
        """Data type description text.

        Returns:
            The ``Description`` CDATA text, or an empty string if absent.
        """
        return self._get_description()

    @property
    def engineering_unit(self) -> str:
        """User-specified engineering unit for the data type.

        Returns:
            The ``EngineeringUnit`` CDATA text, or an empty string if absent.
        """
        return self._get_cdata_child("EngineeringUnit")

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    @property
    def members(self) -> BaseCollection:
        """All members of this data type, keyed by name.

        Includes hidden host bytes used for packed booleans. See
        :attr:`visible_members` to exclude them.

        Returns:
            A ``BaseCollection`` mapping member names to ``DataTypeMember``.
        """
        return BaseCollection(self._element, "Members/Member", DataTypeMember)

    @property
    def visible_members(self) -> dict[str, DataTypeMember]:
        """Members excluding hidden packed-boolean host bytes.

        Returns:
            Dictionary mapping member names to ``DataTypeMember``,
            excluding any member with :attr:`DataTypeMember.hidden` set.
        """
        return {name: m for name, m in self.members.items() if not m.hidden}

    @property
    def bit_groups(self) -> dict[str, list[DataTypeMember]]:
        """Packed boolean bit members, grouped by their hidden host member.

        Returns:
            Dictionary mapping a hidden host member's name to the list of
            ``DataTypeMember`` bit members packed into it, in document order.
        """
        groups: dict[str, list[DataTypeMember]] = {}
        for member in self.members.values():
            if member.is_bit_member and member.target:
                groups.setdefault(member.target, []).append(member)
        return groups

    # ------------------------------------------------------------------
    # Unrecognised attributes
    # ------------------------------------------------------------------

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _DATATYPE_KNOWN_XML_KEYS
        }

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on the ``<DataType>`` element.

        Returns:
            Dictionary mapping every XML attribute name to its string value.
        """
        return dict(self._element.attrib)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a multi-line string representation of the data type.

        Includes the data type name, family, class, member count, and any
        extra attributes.

        Returns:
            A formatted string suitable for display in debug output.
        """
        member_names = "\n"
        for member in self.members.values():
            if not member.hidden:
                member_names += f"   {member.name} ({member.data_type}) \n"
        lines = [
            f"Data Type Name:   {self.name}",
            f"Family:           {self.family}",
            f"Class:            {self.class_}",
            f"Members:          {member_names if member_names else 'None'}",
        ]
        if self.is_string:
            lines.append(f"Max Length:       {self.max_length}")
        extras = self.extra_attributes
        if extras:
            lines.append("Extra Attributes:")
            for k, v in sorted(extras.items()):
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)


class DataTypesCollection(BaseCollection):
    """A ``Mapping`` over every ``<DataType>`` in the ``<DataTypes>`` section.

    Args:
        controller_element: The ``<Controller>`` element from a parsed L5X
            tree. Typically obtained via ``root.find("Controller")``.

    Example:
        >>> from xml.etree import ElementTree as ET
        >>> root = ET.parse("project.L5X").getroot()
        >>> data_types = DataTypesCollection(root.find("Controller"))
        >>> print(data_types["A_UDT"].members["a_sint"].data_type)
        SINT
    """

    def __init__(self, controller_element: ET.Element) -> None:
        """Initialise from a ``<Controller>`` XML element.

        Args:
            controller_element: The ``<Controller>`` element whose
                ``DataTypes/DataType`` children form this collection.
        """
        super().__init__(controller_element, "DataTypes/DataType", DataType)

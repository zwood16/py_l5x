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

from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    bool_attr,
    int_attr,
    str_attr,
)
from py_l5x.parsers.utils import CDATA_TAG, convert_numeric

# ------------------------------------------------------------------
# DataTypes (UDTs)
# ------------------------------------------------------------------


class DataTypeMember(BaseElement):
    """A single ``<Member>`` element within a ``<DataType>``'s ``<Members>``.

    Args:
        element: The ``<Member>`` element from a parsed L5X tree.
    """

    #: Attributes backed by plain @property (not an XmlField descriptor)
    #: because their conversion depends on data_type at read time -- still
    #: "known" and excluded from extra_attributes.
    _DYNAMIC_KEYS: frozenset[str] = frozenset({"Min", "Max"})

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    name = str_attr("Name", doc="Member name.")
    data_type = str_attr(
        "DataType",
        doc='Data type of this member. "BIT" for packed booleans, an atomic '
        'type name (e.g. "SINT", "REAL"), or the name of another UDT/AOI.',
    )
    radix = str_attr("Radix", doc='Display radix (e.g. "Decimal", "Binary", "Float").')

    # ------------------------------------------------------------------
    # Bit packing
    # ------------------------------------------------------------------

    hidden = bool_attr(
        "Hidden",
        default=False,
        doc="Whether this member is a hidden host byte for packed booleans.",
    )
    target = str_attr(
        "Target",
        doc="Name of the hidden host member this bit is packed into. Only "
        "meaningful when is_bit_member is True.",
    )

    bit_number = int_attr(
        "BitNumber",
        doc="Bit position within the host member. Only meaningful when "
        ":attr:`is_bit_member` is ``True``.",
    )

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

    dimension = int_attr(
        "Dimension",
        default=0,
        doc="Array dimension. 0 for an atomic (non-array) member, otherwise "
        "the array length.",
    )

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

    external_access = str_attr(
        "ExternalAccess",
        doc='External access level (e.g. "Read/Write", "Read Only").',
    )
    external_logging = bool_attr(
        "ExternalLogging",
        doc="Whether external logging is enabled for this member.",
    )

    # ------------------------------------------------------------------
    # Documentation
    # ------------------------------------------------------------------

    description = CDataField("Description", doc="Member description text.")
    engineering_unit = CDataField(
        "EngineeringUnit", doc='User-specified engineering unit (e.g. "mm").'
    )
    state0 = CDataField("State0", doc="Description of the boolean member's zero state.")
    state1 = CDataField("State1", doc="Description of the boolean member's one state.")

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by declared fields or dynamic properties.

        See :attr:`_DYNAMIC_KEYS` for the ``Min``/``Max`` properties whose
        conversion depends on :attr:`data_type` and so aren't plain
        :class:`~py_l5x.parsers.base.XmlField` descriptors.
        """
        extras = super().extra_attributes
        return {k: v for k, v in extras.items() if k not in self._DYNAMIC_KEYS}

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

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    name = str_attr("Name", doc="Data type name.")
    family = str_attr(
        "Family",
        doc='Data type family. "StringFamily" for STRING-like types, '
        '"NoFamily" otherwise.',
    )
    class_ = str_attr(
        "Class", doc='Data type class (always "User" for user-defined types).'
    )

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

    description = CDataField("Description", doc="Data type description text.")
    engineering_unit = CDataField(
        "EngineeringUnit",
        doc="User-specified engineering unit for the data type.",
    )

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


class DataTypesCollection(BaseCollection[DataType]):
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


# ------------------------------------------------------------------
# Add On Instruction DataTypes
# ------------------------------------------------------------------

# Similar to data types, but derrived from non-InOut parameters
# Note: actual AOI definitions include all params, not just those that
# appear in the tag browser


class AddOnParameter(BaseElement):
    """A single ``<Parameter>`` element within an ``<AddOnInstructionDefinition>``.

    Args:
        element: The ``<Parameter>`` element from a parsed L5X tree.
    """

    #: Attributes backed by plain @property (not an XmlField descriptor)
    #: because their conversion depends on data_type at read time -- still
    #: "known" and excluded from extra_attributes.
    _DYNAMIC_KEYS: frozenset[str] = frozenset({"Min", "Max"})

    name = str_attr("Name", doc="Parameter name.")
    data_type = str_attr("DataType", doc="Data type of this parameter.")
    usage = str_attr(
        "Usage", doc='Usage of the parameter (e.g., "Input", "Output", "InOut").'
    )
    radix = str_attr("Radix", doc="Display radix.")
    required = bool_attr(
        "Required", default=False, doc="Whether the parameter is required."
    )
    visible = bool_attr(
        "Visible",
        default=False,
        doc="Whether the parameter is visible in Logix Designer.",
    )
    external_access = str_attr(
        "ExternalAccess",
        doc='External access level (e.g. "Read/Write", "Read Only").',
    )
    external_logging = bool_attr(
        "ExternalLogging",
        doc="Whether external logging is enabled for this parameter.",
    )
    description = CDataField("Description", doc="Parameter description text.")

    @property
    def is_inout(self) -> bool:
        """Whether this parameter uses InOut usage."""
        return self.usage == "InOut"

    # ------------------------------------------------------------------
    # Shape / limits
    # ------------------------------------------------------------------

    @property
    def min(self) -> int | float | str | None:
        """User-specified minimum value, if any.

        Returns:
            The ``Min`` XML attribute converted to ``int``/``float`` based
            on :attr:`data_type`, or ``None`` if the attribute is absent.
        """
        value = self._element.get("Min")
        return None if value is None else convert_numeric(value, self.data_type)

    @property
    def max(self) -> int | float | str | None:
        """User-specified maximum value, if any.

        Returns:
            The ``Max`` XML attribute converted to ``int``/``float`` based
            on :attr:`data_type`, or ``None`` if the attribute is absent.
        """
        value = self._element.get("Max")
        return None if value is None else convert_numeric(value, self.data_type)

    # ------------------------------------------------------------------
    # Documentation
    # ------------------------------------------------------------------

    def _get_nested_cdata(self, container_tag: str, child_tag: str) -> str:
        """Return CDATA text from a doubly-nested container/child element pair.

        Unlike ``<Member>`` (used by UDTs), ``<Parameter>`` wraps its
        ``EngineeringUnit``/``State0``/``State1`` children inside a plural
        container element with no ``Operand`` attribute, e.g.::

            <EngineeringUnits><EngineeringUnit><![CDATA[ms]]></EngineeringUnit></EngineeringUnits>

        Args:
            container_tag: The plural wrapper element name (e.g. ``"State0s"``).
            child_tag: The child element name to read CDATA text from (e.g.
                ``"State0"``).

        Returns:
            The text content, stripped of surrounding whitespace, or an empty
            string if the element or its text is absent.
        """
        child = self._element.find(f"{container_tag}/{child_tag}")
        if child is not None:
            cdata_el = child.find(CDATA_TAG)
            if cdata_el is not None and cdata_el.text:
                return cdata_el.text.strip()
            if child.text:
                return child.text.strip()
        return ""

    @property
    def engineering_unit(self) -> str:
        """User-specified engineering unit (e.g. ``"ms"``).

        Returns:
            The ``EngineeringUnits/EngineeringUnit`` CDATA text, or an empty
            string if absent.
        """
        return self._get_nested_cdata("EngineeringUnits", "EngineeringUnit")

    @property
    def state0(self) -> str:
        """Description of the boolean parameter's zero state.

        Returns:
            The ``State0s/State0`` CDATA text, or an empty string if absent.
        """
        return self._get_nested_cdata("State0s", "State0")

    @property
    def state1(self) -> str:
        """Description of the boolean parameter's one state.

        Returns:
            The ``State1s/State1`` CDATA text, or an empty string if absent.
        """
        return self._get_nested_cdata("State1s", "State1")

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by declared fields or dynamic properties.

        See :attr:`_DYNAMIC_KEYS` for the ``Min``/``Max`` properties whose
        conversion depends on :attr:`data_type` and so aren't plain
        :class:`~py_l5x.parsers.base.XmlField` descriptors.
        """
        extras = super().extra_attributes
        return {k: v for k, v in extras.items() if k not in self._DYNAMIC_KEYS}

    def _header(self) -> str:
        """Return the single-line identity header for :meth:`describe`.

        Mirrors :meth:`~py_l5x.parsers.tag.Tag._header` by including the data
        type, so a parameter stays identifiable even among other parameters
        that share a name. This is what both :meth:`__repr__` (via
        :meth:`describe`) and :meth:`describe` use for their first line.
        """
        return f"{type(self).__name__}({self.name!r}, {self.data_type!r})"

    def __repr__(self) -> str:
        """Return the full :meth:`describe` text for this parameter.

        Returns:
            The multi-line description produced by :meth:`describe`.
        """
        return self.describe()

    def describe(self) -> str:
        """Extend :meth:`BaseElement.describe` with metadata properties.

        Includes identity/field info from super(), then appends the metadata
        properties (:attr:`min`, :attr:`max`, :attr:`engineering_unit`,
        :attr:`state0`, :attr:`state1`) -- which are plain ``@property``s rather
        than declared :class:`~py_l5x.parsers.base.XmlField` fields and so don't
        appear in super()'s output -- when they are set.

        Returns:
            A formatted multi-line string suitable for interactive/debug use.
        """
        lines = [super().describe()]
        for name in ("min", "max", "engineering_unit", "state0", "state1"):
            val = getattr(self, name)
            if val is not None and val != "":
                lines.append(f"  {name}: {val!r}")
        return "\n".join(lines)


class AddOnParameters(BaseCollection[AddOnParameter]):
    """A collection of parameters for a specific AOI definition.

    Args:
        aoi_element: The ``<AddOnInstructionDefinition>`` element.
    """

    def __init__(self, aoi_element: ET.Element) -> None:
        super().__init__(aoi_element, "Parameters/Parameter", AddOnParameter)

    @property
    def datatype_members(self) -> dict[str, AddOnParameter]:
        """Input and Output parameters of the AOI, excluding InOut usage.

        These are the tags that appear as the tags members of the AOI instance
        in the Logix Tag Browser - excludes InOut parameters.

        Returns:
            Dictionary mapping parameter names to ``AddOnParameter``.
        """
        return {name: p for name, p in self.items() if not p.is_inout}


class AddOnDataTypeCollection(BaseCollection[AddOnParameters]):
    """A ``Mapping`` over every ``<AddOnInstructionDefinition>``'s parameters.

    Args:
        root_element: The root element of the parsed L5X tree, or an element
            containing the ``<AddOnInstructionDefinitions>`` section.
    """

    def __init__(self, controller_element: ET.Element) -> None:
        """Initialise from a root XML element.

        Args:
            controller_element: The ``<Controller>`` element whose
                ``AddOnInstructionDefinitions/AddOnInstructionDefinition`` children form
                this collection.
        """
        super().__init__(
            controller_element,
            "AddOnInstructionDefinitions/AddOnInstructionDefinition",
            AddOnParameters,
        )

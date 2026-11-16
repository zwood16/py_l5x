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

from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.parsers.atomic_types import ATOMIC_TYPES, default_radix
from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    bool_attr,
    int_attr,
    str_attr,
)
from py_l5x.parsers.names import validate_new_name
from py_l5x.parsers.schema import insert_child, insert_child_at, remove_child
from py_l5x.parsers.utils import cdata_text, convert_numeric

if TYPE_CHECKING:
    from py_l5x.build.specs import DataTypeSpec
    from py_l5x.parsers.tag import TypeRegistry

# ------------------------------------------------------------------
# DataTypes (UDTs)
# ------------------------------------------------------------------


class DataTypeMember(BaseElement):
    """A single ``<Member>`` element within a ``<DataType>``'s ``<Members>``.

    Args:
        element: The ``<Member>`` element from a parsed L5X tree.
    """

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

    #: Attributes backed by plain @property (not an XmlField descriptor)
    #: because their conversion depends on data_type at read time -- still
    #: "known" and excluded from extra_attributes.
    _DYNAMIC_KEYS: frozenset[str] = frozenset({"Min", "Max"})

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by declared fields or dynamic properties.

        See :attr:`_DYNAMIC_KEYS` for the ``Min``/``Max`` properties whose
        conversion depends on :attr:`data_type` and so aren't plain
        :class:`~py_l5x.parsers.base.XmlField` descriptors.
        """
        extras = super().extra_attributes
        return {k: v for k, v in extras.items() if k not in self._DYNAMIC_KEYS}

    @property
    def min(self) -> int | float | str | None:
        """User-specified minimum value, if any.

        Returns:
            The ``Min`` XML attribute converted to ``int``/``float`` based on
            :attr:`data_type`, or ``None`` if the attribute is absent.
        """
        value = self._element.get("Min")
        return None if value is None else convert_numeric(value, self.data_type)

    @property
    def max(self) -> int | float | str | None:
        """User-specified maximum value, if any.

        Returns:
            The ``Max`` XML attribute converted to ``int``/``float`` based on
            :attr:`data_type`, or ``None`` if the attribute is absent.
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

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _header(self) -> str:
        """Return the single-line identity header for :meth:`describe`.

        Includes the data type, matching
        :meth:`~py_l5x.parsers.aoi.AOIParameter._header`, so a
        member stays identifiable among same-named members of other types.
        """
        return f"{type(self).__name__}({self.name!r}, {self.data_type!r})"

    def __repr__(self) -> str:
        """Return the full :meth:`describe` text for this member.

        Returns:
            The multi-line description produced by :meth:`describe`.
        """
        return self.describe()

    def _describe_lines(self) -> list[str]:
        """Return min/max bound lines.

        :attr:`min` and :attr:`max` are plain ``@property``s rather than
        declared fields, so they're emitted here when set.

        Returns:
            Formatted description lines, each indented two spaces.
        """
        lines: list[str] = []
        for name in ("min", "max"):
            val = getattr(self, name)
            if val is not None:
                lines.append(f"  {name}: {val!r}")
        return lines


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

    def to_spec(self) -> DataTypeSpec:
        """Convert this data type to a spec that rebuilds it.

        Hidden members (the ``SINT`` hosts of packed booleans) are dropped and
        ``BIT`` members become plain ``BOOL``. Descriptions, engineering units,
        state text, min/max and external logging are kept, read as raw CDATA
        text. A radix equal to the type's default (``Decimal`` for integers and
        BOOL, ``Float`` for REAL, ``NullType`` for structured types, ...) is
        stored as ``None``; any other radix is kept. Building the spec gives
        back the same members either way, but ``None`` keeps specs minimal.

        Returns:
            A :class:`~py_l5x.build.specs.DataTypeSpec`.
        """
        from py_l5x.build.specs import DataTypeSpec, MemberSpec

        def text(element: ET.Element, tag: str) -> str:
            return cdata_text(element.find(tag), strip=False)

        members = []
        for member in self.members.values():
            if member.hidden:
                continue
            element = member._element
            data_type = "BOOL" if member.data_type == "BIT" else member.data_type
            default = (
                default_radix(data_type) if data_type in ATOMIC_TYPES else "NullType"
            )
            logging = element.get("ExternalLogging")
            members.append(
                MemberSpec(
                    name=member.name,
                    data_type=data_type,
                    dimension=member.dimension,
                    description=text(element, "Description"),
                    radix=None if member.radix == default else member.radix,
                    external_access=member.external_access,
                    engineering_unit=text(element, "EngineeringUnit"),
                    min=element.get("Min"),
                    max=element.get("Max"),
                    state0=text(element, "State0"),
                    state1=text(element, "State1"),
                    external_logging=None if logging is None else logging == "true",
                )
            )
        return DataTypeSpec(
            self.name, members, text(self._element, "Description"), self.family
        )

    def __repr__(self) -> str:
        """Return the full :meth:`describe` text for this data type.

        Returns:
            The multi-line description produced by :meth:`describe`.
        """
        return self.describe()

    def _describe_lines(self) -> list[str]:
        """Return the STRING length line and the visible members block.

        Emits :attr:`max_length` for STRING-family types, then a ``members:``
        block listing each visible member (hidden packed-boolean host bytes
        are omitted) as ``name: data_type``.

        Returns:
            Formatted description lines.
        """
        lines: list[str] = []
        if self.is_string:
            lines.append(f"  max_length: {self.max_length!r}")
        members = self.visible_members
        if members:
            lines.append("  members:")
            for member in members.values():
                lines.append(f"    {member.name}: {member.data_type}")
        return lines


def find_type_users(controller: ET.Element, name: str) -> list[str]:
    """List the tags, members, parameters and local tags of a type.

    Args:
        controller: The ``<Controller>`` element.
        name: A UDT or AOI name.

    Returns:
        Descriptions such as ``"controller tag X"``,
        ``"program P tag X"``, ``"data type U member m"``,
        ``"AOI A parameter p"`` and ``"AOI A local tag l"``. The type's own
        definition is not searched.
    """
    found: list[str] = []
    for tag in controller.findall("Tags/Tag"):
        if tag.get("DataType") == name:
            found.append(f"controller tag {tag.get('Name')}")
    for program in controller.findall("Programs/Program"):
        for tag in program.findall("Tags/Tag"):
            if tag.get("DataType") == name:
                found.append(f"program {program.get('Name')} tag {tag.get('Name')}")
    for data_type in controller.findall("DataTypes/DataType"):
        if data_type.get("Name") == name:
            continue
        for member in data_type.findall("Members/Member"):
            if member.get("DataType") == name:
                found.append(
                    f"data type {data_type.get('Name')} member {member.get('Name')}"
                )
    for aoi in controller.findall(
        "AddOnInstructionDefinitions/AddOnInstructionDefinition"
    ):
        if aoi.get("Name") == name:
            continue
        for kind, path in (
            ("parameter", "Parameters/Parameter"),
            ("local tag", "LocalTags/LocalTag"),
        ):
            for item in aoi.findall(path):
                if item.get("DataType") == name:
                    found.append(f"AOI {aoi.get('Name')} {kind} {item.get('Name')}")
    return found


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
        #: Set by :class:`~py_l5x.parsers.project.Project`; needed by the edit
        #: methods to resolve types and migrate values.
        self._registry: TypeRegistry | None = None

    # ------------------------------------------------------------------
    # Edits
    # ------------------------------------------------------------------

    def _require_registry(self) -> TypeRegistry:
        """Return the type registry the edit methods need.

        Returns:
            The registry bound by the project.

        Raises:
            RuntimeError: If the collection was created without a project.
        """
        if self._registry is None:
            raise RuntimeError(
                "editing data types needs a project; use project.data_types"
            )
        return self._registry

    def _taken_names(
        self, registry: TypeRegistry, ignore: str | None = None
    ) -> list[str]:
        """List every name a data type may not take.

        Args:
            registry: The project's type registry.
            ignore: A type name to leave out (the type being renamed).

        Returns:
            Project UDT and AOI names (product-defined types exported in the
            file included), the built-in table and the atomic types.
        """
        from py_l5x.parsers.layout import builtin_table

        names = [*registry.type_names(), *builtin_table(), *ATOMIC_TYPES]
        return [n for n in names if n != ignore]

    @staticmethod
    def _check_member_types(spec: DataTypeSpec, registry: TypeRegistry) -> None:
        """Check that every member type resolves.

        Studio silently accepts unknown member types, so they are caught here.

        Args:
            spec: The spec.
            registry: The project's type registry.

        Raises:
            ValueError: If a member type is not atomic, built-in, a project
                UDT or an AOI.
        """
        from py_l5x.parsers.layout import builtin_table

        for member in spec.members:
            kind = member.data_type
            if (
                kind in ATOMIC_TYPES
                or kind in builtin_table()
                or registry.udt(kind) is not None
                or registry.aoi(kind) is not None
            ):
                continue
            raise ValueError(f"member {member.name!r}: unknown data type {kind!r}")

    def _container(self) -> ET.Element:
        """Return ``Controller/DataTypes``, creating it if missing.

        Returns:
            The container element.
        """
        container = self._parent.find("DataTypes")
        if container is None:
            container = ET.Element("DataTypes")
            insert_child(self._parent, container)
        return container

    def _find_element(self, name: str) -> ET.Element:
        """Return the ``<DataType>`` element with exactly this name.

        Args:
            name: The data type name.

        Returns:
            The element.

        Raises:
            KeyError: If there is no such data type.
        """
        for element in self._children():
            if element.get("Name") == name:
                return element
        raise KeyError(name)

    def add(self, spec: DataTypeSpec) -> DataType:
        """Add a user-defined data type built from a spec.

        The element comes from :func:`~py_l5x.build.datatype.build_datatype`
        (with ``<Dependencies>``) and is inserted into ``Controller/DataTypes``
        (created if missing) in case-insensitive name order, as Studio sorts
        them.

        Args:
            spec: The data type.

        Returns:
            The new data type.

        Raises:
            ValueError: If the spec is invalid, the name matches (ignoring
                case) a UDT, an AOI, a built-in or an atomic type, or a member
                type does not resolve.
        """
        from py_l5x.build.datatype import build_datatype

        registry = self._require_registry()
        lowered = spec.name.lower()
        for taken in self._taken_names(registry):
            if taken.lower() == lowered:
                raise ValueError(
                    f"data type name {spec.name!r} is already in use as {taken!r}"
                )
        element = build_datatype(spec, registry)
        self._check_member_types(spec, registry)
        container = self._container()
        position = len(container)
        for index, existing in enumerate(container):
            if existing.get("Name", "").lower() > lowered:
                position = index
                break
        insert_child_at(container, position, element)
        return self[spec.name]

    def replace(self, spec: DataTypeSpec) -> DataType:
        """Replace a user-defined data type and migrate its existing data.

        The element is rebuilt in place, then every instance of the type
        (tag roots, nested in other structures, array elements, AOI parameter
        and local tag defaults, and root strings) is migrated the way Studio
        does on import: values are kept by member name (ignoring case), new
        members get defaults, removed members are dropped, and a member whose
        type changed is converted where that makes sense (see
        :func:`~py_l5x.parsers.migrate.convert_atomic_value`). The stale L5K
        data of every touched tag is removed. Operand metadata (comments and
        so on) that points at removed members is left in place, as Studio
        does. The change is all or nothing: if anything fails the document is
        unchanged. The family (``NoFamily``/``StringFamily``) cannot change.

        Args:
            spec: The new definition; ``spec.name`` selects the type.

        Returns:
            The replaced data type.

        Raises:
            KeyError: If there is no data type of that name.
            ValueError: If the spec is invalid, a member type does not
                resolve, the type is not a user type, or the family changes.
        """
        from py_l5x.build.datatype import build_datatype
        from py_l5x.parsers.migrate import plan_instance_migration

        registry = self._require_registry()
        existing = self._find_element(spec.name)
        if existing.get("Class") != "User":
            raise ValueError(f"{spec.name!r} is not a user-defined data type")
        if existing.get("Family") != spec.family:
            raise ValueError("changing the family of a data type is not supported")
        self._check_member_types(spec, registry)
        fresh = build_datatype(spec, registry)
        container = self._container()
        index = list(container).index(existing)
        fresh.tail = existing.tail
        container[index] = fresh
        try:
            ops = plan_instance_migration(self._parent, registry, spec.name)
        except BaseException:
            container[index] = existing
            raise
        for op in ops:
            op()
        return self[spec.name]

    def rename(self, old: str, new: str) -> DataType:
        """Rename a data type and every reference to it.

        Updates the ``Name``; the ``DataType`` attribute of UDT members, AOI
        parameters and local tags, tags of every scope, and of value trees
        (``Structure``, ``StructureMember``, ``Array``, ``ArrayMember`` and the
        string ``DATA`` member); and ``<Dependency Name>`` entries. Hidden host
        member names are not renamed, matching Studio. The type keeps its
        position in ``<DataTypes>``. Logic text is not touched.

        Args:
            old: The current name.
            new: The new name (same rules as :meth:`add`; the type itself is
                ignored by the collision check, so a case-only change works).

        Returns:
            The renamed data type.

        Raises:
            KeyError: If *old* does not exist.
            ValueError: If *new* is invalid or taken.
        """
        registry = self._require_registry()
        element = self._find_element(old)
        validate_new_name(new, self._taken_names(registry, ignore=old), "data type")
        element.set("Name", new)
        for node in self._parent.iter():
            if node.get("DataType") == old:
                node.set("DataType", new)
            elif (
                node.tag == "Dependency"
                and node.get("Type") == "DataType"
                and node.get("Name") == old
            ):
                node.set("Name", new)
        return self[new]

    def users(self, name: str) -> list[str]:
        """List what uses a data type.

        Args:
            name: The data type name.

        Returns:
            Descriptions of every tag (controller and program scope), UDT
            member, AOI parameter and AOI local tag that has this type.
        """
        return find_type_users(self._parent, name)

    def remove(self, name: str, *, force: bool = False) -> None:
        """Delete a data type.

        Args:
            name: The data type name.
            force: Delete even if something uses the type. The users are then
                left pointing at a type that no longer exists.

        Raises:
            KeyError: If there is no such data type.
            ValueError: If the type is in use (listing the users) and *force*
                is false.
        """
        element = self._find_element(name)
        users = self.users(name)
        if users and not force:
            raise ValueError(f"data type {name!r} is in use by: " + ", ".join(users))
        container = self._parent.find("DataTypes")
        assert container is not None
        remove_child(container, element)

"""Plain-data specs for objects built from engineering decisions.

The dataclasses here hold only what an engineer decides (names, types,
descriptions, ...) and use only ``str``/``int``/``bool``/``None``/``list``
fields, so they convert to and from JSON directly. Turning them into
Studio-exact XML is the job of the builder functions, for example
:func:`py_l5x.build.datatype.build_datatype`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MemberSpec:
    """One member of a user-defined data type.

    ``data_type`` ``"BOOL"`` means a plain BOOL: the builder packs runs of them
    into hidden ``SINT`` hosts and writes them as ``BIT`` members.

    Attributes:
        name: Member name.
        data_type: Type name (``"BOOL"``, ``"DINT"``, a UDT, an AOI, ...).
        dimension: Array size, ``0`` for a scalar. Only one dimension exists in
            UDT members. BOOL arrays are rounded up to a multiple of 32.
        description: Member description.
        radix: Display radix, or ``None`` for the type's default.
        external_access: ``"Read/Write"``, ``"Read Only"`` or ``"None"``.
        engineering_unit: Engineering unit text.
        min: Minimum value, as written in the XML.
        max: Maximum value, as written in the XML.
        state0: Text for the zero state of a BOOL.
        state1: Text for the one state of a BOOL.
        external_logging: ``True``/``False`` to write ``ExternalLogging``,
            ``None`` to leave it out.
    """

    name: str
    data_type: str
    dimension: int = 0
    description: str = ""
    radix: str | None = None
    external_access: str = "Read/Write"
    engineering_unit: str = ""
    min: str | int | float | None = None
    max: str | int | float | None = None
    state0: str = ""
    state1: str = ""
    external_logging: bool | None = None


@dataclass
class DataTypeSpec:
    """A user-defined data type.

    Attributes:
        name: Data type name.
        members: The members in order, with BOOLs as plain ``BOOL``.
        description: Data type description.
        family: ``"NoFamily"`` or ``"StringFamily"``.
    """

    name: str
    members: list[MemberSpec]
    description: str = ""
    family: str = "NoFamily"

    @classmethod
    def string(cls, name: str, length: int, description: str = "") -> DataTypeSpec:
        """Create a string type like Studio's ``STRING``.

        Args:
            name: Data type name.
            length: Maximum characters (the size of ``DATA``).
            description: Data type description.

        Returns:
            A ``StringFamily`` spec with ``LEN`` (``DINT``) and ``DATA``
            (``SINT[length]``, radix ``ASCII``).
        """
        return cls(
            name,
            [
                MemberSpec("LEN", "DINT"),
                MemberSpec("DATA", "SINT", dimension=length, radix="ASCII"),
            ],
            description,
            "StringFamily",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-friendly ``dict``.

        Returns:
            Nested ``dict``/``list`` of plain values.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataTypeSpec:
        """Rebuild a spec from :meth:`to_dict` output (or parsed JSON).

        Args:
            data: A mapping with ``name`` and ``members`` and optionally
                ``description`` and ``family``.

        Returns:
            The spec.
        """
        return cls(
            name=data["name"],
            members=[MemberSpec(**member) for member in data["members"]],
            description=data.get("description", ""),
            family=data.get("family", "NoFamily"),
        )


@dataclass
class ParameterSpec:
    """One parameter of an Add-On Instruction.

    ``EnableIn`` and ``EnableOut`` are not listed: the builder always adds them.

    Attributes:
        name: Parameter name.
        data_type: Type name. ``Input``/``Output`` parameters are atomic
            scalars; only ``InOut`` ones may be structured or arrays.
        usage: ``"Input"``, ``"Output"`` or ``"InOut"``.
        required: Whether the parameter is required (appears in calls).
            ``None`` derives it: ``True`` for ``InOut``, else ``False``.
        visible: Whether the parameter is visible on the instruction.
            ``None`` derives it: ``True`` for ``InOut`` and for required
            parameters, else ``False``. Studio rejects ``InOut`` unless both
            are true, and Input/Output with ``required`` but not ``visible``.
        dimension: Array size (``InOut`` only), ``0`` for a scalar.
        description: Parameter description.
        default: The default value as a Python value (a scalar, or a ``dict``
            or ``list`` for structured types), merged over the type default;
            ``None`` keeps the type default. ``InOut`` parameters have none.
        radix: Display radix, or ``None`` for the type's default.
        external_access: ``"Read/Write"``, ``"Read Only"`` or ``"None"``;
            ``None`` means Studio's default for the usage (Input
            ``Read/Write``, Output ``Read Only``). ``InOut`` has none.
        engineering_unit: Engineering unit text.
        min: Minimum value, as written in the XML.
        max: Maximum value, as written in the XML.
        state0: Text for the zero state of a BOOL.
        state1: Text for the one state of a BOOL.
        operand_comments: ``{operand: comment}``, for example ``{".6": "x"}``.
    """

    name: str
    data_type: str
    usage: str = "Input"
    required: bool | None = None
    visible: bool | None = None
    dimension: int = 0
    description: str = ""
    default: Any = None
    radix: str | None = None
    external_access: str | None = None
    engineering_unit: str = ""
    min: str | int | float | None = None
    max: str | int | float | None = None
    state0: str = ""
    state1: str = ""
    operand_comments: dict[str, str] = field(default_factory=dict)


@dataclass
class LocalTagSpec:
    """One local tag of an Add-On Instruction.

    Attributes:
        name: Local tag name.
        data_type: Type name.
        dimension: Array size, ``0`` for a scalar.
        description: Description.
        default: Default value as a Python value (see
            :class:`ParameterSpec`); ``None`` keeps the type default.
        radix: Display radix for atomic types, or ``None`` for the default.
        external_access: ``"Read/Write"``, ``"Read Only"`` or ``"None"``.
    """

    name: str
    data_type: str
    dimension: int = 0
    description: str = ""
    default: Any = None
    radix: str | None = None
    external_access: str = "Read/Write"


@dataclass
class RungSpec:
    """One ladder rung.

    Attributes:
        text: The rung's neutral text.
        comment: Rung comment.
    """

    text: str
    comment: str = ""


@dataclass
class RoutineSpec:
    """One routine of an Add-On Instruction.

    Attributes:
        name: ``Logic``, ``Prescan``, ``Postscan`` or ``EnableInFalse``.
        type_: ``"RLL"`` or ``"ST"``.
        rungs: The rungs of an RLL routine.
        lines: The lines of an ST routine.
        description: Routine description.
    """

    name: str
    type_: str = "RLL"
    rungs: list[RungSpec] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class AOISpec:
    """An Add-On Instruction definition.

    Attributes:
        name: Instruction name.
        parameters: The parameters in order, without ``EnableIn``/``EnableOut``.
        local_tags: The local tags in order.
        routines: The routines; ``Logic`` is required.
        revision: Revision text.
        revision_note: Revision note.
        description: Instruction description.
        vendor: Vendor text.
        execute_prescan: ``ExecutePrescan``; ``None`` means true if a
            ``Prescan`` routine is present.
        execute_postscan: ``ExecutePostscan``, same rule.
        execute_enable_in_false: ``ExecuteEnableInFalse``, same rule.
        additional_help_text: Additional help text.
        metadata: Extra attributes written verbatim (``Class``,
            ``CreatedDate``, ``CreatedBy``, ``EditedDate``, ``EditedBy``,
            ``SoftwareRevision``, ...). New specs leave it empty and Studio
            fills the dates on import.
    """

    name: str
    parameters: list[ParameterSpec]
    local_tags: list[LocalTagSpec] = field(default_factory=list)
    routines: list[RoutineSpec] = field(default_factory=list)
    revision: str = "1.0"
    revision_note: str = ""
    description: str = ""
    vendor: str = ""
    execute_prescan: bool | None = None
    execute_postscan: bool | None = None
    execute_enable_in_false: bool | None = None
    additional_help_text: str = ""
    metadata: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-friendly ``dict``.

        Returns:
            Nested ``dict``/``list`` of plain values.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AOISpec:
        """Rebuild a spec from :meth:`to_dict` output (or parsed JSON).

        Args:
            data: A mapping with ``name`` and ``parameters`` and optionally the
                other fields.

        Returns:
            The spec.
        """
        fields = dict(data)
        fields["parameters"] = [ParameterSpec(**p) for p in data["parameters"]]
        fields["local_tags"] = [LocalTagSpec(**t) for t in data.get("local_tags", [])]
        fields["routines"] = [
            RoutineSpec(
                **{
                    **r,
                    "rungs": [RungSpec(**rung) for rung in r.get("rungs", [])],
                }
            )
            for r in data.get("routines", [])
        ]
        return cls(**fields)


@dataclass
class TagSpec:
    """A controller or program tag.

    Exactly one of ``data_type`` and ``alias_for`` is required.

    Attributes:
        name: Tag name.
        data_type: Type name for a base tag.
        dimensions: Array size, or a tuple of up to three sizes. A BOOL array
            is rounded up to a multiple of 32, as Studio does.
        description: Tag description.
        value: Initial value: a scalar, a ``str``, a ``dict`` (structure) or a
            ``list``/``dict`` (array), as the ``value`` setter accepts. ``None``
            writes no ``<Data>`` (Studio fills in defaults).
        radix: Display radix.
        external_access: ``"Read/Write"``, ``"Read Only"`` or ``"None"``.
        constant: Whether the tag is a constant; ``None`` omits the attribute.
        alias_for: The tag or operand path an alias tag refers to.
        operand_comments: ``{operand: comment}`` (for example ``{".0": "x"}``).
        operand_metadata: Other operand metadata, ``{operand: {key: text}}``
            with keys ``max``, ``min``, ``engineering_unit``, ``state0``,
            ``state1``, ``external_logging`` (or ``comment``). The operand
            ``""`` is the tag itself (an entry without an ``Operand``).
        metadata: Other ``<Tag>`` attributes written verbatim (``Class``,
            ``Usage``, ``OpcUaAccess``, ``Max``, ``Min``, ``ExternalLogging``,
            ``DataExchangeId``, ...).
    """

    name: str
    data_type: str | None = None
    dimensions: int | tuple[int, ...] | None = None
    description: str = ""
    value: Any = None
    radix: str | None = None
    external_access: str | None = None
    constant: bool | None = None
    alias_for: str | None = None
    operand_comments: dict[str, str] | None = None
    operand_metadata: dict[str, dict[str, str]] | None = None
    metadata: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-friendly ``dict`` (tuples become lists).

        Returns:
            Nested ``dict``/``list`` of plain values.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TagSpec:
        """Rebuild a spec from :meth:`to_dict` output (or parsed JSON).

        Args:
            data: A mapping with ``name`` and optionally the other fields.

        Returns:
            The spec (a list ``dimensions`` becomes a tuple).
        """
        fields = dict(data)
        if isinstance(fields.get("dimensions"), list):
            fields["dimensions"] = tuple(fields["dimensions"])
        return cls(**fields)


@dataclass
class ProgramSpec:
    """A program.

    Attributes:
        name: Program name.
        tags: The program's tags, in order.
        routines: The routines (written sorted by name, as Studio does).
        main_routine: Name of the main routine, or ``None``.
        fault_routine: Name of the fault routine, or ``None``.
        description: Program description.
        disabled: Whether the program is disabled.
        class_: ``"Standard"`` or ``"Safety"``; ``None`` omits the attribute.
        metadata: Other ``<Program>`` attributes written verbatim
            (``TestEdits`` and ``UseAsFolder`` default to ``"false"``).
    """

    name: str
    tags: list[TagSpec] = field(default_factory=list)
    routines: list[RoutineSpec] = field(default_factory=list)
    main_routine: str | None = None
    fault_routine: str | None = None
    description: str = ""
    disabled: bool = False
    class_: str | None = "Standard"
    metadata: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-friendly ``dict``.

        Returns:
            Nested ``dict``/``list`` of plain values.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgramSpec:
        """Rebuild a spec from :meth:`to_dict` output (or parsed JSON).

        Args:
            data: A mapping with ``name`` and optionally the other fields.

        Returns:
            The spec.
        """
        fields = dict(data)
        fields["tags"] = [TagSpec.from_dict(t) for t in data.get("tags", [])]
        fields["routines"] = [
            RoutineSpec(
                **{**r, "rungs": [RungSpec(**rung) for rung in r.get("rungs", [])]}
            )
            for r in data.get("routines", [])
        ]
        return cls(**fields)

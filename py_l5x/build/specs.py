"""Plain-data specs for objects built from engineering decisions.

The dataclasses here hold only what an engineer decides (names, types,
descriptions, ...) and use only ``str``/``int``/``bool``/``None``/``list``
fields, so they convert to and from JSON directly. Turning them into
Studio-exact XML is the job of the builder functions, for example
:func:`py_l5x.build.datatype.build_datatype`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
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

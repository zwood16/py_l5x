"""Build ``<DataType>`` elements from :class:`~py_l5x.build.specs.DataTypeSpec`.

The output matches Studio 5000 exports, whitespace included (an element with
children has ``text`` ``"\\n"`` and every child ``tail`` ``"\\n"``; the root has
no ``tail``).

Rules, taken from real exports:

- **BOOL packing.** A run of consecutive scalar ``BOOL`` members gets a hidden
  ``SINT`` host for every 8 bits, placed just before its bits and named
  ``ZZZZZZZZZZ<first 10 characters of the UDT name><index>``, where *index* is
  the host's position in the final member list (hosts included). Each BOOL
  becomes ``DataType="BIT"`` with ``Target`` and ``BitNumber`` 0 to 7. A
  member that is not a scalar BOOL (including a BOOL array) ends the run.
- **BOOL arrays** stay ``BOOL`` and are rounded up to a multiple of 32.
- **Member attributes** are written in the order ``Name DataType Dimension
  Radix Hidden [Target BitNumber] [Max Min] [ExternalLogging] ExternalAccess``.
  ``Radix`` is the spec's, else the type default (``NullType`` for
  non-atomic types). Children are ``Description``, ``EngineeringUnit``,
  ``State0`` and ``State1``.
- **Dependencies** are mandatory (Studio fails to open a project without them)
  for members of a user UDT or an AOI: one ``<Dependency>`` per such member,
  in member order, with ``Type="DataType"`` or
  ``Type="AddOnInstructionDefinition"``. Studio's own exports repeat a type
  that several members share. Atomic types and built-in structures (``TIMER``,
  ``STRING``, ...) are not listed. With a *registry* an AOI name gives the AOI
  type, and a product-defined type counts as built-in; without one, every
  type that is neither atomic nor in the built-in table is a ``DataType``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.build.specs import DataTypeSpec, MemberSpec
from py_l5x.parsers.atomic_types import (
    ATOMIC_TYPES,
    default_radix,
    format_float_literal,
)
from py_l5x.parsers.layout import builtin_table
from py_l5x.parsers.names import validate_new_name
from py_l5x.parsers.schema import new_cdata_element

if TYPE_CHECKING:
    from py_l5x.parsers.tag import TypeRegistry

_FAMILIES = ("NoFamily", "StringFamily")
_HOST_PREFIX = "Z" * 10


def _fill(element: ET.Element, children: list[ET.Element]) -> ET.Element:
    """Append *children* in Studio's one-element-per-line layout.

    Args:
        element: The parent.
        children: Its children.

    Returns:
        *element*.
    """
    if children:
        element.text = "\n"
        for child in children:
            child.tail = "\n"
            element.append(child)
    return element


def _validate(spec: DataTypeSpec) -> None:
    """Check a spec before building.

    Args:
        spec: The spec.

    Raises:
        ValueError: For an invalid or duplicate name, an unknown family, a
            negative or non-integer dimension, a member typed as the UDT
            itself, a ``BIT`` member (use ``BOOL``), or Min/Max on a BOOL.
    """
    validate_new_name(spec.name, [], "data type")
    if spec.family not in _FAMILIES:
        raise ValueError(f"family must be one of {_FAMILIES}, not {spec.family!r}")
    seen: list[str] = []
    for member in spec.members:
        validate_new_name(member.name, seen, "member")
        seen.append(member.name)
        if type(member.dimension) is not int or member.dimension < 0:
            raise ValueError(
                f"member {member.name!r}: dimension must be an integer >= 0 "
                f"(UDT members have one dimension), not {member.dimension!r}"
            )
        if not isinstance(member.data_type, str) or not member.data_type:
            raise ValueError(f"member {member.name!r} needs a data type")
        if member.data_type.lower() == spec.name.lower():
            raise ValueError(f"member {member.name!r} cannot be of its own type")
        if member.data_type == "BIT":
            raise ValueError(f"member {member.name!r}: use BOOL, not BIT")
        if member.data_type == "BOOL" and (
            member.min is not None or member.max is not None
        ):
            raise ValueError(f"member {member.name!r}: BOOL members have no min/max")


def _member_radix(member: MemberSpec) -> str:
    """Return the radix to write for a member.

    Args:
        member: The member.

    Returns:
        The spec's radix, else the atomic default, else ``"NullType"``.
    """
    if member.radix:
        return member.radix
    if member.data_type in ATOMIC_TYPES:
        return default_radix(member.data_type) or "Decimal"
    return "NullType"


def _member_element(
    member: MemberSpec,
    data_type: str,
    dimension: int,
    radix: str,
    *,
    host: tuple[str, int] | None = None,
) -> ET.Element:
    """Create one ``<Member>`` element.

    Args:
        member: The spec the extended properties come from.
        data_type: The ``DataType`` to write (``BIT`` for packed BOOLs).
        dimension: The ``Dimension`` to write.
        radix: The ``Radix`` to write.
        host: ``(host name, bit number)`` for a packed BOOL.

    Returns:
        The element with its children.
    """
    element = ET.Element("Member")
    element.set("Name", member.name)
    element.set("DataType", data_type)
    element.set("Dimension", str(dimension))
    element.set("Radix", radix)
    element.set("Hidden", "false")
    if host is not None:
        element.set("Target", host[0])
        element.set("BitNumber", str(host[1]))
    if member.max is not None:
        element.set("Max", _limit_text(member.max, member.data_type))
    if member.min is not None:
        element.set("Min", _limit_text(member.min, member.data_type))
    if member.external_logging is not None:
        element.set("ExternalLogging", "true" if member.external_logging else "false")
    element.set("ExternalAccess", member.external_access)
    children = [
        new_cdata_element(tag, text)
        for tag, text in (
            ("Description", member.description),
            ("EngineeringUnit", member.engineering_unit),
            ("State0", member.state0),
            ("State1", member.state1),
        )
        if text
    ]
    return _fill(element, children)


def _host_element(name: str) -> ET.Element:
    """Create a hidden ``SINT`` host member.

    Args:
        name: The host name.

    Returns:
        The element.
    """
    element = ET.Element("Member")
    for key, value in (
        ("Name", name),
        ("DataType", "SINT"),
        ("Dimension", "0"),
        ("Radix", "Decimal"),
        ("Hidden", "true"),
        ("ExternalAccess", "Read/Write"),
    ):
        element.set(key, value)
    return element


def _dependency_type(data_type: str, registry: TypeRegistry | None) -> str | None:
    """Classify a member type for ``<Dependencies>``.

    Args:
        data_type: The member's type name.
        registry: The project's type registry, if available.

    Returns:
        ``"DataType"``, ``"AddOnInstructionDefinition"``, or ``None`` for
        atomic and built-in types.
    """
    if data_type in ATOMIC_TYPES or data_type in builtin_table():
        return None
    if registry is not None:
        if registry.aoi(data_type) is not None or registry.is_protected_aoi(data_type):
            return "AddOnInstructionDefinition"
        udt = registry.udt(data_type)
        if udt is not None and udt.class_ == "ProductDefined":
            return None
    return "DataType"


def build_datatype(
    spec: DataTypeSpec, registry: TypeRegistry | None = None
) -> ET.Element:
    """Build a ``<DataType Class="User">`` element from a spec.

    See the module docstring for the packing, attribute and dependency rules.

    Args:
        spec: The data type.
        registry: The project's type registry, used to tell UDT members from
            AOI members when listing dependencies (optional).

    Returns:
        The element, laid out like Studio's export and with no ``tail``.

    Raises:
        ValueError: If the spec is invalid (see :func:`_validate`).
    """
    _validate(spec)
    members: list[ET.Element] = []
    dependencies: list[ET.Element] = []
    run_bits = 0
    host_name = ""
    for member in spec.members:
        if member.data_type == "BOOL" and member.dimension == 0:
            if run_bits % 8 == 0:
                host_name = f"{_HOST_PREFIX}{spec.name[:10]}{len(members)}"
                members.append(_host_element(host_name))
            members.append(
                _member_element(
                    member,
                    "BIT",
                    0,
                    _member_radix(member),
                    host=(host_name, run_bits % 8),
                )
            )
            run_bits += 1
            continue
        run_bits = 0
        dimension = member.dimension
        if member.data_type == "BOOL" and dimension:
            dimension = -(-dimension // 32) * 32
        members.append(
            _member_element(member, member.data_type, dimension, _member_radix(member))
        )
        kind = _dependency_type(member.data_type, registry)
        if kind is not None:
            dependency = ET.Element("Dependency")
            dependency.set("Type", kind)
            dependency.set("Name", member.data_type)
            dependencies.append(dependency)

    root = ET.Element("DataType")
    root.set("Name", spec.name)
    root.set("Family", spec.family)
    root.set("Class", "User")
    children: list[ET.Element] = []
    if spec.description:
        children.append(new_cdata_element("Description", spec.description))
    children.append(_fill(ET.Element("Members"), members))
    if dependencies:
        children.append(_fill(ET.Element("Dependencies"), dependencies))
    return _fill(root, children)


def _limit_text(value: str | int | float, data_type: str) -> str:
    """Format a member Min/Max limit the way Studio exports it.

    Numeric limits on REAL/LREAL members are written as floats (``1800`` becomes
    ``"1800.0"``, as Studio does); other numbers are written as-is and strings
    are passed through unchanged.

    Args:
        value: The limit from the spec.
        data_type: The member's data type.

    Returns:
        The attribute text.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if data_type.upper() in ("REAL", "LREAL"):
            return format_float_literal(float(value), data_type.upper(), "Float")
        return str(value)
    return str(value)

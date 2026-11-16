"""Build ``<AddOnInstructionDefinition>`` elements from an :class:`AOISpec`.

The output matches Studio 5000 exports (whitespace included: an element with
children has ``text`` ``"\\n"`` and every child ``tail`` ``"\\n"``; the root has
no ``tail``). Rules, taken from real exports and from Studio's own re-exports
of imported AOIs:

- **Attributes.** ``Name Class Revision Vendor ExecutePrescan ExecutePostscan
  ExecuteEnableInFalse CreatedDate CreatedBy EditedDate EditedBy
  SoftwareRevision``. ``Class`` and the dates/versions come from
  ``spec.metadata`` (Studio fills them on import when absent); other metadata
  keys follow, in order. The ``Execute*`` flags default to "a routine of that
  name is present". Studio keeps a routine whatever its flag says.
- **Children.** ``Description``, ``RevisionNote``, ``AdditionalHelpText``,
  ``Parameters``, ``LocalTags`` (always present, self-closed when empty),
  ``Routines`` (sorted by name, as Studio writes them), ``Dependencies``.
- **Parameters.** ``EnableIn`` and ``EnableOut`` always come first, with their
  system descriptions. ``Input``/``Output`` parameters have attributes
  ``Name TagType DataType Usage Radix Required Visible ExternalAccess [Max
  Min]`` (ExternalAccess defaults to ``Read/Write`` for Input and ``Read
  Only`` for Output) and a ``DefaultData`` of format ``Decorated``. ``InOut``
  parameters have ``Name TagType DataType [Dimensions] Usage Required Visible
  Constant="false"``, no radix, no access and no data. Children are
  ``Description``, ``Comments``, ``EngineeringUnits``, ``State0s``,
  ``State1s`` (the plural containers hold un-operanded entries) and
  ``DefaultData``.
- **Local tags.** ``Name DataType [Dimensions] [Radix] ExternalAccess`` (the
  radix only for atomic types) with ``Description`` and ``DefaultData``.
  The position of ``Dimensions`` is not confirmed by any export.
- **DefaultData** is always ``Decorated`` (``String`` for string types), never
  L5K, built from :mod:`py_l5x.parsers.layout` defaults with the spec's value
  merged over it.
- **Dependencies.** One entry per distinct user UDT or AOI type used by a
  parameter (``InOut`` included) or local tag, in order of first use: the
  parameters, then the local tags. Atomic and built-in types are not listed.
  Studio's exports order a large AOI's dependencies by something else (not
  recoverable from the definition), so the order may differ there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

from py_l5x.build.datatype import _dependency_type, _fill, _limit_text
from py_l5x.build.specs import AOISpec, LocalTagSpec, ParameterSpec, RoutineSpec
from py_l5x.parsers.atomic_types import ATOMIC_TYPES, default_radix
from py_l5x.parsers.layout import default_data_element
from py_l5x.parsers.names import validate_new_name
from py_l5x.parsers.routine import _check_rung_text, build_rung, build_st_line
from py_l5x.parsers.schema import new_cdata_element
from py_l5x.parsers.tag import _find_value_root, _operand_sort_key, _TagOverrides

if TYPE_CHECKING:
    from py_l5x.parsers.aoi import AOIDefinition
    from py_l5x.parsers.tag import TypeRegistry

#: Names an AOI's routines may have, in the order Studio writes them.
ROUTINE_NAMES = ("EnableInFalse", "Logic", "Postscan", "Prescan")
_RESERVED = ("enablein", "enableout")
_USAGES = ("Input", "Output", "InOut")
_ACCESS = ("Read/Write", "Read Only", "None")
_DEFAULT_ACCESS = {"Input": "Read/Write", "Output": "Read Only"}
_METADATA_ORDER = (
    "Class",
    "CreatedDate",
    "CreatedBy",
    "EditedDate",
    "EditedBy",
    "SoftwareRevision",
)


class _NoTypes:
    """Stand-in registry that knows no project types.

    Lets atomic and built-in types resolve when no real registry is given.
    """

    def udt(self, name: str) -> None:
        """Return ``None``: no UDTs are known.

        Args:
            name: Ignored.
        """
        return None

    def aoi(self, name: str) -> None:
        """Return ``None``: no AOIs are known.

        Args:
            name: Ignored.
        """
        return None

    def is_string_type(self, name: str) -> bool:
        """Return ``False``: no user string types are known.

        Args:
            name: Ignored.

        Returns:
            Always ``False``.
        """
        return False

    def string_max_length(self, name: str) -> None:
        """Return ``None``: no sizes are known.

        Args:
            name: Ignored.
        """
        return None


def required_visible(param: ParameterSpec) -> tuple[bool, bool]:
    """Resolve a parameter's ``Required`` and ``Visible`` flags.

    ``InOut`` parameters are always required and visible. For Input/Output,
    ``required`` defaults to false and ``visible`` to the value of ``required``.

    Args:
        param: The parameter.

    Returns:
        ``(required, visible)``.

    Raises:
        ValueError: If Studio would reject the combination: an ``InOut`` that
            is not both required and visible (``RxE_INVALID_TAG_USAGE_TYPE``),
            or an Input/Output that is required but not visible
            (``RxE_ILLEGAL_OPERATIONS``: failed to set the 'Visible' property).
    """
    if param.usage == "InOut":
        required = True if param.required is None else param.required
        visible = True if param.visible is None else param.visible
        if not (required and visible):
            raise ValueError(
                f"{param.name!r}: InOut parameters must be required and visible "
                "(Studio rejects anything else: RxE_INVALID_TAG_USAGE_TYPE)"
            )
        return True, True
    required = bool(param.required)
    visible = required if param.visible is None else param.visible
    if required and not visible:
        raise ValueError(
            f"{param.name!r}: a required parameter must be visible (Studio aborts "
            "the import: RxE_ILLEGAL_OPERATIONS, failed to set the 'Visible' "
            "property)"
        )
    return required, visible


def aoi_call_operands(source: AOISpec | AOIDefinition) -> list[str]:
    """List the operands of a call after the instance tag.

    In every RLL call, ``Name(instance, <required parameters in order>)``;
    ``EnableIn`` and ``EnableOut`` never appear. ``InOut`` parameters count.

    Args:
        source: An :class:`AOISpec` or a loaded
            :class:`~py_l5x.parsers.aoi.AOIDefinition`.

    Returns:
        The names of the required parameters, in definition order.
    """
    if isinstance(source, AOISpec):
        return [p.name for p in source.parameters if required_visible(p)[0]]
    return [
        element.get("Name", "")
        for element in source._element.findall("Parameters/Parameter")
        if element.get("Required") == "true"
        and element.get("Name") not in ("EnableIn", "EnableOut")
    ]


def _validate(spec: AOISpec) -> None:
    """Check a spec before building.

    Args:
        spec: The spec.

    Raises:
        ValueError: For invalid or duplicate names (parameters and local tags
            share one namespace), the reserved ``EnableIn``/``EnableOut``, a
            bad usage, access or dimension, a structured or array
            ``Input``/``Output`` parameter, a default on an ``InOut``, a
            missing ``Logic`` routine, routine names outside
            ``Logic``/``Prescan``/``Postscan``/``EnableInFalse``, mismatched
            rungs/lines, or an invalid rung text.
    """
    validate_new_name(spec.name, [], "add-on instruction")
    seen: list[str] = []
    for item in [*spec.parameters, *spec.local_tags]:
        if item.name.lower() in _RESERVED:
            raise ValueError(f"{item.name!r} is a reserved parameter name")
        validate_new_name(item.name, seen, "parameter or local tag")
        seen.append(item.name)
        if type(item.dimension) is not int or item.dimension < 0:
            raise ValueError(f"{item.name!r}: dimension must be an integer >= 0")
        if item.external_access is not None and item.external_access not in _ACCESS:
            raise ValueError(f"{item.name!r}: external access must be in {_ACCESS}")
        if not isinstance(item.data_type, str) or not item.data_type:
            raise ValueError(f"{item.name!r} needs a data type")
    for param in spec.parameters:
        if param.usage not in _USAGES:
            raise ValueError(f"{param.name!r}: usage must be one of {_USAGES}")
        if param.usage == "InOut":
            if param.default is not None:
                raise ValueError(f"{param.name!r}: InOut parameters have no default")
            if param.min is not None or param.max is not None:
                raise ValueError(f"{param.name!r}: InOut parameters have no min/max")
        elif param.data_type not in ATOMIC_TYPES or param.dimension:
            raise ValueError(
                f"{param.name!r}: only InOut parameters may be structured or arrays "
                "(Studio: RxE_ARRAY_INVALID_FOR_PARAMETER / "
                "RxE_INVALID_DATATYPE_FOR_PARAMETER)"
            )
        required_visible(param)
    names = [r.name for r in spec.routines]
    if "Logic" not in names:
        raise ValueError("an add-on instruction needs a Logic routine")
    for routine in spec.routines:
        if routine.name not in ROUTINE_NAMES:
            raise ValueError(
                f"routine name must be one of {sorted(ROUTINE_NAMES)}, "
                f"not {routine.name!r}"
            )
        if routine.type_ not in ("RLL", "ST"):
            raise ValueError(f"routine type must be 'RLL' or 'ST': {routine.type_!r}")
        if routine.type_ == "RLL" and routine.lines:
            raise ValueError(f"RLL routine {routine.name!r} cannot have ST lines")
        if routine.type_ == "ST" and routine.rungs:
            raise ValueError(f"ST routine {routine.name!r} cannot have rungs")
        for rung in routine.rungs:
            _check_rung_text(rung.text)
        if any("\n" in line or "\r" in line for line in routine.lines):
            raise ValueError("each ST line must be a single line")
    if len(set(names)) != len(names):
        raise ValueError("duplicate routine names")


def _default_data(
    data_type: str,
    dimension: int,
    radix: str | None,
    value: Any,
    registry: Any,
) -> ET.Element:
    """Build a ``DefaultData`` element: layout defaults with *value* merged in.

    Args:
        data_type: The type name.
        dimension: Array size, ``0`` for a scalar.
        radix: The radix for atomic types.
        value: The default value, or ``None`` for the type default.
        registry: The project's type registry.

    Returns:
        A ``Decorated`` (or ``String``) ``<DefaultData>`` element without tail.

    Raises:
        LayoutError: If the type is unknown or has no decorated layout.
        KeyError: If *value* names an unknown member.
        TypeError: If *value* has the wrong type.
        ValueError: If *value* is out of range.
    """
    data = default_data_element(
        data_type, registry, dimensions=(dimension,) if dimension else None, radix=radix
    )
    if value is not None:
        probe = ET.Element("Tag")
        probe.set("DataType", data_type)
        probe.append(data)
        found = _find_value_root(probe, "Data", registry)
        assert found is not None
        node_cls, root = found
        node = node_cls(root, None, _TagOverrides(probe), "", registry)
        ops: list = []
        node._plan_write(value, ops)
        for op in ops:
            op()
    data.tag = "DefaultData"
    data.tail = None
    return data


def python_default(
    data_type: str, dimension: int, radix: str | None, registry: Any
) -> Any:
    """Return the Python value of a type's default (as ``to_python()`` shows).

    Args:
        data_type: The type name.
        dimension: Array size, ``0`` for a scalar.
        radix: The radix for atomic types.
        registry: The project's type registry.

    Returns:
        The default as a scalar, ``dict`` or ``list``.
    """
    data = default_data_element(
        data_type, registry, dimensions=(dimension,) if dimension else None, radix=radix
    )
    probe = ET.Element("Tag")
    probe.set("DataType", data_type)
    probe.append(data)
    found = _find_value_root(probe, "Data", registry)
    assert found is not None
    node_cls, root = found
    return node_cls(root, None, _TagOverrides(probe), "", registry).to_python()


def _container(tag: str, child_tag: str, text: str) -> ET.Element:
    """Create a plural container holding one un-operanded CDATA entry.

    Args:
        tag: ``"EngineeringUnits"``, ``"State0s"`` or ``"State1s"``.
        child_tag: The entry tag.
        text: The entry text.

    Returns:
        The container element.
    """
    return _fill(ET.Element(tag), [new_cdata_element(child_tag, text)])


def _enable_parameter(name: str, usage: str, description: str) -> ET.Element:
    """Create the system-defined ``EnableIn``/``EnableOut`` parameter.

    Args:
        name: ``"EnableIn"`` or ``"EnableOut"``.
        usage: ``"Input"`` or ``"Output"``.
        description: The system description.

    Returns:
        The element.
    """
    element = ET.Element("Parameter")
    for key, value in (
        ("Name", name),
        ("TagType", "Base"),
        ("DataType", "BOOL"),
        ("Usage", usage),
        ("Radix", "Decimal"),
        ("Required", "false"),
        ("Visible", "false"),
        ("ExternalAccess", "Read Only"),
    ):
        element.set(key, value)
    return _fill(element, [new_cdata_element("Description", description)])


def _parameter(param: ParameterSpec, registry: Any) -> ET.Element:
    """Build one ``<Parameter>`` element.

    Args:
        param: The parameter.
        registry: The project's type registry.

    Returns:
        The element.
    """
    element = ET.Element("Parameter")
    element.set("Name", param.name)
    element.set("TagType", "Base")
    element.set("DataType", param.data_type)
    if param.dimension:
        element.set("Dimensions", str(param.dimension))
    element.set("Usage", param.usage)
    radix = param.radix or default_radix(param.data_type)
    if param.usage != "InOut":
        element.set("Radix", radix or "Decimal")
    required, visible = required_visible(param)
    element.set("Required", "true" if required else "false")
    element.set("Visible", "true" if visible else "false")
    if param.usage == "InOut":
        element.set("Constant", "false")
    else:
        element.set(
            "ExternalAccess", param.external_access or _DEFAULT_ACCESS[param.usage]
        )
        if param.max is not None:
            element.set("Max", _limit_text(param.max, param.data_type))
        if param.min is not None:
            element.set("Min", _limit_text(param.min, param.data_type))
    children: list[ET.Element] = []
    if param.description:
        children.append(new_cdata_element("Description", param.description))
    if param.operand_comments:
        entries = []
        for operand in sorted(param.operand_comments, key=_operand_sort_key):
            entry = new_cdata_element("Comment", param.operand_comments[operand])
            entry.set("Operand", operand)
            entries.append(entry)
        children.append(_fill(ET.Element("Comments"), entries))
    if param.engineering_unit:
        children.append(
            _container("EngineeringUnits", "EngineeringUnit", param.engineering_unit)
        )
    if param.state0:
        children.append(_container("State0s", "State0", param.state0))
    if param.state1:
        children.append(_container("State1s", "State1", param.state1))
    if param.usage != "InOut":
        children.append(
            _default_data(param.data_type, 0, radix, param.default, registry)
        )
    return _fill(element, children)


def _local_tag(local: LocalTagSpec, registry: Any) -> ET.Element:
    """Build one ``<LocalTag>`` element.

    Args:
        local: The local tag.
        registry: The project's type registry.

    Returns:
        The element.
    """
    element = ET.Element("LocalTag")
    element.set("Name", local.name)
    element.set("DataType", local.data_type)
    if local.dimension:
        element.set("Dimensions", str(local.dimension))
    radix = None
    if local.data_type in ATOMIC_TYPES:
        radix = local.radix or default_radix(local.data_type)
        element.set("Radix", radix or "Decimal")
    element.set("ExternalAccess", local.external_access)
    children: list[ET.Element] = []
    if local.description:
        children.append(new_cdata_element("Description", local.description))
    children.append(
        _default_data(local.data_type, local.dimension, radix, local.default, registry)
    )
    return _fill(element, children)


def _routine(routine: RoutineSpec) -> ET.Element:
    """Build one ``<Routine>`` element.

    Args:
        routine: The routine.

    Returns:
        The element.
    """
    element = ET.Element("Routine")
    element.set("Name", routine.name)
    element.set("Type", routine.type_)
    children: list[ET.Element] = []
    if routine.description:
        children.append(new_cdata_element("Description", routine.description))
    if routine.type_ == "RLL":
        content = _fill(
            ET.Element("RLLContent"),
            [
                build_rung(rung.text, rung.comment or None, number)
                for number, rung in enumerate(routine.rungs)
            ],
        )
    else:
        content = _fill(
            ET.Element("STContent"),
            [build_st_line(line, number) for number, line in enumerate(routine.lines)],
        )
    children.append(content)
    return _fill(element, children)


def _flag(value: bool | None, present: bool) -> str:
    """Format an ``Execute*`` flag.

    Args:
        value: The spec value, or ``None`` for "true if present".
        present: Whether the matching routine exists.

    Returns:
        ``"true"`` or ``"false"``.
    """
    return "true" if (present if value is None else value) else "false"


def build_aoi(spec: AOISpec, registry: TypeRegistry | None = None) -> ET.Element:
    """Build an ``<AddOnInstructionDefinition>`` element from a spec.

    See the module docstring for the layout rules.

    Args:
        spec: The instruction.
        registry: The project's type registry. Needed for parameters and local
            tags of project UDT or AOI types (defaults and dependencies);
            atomic and built-in types resolve without it.

    Returns:
        The element, with no ``tail``.

    Raises:
        ValueError: If the spec is invalid (see :func:`_validate`); an unknown
            type or a bad default raises ``LayoutError``, ``KeyError``,
            ``TypeError`` or ``ValueError``.
    """
    _validate(spec)
    types: Any = registry if registry is not None else _NoTypes()
    present = {r.name for r in spec.routines}
    meta = dict(spec.metadata or {})
    root = ET.Element("AddOnInstructionDefinition")
    root.set("Name", spec.name)
    if "Class" in meta:
        root.set("Class", meta.pop("Class"))
    root.set("Revision", spec.revision)
    if spec.vendor:
        root.set("Vendor", spec.vendor)
    root.set("ExecutePrescan", _flag(spec.execute_prescan, "Prescan" in present))
    root.set("ExecutePostscan", _flag(spec.execute_postscan, "Postscan" in present))
    root.set(
        "ExecuteEnableInFalse",
        _flag(spec.execute_enable_in_false, "EnableInFalse" in present),
    )
    for key in _METADATA_ORDER[1:]:
        if key in meta:
            root.set(key, meta.pop(key))
    for key, value in meta.items():
        root.set(key, value)

    parameters = [
        _enable_parameter(
            "EnableIn", "Input", "Enable Input - System Defined Parameter"
        ),
        _enable_parameter(
            "EnableOut", "Output", "Enable Output - System Defined Parameter"
        ),
        *[_parameter(p, types) for p in spec.parameters],
    ]
    dependencies: list[ET.Element] = []
    seen: set[str] = set()
    for item in [*spec.parameters, *spec.local_tags]:
        kind = _dependency_type(item.data_type, registry)
        if kind is not None and item.data_type not in seen:
            seen.add(item.data_type)
            dependency = ET.Element("Dependency")
            dependency.set("Type", kind)
            dependency.set("Name", item.data_type)
            dependencies.append(dependency)

    children: list[ET.Element] = []
    if spec.description:
        children.append(new_cdata_element("Description", spec.description))
    if spec.revision_note:
        children.append(new_cdata_element("RevisionNote", spec.revision_note))
    if spec.additional_help_text:
        children.append(
            new_cdata_element("AdditionalHelpText", spec.additional_help_text)
        )
    children.append(_fill(ET.Element("Parameters"), parameters))
    children.append(
        _fill(ET.Element("LocalTags"), [_local_tag(t, types) for t in spec.local_tags])
    )
    children.append(
        _fill(
            ET.Element("Routines"),
            [_routine(r) for r in sorted(spec.routines, key=lambda r: r.name)],
        )
    )
    if dependencies:
        children.append(_fill(ET.Element("Dependencies"), dependencies))
    return _fill(root, children)

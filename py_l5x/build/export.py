"""Component export: a standalone import file for a target and its context.

``export_component`` builds an in-memory :class:`~py_l5x.parsers.project.Project`
shaped like Studio 5000's own component exports (``ContainsContext="true"``):

- Root ``<RSLogix5000Content SchemaRevision SoftwareRevision TargetName
  TargetType [TargetSubType] [TargetRevision TargetLastEdited] [TargetCount]
  ContainsContext>``. Rung exports have no ``TargetName`` (``TargetCount``
  instead); with several targets ``TargetName`` is the first one and
  ``TargetCount`` is added. Optional Studio-only attributes (``ExportDate``,
  ``ExportOptions``, ...) are left out.
- ``<Controller Use="Context" Name=..>`` with containers marked
  ``Use="Context"`` in schema order. Target elements carry ``Use="Target"`` as
  their first attribute; context elements carry no ``Use`` (modules carry
  ``Use="Reference"``; the program and routine that hold a routine or rung
  target carry ``Use="Context"``).
- ``DataTypes`` is always present (empty if need be); ``Modules`` and
  ``AddOnInstructionDefinitions`` only when they have entries; the
  controller-level ``Tags`` also for Program targets (empty if need be).
- Order: UDT targets first, then context UDTs in project order; AOIs
  (targets and context) in project order, which puts dependencies first (new
  spec targets go last); tags and modules in project order.
- Every UDT and AOI in the file has ``<Dependencies>`` (Studio fails without):
  loaded types are copied and get them if missing, spec types are built by the
  builders. Product-defined types (``TIMER``, ...) are not written.

**Context** is the dependency closure of the targets:

- UDTs and AOIs reachable through tag types, UDT members, AOI parameters
  (any usage) and AOI local tags, transitively, plus every AOI *called* in the
  targets' logic (matched like ``AOICollection.call_sites``).
- For Program, Routine and Rung targets, the tags the logic refers to, found
  by tokenizing rung text and ST (string literals and ST comments skipped; an
  operand's base name is its first identifier, up to ``.`` or ``[``; names
  followed by ``(`` are instructions and are skipped). Only names that resolve
  to an existing tag count (program scope first, then controller), so
  instruction, routine and label names drop out. Alias tags bring their
  target. Controller tags go under ``Tags``; program tags of a Routine or Rung
  export under ``Programs/Program/Tags``. ``\\\\Program.Tag`` cross-program
  references are ignored.
- Modules (``Use="Reference"``) for module I/O tags (``Name:1:I...``) that the
  logic or aliases refer to.

An unresolvable tag, member or parameter *type* raises ``ValueError`` (Studio
silently accepts unknown member types). Unknown tag names in logic are not an
error. Specs need a project to resolve project types; without one only atomic
and built-in types may be used.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from typing import Any
from xml.etree import ElementTree as ET

from py_l5x.build.aoi import _NoTypes, build_aoi
from py_l5x.build.datatype import _dependency_type, _fill, build_datatype
from py_l5x.build.program import build_program
from py_l5x.build.specs import AOISpec, DataTypeSpec, ProgramSpec, TagSpec
from py_l5x.build.tag import build_tag
from py_l5x.parsers.aoi import AOIDefinition, _call_pattern, _mask
from py_l5x.parsers.atomic_types import ATOMIC_TYPES
from py_l5x.parsers.datatype import DataType
from py_l5x.parsers.layout import builtin_table
from py_l5x.parsers.migrate import _raw_cdata
from py_l5x.parsers.program import Program
from py_l5x.parsers.project import Project
from py_l5x.parsers.routine import Routine, Rung
from py_l5x.parsers.tag import Tag

_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_.#$\\])"
    r"([A-Za-z_][A-Za-z0-9_]*(?::[A-Za-z0-9_]+)*)"
    r"(?!\s*\()(?![A-Za-z0-9_:#])"
)
#: Built-in types with specialty data that the default-value table does not
#: hold (they are never written as context, and need no definition).
_SPECIAL_BUILTINS = frozenset(
    {"MESSAGE", "MOTION_GROUP", "ALARM_ANALOG", "ALARM_DIGITAL", "COORDINATE_SYSTEM"}
    | {"HMIBC"}
)
_SPECIAL_PREFIXES = ("AXIS_", "ENERGY_")
_BASE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?::[A-Za-z0-9_]+)*")

_KINDS: dict[type, str] = {
    DataType: "DataType",
    DataTypeSpec: "DataType",
    AOIDefinition: "AddOnInstructionDefinition",
    AOISpec: "AddOnInstructionDefinition",
    Program: "Program",
    ProgramSpec: "Program",
    Tag: "Tag",
    TagSpec: "Tag",
    Routine: "Routine",
    Rung: "Rung",
}


def referenced_names(text: str, st: bool = False) -> list[str]:
    """Extract the base names of the operands in rung text or ST.

    String literals and (for ST) comments are skipped, as are names followed
    by ``(`` (instructions and calls), members after ``.``, numeric literals
    and radix digits, and ``\\Program.Tag`` cross-program references.

    Args:
        text: Rung text, or ST lines joined by newlines.
        st: Whether *text* is structured text.

    Returns:
        The candidate names in order of appearance (duplicates kept).
    """
    return _TOKEN.findall(_mask(text, st))


def _kind(target: Any) -> str:
    """Return the ``TargetType`` of a target object or spec.

    Args:
        target: A loaded object or a spec.

    Returns:
        The target type.

    Raises:
        TypeError: If the object cannot be exported.
    """
    for cls, kind in _KINDS.items():
        if isinstance(target, cls):
            return kind
    raise TypeError(f"cannot export a {type(target).__name__}")


def _with_use(element: ET.Element, use: str) -> ET.Element:
    """Put ``Use`` first among an element's attributes.

    Args:
        element: The element, modified in place.
        use: The ``Use`` value.

    Returns:
        *element*.
    """
    items = [(k, v) for k, v in element.attrib.items() if k != "Use"]
    element.attrib.clear()
    element.set("Use", use)
    for key, value in items:
        element.set(key, value)
    return element


def _container(tag: str, children: Iterable[ET.Element]) -> ET.Element:
    """Create a ``Use="Context"`` container holding *children*.

    Args:
        tag: The container tag.
        children: The child elements (an empty container gets a newline).

    Returns:
        The container.
    """
    container = ET.Element(tag)
    container.set("Use", "Context")
    items = list(children)
    if items:
        return _fill(container, items)
    container.text = "\n"
    return container


class _Resolver:
    """Resolves types and tags against a project, or against nothing.

    Args:
        project: The source project, or ``None`` (atomic and built-in types
            only).
    """

    def __init__(self, project: Project | None) -> None:
        """Index the project's types, tags and modules.

        Args:
            project: The source project, or ``None``.
        """
        self.project = project
        self.registry: Any = project._type_registry if project else _NoTypes()
        controller = project.controller_element if project else None
        self.controller = controller
        self.controller_tags: dict[str, ET.Element] = {}
        self.modules: dict[str, ET.Element] = {}
        self.module_prefixes: dict[str, str] = {}
        self.udt_order: list[str] = []
        self.aoi_order: list[str] = []
        if controller is not None:
            for tag in controller.findall("Tags/Tag"):
                self.controller_tags[tag.get("Name", "").lower()] = tag
            for module in controller.findall("Modules/Module"):
                self.modules[module.get("Name", "").lower()] = module
            for name, wrapper in project.modules.items():
                self.module_prefixes[wrapper.tag_prefix.lower()] = name
            self.udt_order = [
                e.get("Name", "") for e in controller.findall("DataTypes/DataType")
            ]
            self.aoi_order = [
                e.get("Name", "")
                for e in controller.findall(
                    "AddOnInstructionDefinitions/AddOnInstructionDefinition"
                )
            ]

    def module_chain(self, base: str) -> set[str]:
        """Find the modules a module I/O tag name refers to.

        ``Local:1:I`` is addressed through the module whose tag prefix is
        ``Local:1``; its parent modules (``ParentModule``) are included.

        Args:
            base: A tag base name (``Name:slot:suffix`` style).

        Returns:
            Lower-cased module names (empty if *base* is no module tag).
        """
        found: set[str] = set()
        if ":" not in base:
            return found
        name = self.module_prefixes.get(base.rsplit(":", 1)[0].lower())
        while name is not None and name.lower() not in found:
            found.add(name.lower())
            element = self.modules.get(name.lower())
            parent = element.get("ParentModule") if element is not None else None
            name = parent if parent else None
        return found

    def udt_element(self, name: str) -> ET.Element:
        """Return a project UDT element.

        Args:
            name: The UDT name.

        Returns:
            The element.
        """
        assert self.controller is not None
        for element in self.controller.findall("DataTypes/DataType"):
            if element.get("Name") == name:
                return element
        raise KeyError(name)

    def aoi_element(self, name: str) -> ET.Element:
        """Return a project AOI element.

        Args:
            name: The AOI name.

        Returns:
            The element.
        """
        assert self.controller is not None
        for element in self.controller.findall(
            "AddOnInstructionDefinitions/AddOnInstructionDefinition"
        ):
            if element.get("Name") == name:
                return element
        raise KeyError(name)

    def classify(self, name: str) -> str | None:
        """Classify a type name.

        Args:
            name: The type name.

        Returns:
            ``"udt"``, ``"aoi"``, or ``None`` for atomic and built-in types.

        Raises:
            ValueError: If the type cannot be resolved.
        """
        if (
            name in ATOMIC_TYPES
            or name in builtin_table()
            or name in _SPECIAL_BUILTINS
            or name.startswith(_SPECIAL_PREFIXES)
        ):
            return None
        if self.registry.aoi(name) is not None:
            return "aoi"
        udt = self.registry.udt(name)
        if udt is not None:
            return None if udt.class_ == "ProductDefined" else "udt"
        raise ValueError(f"unresolvable data type {name!r}")

    def closure(
        self, types: Iterable[str], called: Iterable[str]
    ) -> tuple[set[str], set[str]]:
        """Compute the UDTs and AOIs reachable from types and AOI calls.

        Args:
            types: Type names to start from.
            called: AOI names called in logic.

        Returns:
            ``(udt names, aoi names)``.

        Raises:
            ValueError: If a type cannot be resolved.
        """
        udts: set[str] = set()
        aois: set[str] = set(called)
        pending = list(types) + list(called)
        seen: set[str] = set()
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            kind = self.classify(name)
            if kind == "udt":
                udts.add(name)
                pending.extend(
                    m.get("DataType", "")
                    for m in self.udt_element(name).findall("Members/Member")
                    if m.get("DataType") != "BIT"
                )
            elif kind == "aoi":
                aois.add(name)
                element = self.aoi_element(name)
                pending.extend(
                    item.get("DataType", "")
                    for item in [
                        *element.findall("Parameters/Parameter"),
                        *element.findall("LocalTags/LocalTag"),
                    ]
                )
        return udts, aois

    def called_aois(self, logic: list[tuple[str, bool]]) -> set[str]:
        """Find the project AOIs called in logic.

        Args:
            logic: ``(text, is_st)`` pairs.

        Returns:
            The names of AOIs with at least one call.
        """
        found: set[str] = set()
        masked = [_mask(text, st) for text, st in logic]
        for name in self.aoi_order:
            pattern = _call_pattern(name)
            if any(pattern.search(m) for m in masked):
                found.add(name)
        return found


def _dependencies(element: ET.Element, resolver: _Resolver, aoi: bool) -> None:
    """Add ``<Dependencies>`` to a loaded UDT or AOI element if it has none.

    A UDT lists one entry per member of a user UDT or AOI type; an AOI lists
    each such type once, parameters first, then local tags.

    Args:
        element: The copied ``<DataType>`` or ``<AddOnInstructionDefinition>``.
        resolver: The resolver (decides UDT versus AOI).
        aoi: Whether *element* is an AOI.
    """
    if element.find("Dependencies") is not None:
        return
    if aoi:
        items = [
            *element.findall("Parameters/Parameter"),
            *element.findall("LocalTags/LocalTag"),
        ]
    else:
        items = element.findall("Members/Member")
    entries: list[ET.Element] = []
    seen: set[str] = set()
    for item in items:
        type_name = item.get("DataType", "")
        kind = (
            None
            if type_name == "BIT"
            else _dependency_type(type_name, resolver.registry)
        )
        if kind is None or (aoi and type_name in seen):
            continue
        seen.add(type_name)
        entry = ET.Element("Dependency")
        entry.set("Type", kind)
        entry.set("Name", type_name)
        entries.append(entry)
    if entries:
        container = _fill(ET.Element("Dependencies"), entries)
        container.tail = "\n"
        if len(element):
            element[-1].tail = "\n"
        else:
            element.text = "\n"
        element.append(container)


def _target_copy(element: ET.Element) -> ET.Element:
    """Copy a loaded element for use as a target.

    Args:
        element: The loaded element.

    Returns:
        A deep copy marked ``Use="Target"`` with a ``"\\n"`` tail.
    """
    copy_ = copy.deepcopy(element)
    copy_.tail = "\n"
    return _with_use(copy_, "Target")


def _logic_of(routine: ET.Element, only: list[ET.Element] | None = None):
    """Collect the rung texts and ST lines of a routine element.

    Args:
        routine: A ``<Routine>``.
        only: If given, only these rungs.

    Returns:
        ``(text, is_st)`` pairs (ST lines are joined into one entry).
    """
    out: list[tuple[str, bool]] = []
    for rung in only if only is not None else routine.findall("RLLContent/Rung"):
        text = rung.find("Text")
        if text is not None:
            out.append((_raw_cdata(text), False))
    lines = routine.findall("STContent/Line")
    if lines and only is None:
        out.append(("\n".join(_raw_cdata(line) for line in lines), True))
    return out


def _logic_of_spec_routines(routines: Iterable[Any]) -> list[tuple[str, bool]]:
    """Collect the logic texts of routine specs.

    Args:
        routines: ``RoutineSpec`` objects.

    Returns:
        ``(text, is_st)`` pairs.
    """
    out: list[tuple[str, bool]] = []
    for routine in routines:
        out.extend((rung.text, False) for rung in routine.rungs)
        if routine.lines:
            out.append(("\n".join(routine.lines), True))
    return out


class _Collected:
    """What the targets contribute to the file.

    Attributes:
        elements: The target elements (``Use="Target"``).
        types: Type names to resolve.
        logic: ``(text, is_st)`` pairs of the targets' logic.
        scope: The program name for program-scope tags, routines and rungs.
        routine: The routine name for Rung targets.
        own_tags: Program tags of a Program/Routine/Rung target (lower name to
            element), searched before controller tags.
        alias_targets: Alias target names of the targets' own tags.
    """

    def __init__(self) -> None:
        """Start empty."""
        self.elements: list[ET.Element] = []
        self.types: list[str] = []
        self.logic: list[tuple[str, bool]] = []
        self.scope: str | None = None
        self.routine: str | None = None
        self.own_tags: dict[str, ET.Element] = {}
        self.aliases: list[str] = []
        self.first_name: str | None = None
        self.revision: str | None = None
        self.last_edited: str | None = None
        self.sub_type: str | None = None
        self.called: set[str] = set()


def _ancestors(project: Project, element: ET.Element) -> list[ET.Element]:
    """Return the chain of ancestors of an element inside the project.

    Args:
        project: The project.
        element: An element of ``project.root``.

    Returns:
        Ancestors from the root down to the parent.

    Raises:
        ValueError: If the element is not part of the project.
    """
    parents = {child: parent for parent in project.root.iter() for child in parent}
    chain: list[ET.Element] = []
    node = element
    while node in parents:
        node = parents[node]
        chain.append(node)
    if not chain or chain[-1] is not project.root:
        raise ValueError("object is not part of the given project")
    return chain[::-1]


def _alias_base(target: str | None) -> str | None:
    """Return the base tag name of an ``AliasFor`` path.

    Args:
        target: The alias path.

    Returns:
        The first identifier (module-style names keep their colons).
    """
    match = _BASE.match(target or "")
    return match.group(0) if match else None


def export_component(
    targets: Any,
    project: Project | None = None,
    *,
    controller_name: str | None = None,
) -> Project:
    """Build a component export for one or more targets of one kind.

    See the module docstring for the file shape and the dependency closure.
    Loaded objects (``DataType``, ``AOIDefinition``, ``Program``, ``Tag``,
    ``Routine``, ``Rung``) must come from *project*: their parents are found by
    walking ``project.root``, since wrappers hold only their own element.
    Specs (``DataTypeSpec``, ``AOISpec``, ``ProgramSpec``, ``TagSpec``) use
    *project* to resolve the types they reference; a ``TagSpec`` is exported as
    a controller tag. A ``Routine`` or ``Rung`` must belong to a program (an
    AOI's routines are exported with the AOI).

    Args:
        targets: One object or a list of objects, all of one kind.
        project: The project the targets and their context come from.
        controller_name: Name of the ``<Controller>``; defaults to the
            project's, else ``"Exported"``.

    Returns:
        A new in-memory project; write it with ``.write(path)``.

    Raises:
        ValueError: If there are no targets, the kinds are mixed, an object is
            not in *project*, loaded objects are given without a project, or a
            type cannot be resolved.
        TypeError: If an object cannot be exported.
    """
    items = list(targets) if isinstance(targets, list | tuple) else [targets]
    if not items:
        raise ValueError("no targets to export")
    kinds = {_kind(item) for item in items}
    if len(kinds) > 1:
        raise ValueError(f"targets must be of one kind, not {sorted(kinds)}")
    kind = kinds.pop()
    loaded = [
        item
        for item in items
        if isinstance(item, DataType | AOIDefinition | Program | Tag | Routine | Rung)
    ]
    if loaded and project is None:
        raise ValueError("loaded objects need the project they come from")
    resolver = _Resolver(project)
    collected = _Collected()
    _collect(kind, items, project, resolver, collected)
    return _assemble(kind, items, project, resolver, collected, controller_name)


def _collect(
    kind: str,
    items: list[Any],
    project: Project | None,
    resolver: _Resolver,
    out: _Collected,
) -> None:
    """Gather target elements, types, logic and scope for one kind.

    Args:
        kind: The target type.
        items: The targets.
        project: The project, or ``None``.
        resolver: The resolver.
        out: The accumulator.

    Raises:
        ValueError: If targets of one kind disagree on their scope, or an
            object is not in the project.
    """
    registry = resolver.registry
    if kind == "DataType":
        for item in items:
            if isinstance(item, DataTypeSpec):
                element = _with_use(build_datatype(item, registry), "Target")
                element.tail = "\n"
                out.types.extend(m.data_type for m in item.members)
                out.first_name = out.first_name or item.name
            else:
                _ancestors(project, item._element)
                element = _target_copy(item._element)
                _dependencies(element, resolver, aoi=False)
                out.types.extend(
                    m.get("DataType", "")
                    for m in element.findall("Members/Member")
                    if m.get("DataType") != "BIT"
                )
                out.first_name = out.first_name or item.name
            out.elements.append(element)
    elif kind == "AddOnInstructionDefinition":
        for item in items:
            if isinstance(item, AOISpec):
                element = _with_use(build_aoi(item, registry), "Target")
                element.tail = "\n"
                out.types.extend(
                    p.data_type for p in [*item.parameters, *item.local_tags]
                )
                out.logic.extend(_logic_of_spec_routines(item.routines))
                out.first_name = out.first_name or item.name
                out.revision = out.revision or item.revision
            else:
                _ancestors(project, item._element)
                element = _target_copy(item._element)
                _dependencies(element, resolver, aoi=True)
                out.types.extend(
                    i.get("DataType", "")
                    for i in [
                        *element.findall("Parameters/Parameter"),
                        *element.findall("LocalTags/LocalTag"),
                    ]
                )
                for routine in element.findall("Routines/Routine"):
                    out.logic.extend(_logic_of(routine))
                out.first_name = out.first_name or item.name
                out.revision = out.revision or element.get("Revision")
                out.last_edited = out.last_edited or element.get("EditedDate")
            out.elements.append(element)
    elif kind == "Program":
        if len(items) > 1:
            raise ValueError("export programs one at a time")
        item = items[0]
        if isinstance(item, ProgramSpec):
            element = _with_use(build_program(item, registry), "Target")
            out.first_name = item.name
            for routine in element.findall("Routines/Routine"):
                out.logic.extend(_logic_of(routine))
        else:
            _ancestors(project, item._element)
            element = _target_copy(item._element)
            out.first_name = item.name
            for routine in element.findall("Routines/Routine"):
                out.logic.extend(_logic_of(routine))
        element.tail = "\n"
        out.elements.append(element)
        out.scope = out.first_name
        for tag in element.findall("Tags/Tag"):
            out.own_tags[tag.get("Name", "").lower()] = tag
            out.types.append(tag.get("DataType", "")) if tag.get("DataType") else None
            out.aliases.append(tag.get("AliasFor", ""))
    elif kind in ("Routine", "Rung"):
        _collect_routine(kind, items, project, out)
    else:
        _collect_tags(items, project, resolver, out)
    out.types = [t for t in out.types if t]
    out.called = resolver.called_aois(out.logic)


def _program_of(project: Project, element: ET.Element) -> ET.Element:
    """Return the ``<Program>`` that holds a routine or rung element.

    Args:
        project: The project.
        element: A ``<Routine>`` or ``<Rung>``.

    Returns:
        The program element.

    Raises:
        ValueError: If the object is not in the project, or belongs to an AOI.
    """
    chain = _ancestors(project, element)
    for ancestor in reversed(chain):
        if ancestor.tag == "Program":
            return ancestor
        if ancestor.tag == "AddOnInstructionDefinition":
            raise ValueError("AOI routines are exported with the AOI")
    raise ValueError("routine is not in a program")


def _collect_routine(
    kind: str, items: list[Any], project: Project, out: _Collected
) -> None:
    """Gather the elements and scope of Routine or Rung targets.

    Args:
        kind: ``"Routine"`` or ``"Rung"``.
        items: The targets.
        project: The project.
        out: The accumulator.

    Raises:
        ValueError: If the targets do not share one program (and routine).
    """
    programs = set()
    routines = set()
    for item in items:
        program = _program_of(project, item._element)
        programs.add(id(program))
        if kind == "Routine":
            routines.add(id(item._element))
        else:
            chain = _ancestors(project, item._element)
            routines.add(
                id(chain[-2]) if chain[-1].tag == "RLLContent" else id(chain[-1])
            )
    if len(programs) != 1:
        raise ValueError("targets must belong to one program")
    program = _program_of(project, items[0]._element)
    out.scope = program.get("Name")
    for tag in program.findall("Tags/Tag"):
        out.own_tags[tag.get("Name", "").lower()] = tag
    if kind == "Routine":
        for item in items:
            element = _target_copy(item._element)
            out.elements.append(element)
            out.logic.extend(_logic_of(element))
            out.first_name = out.first_name or item.name
            out.sub_type = out.sub_type or item.type_
        return
    if len(routines) != 1:
        raise ValueError("rungs must belong to one routine")
    chain = _ancestors(project, items[0]._element)
    routine = next(a for a in reversed(chain) if a.tag == "Routine")
    out.routine = routine.get("Name")
    for item in items:
        element = _target_copy(item._element)
        out.elements.append(element)
        text = element.find("Text")
        if text is not None:
            out.logic.append((_raw_cdata(text), False))


def _collect_tags(
    items: list[Any], project: Project | None, resolver: _Resolver, out: _Collected
) -> None:
    """Gather the elements and scope of Tag targets.

    Args:
        items: ``Tag`` or ``TagSpec`` objects.
        project: The project, or ``None``.
        resolver: The resolver.
        out: The accumulator.

    Raises:
        ValueError: If the tags are not all in one scope.
    """
    scopes = set()
    for item in items:
        if isinstance(item, TagSpec):
            element = build_tag(item, resolver.registry)
            scopes.add(None)
        else:
            chain = _ancestors(project, item._element)
            owner = chain[-2] if chain[-1].tag == "Tags" else chain[-1]
            scopes.add(owner.get("Name") if owner.tag == "Program" else None)
            element = copy.deepcopy(item._element)
        element.tail = "\n"
        out.elements.append(_with_use(element, "Target"))
        out.first_name = out.first_name or item.name
        if element.get("DataType"):
            out.types.append(element.get("DataType", ""))
        out.aliases.append(element.get("AliasFor", ""))
    if len(scopes) != 1:
        raise ValueError("tags must all be controller tags or in one program")
    out.scope = scopes.pop()
    if out.scope is not None:
        assert project is not None
        program = next(
            p
            for p in project.controller_element.findall("Programs/Program")
            if p.get("Name") == out.scope
        )
        for tag in program.findall("Tags/Tag"):
            out.own_tags[tag.get("Name", "").lower()] = tag


def _assemble(
    kind: str,
    items: list[Any],
    project: Project | None,
    resolver: _Resolver,
    out: _Collected,
    controller_name: str | None,
) -> Project:
    """Resolve the context and build the export project.

    Args:
        kind: The target type.
        items: The targets.
        project: The project, or ``None``.
        resolver: The resolver.
        out: What the targets contribute.
        controller_name: Controller name override.

    Returns:
        The new project.
    """
    target_names = {e.get("Name", "").lower() for e in out.elements}
    controller_tags = resolver.controller_tags
    program_scope = kind in ("Program", "Routine", "Rung") or out.scope is not None

    # Referenced tags: program scope first, then controller scope; aliases
    # bring their targets.
    names: list[str] = []
    for text, st in out.logic:
        names.extend(referenced_names(text, st))
    context_program: dict[str, ET.Element] = {}
    context_controller: dict[str, ET.Element] = {}
    module_names: set[str] = set()
    queue = [n for n in names] + [
        b for a in out.aliases if (b := _alias_base(a)) is not None
    ]
    seen: set[str] = set()
    while queue:
        name = queue.pop()
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        module_names |= resolver.module_chain(lowered)
        tag = out.own_tags.get(lowered) if program_scope else None
        scope_is_program = tag is not None
        if tag is None:
            tag = controller_tags.get(lowered)
        if tag is None or lowered in target_names and kind in ("Tag",):
            continue
        if scope_is_program:
            if kind in ("Routine", "Rung"):
                context_program[lowered] = tag
        else:
            context_controller[lowered] = tag
        if tag.get("DataType"):
            out.types.append(tag.get("DataType", ""))
        alias = _alias_base(tag.get("AliasFor"))
        if alias:
            queue.append(alias)

    if kind == "Tag":
        # Alias targets of the exported tags live in the same scope.
        for lowered in list(context_controller):
            if lowered in target_names:
                del context_controller[lowered]

    udts, aois = resolver.closure(out.types, out.called)

    def udt_elements() -> list[ET.Element]:
        target_udts = [e for e in out.elements] if kind == "DataType" else []
        names_t = {e.get("Name") for e in target_udts}
        context = []
        for name in resolver.udt_order:
            if name in udts and name not in names_t:
                element = copy.deepcopy(resolver.udt_element(name))
                element.tail = "\n"
                element.attrib.pop("Use", None)
                _dependencies(element, resolver, aoi=False)
                context.append(element)
        return [*target_udts, *context]

    def aoi_elements() -> list[ET.Element]:
        target_aois = (
            {e.get("Name"): e for e in out.elements}
            if (kind == "AddOnInstructionDefinition")
            else {}
        )
        ordered: list[ET.Element] = []
        for name in resolver.aoi_order:
            if name in target_aois and project is not None:
                loaded = [
                    t for t in items if isinstance(t, AOIDefinition) and t.name == name
                ]
                if loaded:
                    ordered.append(target_aois.pop(name))
                    continue
            if name in aois and name not in target_aois:
                element = copy.deepcopy(resolver.aoi_element(name))
                element.tail = "\n"
                element.attrib.pop("Use", None)
                _dependencies(element, resolver, aoi=True)
                ordered.append(element)
        ordered.extend(target_aois.values())
        return ordered

    controller = ET.Element("Controller")
    controller.set("Use", "Context")
    controller.set(
        "Name",
        controller_name
        or (project.controller.name if project is not None else None)
        or "Exported",
    )
    children: list[ET.Element] = [_container("DataTypes", udt_elements())]
    modules = []
    for name_key, module in resolver.modules.items():
        if name_key in module_names:
            ref = ET.Element("Module")
            ref.set("Use", "Reference")
            ref.set("Name", module.get("Name", ""))
            ref.text = "\n"
            modules.append(ref)
    if modules:
        children.append(_container("Modules", modules))
    aoi_list = aoi_elements()
    if aoi_list:
        children.append(_container("AddOnInstructionDefinitions", aoi_list))

    controller_context = [
        _plain_copy(t)
        for key, t in controller_tags.items()
        if key in context_controller
    ]
    if kind == "Tag" and out.scope is None:
        controller_context = _merge_by_order(controller_context, out.elements, resolver)
    if controller_context or kind == "Program":
        children.append(_container("Tags", controller_context))

    if kind == "Program":
        children.append(_container("Programs", out.elements))
    elif kind in ("Routine", "Rung") or (kind == "Tag" and out.scope is not None):
        program = ET.Element("Program")
        program.set("Use", "Context")
        program.set("Name", out.scope or "")
        parts: list[ET.Element] = []
        if kind == "Tag":
            tag_context = _scope_tag_context(resolver, project, out, context_program)
            parts.append(_container("Tags", tag_context))
        else:
            if context_program:
                ordered_tags = [
                    _plain_copy(t)
                    for key, t in out.own_tags.items()
                    if key in context_program
                ]
                parts.append(_container("Tags", ordered_tags))
            if kind == "Routine":
                parts.append(_container("Routines", out.elements))
            else:
                routine = ET.Element("Routine")
                routine.set("Use", "Context")
                routine.set("Name", out.routine or "")
                content = _container("RLLContent", out.elements)
                _fill(routine, [content])
                parts.append(_container("Routines", [routine]))
        _fill(program, parts)
        children.append(_container("Programs", [program]))
    _fill(controller, children)

    root = ET.Element("RSLogix5000Content")
    root.set("SchemaRevision", "1.0")
    root.set(
        "SoftwareRevision",
        (project.root.get("SoftwareRevision") if project is not None else None)
        or "37.00",
    )
    if kind != "Rung" and out.first_name:
        root.set("TargetName", out.first_name)
    root.set("TargetType", kind)
    if kind == "Routine" and out.sub_type:
        root.set("TargetSubType", out.sub_type)
    if kind == "AddOnInstructionDefinition":
        if out.revision:
            root.set("TargetRevision", out.revision)
        if out.last_edited:
            root.set("TargetLastEdited", out.last_edited)
    if kind == "Rung" or len(out.elements) > 1:
        root.set("TargetCount", str(len(out.elements)))
    root.set("ContainsContext", "true")
    root.text = "\n"
    controller.tail = "\n"
    root.append(controller)
    return Project(root)


def _plain_copy(element: ET.Element) -> ET.Element:
    """Copy a context tag without any ``Use`` attribute.

    Args:
        element: The loaded ``<Tag>``.

    Returns:
        The copy, with a ``"\\n"`` tail.
    """
    copy_ = copy.deepcopy(element)
    copy_.tail = "\n"
    copy_.attrib.pop("Use", None)
    return copy_


def _scope_tag_context(
    resolver: _Resolver,
    project: Project | None,
    out: _Collected,
    context_program: dict[str, ET.Element],
) -> list[ET.Element]:
    """Order program-scope tags for a Tag export: targets among context tags.

    Args:
        resolver: The resolver.
        project: The project.
        out: What the targets contribute.
        context_program: Referenced program tags by lower name.

    Returns:
        Context tag copies and the target elements, in project order (targets
        and alias targets); targets of other scopes cannot occur.
    """
    targets = {e.get("Name", "").lower(): e for e in out.elements}
    alias_context = _alias_closure(out, targets)
    ordered: list[ET.Element] = []
    for key, tag in out.own_tags.items():
        if key in targets:
            ordered.append(targets[key])
        elif key in alias_context:
            ordered.append(_plain_copy(tag))
    return ordered


def _alias_closure(out: _Collected, targets: dict[str, ET.Element]) -> set[str]:
    """Collect the program tags that alias targets of the exported tags need.

    Args:
        out: What the targets contribute.
        targets: The exported tags by lower name.

    Returns:
        Lower names of the context program tags.
    """
    needed: set[str] = set()
    queue = [_alias_base(e.get("AliasFor")) for e in targets.values()]
    while queue:
        name = queue.pop()
        if not name or name.lower() in needed or name.lower() in targets:
            continue
        tag = out.own_tags.get(name.lower())
        if tag is None:
            continue
        needed.add(name.lower())
        queue.append(_alias_base(tag.get("AliasFor")))
    return needed


def _merge_by_order(
    context: list[ET.Element], targets: list[ET.Element], resolver: _Resolver
) -> list[ET.Element]:
    """Place controller target tags among context tags in project order.

    Args:
        context: Context tag copies.
        targets: The exported ``Use="Target"`` tags.
        resolver: The resolver.

    Returns:
        All tags, ordered like the project's controller tags (spec targets
        not in the project last).
    """
    by_name = {e.get("Name", "").lower(): e for e in [*context, *targets]}
    ordered = [by_name.pop(k) for k in resolver.controller_tags if k in by_name]
    ordered.extend(by_name.values())
    return ordered

"""Top-level Project container for L5X files.

This module provides the ``Project`` class, which serves as the root object
for a parsed L5X file.  It loads the XML tree, builds a shared
``TypeRegistry`` for UDT/AOI metadata cross-referencing, and exposes all
child parsers as typed properties in a hierarchical structure:

    Project
    ├── controller       → ControllerInfo
    ├── data_types       → DataTypesCollection
    ├── aois             → AOICollection
    ├── modules          → ModulesCollection
    ├── tags             → ProjectTagsView (merged: controller tags + module I/O tags)
    ├── programs         → ProgramsCollection
    │   └── tags         → TagsCollection (per-program)
    │   └── routines     → RoutinesCollection (per-program)
    └── tasks            → TasksCollection
        └── programs     → Mapping[str, Program] (per-task)

``project.tags`` merges the controller's own tags with each module's I/O tags
(their Studio 5000 global-variable names), so ``project.tags["ValveBank:I"]``
and ``project.tags["Local:1:C"]`` resolve alongside ordinary controller tags.

Usage:
    >>> from py_l5x import load
    >>> project = load("my_project.L5X")
    >>> print(project.controller.name)
    MyController
    >>> for task in project.tasks.values():
    ...     for prog in task.programs.values():
    ...         print(prog.name, list(prog.tags))
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Union
from xml.etree import ElementTree as ET

from py_l5x.parsers.aoi import AOICollection, AOIDefinition
from py_l5x.parsers.controller import ControllerInfo
from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.module import Module, ModulesCollection, ModuleTagRef
from py_l5x.parsers.program import Program, ProgramsCollection
from py_l5x.parsers.routine import Routine, Rung
from py_l5x.parsers.tag import Tag, TagsCollection, TypeRegistry
from py_l5x.parsers.task import TasksCollection

if TYPE_CHECKING:
    from py_l5x.parsers.datatype import DataType

# Union of all possible target types returned by ``Project.target``.
_TargetObject = Union[
    "DataType",
    AOIDefinition,
    Module,
    Program,
    Routine,
    Rung,
    Tag,
]


class ProjectTagsView(Mapping[str, Tag | ModuleTagRef]):
    """Merged view of controller tags and module I/O tags by global name.

    In Studio 5000 a module's communication tags surface as *global variables*
    alongside the controller's own tags. This read-only mapping exposes both
    under one ``project.tags`` surface: every controller tag keeps its name, and
    each module I/O tag is added under its Studio 5000 global name (see
    :class:`py_l5x.parsers.module.ModuleTagsView`). The underlying objects are
    the same instances produced by the controller/program tag parsers and the
    per-module tag views, so modules remain the single source of truth for
    module tags.

    Logix tag names cannot contain ``':'`` while every module global name does,
    so a controller tag and a module tag can never share a name. Lookup is
    therefore decided by the presence of ``':'``: names without one are
    controller tags, and names with one are resolved against the module whose
    :attr:`~py_l5x.parsers.module.Module.tag_prefix` matches the part before the
    last ``':'``.

    Values are ``Tag`` instances for controller tags and :class:`ModuleTagRef`
    instances for module I/O tags.

    Args:
        controller_tags (TagsCollection): The controller-level tag collection.
        modules (ModulesCollection): The module collection to merge in.
    """

    def __init__(
        self, controller_tags: TagsCollection, modules: ModulesCollection
    ) -> None:
        """Initialize the merged tag view.

        Args:
            controller_tags: The controller-level tag collection.
            modules: The module collection whose I/O tags are merged in.
        """
        self._controller_tags = controller_tags
        self._modules = modules

    def __getitem__(self, name: str) -> Tag | ModuleTagRef:
        """Get a controller tag or a module I/O tag by name.

        Args:
            name: A controller tag name (no ``':'``) or a module global name
                (``<tag_prefix>:<suffix>``).

        Returns:
            The matching ``Tag`` or :class:`ModuleTagRef`.

        Raises:
            KeyError: If no controller tag or module tag has that name.
        """
        if ":" not in name:
            return self._controller_tags[name]
        prefix, _, _ = name.rpartition(":")
        for module in self._modules.values():
            if module.tag_prefix == prefix:
                return module.tags[name]
        raise KeyError(name)

    def __iter__(self) -> Iterator[str]:
        """Iterate all tag names: controller tags, then module global names.

        Yields:
            Controller tag names first, then each module's global tag names in
            module order.
        """
        yield from self._controller_tags
        for module in self._modules.values():
            yield from module.tags

    def __len__(self) -> int:
        """Return the number of tags in the merged view.

        Returns:
            The controller tag count plus each module's tag count.
        """
        return len(self._controller_tags) + sum(
            len(module.tags) for module in self._modules.values()
        )

    def __repr__(self) -> str:
        """Return a debug-friendly representation of this merged tag view.

        Returns:
            A representation containing the currently visible tag names.
        """
        return f"ProjectTagsView({list(self)!r})"


class Project:
    """Top-level container for a parsed L5X project.

    Loads an L5X file, parses the XML tree, and provides typed access to
    controller metadata, data types, modules, AOIs, tags, programs, and
    tasks through a hierarchical object model.

    Args:
        file_path: Path to the L5X file to load.

    Raises:
        FileNotFoundError: If the file does not exist or cannot be read.
        ValueError: If the file is not a valid L5X XML document or lacks
            a ``<Controller>`` element.

    Example:
        >>> project = Project("examples/example.L5X")
        >>> print(project.controller.name)
        Example_PLC
        >>> list(project.data_types)
        ['A_UDT', 'GenericRobotInputs', ...]
    """

    def __init__(self, root: ET.Element) -> None:
        """Load and parse an L5X xml into a hierarchical project object.

        Args:
            root: The root element of the L5X file.

        Raises:
            ValueError: If the file is not a valid L5X file.
        """
        self._root = root
        controller = self._root.find("Controller")
        if controller is None:
            raise ValueError("No <Controller> element found; not a valid L5X file.")
        self._controller_element = controller

        # Build collections that don't depend on TypeRegistry first.
        self._data_types = DataTypesCollection(self._controller_element)
        self._aoi_types = AddOnDataTypeCollection(self._controller_element)

        # Build the shared TypeRegistry (glue for tag value parsing).
        self._type_registry = TypeRegistry(self._data_types, self._aoi_types)

        # Build collections that depend on TypeRegistry.
        self._controller = ControllerInfo(self._controller_element)
        self._modules = ModulesCollection(self._controller_element, self._type_registry)
        self._aois = AOICollection(self._controller_element, self._type_registry)
        self._tags = TagsCollection(self._controller_element, self._type_registry)
        self._programs = ProgramsCollection(
            self._controller_element, self._type_registry
        )
        self._tasks = TasksCollection(self._controller_element, self._type_registry)

    # ------------------------------------------------------------------
    # Target / export-type introspection
    # ------------------------------------------------------------------

    @property
    def target_type(self) -> str:
        """The ``TargetType`` attribute from ``<RSLogix5000Content>``.

        For full project exports this is ``"Controller"``; for component
        exports it describes the specific exported object, e.g. ``"Program"``,
        ``"Routine"``, ``"DataType"``, ``"AddOnInstructionDefinition"``,
        ``"Module"``, ``"Rung"``, or ``"Tag"``.

        Returns:
            The target type string, or ``""`` if the attribute is absent.
        """
        return self._root.get("TargetType", "")

    @property
    def target_name(self) -> str:
        """The ``TargetName`` attribute from ``<RSLogix5000Content>``.

        Returns:
            The target name string, or ``""`` if the attribute is absent.
        """
        return self._root.get("TargetName", "")

    @property
    def contains_context(self) -> bool:
        """Whether this L5X file is a component export (contains context).

        Full project exports have ``ContainsContext="false"``; component
        exports set this to ``"true"`` and include dependency data.

        Returns:
            ``True`` for component exports; ``False`` for full project exports.
        """
        return self._root.get("ContainsContext", "false").lower() == "true"

    @property
    def target(self) -> _TargetObject | None:
        """The specific object marked ``Use="Target"`` in a component export.

        For component exports, Studio 5000 marks exactly one child element
        with ``Use="Target"``; all other elements are context/dependencies.
        This property locates that element and returns the appropriate typed
        wrapper by dispatching on :attr:`target_type`:

        * ``"DataType"`` → :class:`~py_l5x.parsers.datatype.DataType`
        * ``"AddOnInstructionDefinition"`` → :class:`~py_l5x.parsers.aoi.AOIDefinition`
        * ``"Module"`` → :class:`~py_l5x.parsers.module.Module`
        * ``"Program"`` → :class:`~py_l5x.parsers.program.Program`
        * ``"Routine"`` → :class:`~py_l5x.parsers.routine.Routine`
        * ``"Rung"`` → :class:`~py_l5x.parsers.routine.Rung`
        * ``"Tag"`` → :class:`~py_l5x.parsers.tag.Tag`

        For a full project export (``TargetType="Controller"``) there is no
        component target, so ``None`` is returned.  ``None`` is also returned
        if the target cannot be located (unexpected ``TargetType`` value or
        missing element).

        Returns:
            The typed target object, or ``None`` for full-project exports or
            unknown target types.
        """
        tt = self.target_type
        name = self.target_name

        if tt == "DataType":
            try:
                return self._data_types[name]
            except KeyError:
                return None

        if tt == "AddOnInstructionDefinition":
            try:
                return self._aois[name]
            except KeyError:
                return None

        if tt == "Module":
            try:
                return self._modules[name]
            except KeyError:
                return None

        if tt == "Program":
            try:
                return self._programs[name]
            except KeyError:
                return None

        if tt == "Routine":
            # Walk all programs (including context programs) to find the one
            # whose routine carries Use="Target".
            for prog in self._programs.values():
                try:
                    routine = prog.routines[name]
                    if routine.use == "Target":
                        return routine
                except KeyError:
                    continue
            return None

        if tt == "Rung":
            # The target rung lives inside the target routine, which lives
            # inside the target program.  Walk programs → routines until we
            # find a rung marked Use="Target".
            for prog in self._programs.values():
                for routine in prog.routines.values():
                    rung = routine.target_rung
                    if rung is not None:
                        return rung
            return None

        if tt == "Tag":
            # Try controller-level tags first, then program-local tags.
            try:
                return self._tags[name]
            except KeyError:
                pass
            for prog in self._programs.values():
                try:
                    return prog.tags[name]
                except KeyError:
                    continue
            return None

        # "Controller" (full project) or unknown TargetType → no component target.
        return None

    # ------------------------------------------------------------------
    # Root XML access
    # ------------------------------------------------------------------

    @property
    def root(self) -> ET.Element:
        """Raw XML root element (``<RSLogix5000Content>``).

        Returns:
            The top-level XML element of the parsed L5X document.
        """
        return self._root

    @property
    def controller_element(self) -> ET.Element:
        """Raw XML ``<Controller>`` element.

        Returns:
            The ``<Controller>`` element from the parsed L5X document.
        """
        return self._controller_element

    # ------------------------------------------------------------------
    # Controller metadata
    # ------------------------------------------------------------------

    @property
    def controller(self) -> ControllerInfo:
        """Controller identity, firmware, and configuration metadata.

        Returns:
            A ``ControllerInfo`` instance wrapping the ``<Controller>`` element.
        """
        return self._controller

    # ------------------------------------------------------------------
    # Data types & AOIs
    # ------------------------------------------------------------------

    @property
    def data_types(self) -> DataTypesCollection:
        """User-defined data types (UDTs), keyed by name.

        Returns:
            A ``DataTypesCollection`` mapping UDT names to ``DataType`` instances.
        """
        return self._data_types

    @property
    def aois(self) -> AOICollection:
        """Add-On Instruction definitions, keyed by name.

        Returns:
            An ``AOICollection`` mapping AOI names to ``AOIDefinition`` instances.
        """
        return self._aois

    # ------------------------------------------------------------------
    # Hardware
    # ------------------------------------------------------------------

    @property
    def modules(self) -> ModulesCollection:
        """Hardware modules, keyed by name.

        Returns:
            A ``ModulesCollection`` mapping module names to ``Module`` instances.
        """
        return self._modules

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    @property
    def tags(self) -> ProjectTagsView:
        """Merged global tags: controller tags plus module I/O tags, keyed by name.

        In Studio 5000 a module's communication tags surface as *global
        variables* alongside the controller's own tags. This view exposes both
        under one surface: every controller tag keeps its name, and each module
        I/O tag is added under its Studio 5000 global name (for example
        ``ValveBank:I`` or ``Local:1:C``). Logix tag names cannot contain
        ``':'`` and module global names always do, so the two never collide.

        Returns:
            A :class:`ProjectTagsView` mapping tag names to either ``Tag``
            instances (controller tags) or :class:`ModuleTagRef` instances
            (module I/O tags).
        """
        return ProjectTagsView(self._tags, self._modules)

    # ------------------------------------------------------------------
    # Programs
    # ------------------------------------------------------------------

    @property
    def programs(self) -> ProgramsCollection:
        """Programs defined in the project, keyed by name.

        Each program contains its own local tags and routines.

        Returns:
            A ``ProgramsCollection`` mapping program names to ``Program`` instances.
        """
        return self._programs

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    @property
    def tasks(self) -> TasksCollection:
        """Tasks defined in the project, keyed by name.

        Each task schedules one or more programs and controls execution
        (CONTINUOUS, PERIODIC, or EVENT).

        Returns:
            A ``TasksCollection`` mapping task names to ``Task`` instances.
        """
        return self._tasks

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a concise representation of the project.

        Includes the export target, controller name, processor type, and
        counts of data types, modules, AOIs, tags, programs, and tasks.

        Returns:
            A formatted string suitable for display in debug output.
        """
        if self.contains_context:
            # For Rung exports the root has no TargetName; use the resolved
            # rung number instead so the repr is informative.
            if self.target_type == "Rung":
                t = self.target
                rung_label = f"number={t.number}" if isinstance(t, Rung) else "?"
                target_line = f"  Target:       Rung {rung_label}"
            else:
                target_line = f"  Target:       {self.target_type} {self.target_name!r}"
        else:
            target_line = "  Target:       Full project"

        processor = self.controller.processor_type or "—"
        major = self.controller.major_rev or "—"
        minor = self.controller.minor_rev or "—"

        lines = [
            f"Project({self.controller.name!r})",
            target_line,
            f"  Processor:    {processor}",
            f"  Firmware:     {major}.{minor}",
            f"  Data Types:   {len(self._data_types)}",
            f"  Modules:      {len(self._modules)}",
            f"  AOIs:         {len(self._aois)}",
            f"  Controller Tags: {len(self._tags)}",
            f"  Programs:     {len(self._programs)}",
            f"  Tasks:        {len(self._tasks)}",
        ]
        return "\n".join(lines)

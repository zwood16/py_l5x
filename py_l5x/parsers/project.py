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
    ├── tags             → TagsCollection (controller-level)
    ├── programs         → ProgramsCollection
    │   └── tags         → TagsCollection (per-program)
    │   └── routines     → RoutinesCollection (per-program)
    └── tasks            → TasksCollection
        └── programs     → Mapping[str, Program] (per-task)

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

from typing import TYPE_CHECKING, Union
from xml.etree import ElementTree as ET

from py_l5x.parsers.aoi import AOICollection, AOIDefinition
from py_l5x.parsers.controller import ControllerInfo
from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.module import Module, ModulesCollection
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
        self._controller_element = self._root.find("Controller")
        if self._controller_element is None:
            raise ValueError("No <Controller> element found; not a valid L5X file.")

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
    def tags(self) -> TagsCollection:
        """Controller-level (global) tags, keyed by name.

        Returns:
            A ``TagsCollection`` mapping tag names to ``Tag`` instances.
        """
        return self._tags

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
                rung_label = f"number={t.number}" if t is not None else "?"
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

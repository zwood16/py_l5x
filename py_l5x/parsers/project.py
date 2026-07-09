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

from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.parsers.aoi import AOICollection
from py_l5x.parsers.controller import ControllerInfo
from py_l5x.parsers.datatype import AddOnDataTypeCollection, DataTypesCollection
from py_l5x.parsers.module import ModulesCollection
from py_l5x.parsers.program import ProgramsCollection
from py_l5x.parsers.tag import TagsCollection, TypeRegistry
from py_l5x.parsers.task import TasksCollection

if TYPE_CHECKING:
    pass


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

        Includes the controller name, processor type, and counts of
        data types, modules, AOIs, tags, programs, and tasks.

        Returns:
            A formatted string suitable for display in debug output.
        """
        lines = [
            f"Project({self.controller.name!r})",
            f"  Processor:    {self.controller.processor_type}",
            f"  Firmware:     {self.controller.major_rev}.{self.controller.minor_rev}",
            f"  Data Types:   {len(self._data_types)}",
            f"  Modules:      {len(self._modules)}",
            f"  AOIs:         {len(self._aois)}",
            f"  Controller Tags: {len(self._tags)}",
            f"  Programs:     {len(self._programs)}",
            f"  Tasks:        {len(self._tasks)}",
        ]
        return "\n".join(lines)

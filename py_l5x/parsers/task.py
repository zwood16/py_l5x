"""Task-scoped data.

This module provides ``Task``, a wrapper around the ``<Task>`` element,
plus ``TasksCollection`` for accessing every ``<Task>`` by name.
Tasks control which programs run and when (CONTINUOUS, PERIODIC, or EVENT).
Programs scheduled under a task are exposed via ``task.programs`` as a live
``Mapping[str, Program]`` view resolved back to the ``<Programs>`` section.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.parsers.base import BaseCollection, BaseElement

if TYPE_CHECKING:
    from py_l5x.parsers.program import Program
    from py_l5x.parsers.tag import TypeRegistry

_TASK_KNOWN_XML_KEYS: frozenset[str] = frozenset(
    {
        "Name",
        "Type",
        "Rate",
        "Priority",
        "Watchdog",
        "DisableUpdateOutputs",
        "InhibitTask",
    }
)
"""Known XML attribute names on ``<Task>`` elements."""


class EventInfo(BaseElement):
    """A single ``<EventInfo>`` child of an EVENT ``<Task>``.

    Attributes:
        event_trigger: Value of the ``EventTrigger`` attribute.
        enable_timeout: Whether ``EnableTimeout`` is ``"true"``.

    Args:
        element: The ``<EventInfo>`` element from a parsed L5X tree.
    """

    @property
    def event_trigger(self) -> str:
        """Event trigger source.

        Returns:
            The value of the ``EventTrigger`` XML attribute.
        """
        return self._get("EventTrigger")

    @property
    def enable_timeout(self) -> bool:
        """Whether enable timeout is configured.

        Returns:
            ``True`` if ``EnableTimeout`` is ``"true"``, ``False`` otherwise.
        """
        return self._get("EnableTimeout") == "true"

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in {"EventTrigger", "EnableTimeout"}
        }

    def __repr__(self) -> str:
        """Return a concise representation.

        Returns:
            A string in the format ``EventInfo()``.
        """
        return f"EventInfo(Trigger: {self.event_trigger})"


class _ScheduledPrograms(Mapping[str, "Program"]):
    """A live ``Mapping`` over scheduled programs for a single task.

    Keys are the ``Name`` attributes of ``<ScheduledProgram>`` children
    (in XML order). Values are ``Program`` instances resolved from the
    ``<Programs>`` section of the controller.

    This is *not* a ``BaseCollection`` because the keys come from one XML
    section (``<ScheduledPrograms>``) while the values live in another
    (``<Programs>``).
    """

    def __init__(
        self,
        task_element: ET.Element,
        controller_element: ET.Element,
        type_registry: TypeRegistry,
    ) -> None:
        """Initialise from a ``<Task>`` element and its controller.

        Args:
            task_element: The ``<Task>`` element whose
                ``ScheduledPrograms/ScheduledProgram`` children form the keys.
            controller_element: The ``<Controller>`` element whose
                ``Programs/Program`` children are resolved by name.
            type_registry: Used to resolve each program's tags' value tree
                members.
        """
        self._task_element = task_element
        self._controller_element = controller_element
        self._type_registry = type_registry

    def _children(self) -> list[ET.Element]:
        """Return all ``<ScheduledProgram>`` elements in XML order.

        Returns:
            List of ``ET.Element`` objects under ``ScheduledPrograms/ScheduledProgram``.
        """
        sched_el = self._task_element.find("ScheduledPrograms")
        if sched_el is None:
            return []
        return sched_el.findall("ScheduledProgram")

    def __getitem__(self, name: str) -> Program:
        """Retrieve a scheduled program by its ``Name`` attribute.

        Args:
            name: The ``Name`` attribute of the desired ``<Program>``.

        Returns:
            A ``Program`` instance constructed from the matching element.

        Raises:
            KeyError: If no scheduled program with the given name is found.
        """
        # First check if the name is in our scheduled list.
        for sched in self._children():
            if sched.get("Name") == name:
                # Now find the actual Program element in the controller.
                for prog_el in self._controller_element.findall("Programs/Program"):
                    if prog_el.get("Name") == name:
                        from py_l5x.parsers.program import Program

                        return Program(prog_el, self._type_registry)
                raise KeyError(name)
        raise KeyError(name)

    def __iter__(self) -> Iterator[str]:
        """Iterate over the ``Name`` attributes of all scheduled programs.

        Yields:
            The ``Name`` attribute value for each scheduled program, in XML order.
        """
        for sched in self._children():
            yield sched.get("Name", "")

    def __len__(self) -> int:
        """Return the number of scheduled programs.

        Returns:
            The count of ``<ScheduledProgram>`` children.
        """
        return len(self._children())

    def __repr__(self) -> str:
        """Return a string representation of the scheduled programs.

        Returns:
            A string of the form ``_ScheduledPrograms([name1, name2, ...])``.
        """
        return f"_ScheduledPrograms({list(self)!r})"


class Task(BaseElement):
    """A single ``<Task>`` element from the ``<Tasks>`` section.

    Attributes:
        name: Task name.
        description: Task description text.
        type_: Task type (CONTINUOUS, PERIODIC, or EVENT).
        rate: Task period in milliseconds (``None`` if not present).
        priority: Task priority level (``None`` if not present).
        watchdog: Watchdog timeout value (``None`` if not present).
        disable_update_outputs: Whether output updates are disabled.
        inhibit_task: Whether the task is inhibited.
        event_info: Event-specific configuration (``None`` for non-EVENT tasks).
        scheduled_program_names: Ordered names of programs scheduled under this task.
        programs: A ``Mapping`` of scheduled program names to ``Program`` instances.

    Args:
        element: The ``<Task>`` element from a parsed L5X tree.
        controller_element: The ``<Controller>`` element used to resolve
            scheduled program references.
        type_registry: Used to resolve scheduled programs' tags' value tree members.
    """

    def __init__(
        self,
        element: ET.Element,
        controller_element: ET.Element,
        type_registry: TypeRegistry,
    ) -> None:
        """Initialise from a ``<Task>`` XML element.

        Args:
            element: The ``<Task>`` element to wrap.
            controller_element: The ``<Controller>`` element whose
                ``Programs/Program`` children are resolved by name.
            type_registry: Used to resolve scheduled programs' tags' value
                tree members.
        """
        super().__init__(element)
        self._controller_element = controller_element
        self._type_registry = type_registry

    @property
    def name(self) -> str:
        """Task name.

        Returns:
            The task name string.
        """
        return self._get("Name")

    @property
    def description(self) -> str:
        """Task description text.

        Returns:
            The description text string, or ``""`` if no description is present.
        """
        return self._get_description()

    @property
    def type_(self) -> str:
        """Task type.

        Returns:
            The value of the ``Type`` XML attribute (e.g. ``"CONTINUOUS"``,
            ``"PERIODIC"``, ``"EVENT"``).
        """
        return self._get("Type")

    @property
    def rate(self) -> float | None:
        """Task period in milliseconds.

        Returns:
            The rate as a ``float``, or ``None`` if the ``Rate`` attribute
            is not present.
        """
        rate_str = self._get("Rate")
        if rate_str:
            return float(rate_str)
        return None

    @property
    def priority(self) -> int | None:
        """Task priority level.

        Returns:
            The priority as an ``int``, or ``None`` if the ``Priority``
            attribute is not present.
        """
        priority_str = self._get("Priority")
        if priority_str:
            return int(priority_str)
        return None

    @property
    def watchdog(self) -> int | None:
        """Watchdog timeout value.

        Returns:
            The watchdog value as an ``int``, or ``None`` if the ``Watchdog``
            attribute is not present.
        """
        watchdog_str = self._get("Watchdog")
        if watchdog_str:
            return int(watchdog_str)
        return None

    @property
    def disable_update_outputs(self) -> bool:
        """Whether output updates are disabled for this task.

        Returns:
            ``True`` if ``DisableUpdateOutputs`` is ``"true"``, ``False`` otherwise.
        """
        return self._get("DisableUpdateOutputs") == "true"

    @property
    def inhibit_task(self) -> bool:
        """Whether the task is inhibited.

        Returns:
            ``True`` if ``InhibitTask`` is ``"true"``, ``False`` otherwise.
        """
        return self._get("InhibitTask") == "true"

    @property
    def event_info(self) -> EventInfo | None:
        """Event-specific configuration.

        Returns:
            An ``EventInfo`` instance if an ``<EventInfo>`` child is present,
            ``None`` otherwise.
        """
        event_info_el = self._element.find("EventInfo")
        if event_info_el is not None:
            return EventInfo(event_info_el)
        return None

    @property
    def scheduled_program_names(self) -> tuple[str, ...]:
        """Ordered names of programs scheduled under this task.

        Returns:
            A tuple of ``Name`` attribute values from ``<ScheduledProgram>``
            children, in XML order.
        """
        sched_el = self._element.find("ScheduledPrograms")
        if sched_el is None:
            return ()
        return tuple(
            sched.get("Name", "") for sched in sched_el.findall("ScheduledProgram")
        )

    @property
    def programs(self) -> Mapping[str, Program]:
        """A ``Mapping`` of scheduled program names to ``Program`` instances.

        Programs are resolved live from the ``<Programs>`` section of the
        controller on each access, so future in-place mutations to the
        underlying elements are always reflected.

        Returns:
            A ``_ScheduledPrograms`` mapping keyed by program name.
        """
        return _ScheduledPrograms(
            self._element, self._controller_element, self._type_registry
        )

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes not covered by explicit properties.

        Returns:
            Dictionary mapping attribute names to their string values.
        """
        return {
            k: v
            for k, v in self._element.attrib.items()
            if k not in _TASK_KNOWN_XML_KEYS
        }

    def __repr__(self) -> str:
        """Return a concise representation including the task name.

        Returns:
            A string in the format ``Task('name')``.
        """
        return f"Task({self.name!r})"


class TasksCollection(BaseCollection[Task]):
    """A ``Mapping`` over every ``<Task>`` in the ``<Tasks>`` section.

    Attributes:
        tasks: All tasks in the collection, keyed by name.

    Args:
        controller_element: The ``<Controller>`` element from a parsed L5X
            tree.
        type_registry: Used to resolve each scheduled program's tags' value
            tree members.
    """

    def __init__(
        self, controller_element: ET.Element, type_registry: TypeRegistry
    ) -> None:
        """Initialise from a ``<Controller>`` XML element.

        Args:
            controller_element: The ``<Controller>`` element whose
                ``Tasks/Task`` children form this collection.
            type_registry: Used to resolve each scheduled program's tags'
                value tree members.
        """
        super().__init__(
            controller_element,
            "Tasks/Task",
            Task,
            item_args=(controller_element, type_registry),
        )

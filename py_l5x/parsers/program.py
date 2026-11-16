"""Program-scoped data.

This module provides ``Program``, a wrapper around the ``<Program>`` element,
plus ``ProgramsCollection`` for accessing every ``<Program>`` by name.
Program identity, local tags, and routines/logic are exposed directly via
typed parser wrappers.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.parsers.atomic_types import ATOMIC_TYPES
from py_l5x.parsers.base import (
    BaseCollection,
    BaseElement,
    CDataField,
    bool_attr,
    str_attr,
)
from py_l5x.parsers.names import validate_new_name
from py_l5x.parsers.routine import RoutinesCollection
from py_l5x.parsers.schema import insert_child, insert_child_at, remove_child
from py_l5x.parsers.tag import TagsCollection, TypeRegistry

if TYPE_CHECKING:
    from py_l5x.build.specs import ProgramSpec


class Program(BaseElement):
    """A single ``<Program>`` element from the ``<Programs>`` section.

    Attributes:
        tags: This program's local tags, keyed by name.
        routines: This program's routines, keyed by routine name.

    Args:
        element: The ``<Program>`` element from a parsed L5X tree.
        type_registry: Used to resolve this program's tags' value tree members.
    """

    name = str_attr("Name", doc="Program name.")
    use = str_attr(
        "Use",
        doc='Export target role for this program. "Target" when this '
        "program is the exported target in a component export.",
    )
    description = CDataField("Description", doc="Program description text.")
    test_edits = bool_attr(
        "TestEdits",
        default=False,
        doc="Whether the program has pending test edits.",
    )
    main_routine_name = str_attr(
        "MainRoutineName", doc="Name of the program's main routine."
    )
    disabled = bool_attr(
        "Disabled", default=False, doc="Whether the program is disabled."
    )
    use_as_folder = bool_attr(
        "UseAsFolder",
        default=False,
        doc="Whether the program is used purely as an organizational folder.",
    )
    class_ = str_attr("Class", doc='Program class: "Standard" or "Safety".')

    def __init__(self, element: ET.Element, type_registry: TypeRegistry) -> None:
        """Initialise from a ``<Program>`` XML element.

        Args:
            element: The ``<Program>`` element to wrap.
            type_registry: Used to resolve this program's tags' value tree
                members.
        """
        super().__init__(element)
        self._type_registry = type_registry

    @property
    def is_safety(self) -> bool:
        """Whether this is a safety program.

        Returns:
            ``True`` if :attr:`class_` is ``"Safety"``, ``False`` otherwise.
        """
        return self.class_ == "Safety"

    @property
    def tags(self) -> TagsCollection:
        """This program's local tags, keyed by name.

        Returns:
            A TagsCollection of the program's local tags.
        """
        return TagsCollection(self._element, self._type_registry)

    @property
    def routines(self) -> RoutinesCollection:
        """This program's routines, keyed by routine name.

        Returns:
            A RoutinesCollection of the program's routines.
        """
        return RoutinesCollection(self._element)

    def to_spec(self) -> ProgramSpec:
        """Convert this program to a spec that rebuilds it.

        Tags keep their order (see :meth:`Tag.to_spec`), routines are converted
        with :meth:`Routine.to_spec`. ``Class`` is ``None`` when the attribute
        is absent. ``metadata`` carries any attribute other than the modelled
        ones, except ``TestEdits``/``UseAsFolder`` while they are ``"false"``
        and the component export marker ``Use``.

        Returns:
            A :class:`~py_l5x.build.specs.ProgramSpec`.

        Raises:
            ValueError: If a tag or routine cannot be converted.
        """
        from py_l5x.build.specs import ProgramSpec
        from py_l5x.parsers.migrate import _raw_cdata

        element = self._element
        description = element.find("Description")
        modelled = {
            "Name",
            "MainRoutineName",
            "FaultRoutineName",
            "Disabled",
            "Class",
            "Use",
        }
        metadata = {
            key: value
            for key, value in element.attrib.items()
            if key not in modelled
            and not (key in ("TestEdits", "UseAsFolder") and value == "false")
        }
        return ProgramSpec(
            name=self.name,
            tags=[tag.to_spec() for tag in self.tags.values()],
            routines=[routine.to_spec() for routine in self.routines.values()],
            main_routine=element.get("MainRoutineName"),
            fault_routine=element.get("FaultRoutineName"),
            description=_raw_cdata(description) if description is not None else "",
            disabled=element.get("Disabled") == "true",
            class_=element.get("Class"),
            metadata=metadata or None,
        )

    def logic_text(self) -> str:
        """Render this program's routine logic as a quick-reference text block.

        Formatting:
            - The first line is ``Program: <name>``.
            - Each routine is preceded by a blank line and a header line of the
              form ``Routine: <name> (<type>)``.
            - The routine body is rendered by :meth:`Routine.as_text`. Ladder
              (``RLL``) rungs are rendered as a ``Rung N ---`` header (padded
              with ``-`` to 40 characters), an optional ``Comment`` block with
              the full comment, and a ``Logic`` block with the rung text. Rungs
              are separated by a blank line::

                  Rung 0 ---------------------------------
                  Comment
                  <comment, possibly multi-line>
                  Logic
                  <rung text>

              and Structured Text (``ST``) routines are rendered line-by-line.
            - Routines of any other type have no body; they are shown as
              ``[Unsupported routine type: <type>]`` instead.

        Returns:
            A human-readable multi-line string containing all routines in the
            program, in XML order.
        """
        lines: list[str] = [f"Program: {self.name}"]

        for routine in self.routines.values():
            lines.append("")
            lines.append(f"Routine: {routine.name} ({routine.type_})")
            text = routine.as_text()
            if text:
                lines.extend(text.splitlines())
            elif routine.type_ not in ("RLL", "ST"):
                lines.append(f"[Unsupported routine type: {routine.type_}]")

        return "\n".join(lines)

    def print_logic_text(self) -> str:
        """Print and return :meth:`logic_text` for quick interactive inspection.

        Returns:
            The logic text string from :meth:`logic_text`.
        """
        text = self.logic_text()
        print(text)
        return text

    def __repr__(self) -> str:
        """Return a concise representation including the program name.

        Returns:
            A string in the format ``Program('name')``.
        """
        return f"Program({self.name!r})"


class ProgramsCollection(BaseCollection[Program]):
    """A ``Mapping`` over every ``<Program>`` in the ``<Programs>`` section.

    Attributes:
        programs: All programs in the collection, keyed by name.

    Args:
        controller_element: The ``<Controller>`` element from a parsed L5X
            tree.
        type_registry: Used to resolve each program's tags' value tree members.
    """

    def __init__(
        self, controller_element: ET.Element, type_registry: TypeRegistry
    ) -> None:
        """Initialise from a ``<Controller>`` XML element.

        Args:
            controller_element: The ``<Controller>`` element whose
                ``Programs/Program`` children form this collection.
            type_registry: Used to resolve each program's tags' value tree
                members.
        """
        super().__init__(
            controller_element, "Programs/Program", Program, item_args=(type_registry,)
        )
        self._registry = type_registry

    # ------------------------------------------------------------------
    # Edits
    # ------------------------------------------------------------------

    def _find_element(self, name: str) -> ET.Element:
        """Return the program element with exactly this name.

        Args:
            name: The program name.

        Returns:
            The element.

        Raises:
            KeyError: If there is no such program.
        """
        for element in self._children():
            if element.get("Name") == name:
                return element
        raise KeyError(name)

    def _find_task(self, task: str) -> ET.Element:
        """Return the task element with exactly this name.

        Args:
            task: The task name.

        Returns:
            The ``<Task>`` element.

        Raises:
            KeyError: If there is no such task.
        """
        for element in self._parent.findall("Tasks/Task"):
            if element.get("Name") == task:
                return element
        raise KeyError(task)

    def _scheduled(self, name: str) -> list[tuple[ET.Element, ET.Element]]:
        """Find every ``ScheduledProgram`` entry of a program.

        Args:
            name: The program name.

        Returns:
            ``(ScheduledPrograms element, ScheduledProgram element)`` pairs.
        """
        found = []
        for container in self._parent.findall("Tasks/Task/ScheduledPrograms"):
            for entry in container.findall("ScheduledProgram"):
                if entry.get("Name") == name:
                    found.append((container, entry))
        return found

    def _check_name(self, name: str, ignore: str | None = None) -> None:
        """Validate a program name and check it is unused (ignoring case).

        Args:
            name: The proposed name.
            ignore: A program name to leave out (the one being renamed).

        Raises:
            ValueError: If the name is invalid or taken.
        """
        validate_new_name(name, [n for n in self if n != ignore], "program")

    def _check_types(self, spec: ProgramSpec) -> None:
        """Check that every tag type in a spec resolves.

        Args:
            spec: The program spec.

        Raises:
            ValueError: If a base tag's type is not atomic, built-in, a project
                UDT or an AOI.
        """
        from py_l5x.parsers.layout import builtin_table

        for tag in spec.tags:
            kind = tag.data_type
            if kind is None:
                continue
            if (
                kind in ATOMIC_TYPES
                or kind in builtin_table()
                or self._registry.udt(kind) is not None
                or self._registry.aoi(kind) is not None
            ):
                continue
            raise ValueError(f"tag {tag.name!r}: unknown data type {kind!r}")

    def add(self, spec: ProgramSpec, *, task: str | None = None) -> Program:
        """Add a program built from a spec.

        The program is inserted into ``Controller/Programs`` (created if
        missing) in case-insensitive name order, as Studio lists them. Without
        *task* it is unscheduled, which is what Studio does on import; with one
        a ``ScheduledProgram`` entry is added to that task.

        Calls made by the logic are not checked: a missing AOI cannot be told
        from an unknown instruction mnemonic without Studio's instruction
        table, so only tag types are resolved.

        Args:
            spec: The program.
            task: Name of the task to schedule it in, or ``None``.

        Returns:
            The new program.

        Raises:
            KeyError: If *task* does not exist.
            ValueError: If the spec is invalid, the name is taken (ignoring
                case), or a tag type does not resolve.
        """
        from py_l5x.build.program import build_program

        task_element = self._find_task(task) if task is not None else None
        self._check_name(spec.name)
        self._check_types(spec)
        element = build_program(spec, self._registry)
        container = self._parent.find("Programs")
        if container is None:
            container = ET.Element("Programs")
            insert_child(self._parent, container)
        lowered = spec.name.lower()
        position = len(container)
        for index, existing in enumerate(container):
            if existing.get("Name", "").lower() > lowered:
                position = index
                break
        insert_child_at(container, position, element)
        if task_element is not None:
            self._schedule_in(task_element, spec.name)
        return self[spec.name]

    def replace(self, spec: ProgramSpec) -> Program:
        """Replace a program, keeping its position and its task scheduling.

        The element is rebuilt in place. A tag whose spec has ``value=None``
        and that already exists with the same type and dimensions **keeps its
        current data**: unlike Studio's program overwrite, which resets values,
        a replace here never silently resets them. If the type or dimensions
        changed, or the spec has a value, the data comes from the spec. The
        change is all or nothing.

        Args:
            spec: The new program; ``spec.name`` selects the program.

        Returns:
            The replaced program.

        Raises:
            KeyError: If there is no program of that name.
            ValueError: If the spec is invalid or a tag type does not resolve.
        """
        from py_l5x.build.program import build_program

        existing = self._find_element(spec.name)
        self._check_types(spec)
        fresh = build_program(spec, self._registry)
        old_tags = {t.get("Name"): t for t in existing.findall("Tags/Tag")}
        for tag_spec, tag in zip(spec.tags, fresh.findall("Tags/Tag"), strict=True):
            old = old_tags.get(tag_spec.name)
            if (
                tag_spec.value is None
                and old is not None
                and tag_spec.data_type is not None
                and old.get("DataType") == tag.get("DataType")
                and old.get("Dimensions") == tag.get("Dimensions")
                and old.get("TagType", "Base") == "Base"
            ):
                for data in [d for d in tag if d.tag == "Data"]:
                    remove_child(tag, data)
                for data in old.findall("Data"):
                    insert_child(tag, copy.deepcopy(data))
        container = self._parent.find("Programs")
        assert container is not None
        index = list(container).index(existing)
        fresh.tail = existing.tail
        container[index] = fresh
        return self[spec.name]

    def remove(self, name: str) -> None:
        """Delete a program and its ``ScheduledProgram`` entries.

        Args:
            name: The program name.

        Raises:
            KeyError: If there is no such program.
        """
        element = self._find_element(name)
        for container, entry in self._scheduled(name):
            remove_child(container, entry)
        programs = self._parent.find("Programs")
        assert programs is not None
        remove_child(programs, element)

    def rename(self, old: str, new: str) -> Program:
        """Rename a program, updating its ``ScheduledProgram`` entries.

        References to the program's tags from other programs in logic
        (``\\Program.Tag`` style) are **not** rewritten.

        Args:
            old: The current name.
            new: The new name (same rules as :meth:`add`; a case-only change
                of the program itself works).

        Returns:
            The renamed program.

        Raises:
            KeyError: If *old* does not exist.
            ValueError: If *new* is invalid or taken.
        """
        element = self._find_element(old)
        self._check_name(new, ignore=old)
        element.set("Name", new)
        for _container, entry in self._scheduled(old):
            entry.set("Name", new)
        return self[new]

    def _schedule_in(self, task_element: ET.Element, name: str) -> None:
        """Append a ``ScheduledProgram`` to a task, creating its container.

        Args:
            task_element: The ``<Task>``.
            name: The program name.
        """
        container = task_element.find("ScheduledPrograms")
        if container is None:
            container = ET.Element("ScheduledPrograms")
            insert_child(task_element, container)
        entry = ET.Element("ScheduledProgram")
        entry.set("Name", name)
        insert_child_at(container, len(container), entry)

    def schedule(self, name: str, task: str) -> None:
        """Schedule a program in a task.

        Args:
            name: The program name.
            task: The task name.

        Raises:
            KeyError: If the program or the task does not exist.
            ValueError: If the program is already scheduled (a program can be
                scheduled in at most one task).
        """
        self._find_element(name)
        task_element = self._find_task(task)
        if self._scheduled(name):
            raise ValueError(f"program {name!r} is already scheduled")
        self._schedule_in(task_element, name)

    def unschedule(self, name: str) -> str | None:
        """Remove a program from the task it is scheduled in.

        Args:
            name: The program name.

        Returns:
            The name of the task it was scheduled in, or ``None`` if it was
            not scheduled (nothing changes).

        Raises:
            KeyError: If there is no such program.
        """
        self._find_element(name)
        task = None
        for container, entry in self._scheduled(name):
            task = self._owner_task(container)
            remove_child(container, entry)
        return task

    def _owner_task(self, container: ET.Element) -> str | None:
        """Return the name of the task holding a ``ScheduledPrograms``.

        Args:
            container: A ``ScheduledPrograms`` element.

        Returns:
            The task name.
        """
        for task in self._parent.findall("Tasks/Task"):
            if task.find("ScheduledPrograms") is container:
                return task.get("Name")
        return None

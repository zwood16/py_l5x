"""Build ``<Program>`` elements from a :class:`~py_l5x.build.specs.ProgramSpec`.

The output matches Studio exports: attributes ``Name TestEdits
MainRoutineName FaultRoutineName Disabled Class UseAsFolder`` (``TestEdits``
and ``UseAsFolder`` default to ``"false"``; ``MainRoutineName``,
``FaultRoutineName`` and ``Class`` are written only when set; the fixtures
have no fault routine, so ``FaultRoutineName`` is placed right after
``MainRoutineName``), then ``Description``, ``Tags`` (always present, in spec
order) and ``Routines`` (always present, sorted by name ignoring case, as
Studio writes them).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from py_l5x.build.aoi import build_routine
from py_l5x.build.datatype import _fill
from py_l5x.build.specs import ProgramSpec
from py_l5x.build.tag import build_tag
from py_l5x.parsers.names import validate_new_name
from py_l5x.parsers.routine import _check_rung_text
from py_l5x.parsers.schema import new_cdata_element

if TYPE_CHECKING:
    from py_l5x.parsers.tag import TypeRegistry


def _validate(spec: ProgramSpec) -> None:
    """Check a program spec before building.

    Args:
        spec: The spec.

    Raises:
        ValueError: For invalid or duplicate names (tags and routines are
            separate namespaces, ignoring case), a main or fault routine that
            is not in ``routines``, an unknown routine type, mismatched
            rungs/lines, or an invalid rung text.
    """
    validate_new_name(spec.name, [], "program")
    seen: list[str] = []
    for tag in spec.tags:
        validate_new_name(tag.name, seen, "tag")
        seen.append(tag.name)
    names: list[str] = []
    for routine in spec.routines:
        validate_new_name(routine.name, names, "routine")
        names.append(routine.name)
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
    for label, routine_name in (
        ("main", spec.main_routine),
        ("fault", spec.fault_routine),
    ):
        if routine_name is not None and routine_name not in names:
            raise ValueError(f"{label} routine {routine_name!r} is not in the routines")


def build_program(spec: ProgramSpec, registry: TypeRegistry) -> ET.Element:
    """Build a detached ``<Program>`` from a spec.

    Args:
        spec: The program.
        registry: The project's type registry (for tag values and types).

    Returns:
        The ``<Program>`` element, with no ``tail``.

    Raises:
        ValueError: If the spec is invalid (see :func:`_validate`) or a tag
            spec is invalid or has a bad value.
    """
    _validate(spec)
    meta = dict(spec.metadata or {})
    element = ET.Element("Program")
    element.set("Name", spec.name)
    element.set("TestEdits", meta.pop("TestEdits", "false"))
    if spec.main_routine is not None:
        element.set("MainRoutineName", spec.main_routine)
    if spec.fault_routine is not None:
        element.set("FaultRoutineName", spec.fault_routine)
    element.set("Disabled", "true" if spec.disabled else "false")
    if spec.class_ is not None:
        element.set("Class", spec.class_)
    element.set("UseAsFolder", meta.pop("UseAsFolder", "false"))
    for key, value in meta.items():
        element.set(key, value)
    children: list[ET.Element] = []
    if spec.description:
        children.append(new_cdata_element("Description", spec.description))
    children.append(
        _fill(ET.Element("Tags"), [build_tag(t, registry) for t in spec.tags])
    )
    routines = sorted(spec.routines, key=lambda r: r.name.lower())
    children.append(_fill(ET.Element("Routines"), [build_routine(r) for r in routines]))
    return _fill(element, children)

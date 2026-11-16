"""Templating: name substitution on specs, for stamping out repeated objects.

Typical use: ``program.to_spec()``, then :func:`substitute` (or :func:`stamp`)
to make copies with other names, then ``programs.add(...)`` for each.

Substitution rules:

- It applies to every ``str`` **value** found by walking dataclass fields,
  lists, tuples and dicts recursively: names, data types, alias targets, rung
  text and comments, ST lines, descriptions, revision notes, string tag
  values, metadata values and dict values. Non-strings (numbers, booleans,
  ``None``) are untouched.
- Dict **keys** are left alone by default. In specs they are almost always
  member names or operand paths (``value={"PRE": 2500}``,
  ``operand_comments={".DN": ...}``, ``operand_metadata``, ``metadata``
  attribute names, AOI parameter defaults), which belong to a type definition
  and are not instance specific: a broad mapping such as ``{"a_": "m2_"}``
  must not turn the UDT member ``a_Bool`` into ``m2_Bool``. Pass
  ``keys=True`` to substitute keys as well, for example when operand comments
  are keyed by members whose names themselves follow the instance prefix
  (``{".M1_RUN": ...}``); two keys that become equal then raise
  ``ValueError`` instead of silently dropping one.
- It is one simultaneous pass: a single regular expression made of the
  escaped keys, **longest keys first**. ``{"Motor1": "Motor7", "M1_": "M7_"}``
  is predictable, and replacements never cascade (``{"A": "B", "B": "C"}``
  maps ``A`` to ``B`` and ``B`` to ``C``, never ``A`` to ``C``).
- Matching is plain substring matching and case-sensitive. There are no word
  boundaries, so choose keys that cannot match unrelated text.
- The input spec is never modified; a new deep copy is returned.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any, TypeVar

from py_l5x.parsers.names import validate_new_name

SpecT = TypeVar("SpecT")


def _replacer(mapping: Mapping[str, str]) -> Callable[[str], str]:
    """Compile a mapping into a one-pass, longest-first replacement function.

    Args:
        mapping: Old text to new text.

    Returns:
        A function applying the mapping to a string.

    Raises:
        ValueError: If a key is empty.
        TypeError: If a key or value is not a ``str``.
    """
    for key, value in mapping.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("substitution keys and values must be str")
        if not key:
            raise ValueError("substitution keys must not be empty")
    if not mapping:
        return lambda text: text
    pattern = re.compile(
        "|".join(re.escape(key) for key in sorted(mapping, key=len, reverse=True))
    )
    return lambda text: pattern.sub(lambda match: mapping[match.group(0)], text)


def _walk(value: Any, replace: Callable[[str], str], keys: bool) -> Any:
    """Copy *value* with the replacement applied to every string.

    Args:
        value: A string, container, dataclass instance or other value.
        replace: The string replacement function.
        keys: Whether string dict keys are substituted too.

    Returns:
        The new value. Dataclasses, lists, tuples and dicts are rebuilt; other
        non-string values are copied.

    Raises:
        ValueError: If *keys* is true and two dict keys become equal.
    """
    if isinstance(value, str):
        return replace(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.replace(
            value,
            **{
                f.name: _walk(getattr(value, f.name), replace, keys)
                for f in dataclasses.fields(value)
                if f.init
            },
        )
    if isinstance(value, list):
        return [_walk(item, replace, keys) for item in value]
    if isinstance(value, tuple):
        return tuple(_walk(item, replace, keys) for item in value)
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            new_key = replace(key) if keys and isinstance(key, str) else key
            if new_key in out:
                raise ValueError(f"substitution makes two keys equal: {new_key!r}")
            out[new_key] = _walk(item, replace, keys)
        return out
    return value


def substitute[SpecT](
    spec: SpecT, mapping: Mapping[str, str], *, keys: bool = False
) -> SpecT:
    """Return a copy of a spec with *mapping* applied to every string value.

    Works on any spec dataclass (``ProgramSpec``, ``AOISpec``,
    ``DataTypeSpec``, ``TagSpec``, ``RoutineSpec``, ...). See the module
    docstring for the exact rules (every string value, simultaneous
    longest-first replacement, case-sensitive). Dict keys (member names,
    operand paths, attribute names) are **not** substituted unless
    ``keys=True``.

    Only the top-level ``name`` is validated here (so an obviously bad result
    fails early); duplicate names inside the spec and other problems surface
    when the spec is built or added.

    Args:
        spec: The spec to copy.
        mapping: Old text to new text.
        keys: Also substitute string dict keys (for example operand-comment
            operands that follow the instance prefix).

    Returns:
        A new spec of the same type.

    Raises:
        ValueError: If the top-level name becomes invalid, a mapping key is
            empty, or (with ``keys=True``) two dict keys become equal.
        TypeError: If *spec* is not a dataclass instance, or the mapping holds
            non-strings.
    """
    if not dataclasses.is_dataclass(spec) or isinstance(spec, type):
        raise TypeError(f"cannot substitute in a {type(spec).__name__}")
    result = _walk(spec, _replacer(mapping), keys)
    name = getattr(result, "name", None)
    if isinstance(name, str):
        validate_new_name(name, [], "name")
    return result


def stamp[SpecT](
    spec: SpecT, instances: Iterable[Mapping[str, str]], *, keys: bool = False
) -> list[SpecT]:
    """Make one substituted copy of a spec per mapping.

    Args:
        spec: The template spec.
        instances: One mapping per copy.
        keys: Also substitute string dict keys (see :func:`substitute`).

    Returns:
        ``[substitute(spec, m, keys=keys) for m in instances]``.
    """
    return [substitute(spec, mapping, keys=keys) for mapping in instances]


class SubstituteMixin:
    """Adds ``substitute`` to spec dataclasses."""

    def substitute(
        self: SpecT, mapping: Mapping[str, str], *, keys: bool = False
    ) -> SpecT:
        """Return a copy with *mapping* applied to every string value.

        See :func:`py_l5x.build.template.substitute`.

        Args:
            mapping: Old text to new text.
            keys: Also substitute string dict keys.

        Returns:
            A new spec of the same type.
        """
        return substitute(self, mapping, keys=keys)

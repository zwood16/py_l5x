"""Logix name validation shared by tag and routine edits."""

import re
from collections.abc import Iterable

#: Letters, digits and underscores, not starting with a digit.
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Longest tag or routine name Logix accepts.
MAX_NAME_LENGTH = 40


def validate_new_name(name: str, existing: Iterable[str], kind: str = "tag") -> None:
    """Check that *name* is a valid Logix name and is not already in use.

    Rules: letters, digits and underscores; not starting with a digit; at most
    40 characters; no consecutive underscores; not ending in an underscore.
    Logix names are case-insensitive, so duplicates are matched ignoring case.

    Args:
        name: The proposed name.
        existing: Names already in use in the same scope (leave out the item
            being renamed).
        kind: What is being named, for error messages (``"tag"``/``"routine"``).

    Raises:
        ValueError: If the name breaks a rule or matches an existing name
            ignoring case.
    """
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError(
            f"invalid {kind} name {name!r}: use letters, digits and underscores, "
            "not starting with a digit"
        )
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(
            f"invalid {kind} name {name!r}: longer than {MAX_NAME_LENGTH} characters"
        )
    if "__" in name:
        raise ValueError(f"invalid {kind} name {name!r}: consecutive underscores")
    if name.endswith("_"):
        raise ValueError(f"invalid {kind} name {name!r}: ends with an underscore")
    lowered = name.lower()
    for other in existing:
        if other.lower() == lowered:
            raise ValueError(
                f"{kind} {name!r} already exists as {other!r} "
                f"({kind} names are case-insensitive)"
            )

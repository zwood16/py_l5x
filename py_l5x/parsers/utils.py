"""Miscellaneous helper functions."""

import re

def to_snake(name: str) -> str:
    """Convert PascalCase/camelCase XML keys to snake_case names."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

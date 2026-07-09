"""py_l5x - Parse and inspect Rockwell Logix 5000 L5X project files.

Usage:
    >>> from py_l5x import load
    >>> project = load("my_project.L5X")
    >>> print(project.controller.name)
    MyController
"""

from py_l5x.parse import load

__all__ = ["load"]

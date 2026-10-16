"""py_l5x - Parse and inspect Rockwell Logix 5000 L5X project files.

Usage:
    >>> from py_l5x import load
    >>> project = load("my_project.L5X")
    >>> print(project.controller.name)
    MyController
"""

from py_l5x.parse import load
from py_l5x.parsers.aoi import AOIDefinition
from py_l5x.parsers.controller import ControllerInfo
from py_l5x.parsers.datatype import AddOnParameter, DataType, DataTypeMember
from py_l5x.parsers.module import Module
from py_l5x.parsers.program import Program
from py_l5x.parsers.project import Project
from py_l5x.parsers.routine import Routine
from py_l5x.parsers.tag import (
    ArrayNode,
    AtomicNode,
    BoolNode,
    ConsumeInfo,
    DateTimeNode,
    FloatNode,
    IntegerNode,
    ProduceInfo,
    StringNode,
    StructNode,
    Tag,
    TagExtendedProperties,
    TagNode,
    TimeNode,
)
from py_l5x.parsers.task import Task

__all__ = [
    "AOIDefinition",
    "AddOnParameter",
    "ArrayNode",
    "AtomicNode",
    "BoolNode",
    "ConsumeInfo",
    "ControllerInfo",
    "DataType",
    "DataTypeMember",
    "DateTimeNode",
    "FloatNode",
    "IntegerNode",
    "Module",
    "ProduceInfo",
    "Program",
    "Project",
    "Routine",
    "StringNode",
    "StructNode",
    "Tag",
    "TagExtendedProperties",
    "TagNode",
    "Task",
    "TimeNode",
    "load",
]

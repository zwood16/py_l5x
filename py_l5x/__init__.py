"""py_l5x - Parse and inspect Rockwell Logix 5000 L5X project files.

Usage:
    >>> from py_l5x import load
    >>> project = load("my_project.L5X")
    >>> print(project.controller.name)
    MyController
"""

from py_l5x.parse import load
from py_l5x.parsers.aoi import (
    AOIDefinition,
    AOILocalArrayTag,
    AOILocalAtomicTag,
    AOILocalBoolTag,
    AOILocalDateTimeTag,
    AOILocalFloatTag,
    AOILocalIntegerTag,
    AOILocalStringTag,
    AOILocalStructTag,
    AOILocalTag,
    AOILocalTimeTag,
)
from py_l5x.parsers.controller import ControllerInfo
from py_l5x.parsers.datatype import AddOnParameter, DataType, DataTypeMember
from py_l5x.parsers.module import Module, ModuleTagRef, ModuleTagsView
from py_l5x.parsers.program import Program
from py_l5x.parsers.project import Project, ProjectTagsView
from py_l5x.parsers.routine import Routine
from py_l5x.parsers.tag import (
    AliasTag,
    ArrayNode,
    ArrayTag,
    AtomicNode,
    AtomicTag,
    AxisTag,
    BoolNode,
    BoolTag,
    ConsumeInfo,
    DateTimeNode,
    DateTimeTag,
    FloatNode,
    FloatTag,
    IntegerNode,
    IntegerTag,
    MessageTag,
    MotionGroupTag,
    ProduceInfo,
    StringNode,
    StringTag,
    StructNode,
    StructTag,
    Tag,
    TagNode,
    TimeNode,
    TimeTag,
    UnknownTag,
)
from py_l5x.parsers.task import Task

__all__ = [
    "AOIDefinition",
    "AOILocalArrayTag",
    "AOILocalAtomicTag",
    "AOILocalBoolTag",
    "AOILocalDateTimeTag",
    "AOILocalFloatTag",
    "AOILocalIntegerTag",
    "AOILocalStringTag",
    "AOILocalStructTag",
    "AOILocalTag",
    "AOILocalTimeTag",
    "AddOnParameter",
    "AliasTag",
    "ArrayNode",
    "ArrayTag",
    "AtomicNode",
    "AtomicTag",
    "AxisTag",
    "BoolNode",
    "BoolTag",
    "ConsumeInfo",
    "ControllerInfo",
    "DataType",
    "DataTypeMember",
    "DateTimeNode",
    "DateTimeTag",
    "FloatNode",
    "FloatTag",
    "IntegerNode",
    "IntegerTag",
    "MessageTag",
    "Module",
    "ModuleTagRef",
    "ModuleTagsView",
    "MotionGroupTag",
    "ProduceInfo",
    "Program",
    "Project",
    "ProjectTagsView",
    "Routine",
    "StringNode",
    "StringTag",
    "StructNode",
    "StructTag",
    "Tag",
    "TagNode",
    "Task",
    "TimeNode",
    "TimeTag",
    "UnknownTag",
    "load",
]

"""Spec builders: plain dataclasses turned into Studio-exact XML."""

from py_l5x.build.aoi import aoi_call_operands, build_aoi
from py_l5x.build.datatype import build_datatype
from py_l5x.build.export import export_component
from py_l5x.build.program import build_program
from py_l5x.build.specs import (
    AOISpec,
    DataTypeSpec,
    LocalTagSpec,
    MemberSpec,
    ParameterSpec,
    ProgramSpec,
    RoutineSpec,
    RungSpec,
    TagSpec,
)
from py_l5x.build.tag import build_tag
from py_l5x.build.template import stamp, substitute

__all__ = [
    "AOISpec",
    "DataTypeSpec",
    "LocalTagSpec",
    "MemberSpec",
    "ParameterSpec",
    "ProgramSpec",
    "RoutineSpec",
    "RungSpec",
    "TagSpec",
    "aoi_call_operands",
    "build_aoi",
    "build_datatype",
    "build_program",
    "build_tag",
    "export_component",
    "stamp",
    "substitute",
]

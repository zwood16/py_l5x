"""Spec builders: plain dataclasses turned into Studio-exact XML."""

from py_l5x.build.aoi import aoi_call_operands, build_aoi
from py_l5x.build.datatype import build_datatype
from py_l5x.build.specs import (
    AOISpec,
    DataTypeSpec,
    LocalTagSpec,
    MemberSpec,
    ParameterSpec,
    RoutineSpec,
    RungSpec,
)

__all__ = [
    "AOISpec",
    "DataTypeSpec",
    "LocalTagSpec",
    "MemberSpec",
    "ParameterSpec",
    "RoutineSpec",
    "RungSpec",
    "aoi_call_operands",
    "build_aoi",
    "build_datatype",
]

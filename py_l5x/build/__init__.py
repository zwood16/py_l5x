"""Spec builders: plain dataclasses turned into Studio-exact XML."""

from py_l5x.build.datatype import build_datatype
from py_l5x.build.specs import DataTypeSpec, MemberSpec

__all__ = ["DataTypeSpec", "MemberSpec", "build_datatype"]

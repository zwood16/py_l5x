"""UDT and basic Tag type parsing and definitions."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass


class TagBase:
    """Base class for Tag types."""

    def __init__(self, name: str, tag_type: str):
        self.name = name
        self.tag_type = tag_type

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name}, tag_type={self.tag_type})"
"""Base classes for L5X parser elements and collections."""

from __future__ import annotations

from collections.abc import Mapping
from xml.etree import ElementTree as ET

from py_l5x.parse import CDATA_TAG


class XmlAttrMixin:
    """Mixin providing a helper for XML attribute access.

    Subclasses must define a ``_element`` attribute that is an
    ``xml.etree.ElementTree.Element`` instance.
    """

    _element: ET.Element

    def _get(self, xml_key: str, default: str = "") -> str:
        """Retrieve an XML attribute value by key.

        Args:
            xml_key: The XML attribute name to look up.
            default: Value to return if the attribute is absent.
                Defaults to an empty string.

        Returns:
            The attribute value or *default* if the key is not present.
        """
        return self._element.get(xml_key, default)

    def _get_cdata_child(self, tag: str) -> str:
        """Return text from a CDATA-bearing child element.

        After CDATA pre-processing in ``_load_l5x``, any ``<![CDATA[...]]>``
        section is stored as a child element whose tag is ``CDATA_TAG``
        (imported from :mod:`py_l5x.parse`)::

            <tag><CDataContent>text</CDataContent></tag>

        This helper handles ``Description``, ``Comment``, ``Text`` (rung
        ladder logic), and any other child element that follows this pattern.

        Args:
            tag: The XML child element name to search for.

        Returns:
            The text content, stripped of surrounding whitespace, or an empty
            string if the element or its text is absent.
        """
        el = self._element.find(tag)
        if el is not None:
            cdata_el = el.find(CDATA_TAG)
            if cdata_el is not None and cdata_el.text:
                return cdata_el.text.strip()
            if el.text:
                return el.text.strip()
        return ""

    def _get_description(self) -> str:
        """Return the element description string.

        Delegates to :meth:`_get_cdata_child` for the ``Description`` child
        element and falls back to a plain ``Description`` XML attribute when
        no child element is present.

        Returns:
            The description text, stripped of surrounding whitespace, or an
            empty string if no description is found.
        """
        return self._get_cdata_child("Description") or self._element.get(
            "Description", ""
        )


class BaseElement(XmlAttrMixin):
    """Wraps a single XML element and provides helpers for subclasses.

    Subclasses define known XML attributes as explicit ``@property`` descriptors.
    Unrecognised attributes are accessible via ``extra_attributes``.

    Attributes:
        _element: The underlying XML element to wrap.
    """

    def __init__(self, element: ET.Element) -> None:
        """Initialize the base element wrapper.

        Args:
            element: The underlying XML element to wrap. Stored as
                ``_element`` for attribute access by subclasses.
        """
        # Use object.__setattr__ so subclass @property setters work without
        # hitting any custom __setattr__ we might add later.
        object.__setattr__(self, "_element", element)

    def __repr__(self) -> str:
        """Return a concise representation including the element name.

        Returns:
            A string of the form ``ClassName('Name')`` if a ``Name``
            attribute exists, otherwise ``ClassName()``.
        """
        name = self._element.get("Name", "")
        return (
            f"{self.__class__.__name__}({name!r})"
            if name
            else f"{self.__class__.__name__}()"
        )


class BaseCollection(Mapping):
    """A ``Mapping`` over a set of named XML child elements.

    Keys are the ``Name`` attribute of each child element. Values are instances
    of *item_class* built from the child element.

    Collection contents are read live from the XML tree on every access, so
    future in-place mutations to the underlying elements are always reflected.

    Attributes:
        _parent: XML element whose descendants form this collection.
        _child_xpath: XPath string passed to ``parent_el.findall()`` to locate
            children (e.g. ``"Tags/Tag"`` or ``"Members/Member"``).
        _item_class: Class instantiated for each matching child element.

    Args:
        parent_el: XML element whose descendants form this collection.
        child_xpath: XPath string passed to ``parent_el.findall()`` to locate
            children (e.g. ``"Tags/Tag"`` or ``"Members/Member"``).
        item_class: Class instantiated for each matching child element.
    """

    def __init__(
        self,
        parent_el: ET.Element,
        child_xpath: str,
        item_class: type,
        item_args: tuple = (),
    ) -> None:
        """Initialize the collection.

        Args:
            parent_el: XML element whose descendants form this collection.
            child_xpath: XPath string passed to ``parent_el.findall()`` to locate
                children (e.g. ``"Tags/Tag"`` or ``"Members/Member"``).
            item_class: Class instantiated for each matching child element.
            item_args: Additional arguments passed to the item_class constructor.
        """
        self._parent = parent_el
        self._child_xpath = child_xpath
        self._item_class = item_class
        self._item_args = item_args

    def _children(self) -> list[ET.Element]:
        """Return all child elements matching the configured XPath.

        Returns:
            List of ``ET.Element`` objects found under *parent_el*.
        """
        return self._parent.findall(self._child_xpath)

    # ------------------------------------------------------------------
    # Mapping protocol (three required methods)
    # ------------------------------------------------------------------

    def __getitem__(self, name: str):
        """Retrieve an item by its ``Name`` attribute.

        Args:
            name: The ``Name`` attribute value of the desired child element.

        Returns:
            An instance of *item_class* constructed from the matching element.

        Raises:
            KeyError: If no child element with the given name is found.
        """
        for el in self._children():
            if el.get("Name") == name:
                return self._item_class(el, *self._item_args)
        raise KeyError(name)

    def __iter__(self):
        """Iterate over the ``Name`` attributes of all child elements.

        Yields:
            The ``Name`` attribute value for each child element.
        """
        for el in self._children():
            yield el.get("Name", "")

    def __len__(self) -> int:
        """Return the number of child elements in the collection.

        Returns:
            The count of child elements matching the configured XPath.
        """
        return len(self._children())

    # Mapping gives us .get(), .keys(), .values(), .items(), __contains__ for free.

    def __repr__(self) -> str:
        """Return a string representation of the collection.

        Returns:
            A string of the form ``ClassName([name1, name2, ...])``.
        """
        return f"{self.__class__.__name__}({list(self)!r})"

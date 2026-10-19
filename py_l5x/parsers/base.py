"""Base classes for L5X parser elements and collections."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any, cast, overload
from xml.etree import ElementTree as ET

from py_l5x.parsers.utils import CDATA_TAG


class XmlAttrMixin:
    """Mixin providing a helper for XML attribute access.

    Subclasses must define a ``_element`` attribute that is an
    ``xml.etree.ElementTree.Element`` instance.
    """

    _element: ET.Element

    def _get_cdata_child(self, tag: str) -> str:
        """Return text from a CDATA-bearing child element.

        After CDATA pre-processing in ``_load_l5x``, any ``<![CDATA[...]]>``
        section is stored as a child element whose tag is ``CDATA_TAG``
        (imported from :mod:`py_l5x.parsers.utils`)::

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


class XmlField[T]:
    """Descriptor mapping a Python attribute to a single XML attribute.

    Reading returns the value converted by *parse*, or *default* when the
    XML attribute is absent. Writing converts the value back via *unparse*
    and sets it on the underlying element -- writing ``None`` instead
    *removes* the XML attribute entirely, so fields that are never set
    never serialize as empty/placeholder attributes.

    Each class that declares one or more ``XmlField`` attributes gets a
    ``_fields`` registry (name -> descriptor) attached automatically via
    :meth:`__set_name__`, which powers :meth:`BaseElement.fields` and
    :meth:`BaseElement.describe`.

    Prefer the factory functions below (:func:`str_attr`, :func:`bool_attr`,
    :func:`flag_attr`, :func:`int_attr`, :func:`float_attr`) over
    constructing this directly.

    Args:
        xml_name: The XML attribute name this field reads/writes.
        parse: Converts the raw attribute string to a Python value of type T.
        unparse: Converts a Python value of type T back to an attribute
            string. Defaults to ``str``.
        default: Value returned when the XML attribute is absent.
        doc: Docstring shown for the field (surfaces via ``help()``/IDE hover).
    """

    def __init__(
        self,
        xml_name: str,
        *,
        parse: Callable[[str], T],
        unparse: Callable[[T], str] = str,
        default: T | None = None,
        doc: str = "",
    ) -> None:
        """Initialize the field descriptor.

        Args:
            xml_name: The XML attribute name this field reads/writes.
            parse: Converts the raw attribute string to a Python value.
            unparse: Converts a Python value back to an attribute string.
            default: Value returned when the XML attribute is absent.
            doc: Docstring shown for the field.
        """
        self.xml_name = xml_name
        self.parse = parse
        self.unparse = unparse
        self.default = default
        self.__doc__ = doc
        self.name = xml_name

    def __set_name__(self, owner: type, name: str) -> None:
        """Register this field under *name* in the owning class's registry.

        Args:
            owner: The class this descriptor was assigned on.
            name: The attribute name it was assigned to.
        """
        self.name = name
        # Copy-on-write so each class's registry only contains fields
        # declared on it or an ancestor, without mutating the ancestor's dict.
        registry: dict[str, XmlField[Any]] = dict(getattr(owner, "_fields", {}))
        registry[name] = self
        owner._fields = registry

    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> XmlField[T]: ...
    @overload
    def __get__(self, obj: XmlAttrMixin, objtype: type | None = None) -> T: ...

    def __get__(
        self, obj: XmlAttrMixin | None, objtype: type | None = None
    ) -> XmlField[T] | T:
        """Read and convert the underlying XML attribute.

        Args:
            obj: The owning instance, or ``None`` when accessed on the class.
            objtype: The owning class.

        Returns:
            This descriptor itself when accessed on the class; otherwise the
            parsed attribute value, or :attr:`default` if the XML attribute
            is absent.
        """
        if obj is None:
            return self
        raw = obj._element.get(self.xml_name)
        # Fields declared with default=None may return None at runtime.
        return cast(T, self.default) if raw is None else self.parse(raw)

    def __set__(self, obj: XmlAttrMixin, value: T | None) -> None:
        """Convert and write *value* to the underlying XML attribute.

        Args:
            obj: The owning instance.
            value: The new value, or ``None`` to remove the XML attribute.
        """
        if value is None:
            obj._element.attrib.pop(self.xml_name, None)
        else:
            obj._element.set(self.xml_name, self.unparse(value))


def str_attr(
    xml_name: str, *, default: str | None = "", doc: str = ""
) -> XmlField[str]:
    """Create a plain string-valued :class:`XmlField`.

    Args:
        xml_name: The XML attribute name.
        default: Value returned when the attribute is absent. Pass ``None``
            (instead of the usual ``""``) for attributes that are entirely
            absent in some export contexts (e.g. controller firmware/date
            attributes on a "Context" controller element) and should be
            distinguishable from "present but empty".
        doc: Docstring for the field.

    Returns:
        An :class:`XmlField` that reads/writes the attribute as-is.
    """
    return XmlField(xml_name, parse=str, unparse=str, default=default, doc=doc)


def bool_attr(
    xml_name: str,
    *,
    default: bool | None = None,
    true_str: str = "true",
    false_str: str = "false",
    doc: str = "",
) -> XmlField[bool]:
    """Create a word-valued boolean :class:`XmlField` (e.g. ``"true"``/``"false"``).

    Matched case-insensitively against *true_str* on read. Use
    ``true_str="TRUE", false_str="FALSE"`` for attributes exported in upper
    case (e.g. ``CacheConnections``); the L5X convention is inconsistent
    between elements, so this is not hard-coded.

    Args:
        xml_name: The XML attribute name.
        default: Value returned when the attribute is absent.
        true_str: The attribute string written for ``True``, and matched
            (case-insensitively) as the "true" word on read.
        false_str: The attribute string written for ``False``.
        doc: Docstring for the field.

    Returns:
        An :class:`XmlField` for word-style boolean attributes.
    """

    def _parse(raw: str) -> bool:
        return raw.strip().lower() == true_str.lower()

    def _unparse(value: bool) -> str:
        return true_str if value else false_str

    return XmlField(xml_name, parse=_parse, unparse=_unparse, default=default, doc=doc)


def flag_attr(
    xml_name: str, *, default: bool | None = None, doc: str = ""
) -> XmlField[bool]:
    """Create a numeric-flag boolean :class:`XmlField` (``"1"``/``"0"``).

    Args:
        xml_name: The XML attribute name.
        default: Value returned when the attribute is absent.
        doc: Docstring for the field.

    Returns:
        An :class:`XmlField` for ``"1"``/``"0"``-style boolean attributes.
    """

    def _parse(raw: str) -> bool:
        return raw.strip() == "1"

    def _unparse(value: bool) -> str:
        return "1" if value else "0"

    return XmlField(xml_name, parse=_parse, unparse=_unparse, default=default, doc=doc)


def int_attr(
    xml_name: str, *, default: int | None = None, doc: str = ""
) -> XmlField[int]:
    """Create an integer-valued :class:`XmlField`.

    Empty or unparsable text is treated the same as an absent attribute
    (returns *default*), matching the historical behaviour of this parser's
    hand-written numeric properties.

    Args:
        xml_name: The XML attribute name.
        default: Value returned when the attribute is absent, empty, or
            unparsable.
        doc: Docstring for the field.

    Returns:
        An :class:`XmlField` for integer attributes.
    """

    def _parse(raw: str) -> int:
        if not raw:
            return default  # type: ignore[return-value]
        try:
            return int(raw)
        except ValueError:
            return default  # type: ignore[return-value]

    return XmlField(xml_name, parse=_parse, unparse=str, default=default, doc=doc)


def float_attr(
    xml_name: str, *, default: float | None = None, doc: str = ""
) -> XmlField[float]:
    """Create a floating-point-valued :class:`XmlField`.

    Empty or unparsable text is treated the same as an absent attribute
    (returns *default*), matching the historical behaviour of this parser's
    hand-written numeric properties.

    Args:
        xml_name: The XML attribute name.
        default: Value returned when the attribute is absent, empty, or
            unparsable.
        doc: Docstring for the field.

    Returns:
        An :class:`XmlField` for floating-point attributes.
    """

    def _parse(raw: str) -> float:
        if not raw:
            return default  # type: ignore[return-value]
        try:
            return float(raw)
        except ValueError:
            return default  # type: ignore[return-value]

    return XmlField(xml_name, parse=_parse, unparse=str, default=default, doc=doc)


class CDataField:
    """Descriptor for a CDATA-bearing child element (e.g. ``Description``).

    After CDATA pre-processing in ``_load_l5x``, ``<![CDATA[...]]>`` sections
    are stored as a child element whose tag is ``CDATA_TAG``::

        <Description><CDataContent>text</CDataContent></Description>

    Reading delegates to :meth:`XmlAttrMixin._get_cdata_child` (with an
    optional plain-attribute fallback for elements like ``<Tag>`` that
    sometimes carry a bare ``Description="..."`` attribute instead). Writing
    creates/updates/removes that child element -- setting ``None`` or ``""``
    removes it (and the fallback attribute, if any) entirely.

    Participates in the same per-class ``_fields`` registry as
    :class:`XmlField`, so it shows up in :meth:`BaseElement.fields`/
    :meth:`BaseElement.describe` alongside ordinary attribute fields.

    Args:
        child_tag: The child element name to read/write (e.g.
            ``"Description"``, ``"EngineeringUnit"``).
        attr_fallback: A plain XML attribute name to fall back to on read
            (and clear on write) when no CDATA child is present/being set.
        doc: Docstring shown for the field.
    """

    def __init__(
        self, child_tag: str, *, attr_fallback: str | None = None, doc: str = ""
    ) -> None:
        """Initialize the field descriptor.

        Args:
            child_tag: The child element name to read/write.
            attr_fallback: A plain XML attribute name to fall back to.
            doc: Docstring shown for the field.
        """
        self.child_tag = child_tag
        self.attr_fallback = attr_fallback
        #: Exposed for symmetry with XmlField so fields()/describe() work
        #: uniformly; this isn't an XML *attribute* name but the child tag.
        self.xml_name = child_tag
        self.default = ""
        self.__doc__ = doc
        self.name = child_tag

    def __set_name__(self, owner: type, name: str) -> None:
        """Register this field under *name* in the owning class's registry.

        Args:
            owner: The class this descriptor was assigned on.
            name: The attribute name it was assigned to.
        """
        self.name = name
        registry: dict[str, XmlField[Any] | CDataField] = dict(
            getattr(owner, "_fields", {})
        )
        registry[name] = self
        owner._fields = registry

    @overload
    def __get__(self, obj: None, objtype: type | None = None) -> CDataField: ...
    @overload
    def __get__(self, obj: XmlAttrMixin, objtype: type | None = None) -> str: ...

    def __get__(
        self, obj: XmlAttrMixin | None, objtype: type | None = None
    ) -> CDataField | str:
        """Read the CDATA text (or fallback attribute) for this field.

        Args:
            obj: The owning instance, or ``None`` when accessed on the class.
            objtype: The owning class.

        Returns:
            This descriptor itself when accessed on the class; otherwise the
            stripped text content, or ``""`` if absent.
        """
        if obj is None:
            return self
        text = obj._get_cdata_child(self.child_tag)
        if not text and self.attr_fallback:
            text = obj._element.get(self.attr_fallback, "")
        return text

    def __set__(self, obj: XmlAttrMixin, value: str | None) -> None:
        """Create/update/remove the CDATA child element for this field.

        Args:
            obj: The owning instance.
            value: The new text content, or ``None``/``""`` to remove the
                child element (and fallback attribute, if any).
        """
        child = obj._element.find(self.child_tag)
        if not value:
            if child is not None:
                obj._element.remove(child)
            if self.attr_fallback:
                obj._element.attrib.pop(self.attr_fallback, None)
            return
        if child is None:
            child = ET.SubElement(obj._element, self.child_tag)
        else:
            child.clear()
        cdata_el = ET.SubElement(child, CDATA_TAG)
        cdata_el.text = value


class BaseElement(XmlAttrMixin):
    """Wraps a single XML element and provides helpers for subclasses.

    Subclasses declare known XML attributes as :class:`XmlField` descriptors
    (see :func:`str_attr`/:func:`bool_attr`/:func:`flag_attr`/:func:`int_attr`/
    :func:`float_attr`) and CDATA-bearing children as :class:`CDataField`,
    which are collected into a per-class ``_fields`` registry used by
    :meth:`fields` and :meth:`describe`. Unrecognised attributes remain
    accessible via :attr:`extra_attributes`/:attr:`attributes`.

    Attributes:
        _element: The underlying XML element to wrap.
    """

    #: name -> XmlField/CDataField, populated automatically by
    #: XmlField.__set_name__/CDataField.__set_name__. Never mutated
    #: directly; each subclass gets its own copy-on-write dict.
    _fields: dict[str, XmlField[Any] | CDataField] = {}

    def __init__(self, element: ET.Element) -> None:
        """Initialize the base element wrapper.

        Args:
            element: The underlying XML element to wrap. Stored as
                ``_element`` for attribute access by subclasses.
        """
        # Use object.__setattr__ so subclass @property setters work without
        # hitting any custom __setattr__ we might add later.
        object.__setattr__(self, "_element", element)

    @classmethod
    def fields(cls) -> dict[str, str]:
        """Return every declared field name mapped to its XML attribute name.

        Includes fields inherited from base classes. Useful for discovering
        what a class *can* expose, independent of what's populated on any
        particular instance -- see :meth:`describe` for the populated subset.

        Returns:
            A dict of Python attribute name -> XML attribute name.
        """
        return {name: field.xml_name for name, field in cls._fields.items()}

    @property
    def extra_attributes(self) -> dict[str, str]:
        """XML attributes on this element with no declared :class:`XmlField`.

        A declared :class:`CDataField` with an ``attr_fallback`` also
        reserves that plain-attribute name, since it's an alternate
        representation of the same field.

        Returns:
            A dict of attribute name to raw string value, for attributes not
            covered by any field declared on this class.
        """
        known: set[str] = set()
        for field in type(self)._fields.values():
            known.add(field.xml_name)
            fallback = getattr(field, "attr_fallback", None)
            if fallback:
                known.add(fallback)
        return {k: v for k, v in self._element.attrib.items() if k not in known}

    @property
    def attributes(self) -> dict[str, str]:
        """All XML attributes on this element, known or not.

        Returns:
            A dict of every attribute name to its raw string value.
        """
        return dict(self._element.attrib)

    def _header(self) -> str:
        """Return the single-line header shown at the top of :meth:`describe`.

        Defaults to a concise ``ClassName('Name')`` form (or ``ClassName()``
        when no ``Name`` attribute is present). Subclasses with richer
        identity (e.g. tags, which also carry a data type) override this so
        that :meth:`describe` and :meth:`__repr__` share the same header.

        Returns:
            A single-line header string for this element.
        """
        name = self._element.get("Name", "")
        return (
            f"{self.__class__.__name__}({name!r})"
            if name
            else f"{self.__class__.__name__}()"
        )

    def describe(self) -> str:
        """Return a multi-line summary of only this instance's populated fields.

        Unlike :meth:`fields` (every field a class *can* have), this shows
        only fields whose value differs from their declared default --
        answering "what actually matters for this particular element?".
        Attributes not covered by any declared field are listed separately.

        The first line comes from :meth:`_header` rather than :meth:`__repr__`,
        so subclasses may safely make their ``__repr__`` return the full
        :meth:`describe` output without recursing.

        Returns:
            A formatted multi-line string suitable for interactive/debug use.
        """
        lines = [self._header()]
        for name, field in type(self)._fields.items():
            value = getattr(self, name)
            if value != field.default:
                lines.append(f"  {name} = {value!r}")
        extras = self.extra_attributes
        if extras:
            lines.append("  Extra Attributes:")
            for k, v in sorted(extras.items()):
                lines.append(f"    {k} = {v!r}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        """Return a concise representation including the element name.

        Returns:
            A string of the form ``ClassName('Name')`` if a ``Name``
            attribute exists, otherwise ``ClassName()``.
        """
        return self._header()


class BaseCollection[T](Mapping[str, T]):
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
        item_class: Callable[..., T],
        item_args: tuple[Any, ...] = (),
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

    def __getitem__(self, name: str) -> T:
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

    def __iter__(self) -> Iterator[str]:
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

        Each item name is printed on its own line so that large collections
        remain easy to scan.

        Returns:
            A string of the form::

                ClassName([
                    'name1',
                    'name2'
                ])
        """
        names = list(self)
        if not names:
            return f"{self.__class__.__name__}([])"
        items = ",\n    ".join(repr(name) for name in names)
        return f"{self.__class__.__name__}([\n    {items}\n])"

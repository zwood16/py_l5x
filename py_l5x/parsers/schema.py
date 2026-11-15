"""Child element ordering for L5X documents.

Studio 5000 rejects an import when child elements appear out of schema order
(``XMLSrv_E_ELEMENT_OUT_OF_ORDER``). :data:`CHILD_ORDER` lists the child
order per parent tag (taken from real Studio v37 exports) and
:func:`insert_child` places a new child accordingly while keeping Studio's
one-element-per-line whitespace layout: the parent's ``text`` is ``"\\n"``
and every child's ``tail`` is ``"\\n"``.

Parents or children missing from :data:`CHILD_ORDER` are never an error; new
children of unknown kinds are simply appended.
"""

from xml.etree import ElementTree as ET

from py_l5x.parsers.utils import CDATA_TAG

_TAG_VALUE_ORDER = (
    "Description",
    "Comments",
    "EngineeringUnits",
    "Maxes",
    "Mins",
    "State0s",
    "State1s",
    "ExternalLoggings",
)

#: Parent tag -> child tags in the order Studio requires.
CHILD_ORDER: dict[str, tuple[str, ...]] = {
    "Tag": (
        "ConsumeInfo",
        "ProduceInfo",
        *_TAG_VALUE_ORDER,
        "Data",
    ),
    "DataType": ("Description", "Members", "Dependencies"),
    "Member": ("Description", "EngineeringUnit", "State0", "State1"),
    "Parameter": (*_TAG_VALUE_ORDER, "DefaultData"),
    "LocalTag": (*_TAG_VALUE_ORDER, "DefaultData"),
    "AddOnInstructionDefinition": (
        "Description",
        "RevisionNote",
        "AdditionalHelpText",
        "Parameters",
        "LocalTags",
        "Routines",
        "Dependencies",
    ),
    "Program": ("Description", "Tags", "Routines"),
    "Routine": ("Description", "RLLContent", "STContent"),
    "Rung": ("Comment", "Text"),
    "Task": ("Description", "EventInfo", "ScheduledPrograms"),
    "Module": (
        "Description",
        "EKey",
        "Ports",
        "Communications",
        "ExtendedProperties",
    ),
    "Controller": (
        "Description",
        "RedundancyInfo",
        "Security",
        "SafetyInfo",
        "DataTypes",
        "Modules",
        "AddOnInstructionDefinitions",
        "Tags",
        "Programs",
        "SafetySignaturesHmac",
        "Tasks",
        "CST",
        "WallClockTime",
        "Trends",
        "DataLogs",
        "TimeSynchronize",
        "EthernetPorts",
        "OpcUaInfo",
    ),
}

#: Child tags that may repeat within one slot, ordered by ``Format``.
_MULTI_FORMAT_TAGS = frozenset({"Data", "DefaultData"})


def new_cdata_element(tag: str, text: str) -> ET.Element:
    """Build an element holding one CDATA section, shaped like a loaded file.

    The result is ``<tag>\\n<CDataContent>text</CDataContent>\\n</tag>``: the
    element's ``text`` and the CDATA child's ``tail`` are both ``"\\n"``. The
    element's own ``tail`` is left unset; :func:`insert_child` assigns it.

    Args:
        tag: The element name (for example ``"Description"``).
        text: The CDATA text.

    Returns:
        The new element.
    """
    element = ET.Element(tag)
    element.text = "\n"
    cdata = ET.SubElement(element, CDATA_TAG)
    cdata.text = text
    cdata.tail = "\n"
    return element


def insert_child(parent: ET.Element, child: ET.Element) -> ET.Element:
    """Insert *child* into *parent* at its schema position.

    The child goes before the first existing child with a greater rank, or
    is appended when there is none, when the parent tag is not in
    :data:`CHILD_ORDER`, or when the child tag is not listed for the parent.
    Existing children with unlisted tags are ignored when comparing. For
    ``Data``/``DefaultData`` a new ``Format="L5K"`` element goes first in its
    slot; any other format goes after the existing ones.

    Whitespace is kept in Studio's layout: the child's ``tail`` becomes
    ``"\\n"``, an empty parent ``text`` becomes ``"\\n"``, and the preceding
    sibling's ``tail`` (or the parent's ``text``) is made to end with a
    newline so no two elements share a line.

    Args:
        parent: The element to insert into.
        child: The new element.

    Returns:
        *child*.
    """
    order = CHILD_ORDER.get(parent.tag)
    index = len(parent)
    if order is not None and child.tag in order:
        rank = order.index(child.tag)
        l5k_first = child.tag in _MULTI_FORMAT_TAGS and child.get("Format") == "L5K"
        for i, existing in enumerate(parent):
            if existing.tag not in order:
                continue
            existing_rank = order.index(existing.tag)
            if existing_rank > rank or (l5k_first and existing_rank == rank):
                index = i
                break
    parent.insert(index, child)

    child.tail = "\n"
    if index == 0:
        if not (parent.text or "").strip():
            parent.text = "\n"
        elif not parent.text.endswith("\n"):
            parent.text += "\n"
    else:
        previous = parent[index - 1]
        if not (previous.tail or "").endswith("\n"):
            previous.tail = (previous.tail or "") + "\n"
    return child


def remove_child(parent: ET.Element, child: ET.Element) -> None:
    """Remove *child* from *parent* without joining two elements on one line.

    Args:
        parent: The element containing *child*.
        child: The child to remove.
    """
    children = list(parent)
    index = children.index(child)
    parent.remove(child)
    if index + 1 >= len(children):
        return
    if index == 0:
        if not (parent.text or "").endswith("\n"):
            parent.text = (parent.text or "") + "\n"
    else:
        previous = children[index - 1]
        if not (previous.tail or "").endswith("\n"):
            previous.tail = (previous.tail or "") + "\n"

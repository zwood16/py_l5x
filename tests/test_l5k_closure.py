"""L5K handling for data that reaches AOIs (stale after layout changes, kept on writes).

An AOI instance's decorated data holds only its Input/Output parameters; its L5K
data also holds the AOI's local tag values, which only L5K has. So replacing a
type drops L5K from every dependent owner, while ordinary value writes keep it
for data that contains AOI instances.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from py_l5x import MemberSpec, Project, load, loads
from py_l5x.parsers.migrate import type_dependents

FIXTURES = Path(__file__).parent / "fixtures"


def _example() -> Project:
    """Load the main example project.

    Returns:
        The parsed project.
    """
    return load(str(FIXTURES / "example.L5X"))


def _l5k(owner: ET.Element) -> list[ET.Element]:
    """Return an owner's L5K data blocks.

    Args:
        owner: A ``Tag``, ``Parameter`` or ``LocalTag``.

    Returns:
        The ``Data``/``DefaultData`` children with ``Format="L5K"``.
    """
    return [
        child
        for child in owner
        if child.tag in ("Data", "DefaultData") and child.get("Format") == "L5K"
    ]


def _owners(project: Project) -> list[tuple[str, ET.Element]]:
    """List every tag, parameter and local tag that has L5K data.

    Args:
        project: The project.

    Returns:
        ``(description, element)`` pairs.
    """
    out = []
    controller = project.controller_element
    for tag in controller.findall("Tags/Tag"):
        out.append((f"controller {tag.get('Name')}", tag))
    for program in controller.findall("Programs/Program"):
        for tag in program.findall("Tags/Tag"):
            out.append((f"{program.get('Name')} {tag.get('Name')}", tag))
    for aoi in controller.findall(
        "AddOnInstructionDefinitions/AddOnInstructionDefinition"
    ):
        for item in [
            *aoi.findall("Parameters/Parameter"),
            *aoi.findall("LocalTags/LocalTag"),
        ]:
            out.append((f"{aoi.get('Name')} {item.get('Name')}", item))
    return [(name, el) for name, el in out if _l5k(el)]


class TestClosure:
    """type_dependents."""

    def test_debounce(self) -> None:
        """Debounce reaches GenericInput (local) and A_UDT (member)."""
        closure = type_dependents(_example().controller_element, "Debounce")
        assert closure == {"Debounce", "GenericInput", "A_UDT"}

    def test_simple_udt(self) -> None:
        """simple_udt reaches A_UDT."""
        closure = type_dependents(_example().controller_element, "simple_udt")
        assert closure == {"simple_udt", "A_UDT"}

    def test_locals_and_inout_parameters_count(self) -> None:
        """Locals and InOut parameters of any usage are dependencies."""
        closure = type_dependents(_example().controller_element, "SeqCtrl")
        assert closure == {"SeqCtrl", "FanucRobot"}
        closure = type_dependents(_example().controller_element, "FanucPNS")
        assert closure == {"FanucPNS", "FanucRobot"}

    def test_transitive_and_unrelated(self) -> None:
        """Chains are followed; types nothing uses are alone."""
        project = _example()
        assert type_dependents(project.controller_element, "robotUI") >= {
            "robotUI",
            "FanucPNS",
            "FanucRobot",
        }
        assert type_dependents(project.controller_element, "TIMER") >= {
            "TIMER",
            "Debounce",
            "GenericInput",
            "A_UDT",
        }
        assert type_dependents(project.controller_element, "Nope") == {"Nope"}

    def test_contains_aoi(self) -> None:
        """AOIs and UDTs holding AOI members contain AOI data."""
        registry = _example()._type_registry
        assert registry.contains_aoi("Debounce")
        assert registry.contains_aoi("A_UDT")
        assert not registry.contains_aoi("simple_udt")
        assert not registry.contains_aoi("TIMER")
        assert not registry.contains_aoi("DINT")
        assert not registry.contains_aoi("Unknown")


class TestReplaceDropsDependentL5K:
    """Replacing a type drops L5K from every dependent owner."""

    def test_replace_debounce(self) -> None:
        """TestInput, A_UDT instances and the GenericInput local lose L5K."""
        project = _example()
        closure = type_dependents(project.controller_element, "Debounce")
        before = _owners(project)
        names = {name for name, _ in before}
        assert {"AnotherProgram TestInput", "MainProgram a_udt_instance"} <= names
        spec = project.aois["Debounce"].to_spec()
        spec.parameters.insert(0, type(spec.parameters[0])("extra", "DINT"))
        project.aois.replace(spec)
        after = {name for name, _ in _owners(project)}
        for name, element in before:
            if name.startswith("Debounce "):
                continue  # the rebuilt definition never emits L5K
            dependent = element.get("DataType") in closure
            assert (name in after) != dependent, name
        assert "AnotherProgram TestInput" not in after
        assert "MainProgram a_udt_instance" not in after
        assert "GenericInput debounce" not in after
        assert "MainProgram a_timer" in after
        assert "MainProgram a_dint" in after

    def test_replace_simple_udt(self) -> None:
        """Tags reaching simple_udt through UDT members lose L5K."""
        project = _example()
        before = _owners(project)
        project.data_types.replace(project.data_types["simple_udt"].to_spec())
        after = {name for name, _ in _owners(project)}
        assert "MainProgram a_simple_udt_instance" not in after
        assert "MainProgram a_udt_instance" not in after
        assert "MainProgram a_timer" in after
        gone = {name for name, _ in before} - after
        closure = type_dependents(project.controller_element, "simple_udt")
        for name, element in before:
            if name in gone:
                assert element.get("DataType") in closure

    _DOC = """<RSLogix5000Content><Controller Name="C">
<DataTypes>
<DataType Name="U" Family="NoFamily" Class="User">
<Members>
<Member Name="a" DataType="DINT" Dimension="0" Radix="Decimal" Hidden="false" ExternalAccess="Read/Write"/>
</Members>
</DataType>
</DataTypes>
<AddOnInstructionDefinitions>
<AddOnInstructionDefinition Name="A" Revision="1.0">
<Parameters>
<Parameter Name="p" TagType="Base" DataType="DINT" Usage="Input" Radix="Decimal" Required="false" Visible="false" ExternalAccess="Read/Write">
<DefaultData Format="L5K"><![CDATA[0]]></DefaultData>
<DefaultData Format="Decorated"><DataValue DataType="DINT" Radix="Decimal" Value="0"/></DefaultData>
</Parameter>
</Parameters>
<LocalTags>
<LocalTag Name="loc" DataType="U" ExternalAccess="None">
<DefaultData Format="L5K"><![CDATA[[5]]]></DefaultData>
<DefaultData Format="Decorated"><Structure DataType="U"><DataValueMember Name="a" DataType="DINT" Radix="Decimal" Value="5"/></Structure></DefaultData>
</LocalTag>
</LocalTags>
<Routines><Routine Name="Logic" Type="RLL"><RLLContent/></Routine></Routines>
</AddOnInstructionDefinition>
</AddOnInstructionDefinitions>
<Tags>
<Tag Name="inst" TagType="Base" DataType="A">
<Data Format="L5K"><![CDATA[[0,[5]]]]></Data>
<Data Format="Decorated"><Structure DataType="A"><DataValueMember Name="p" DataType="DINT" Radix="Decimal" Value="0"/></Structure></Data>
</Tag>
<Tag Name="plain" TagType="Base" DataType="DINT" Radix="Decimal">
<Data Format="L5K"><![CDATA[3]]></Data>
<Data Format="Decorated"><DataValue DataType="DINT" Radix="Decimal" Value="3"/></Data>
</Tag>
</Tags>
</Controller></RSLogix5000Content>"""  # noqa: E501

    def test_udt_reached_through_aoi_local(self) -> None:
        """An AOI-typed tag loses L5K when the UDT of its local changes."""
        project = loads(self._DOC)
        spec = project.data_types["U"].to_spec()
        spec.members.append(MemberSpec("b", "DINT"))
        project.data_types.replace(spec)
        tags = project.controller_tags
        assert not _l5k(tags["inst"]._element)
        assert _l5k(tags["plain"]._element)
        loc = project.aois["A"].local_tags["loc"]
        assert not _l5k(loc._element)
        assert loc.to_python() == {"a": 5, "b": 0}
        assert _l5k(project.aois["A"].parameters["p"]._element)  # type DINT: untouched

    def test_replace_aoi_drops_dependents(self) -> None:
        """Replacing the AOI drops L5K of its instances; others keep it."""
        project = loads(self._DOC)
        spec = project.aois["A"].to_spec()
        spec.parameters.append(type(spec.parameters[0])("q", "DINT"))
        project.aois.replace(spec)
        assert not _l5k(project.controller_tags["inst"]._element)
        assert _l5k(project.controller_tags["plain"]._element)


class TestWritesKeepAoiL5K:
    """Value writes keep L5K where the data contains AOI instances."""

    @staticmethod
    def _text(element: ET.Element) -> list[bytes]:
        """Serialize an owner's L5K blocks for comparison.

        Args:
            element: The owner.

        Returns:
            One byte string per L5K block.
        """
        return [ET.tostring(block) for block in _l5k(element)]

    def test_aoi_typed_tag_parameter(self) -> None:
        """TestInput.onDelay: L5K is byte-identical, Decorated changes."""
        project = _example()
        tag = project.programs["AnotherProgram"].tags["TestInput"]
        before = self._text(tag._element)
        assert before
        tag.members["onDelay"].value = 999
        assert self._text(tag._element) == before
        assert tag.members["onDelay"].value == 999
        again = loads(project.to_string()).programs["AnotherProgram"].tags["TestInput"]
        assert again.members["onDelay"].value == 999

    def test_dict_assignment_on_aoi_tag(self) -> None:
        """sequence (SeqCtrl) keeps L5K through a dict assignment."""
        project = _example()
        tag = project.programs["MainProgram"].tags["sequence"]
        before = self._text(tag._element)
        assert before
        tag.value = {"mode": True}
        assert self._text(tag._element) == before
        assert tag.members["mode"].value is True

    def test_udt_with_aoi_member(self) -> None:
        """A UDT containing an AOI keeps L5K, even writing a plain member."""
        project = _example()
        tag = project.programs["MainProgram"].tags["a_udt_instance"]
        before = self._text(tag._element)
        tag.members["a_dint"].value = 8
        assert self._text(tag._element) == before
        tag.members["an_aoi"].members["onDelay"].value = 77
        assert self._text(tag._element) == before

    def test_array_element_of_udt_with_aoi(self) -> None:
        """Nested array members of AOI-containing data keep L5K too."""
        project = _example()
        tag = project.programs["MainProgram"].tags["a_udt_instance"]
        before = self._text(tag._element)
        tag.members["an_array"][1].value = 2.5
        assert self._text(tag._element) == before

    @pytest.mark.parametrize(
        "name", ["a_dint", "a_timer", "a_simple_udt_instance", "a_2d_array", "a_string"]
    )
    def test_other_types_drop_l5k(self, name: str) -> None:
        """Plain DINT, TIMER, UDT without AOI, arrays and strings drop L5K."""
        project = _example()
        tag = project.programs["MainProgram"].tags[name]
        assert _l5k(tag._element)
        if name == "a_dint":
            tag.value = 5
        elif name == "a_timer":
            tag.members["PRE"].value = 5
        elif name == "a_simple_udt_instance":
            tag.value = {"Dint": 5}
        elif name == "a_2d_array":
            tag.value = {0: 5}
        else:
            tag.value = "x"
        assert not _l5k(tag._element)

    def test_initialize_data_keeps_l5k_for_aoi(self) -> None:
        """initialize_data on a data-less AOI tag keeps its L5K block."""
        project = loads(TestReplaceDropsDependentL5K._DOC)
        tag = project.controller_tags["inst"]
        decorated = tag._element.find("Data[@Format='Decorated']")
        tag._element.remove(decorated)
        before = self._text(tag._element)
        tag = project.controller_tags["inst"]
        tag.initialize_data()
        assert self._text(tag._element) == before
        assert tag._element.find("Data[@Format='Decorated']") is not None

    def test_aoi_parameter_default_write(self) -> None:
        """A parameter of plain type still drops its L5K on a write."""
        project = _example()
        parameter = project.aois["Debounce"].parameters["onDelay"]
        assert _l5k(parameter._element)
        parameter.value = 5
        assert not _l5k(parameter._element)

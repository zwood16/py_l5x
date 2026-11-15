"""Tests for the L5X writer (``py_l5x.writer``) and ``loads``."""

import re
from pathlib import Path

import pytest

from py_l5x import Project, load, loads
from py_l5x.parsers.utils import CDATA_TAG
from py_l5x.writer import to_bytes, to_string, write

FIXTURES = Path(__file__).parent / "fixtures"
L5X_FILES = sorted(FIXTURES.glob("*.L5X"))

_CDATA_SPLIT_RE = re.compile(r"(<!\[CDATA\[.*?\]\]>)", re.DOTALL)
_TAG_RE = re.compile(r"<[^<>!?/][^<>]*>|<[^<>!?/][^<>]*/>")


def _collapse_tag(match: re.Match) -> str:
    """Collapse whitespace runs inside a start or empty tag to one space.

    Args:
        match: Match of a complete start/empty tag.

    Returns:
        The tag with whitespace normalized and no space before ``>``.
    """
    tag = re.sub(r"\s+", " ", match.group(0))
    return re.sub(r" (/?>)$", r"\1", tag)


def normalize(text: str) -> str:
    """Normalize L5X text for comparison.

    Strips the BOM, converts CRLF to LF, and collapses whitespace inside
    start/empty tags outside CDATA sections.

    Args:
        text: L5X document text.

    Returns:
        The normalized text.
    """
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    parts = _CDATA_SPLIT_RE.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = _TAG_RE.sub(_collapse_tag, parts[i])
    return "".join(parts)


def _summary(project: Project) -> dict:
    """Collect a comparable summary of a project.

    Args:
        project: The project to summarize.

    Returns:
        A dict of names, logic text and tag values.
    """

    def routine_info(routines) -> dict:
        out = {}
        for name, routine in routines.items():
            out[name] = (
                routine.type_,
                [(r.number, r.text, r.comment) for r in routine.rungs],
                routine.st_code,
            )
        return out

    def tag_info(tags) -> dict:
        return {
            name: (type(tag).__name__, tag.data_type, repr(tag))
            for name, tag in tags.items()
        }

    return {
        "controller": project.controller.name,
        "data_types": sorted(project.data_types),
        "aois": {
            name: (
                routine_info(aoi.routines),
                sorted(aoi.local_tags),
            )
            for name, aoi in project.aois.items()
        },
        "controller_tags": tag_info(project.controller_tags),
        "programs": {
            name: (routine_info(prog.routines), tag_info(prog.tags))
            for name, prog in project.programs.items()
        },
    }


@pytest.mark.parametrize("path", L5X_FILES, ids=lambda p: p.name)
class TestRoundTrip:
    """Round trips over every fixture."""

    def test_text(self, path: Path) -> None:
        """Serialized text matches the original after normalization."""
        original = path.read_text(encoding="utf-8")
        assert normalize(original) == normalize(load(str(path)).to_string())

    def test_objects(self, path: Path) -> None:
        """Reloading serialized text yields the same object model."""
        project = load(str(path))
        again = loads(project.to_string())
        assert _summary(again) == _summary(project)


class TestBytes:
    """Byte-level output checks."""

    @pytest.fixture
    def root(self):
        """Root element of the simple example project."""
        return load(str(FIXTURES / "simple_example.L5X")).root

    def test_bom_default(self, root) -> None:
        """A BOM is written by default."""
        assert to_bytes(root).startswith(b"\xef\xbb\xbf<?xml")

    def test_no_bom(self, root) -> None:
        """bom=False omits the BOM."""
        assert to_bytes(root, bom=False).startswith(b"<?xml")

    def test_crlf_default(self, root) -> None:
        """Line endings are CRLF with no bare LF."""
        data = to_bytes(root)
        assert b"\r\n" in data
        assert b"\n" not in data.replace(b"\r\n", b"")

    def test_lf(self, root) -> None:
        """newline='\\n' produces LF only."""
        assert "\r" not in to_string(root, newline="\n")

    def test_ending(self, root) -> None:
        """Output ends with the root close tag and CRLF."""
        assert to_bytes(root).endswith(b"</RSLogix5000Content>\r\n")

    def test_input_not_mutated(self, root) -> None:
        """Serializing leaves the tree unchanged."""
        before = to_string(root)
        to_string(root)
        assert to_string(root) == before
        assert root.find(f".//{CDATA_TAG}") is not None


_CDATA_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0">
<Controller Name="C" ProcessorType="1756-L83E">
<Programs>
<Program Name="P">
<Routines>
<Routine Name="R" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N">
<Comment>
<![CDATA[%s]]>
</Comment>
<Text>
<![CDATA[XIC(a)OTE(b);]]>
</Text>
</Rung>
</RLLContent>
</Routine>
</Routines>
</Program>
</Programs>
</Controller>
</RSLogix5000Content>
"""


def _comment(project: Project) -> str:
    """Return the comment of rung 0 in routine P/R.

    Args:
        project: The project to read.

    Returns:
        The rung comment text.
    """
    return project.programs["P"].routines["R"].rungs[0].comment


class TestCDataEdgeCases:
    """CDATA handling on a small hand-written document."""

    @pytest.mark.parametrize(
        "content",
        [
            "a < b > c",
            "x & y &amp; z",
            "",
            "line1\nline2\n\nline4",
            "\"quoted\" 'single'",
        ],
        ids=["angle", "amp", "empty", "multiline", "quotes"],
    )
    def test_survives(self, content: str) -> None:
        """Content is identical after loads -> to_string -> loads."""
        first = loads(_CDATA_DOC % content)
        assert _comment(first) == content
        text = first.to_string()
        assert CDATA_TAG not in text
        assert "<![CDATA[" in text
        assert _comment(loads(text)) == content

    def test_terminator_is_split(self) -> None:
        """Text containing ``]]>`` is split into two CDATA sections, read back whole."""
        project = loads(_CDATA_DOC % "placeholder")
        element = project.root.find(f".//Comment/{CDATA_TAG}")
        element.text = "a ]]> b"
        text = project.to_string()
        assert "<![CDATA[a ]]]]><![CDATA[> b]]>" in text
        assert CDATA_TAG not in text
        assert _comment(loads(text)) == "a ]]> b"

    def test_empty_cdata_form(self) -> None:
        """Empty CDATA is written as an empty CDATA section."""
        assert "<![CDATA[]]>" in loads(_CDATA_DOC % "").to_string()

    def test_loads_bom_and_crlf(self) -> None:
        """loads strips a BOM and normalizes line endings."""
        text = "﻿" + (_CDATA_DOC % "a\nb").replace("\n", "\r\n")
        assert _comment(loads(text)) == "a\nb"

    def test_loads_bad_xml(self) -> None:
        """loads raises ValueError on invalid XML."""
        with pytest.raises(ValueError):
            loads("<not-closed>")


def test_project_write(tmp_path: Path) -> None:
    """Project.write produces a file that load() can read back."""
    src = FIXTURES / "example.L5X"
    out = tmp_path / "x.L5X"
    project = load(str(src))
    project.write(out)
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")
    assert _summary(load(str(out))) == _summary(project)


def test_write_function(tmp_path: Path) -> None:
    """writer.write honours bom=False."""
    project = load(str(FIXTURES / "simple_example.L5X"))
    out = tmp_path / "y.L5X"
    write(project.root, out, bom=False)
    assert out.read_bytes().startswith(b"<?xml")

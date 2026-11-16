"""Build the packaged built-in type table and the type-defaults test fixture.

Inputs are Studio exports produced by the harness (run these first):
    python3 gen.py exp13 && ./go.sh exp13   # one data-less tag per ProductDefined type
    python3 gen.py exp14 && ./go.sh exp14   # data-less tags of fixture UDT/AOI types

Outputs:
    py_l5x/data/builtin_types_v37.L5X.gz
        One controller tag per built-in type whose value data is Decorated or String,
        holding Studio's default value tree. This is the layout and default table for
        built-in types. L5K data, context data types and tags with special data formats
        (Message, Axis, Alarm, ...) are removed.
    tests/fixtures/type_defaults_Tags.L5X
        Studio's default trees for data-less tags of user types (UDTs, AOIs, arrays),
        with their UDT/AOI definitions as context. Computed defaults are tested
        against this file.

Usage: uv run python tools/sdk/make_type_tables.py
"""

import gzip
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from py_l5x import load, writer  # noqa: E402

VALUE_FORMATS = {"Decorated", "String"}


def _strip_l5k(tag):
    for d in list(tag):
        if d.tag == "Data" and d.get("Format") == "L5K":
            tag.remove(d)


def _strip_owner(root):
    root.attrib.pop("Owner", None)


def builtin_table() -> None:
    p = load(str(HERE / "results" / "exp13" / "all_tags.L5X"))
    root = p.root
    _strip_owner(root)
    root.set("TargetName", "builtin_types")
    c = root.find("Controller")
    c.remove(c.find("DataTypes"))
    tags = c.find("Tags")
    kept = 0
    for tag in list(tags):
        name = tag.get("Name", "")
        formats = {d.get("Format") for d in tag.findall("Data")} - {"L5K"}
        if not name.startswith("bt_") or not formats <= VALUE_FORMATS or not formats:
            tags.remove(tag)
            continue
        _strip_l5k(tag)
        tag.set("Name", name[len("bt_") :])
        kept += 1
    out = ROOT / "py_l5x" / "data" / "builtin_types_v37.L5X.gz"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(gzip.compress(writer.to_bytes(root), mtime=0))
    print(f"{out.relative_to(ROOT)}: {kept} types")


def type_defaults_fixture() -> None:
    p = load(str(HERE / "results" / "exp14" / "all_tags.L5X"))
    root = p.root
    _strip_owner(root)
    c = root.find("Controller")
    tags = c.find("Tags")
    kept = 0
    for tag in list(tags):
        name = tag.get("Name", "")
        if not (name.startswith("d_") or name.startswith("a_")):
            tags.remove(tag)
            continue
        _strip_l5k(tag)
        kept += 1
    out = ROOT / "tests" / "fixtures" / "type_defaults_Tags.L5X"
    writer.write(root, out)
    print(f"{out.relative_to(ROOT)}: {kept} tags")


if __name__ == "__main__":
    builtin_table()
    type_defaults_fixture()

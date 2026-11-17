"""Build the packaged built-in type table and the type-defaults test fixture.

Inputs are Studio exports produced by the harness (run these first):
    python3 gen.py exp13 && ./go.sh exp13   # v37: one data-less tag per ProductDefined type
    python3 gen.py exp31 && ./go.sh exp31   # v38: the same on v38 (adds TIMER_T)
    python3 gen.py exp14 && ./go.sh exp14   # data-less tags of fixture UDT/AOI types
    python3 gen.py exp33 && ./go.sh exp33   # v38 TIMER_T golden fixture

Outputs:
    py_l5x/data/builtin_types.L5X.gz
        One controller tag per built-in type whose value data is Decorated or String,
        holding Studio's default value tree. This is the layout and default table for
        built-in types. It is **cumulative across Logix versions**: built-in type
        definitions never change between versions (verified v37 vs v38: all 206 identical),
        only new types are added, so the sources below are merged by type name with the
        newest version winning. The root ``SoftwareRevision`` is the newest source's.
        L5K data, context data types and tags with special data formats (Message, Axis,
        Alarm, ...) are removed. To add a Logix version, run its per-type export and
        append it to ``BUILTIN_SOURCES``.
    tests/fixtures/v38_timer_t_Tags.L5X
        Studio's export of TIMER_T tags (values and data-less), a UDT with TIMER_T members
        and an AOI with a TIMER_T local (exp33).
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


#: Per-type exports, oldest first. Later sources add new types and win on conflicts.
BUILTIN_SOURCES = [
    HERE / "results" / "exp13" / "all_tags.L5X",  # v37.00, 5069-L310ERMS3 (safety)
    HERE / "results" / "exp31" / "all_type_tags.L5X",  # v38.03, 1756-L85E
]


def _value_tags(path: Path) -> tuple[object, dict[str, object]]:
    """Return a source export's root and its built-in value tags keyed by type name."""
    p = load(str(path))
    found = {}
    for tag in p.root.find("Controller/Tags"):
        name = tag.get("Name", "")
        formats = {d.get("Format") for d in tag.findall("Data")} - {"L5K"}
        if not name.startswith("bt_") or not formats or not formats <= VALUE_FORMATS:
            continue
        _strip_l5k(tag)
        tag.set("Name", name[len("bt_") :])
        found[tag.get("Name")] = tag
    return p.root, found


def builtin_table() -> None:
    merged: dict[str, object] = {}
    root = None
    for src in BUILTIN_SOURCES:
        root, found = _value_tags(src)
        added = sorted(set(found) - set(merged))
        merged.update(found)
        print(
            f"{src.parent.name}: {len(found)} value types, new: {added if len(added) < 20 else len(added)}"
        )
    _strip_owner(root)
    root.set("TargetName", "builtin_types")
    c = root.find("Controller")
    dts = c.find("DataTypes")
    if dts is not None:
        c.remove(dts)
    tags = c.find("Tags")
    for tag in list(tags):
        tags.remove(tag)
    for name in sorted(merged, key=str.lower):
        tags.append(merged[name])
    out = ROOT / "py_l5x" / "data" / "builtin_types.L5X.gz"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(gzip.compress(writer.to_bytes(root), mtime=0))
    print(
        f"{out.relative_to(ROOT)}: {len(merged)} types (SoftwareRevision {root.get('SoftwareRevision')})"
    )


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


def v38_fixture() -> None:
    p = load(str(HERE / "results" / "exp33" / "all_tags.L5X"))
    root = p.root
    _strip_owner(root)
    for tag in root.iter("Tag"):
        _strip_l5k(tag)
    out = ROOT / "tests" / "fixtures" / "v38_timer_t_Tags.L5X"
    writer.write(root, out)
    print(f"{out.relative_to(ROOT)}: written")


if __name__ == "__main__":
    builtin_table()
    type_defaults_fixture()
    v38_fixture()

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`py_l5x` parses Rockwell Studio 5000 Logix Designer `.L5X` exports (full projects and single-component exports) into a typed Python object model. It uses only the standard library (`xml.etree.ElementTree`) and has no runtime dependencies. It requires Python >= 3.12 (it uses PEP 695 generics such as `class XmlField[T]`). It is read-only today, but write-back is on the roadmap (see below). The README is the user-facing API reference; update it when public behavior changes.

## Commands

The project is managed with `uv`. Ruff and pytest are dev dependencies.

```bash
uv run pytest                                   # full suite (~900 tests, a few seconds)
uv run pytest tests/test_tag.py                 # one file
uv run pytest tests/test_tag.py::TestClass::test_name   # one test
uv run pytest -k "operand"                      # by keyword
uv run ruff check .                             # lint (E, F, I, UP, B, SIM; line length 88)
uv run ruff format .                            # format
uv build                                        # build the wheel into dist/
```

Tests load real exports from `tests/fixtures/` (`example.L5X` is the main full project; the `*_Program.L5X`, `*_AOI.L5X` and similar files are component exports). The `.ACD` and `eds/` files there are not used by the tests. `scratch/` is gitignored and is only for ad-hoc experiments.

## Architecture

**Loading** ([py_l5x/parse.py](py_l5x/parse.py)): `load()` uses a regex to replace every `<![CDATA[...]]>` with an XML-escaped `<CDataContent>` element (`CDATA_TAG` in `parsers/utils.py`) before `ET.fromstring`, because ElementTree drops CDATA boundaries. Read CDATA-bearing children (Description, Comment, rung Text, ST lines) through `cdata_text()` / `CDataField` / `_get_cdata_child()`, never through `.text` directly. Any future writer must reverse this substitution.

**Wrappers stay live over the XML** ([py_l5x/parsers/base.py](py_l5x/parsers/base.py)):
- `BaseElement` wraps one `ET.Element`. Attributes are declared as `XmlField` descriptors created with `str_attr` / `bool_attr` / `flag_attr` / `int_attr` / `float_attr`, and CDATA children as `CDataField`. Descriptors read from and write to the element on every access, and setting `None` removes the attribute. Each class gets a copy-on-write `_fields` registry, which drives `fields()`, `describe()` / `__str__`, and `extra_attributes` (attributes that have no declared field). To add summary lines to `describe()`, override `_describe_lines()`, not `describe()`.
- `BaseCollection[T]` is a `Mapping[str, T]` keyed by `Name`. It re-runs `findall` on every access and builds a new wrapper each time, so nothing is cached and wrapper identity is not stable.
- New element types should follow this pattern (declare fields, don't hand-write property getters) so they keep working with `describe()` and with future write support.

**Project assembly** ([py_l5x/parsers/project.py](py_l5x/parsers/project.py)): `Project.__init__` builds `DataTypesCollection` and `AOIDataTypesCollection` first, combines them into a shared `TypeRegistry`, and passes that registry to every collection that holds tags (modules, AOIs, controller tags, programs, tasks). `project.tags` (`ProjectTagsView`) merges controller tags with module I/O tags (`ModuleTagRef`, for example `Local:1:I`). `project.target` dispatches on the root `TargetType` to return the `Use="Target"` element of a component export. For component exports, `ControllerInfo.is_context` is True and the firmware, processor and date fields are `None`.

**Tags and value trees** ([py_l5x/parsers/tag.py](py_l5x/parsers/tag.py), the largest module; read its module docstring first):
- `_make_tag()` picks a `Tag` subclass from the data type and the shape of the `<Data>`. Value tags inherit from both `Tag` and the matching node class (for example `IntegerTag(_ValueTag, IntegerNode)`), so a tag *is* its root value node. Alias, Message, Axis, MotionGroup and Unknown tags have no value tree.
- Values come from the `Decorated` / `String` `<Data>` format. The `L5K` format is deliberately ignored. Type definitions (UDT members, AOI parameters) are used only for metadata (description, min/max, engineering unit, state labels), looked up through `TypeRegistry`.
- Per-operand overrides (`<Comments>`, `<Mins>`, `<EngineeringUnits>`, etc.) are collected by `_TagOverrides`. Resolution order: the instance tag's entry at the full operand path, then each enclosing AOI parameter definition (innermost first, using the relative path), then the member or parameter definition itself.
- [atomic_types.py](py_l5x/parsers/atomic_types.py) holds the atomic type table and the Logix literal parsing (radix prefixes, two's complement, ASCII literals, TIME/LTIME/DT/LDT).

**AOIs** ([py_l5x/parsers/aoi.py](py_l5x/parsers/aoi.py)): parameters and local tags reuse the tag node classes through parallel typed families (`AOIParameter*Tag`, `AOILocal*Tag`) that share `_RootMetadataMixin` with `Tag`. `aoi.py` imports `tag.py` at runtime, so `tag.py` may reference AOI types only under `TYPE_CHECKING`. Avoid adding new import cycles between these modules.

Public API: everything users import is re-exported in [py_l5x/__init__.py](py_l5x/__init__.py) and listed in `__all__`. Add new public classes there.

## Write support (in progress)

Modifying and generating L5X files (phases 1–5 done: writer, in-place edits, type layouts/values, spec builders for UDTs/AOIs/programs/tags, component export, templating). Development and verification target **Logix v37**, but the generated XML is version-neutral: components built for v37 import into v33/v35 with values and UDT packing intact (exp26). Choosing instructions and types that exist in the target version is the user's responsibility (v36 renamed many instructions, e.g. `MOV` → `MOVE`, `EQU` → `EQ`; newer versions added types such as unsigned integers and TIME/DT); Studio rejects or fails to verify the wrong ones. Don't add version-specific instruction or type validation. Rung/ST text is passed through untouched, and built-in type layouts never change between versions (verified v37 vs v38), so the built-in table `py_l5x/data/builtin_types.L5X.gz` is cumulative: add new types by appending a version's per-type export to `BUILTIN_SOURCES` in `tools/sdk/make_type_tables.py` (v38 added only `TIMER_T`, whose `ACC`/`PRE` order is the reverse of `TIMER`). v38 support is verified (exp30–exp33). Note that the SDK's `build()` only works on v37+, so the harness cannot verify logic for older versions. Builders live in `py_l5x/build/` (tracked despite the template's `build/` ignore rule; see the exception at the end of `.gitignore`).
- [docs/write-plan.md](docs/write-plan.md) is the phased plan. Order: serializer and round trip, then editing loaded documents, then type layouts and values, then spec builders.
- [docs/import-format.md](docs/import-format.md) records what Studio actually accepts on import, verified through the SDK. Read it before writing any code that emits XML. Key rules: Decorated tag data must be complete and in order, or it is dropped (sometimes silently), and omitting `<Data>` is safe; never emit L5K data; child elements must be in schema order; always emit `<Dependencies>` on UDTs and AOIs that reference other user types (Studio crashes otherwise); UDT BOOLs use the hidden SINT host plus `BIT` form.
- [tools/sdk/](tools/sdk/) is the SDK verification harness, which runs on the Windows VM. Use it to verify fixtures and golden files; the pytest suite must stay OS- and Rockwell-independent and never call the SDK.

## Conventions

- Google-style docstrings with `Args:` / `Returns:` / `Raises:` on public and private members. Module docstrings carry the design notes.
- Missing XML attributes return the field's default (usually `""` or `None`). Use `default=None` when "absent" has to be distinguishable from "empty".
- Unknown or unsupported L5X content should be preserved and reachable (through `extra_attributes`, `_element`, `Project.root`, or `UnknownTag`), not raise errors.

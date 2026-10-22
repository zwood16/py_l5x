# py_l5x

A pythonic interface for reading Rockwell Automation L5X files.

> [!IMPORTANT]
> **⚠️ Work in Progress**: This project is currently under active development. APIs are subject to change, and not all features may be fully implemented or tested.

`py_l5x` parses Rockwell Automation L5X exports from Studio 5000 Logix Designer and exposes the contents as a typed Python object hierarchy. It handles CDATA sections transparently, resolves packed-boolean bit members, and cross-references type definitions so that every tag's value tree carries full metadata (descriptions, engineering units, min/max bounds, state labels).

Both **full project exports** (an entire `.L5X` file exported from the controller) and **component exports** (a single Program, Routine, AOI, DataType, Module, Rung, or Tag exported in isolation) are supported through the same `load()` API.

## Installation

I don't yet have plans to upload this to PyPi. For now, download the `.whl` and install it manually:

```bash
pip install py_l5x-0.2.0-py3-none-any.whl
```

or

```bash
uv add py_l5x-0.2.0-py3-none-any.whl
```

Or pull it straight from the Github release:

```base
uv add https://github.com/zwood16/py_l5x/releases/download/v0.3.0/py_l5x-0.3.0-py3-none-any.whl
```

Check the [Releases](https://github.com/zwood16/py_l5x/releases) page for the most up to date release files.

## Quick start

```python
from py_l5x import load

project = load("my_project.L5X")
print(project)
# Project('Example_PLC')
#   Target:       Full project
#   Processor:    5069-L310ERMS3
#   Firmware:     37.11
#   Data Types:   9
#   Modules:      17
#   AOIs:         6
#   Controller Tags: 9
#   Programs:     7
#   Tasks:        4
```

`load()` accepts either a `str` path or a `pathlib.Path`. It raises `FileNotFoundError` if the file does not exist and `ValueError` if the file is not valid XML.

## Project hierarchy

A loaded project exposes everything through a tree of typed objects:

```
Project
├── controller          → ControllerInfo
├── data_types          → DataTypesCollection  (keyed by name)
├── aois                → AOICollection         (keyed by name)
├── modules             → ModulesCollection     (keyed by name)
├── tags                → ProjectTagsView       (merged: controller + module I/O tags, keyed by name)
├── controller_tags     → TagsCollection        (controller-scoped only, keyed by name)
├── programs            → ProgramsCollection    (keyed by name)
│   ├── tags            → TagsCollection        (program-local, keyed by name)
│   └── routines        → RoutinesCollection    (keyed by name)
│       ├── rungs       → list[Rung]            (RLL routines)
│       └── st_lines    → list[StLine]          (ST routines)
└── tasks               → TasksCollection       (keyed by name)
```

All collections implement `Mapping[str, T]` so they support the usual `dict`-like access: `project.programs["MainProgram"]`, `"A_UDT" in project.data_types`, `list(project.tags)`, etc.

## Inspecting objects

Most objects (tags, AOI local tags, data types, data type members, AOI parameters, and `ControllerInfo`) print as a multi-line summary of their populated fields. `print(obj)` and `obj.describe()` produce the same output, and `Cls.fields()` lists every field a class can expose (Python attribute name → XML attribute name):

```python
from py_l5x import IntegerTag

tag = project.programs["MainProgram"].tags["an_int"]
print(tag)
# IntegerTag('an_int', 'INT')
#   name = 'an_int'
#   tag_type = 'Base'
#   data_type = 'INT'
#   external_access = 'Read/Write'
#   opc_ua_access = 'None'
#   value: 0
#   radix: 'Decimal'

print(IntegerTag.fields()["data_type"])  # "DataType"
```

Attributes that are present in the XML but not modeled by a field are listed under `Extra Attributes:`. Tags, AOI local tags, and AOI parameters also print an `operand_comments:` block when they have per-operand comments (see [Per-operand metadata](#per-operand-metadata)).

## Controller metadata

The `ControllerInfo` object exposes project-level metadata such as the controller name, processor type, firmware version, and project dates. For full-project exports, all metadata is populated; for component exports (single Programs, AOIs, etc.), this metadata is sparse or `None` since Studio 5000 does not include it in the export envelope.

```python
ctrl = project.controller

print(ctrl.name)  # "Example_PLC"
print(ctrl.processor_type)  # "5069-L310ERMS3"  (None for component exports)
print(ctrl.major_rev)  # "37"             (None for component exports)
print(ctrl.minor_rev)  # "11"             (None for component exports)
print(ctrl.last_modified_date)  # "Mon Oct 19 17:30:00 2026"
print(ctrl.project_sn)  # "16#0000_0000"
print(ctrl.is_context)  # False (True when loaded from a component export)
```

For component exports (see [Component exports](#component-exports)), `is_context` is `True` and the firmware/processor/date attributes are `None` because Studio 5000 does not include them.

## Data types (UDTs)

User-defined data types (UDTs) are custom type definitions that group members (fields) of various data types together. They can be atomic (NoFamily) or string-based (StringFamily). Every UDT member carries metadata like descriptions, engineering units, min/max bounds, and state labels. The `visible_members` property excludes hidden packed-boolean host bytes, showing only user-facing fields.

```python
# Iterate all UDTs - show if the UDT is a custom string
for name, udt in project.data_types.items():
    print(name, "—", udt.family)
# A_UDT — NoFamily
# GenericRobotInputs — NoFamily
# GenericRobotIO — NoFamily
# GenericRobotOutputs — NoFamily
# robotAlarmCode — StringFamily
# robotString — StringFamily
# robotUI — NoFamily
# robotUO — NoFamily
# simple_udt — NoFamily

# Access a specific UDT
udt = project.data_types["A_UDT"]
print(udt.name)  # "A_UDT"
print(udt.family)  # "NoFamily"
print(udt.is_string)  # False

# Iterate visible members (hidden packed-boolean host bytes excluded)
for name, member in udt.visible_members.items():
    print(f"  {name}: {member.data_type}")
    if member.description:
        print(f"    {member.description}")
    if member.engineering_unit:
        print(f"    EU: {member.engineering_unit}")
#   a_Bool: BIT
#     This is a bool
#   on_off_bool: BIT
#     This is a bool with extended properties
#     EU: Boolean
#   a_sint: SINT
#     This is a sint or byte
#   a_sint_with_props: SINT
#     This is a SINT with extended properties
#     EU: mm
#   a_real: REAL
#     a floating point value
#   ... (remaining members)

# STRING-family UDT
stype = project.data_types["robotAlarmCode"]
print(stype.is_string)  # True
print(stype.max_length)  # 8
```

## Add-On Instructions (AOIs)

Add-On Instructions are parameterized routines (logic blocks) that can be instantiated and called like built-in instructions (e.g., `MOV`, `ADD`). Each AOI has parameters (inputs/outputs), local tags (internal state), and one or more routines containing the logic. AOIs are reusable across the project and can be used as building blocks in other programs and AOIs.

```python
for name, aoi in project.aois.items():
    print(name, aoi.revision)
# Debounce 1.2
# GenericInput 1.2
# FanucAlarmLookup 1.0
# FanucPNS 1.0
# SeqCtrl 3.3
# FanucRobot 1.4

aoi = project.aois["Debounce"]
print(aoi.name)  # "Debounce"
print(aoi.revision)  # "1.2"
print(aoi.execute_enable_in_false)  # True

# Parameters
for name, param in aoi.parameters.items():
    print(f"  {name}: {param.data_type} ({param.usage})")
#   EnableIn: BOOL (Input)
#   EnableOut: BOOL (Output)
#   state: BOOL (Output)
#   onDelay: DINT (Input)
#   offDelay: DINT (Input)

# Local tags
from py_l5x import AOILocalStructTag

for name, local in aoi.local_tags.items():
    print(f"  {name}: {local.data_type}")
    if isinstance(local, AOILocalStructTag):
        print(f"    Members: {list(local.members.keys())}")
    else:
        print(f"    Value: {local.value}")
#   debounceOnTimer: TIMER
#     Members: ['PRE', 'ACC', 'EN', 'TT', 'DN']
#   debounceOffTimer: TIMER
#     Members: ['PRE', 'ACC', 'EN', 'TT', 'DN']
```

Each local tag is an instance of a typed class: `AOILocalBoolTag`, `AOILocalIntegerTag`, `AOILocalFloatTag`, `AOILocalTimeTag`, `AOILocalDateTimeTag`, `AOILocalStringTag`, `AOILocalStructTag`, `AOILocalArrayTag`, and `AOILocalAtomicTag`. They all subclass `AOILocalTag` and the matching node class (e.g. `AOILocalStructTag` is also a `StructNode`), so you can branch with `isinstance()`:

```python
from py_l5x import AOILocalIntegerTag, AOILocalStructTag, AOILocalTag, StructNode

timer = aoi.local_tags["debounceOnTimer"]
print(isinstance(timer, AOILocalStructTag))  # True
print(isinstance(timer, StructNode))  # True
print(isinstance(timer, AOILocalTag))  # True

step = project.aois["FanucPNS"].local_tags["Step"]
print(isinstance(step, AOILocalIntegerTag))  # True
print(step.value)  # 0

# AOI routines (same API as program routines — see below)
logic = aoi.routines["Logic"]
print(logic.as_text())
```

### Parameters

`aoi.parameters` is an `AOIParametersCollection` of `AOIParameter` objects. Input and Output parameters that have default data are created as typed subclasses: `AOIParameterBoolTag`, `AOIParameterIntegerTag`, `AOIParameterFloatTag`, `AOIParameterTimeTag`, `AOIParameterDateTimeTag`, or `AOIParameterAtomicTag` (the fallback). Each subclasses `AOIParameter` and the matching node class, so `.value`, `.bit(n)`, `.min`/`.max` (int/float), `.engineering_unit`, and `.state0`/`.state1` (bool) work as they do on tags:

```python
from py_l5x import AOIParameter, AOIParameterIntegerTag

state = project.aois["SeqCtrl"].parameters["state"]
print(isinstance(state, AOIParameterIntegerTag))  # True
print(isinstance(state, AOIParameter))  # True
print(state.value)  # 0
print(state.bit(0).description)  # "running"
print(state.bit(6).description)  # "aborted"
```

InOut parameters, and EnableIn/EnableOut (which have no default data), are plain `AOIParameter` objects that expose identity only: `name`, `data_type`, `usage`, `required`, `visible`, `description`, `tag_type`, and `is_inout`. Per Logix rules, STRING, UDT, and array parameters must be InOut, so they are always plain `AOIParameter` objects. Their per-operand comments are still available through `operand_comments`:

```python
seq = project.aois["FanucRobot"].parameters["seq"]
print(type(seq).__name__)  # "AOIParameter"
print(seq.is_inout)  # True
for operand, comment in seq.operand_comments.items():
    print(f"{operand}: {comment}")
# .FAULT.0: Robot fault did not reset when running
# .FAULT.1: Robot did not stop (cstopi)
# ...
```

## Modules

Modules represent physical or logical I/O hardware (local processors, communication modules, analog/digital I/O, etc.) connected to the controller. Each module has ports (connection points), communication settings, and optional configuration/input/output tag payloads that define the data exchanged with the module.

Module I/O tags are also exposed under their Studio 5000 global names in `project.tags`. The name prefix depends on where the module is attached:

- **Local chassis:** `Local:<slot>:<suffix>` (e.g. `Local:1:C`)
- **Remote rack** (behind an adapter): `<AdapterName>:<slot>:<suffix>` (e.g. `PointIO:3:I`, `Compact5000_IO_Adapter:1:O`)
- **Network-attached:** `<ModuleName>:<suffix>` (e.g. `ValveBank:I`, `ValveBank:O`)

The suffix comes from the connection's `InputTagSuffix`/`OutputTagSuffix` when set, otherwise from the tag's data type, otherwise `I`/`O`. Configuration tags always use `C`.

Each entry is a `ModuleTagRef`, a thin reference to the underlying tag in `project.modules` (still the single source of truth). It provides `name`, `kind`, `data_type`, `class_`, `is_safety`, and `.module` / `.connection` back-references. Value attributes such as `members`, `elements`, and `value` are forwarded to the root value node (`ref.data`), then to the wrapped module tag. Anything missing from both raises `AttributeError` naming `ModuleTagRef`. Module tag names always contain `:`, while Logix controller tag names cannot, so the two never collide in `project.tags`.

```python
# Module I/O tag via its global name
ref = project.tags["ValveBank:I"]
print(ref.module_name)  # "ValveBank"
print(ref.members["ConnectionFaulted"].value)  # False

try:
    ref.elements  # ValveBank:I is a structure, so it has no elements
except AttributeError as e:
    print(e)  # 'ModuleTagRef' object has no attribute 'elements'

# Or directly off the module
for name, ref in project.modules["ShopRobot"].tags.items():
    print(name, ref.kind)
# ShopRobot:C C
# ShopRobot:I I
# ShopRobot:O O
```

> Warning: only a few modules have been tested. Your results may vary with module parsing and how useful the available info is.

```python
for name, mod in project.modules.items():
    print(f"{name}: {mod.catalog_number}")
# Local: 5069-L310ERMS3
# Test_Input_Module: 5069-IB16/A
# Test_Safety_Input: 5069-IB8S/A
# Fast_Local_Input: 5069-IB16F/A
# ShopRobot: ETHERNET-MODULE
# ... (17 modules in total)

mod = project.modules["ShopRobot"]
print(mod.name)  # "ShopRobot"
print(mod.catalog_number)  # "ETHERNET-MODULE"
print(mod.inhibited)  # False
print(mod.ekey_state)  # "Disabled"

# Ports
for port_id, port in mod.ports.items():
    print(f"  Port {port_id}: {port.type} @ {port.address}")
#   Port 2: Ethernet @ 192.168.0.3

# Communications / connections
if mod.communications:
    for cxn_name, cxn in mod.communications.connections.items():
        print(f"  {cxn_name}: RPI={cxn.rpi}ms")
#   Standard: RPI=10000ms
```

## Tags and the value tree

Tags are typed variables that hold data in the controller. Each tag can be a scalar (a single value like an integer or boolean), a structure (an instance of a UDT or AOI), or an array. Tags ARE their root value node — there is no separate `.data` property. Instead, tags are instances of typed classes (`IntegerTag`, `BoolTag`, `StructTag`, `ArrayTag`, `StringTag`, etc.) that also subclass the appropriate node class, so you access value data directly on the tag.

### Tag types and isinstance-based branching

`TagsCollection` returns one of several typed tag classes from `py_l5x`:

```python
from py_l5x import (
    IntegerTag,
    FloatTag,
    BoolTag,
    TimeTag,
    DateTimeTag,
    StringTag,
    StructTag,
    ArrayTag,
    AtomicTag,
    AliasTag,
    MessageTag,
    AxisTag,
    MotionGroupTag,
    UnknownTag,
    StructNode,
    ArrayNode,
)

for name, tag in project.programs["MainProgram"].tags.items():
    if isinstance(tag, IntegerTag):
        print(f"{name}: int = {tag.value}")
    elif isinstance(tag, BoolTag):
        print(f"{name}: bool = {tag.value} (state0={tag.state0}, state1={tag.state1})")
    elif isinstance(tag, StructTag):
        print(f"{name}: struct with members {list(tag.members.keys())}")
    elif isinstance(tag, ArrayTag):
        print(f"{name}: array of length {len(tag)}")
    elif isinstance(tag, AliasTag):
        print(f"{name}: alias for {tag.alias_for}")
    elif isinstance(tag, MessageTag):
        print(f"{name}: MESSAGE tag")
    else:
        print(f"{name}: {tag.data_type}")
```

Scalar/structure/array tags subclass both `Tag` and the corresponding node class (`IntegerNode`, `StructNode`, `ArrayNode`, etc.), so all node accessors work directly on the tag.

### Accessing tags

```python
# Controller-level tags (controller_tags holds only Tag instances)
for name, tag in project.controller_tags.items():
    print(name, tag.data_type, tag.tag_type)
# ALLOWABLE_ALARMS robotAlarmCode Base
# consumed_tag DINT Consumed
# fromNormal_reset BOOL Base
# message_data DINT Base
# message_tag MESSAGE Base
# produced_tag DINT Produced
# ServosMotionGroup MOTION_GROUP Base
# testServo AXIS_CIP_DRIVE Base
# toSafety_reset BOOL Base

# project.tags additionally includes module I/O tags under their global names
"Local:1:C" in project.tags  # True
type(project.tags["Local:1:C"]).__name__  # "ModuleTagRef"

# Program-local tags
for name, tag in project.programs["MainProgram"].tags.items():
    print(name, tag.data_type)
# an_alias_tag
# an_input_param DINT
# an_int INT
# an_output_param REAL
# an_unsigned_dint UDINT
# an_unsigned_int UINT
# ...
```

### Tag properties

All tags carry common metadata:

```python
tag = project.programs["MainProgram"].tags["a_udt_instance"]
print(tag.name)  # "a_udt_instance"
print(tag.data_type)  # "A_UDT"
print(tag.tag_type)  # "Base"
print(tag.external_access)  # "Read/Write"
print(tag.constant)  # False
print(tag.description)  # tag-level description if any

# Alias tags expose the aliased target path
alias = project.programs["MainProgram"].tags["an_alias_tag"]
print(alias.tag_type)  # "Alias"
print(alias.alias_for)  # "Local:1:I.Pt01.Data"
```

### Scalars: integers, booleans, floats

Scalar tags have a `.value` property and expose type-specific accessors:

```python
# Integer tag
int_tag = project.programs["MainProgram"].tags["an_int"]
print(int_tag.value)  # 0
print(int_tag.data_type)  # "INT"
print(int_tag.radix)  # "Decimal"
print(int_tag.min)  # None (no Min set on the tag)
print(int_tag.max)  # None (no Max set on the tag)

# Drill into individual bits (tag with per-bit descriptions)
dint_tag = project.programs["MainProgram"].tags["a_commented_dint"]
for i in range(3):
    bit = dint_tag.bit(i)
    print(f"  bit({i}): {bit.value}  desc={bit.description!r}")
#   bit(0): False  desc='this is bit 0'
#   bit(1): False  desc='this is bit 1'
#   bit(2): False  desc=''

# Boolean tag (with state labels)
bool_tag = project.programs["MainProgram"].tags["a_bool_with_properties"]
print(bool_tag.value)  # False
print(bool_tag.state0)  # "Off"
print(bool_tag.state1)  # "On"

# Float tag (with min/max bounds)
float_tag = project.programs["MainProgram"].tags["a_real_with_properties"]
print(float_tag.value)  # 12.3
print(float_tag.min)  # -10.0
print(float_tag.max)  # 400.0
```

Metadata properties (`description`, `engineering_unit`, `min`, `max`, `state0`, `state1`, `external_logging`) come from the tag-level `<Tag>` element on value tags. `min` and `max` are only populated when the tag sets them; the data type's natural range is not assumed, so they return `None` otherwise. `description` and `engineering_unit` return `""` when absent (as do `state0` and `state1` on `BoolTag`), and `external_logging` returns `None`.

### Structures and nested members

Structure tags have a `.members` dict-like accessor:

```python
tag = project.programs["MainProgram"].tags["a_udt_instance"]
print(isinstance(tag, StructTag))  # True
print(tag.data_type)  # "A_UDT"

# Drill into structure members
for name, node in tag.members.items():
    # Scalars/strings have .value; structs/arrays don't
    if hasattr(node, "value"):
        print(f"  .{name} ({node.data_type}): value={node.value}")
    elif isinstance(node, StructNode):
        print(f"  .{name} ({node.data_type}): <struct>")
    elif isinstance(node, ArrayNode):
        print(f"  .{name} ({node.data_type}): <array len={len(node)}>")

    if node.description:
        print(f"    desc: {node.description}")
    if node.engineering_unit:
        print(f"    EU:   {node.engineering_unit}")
    if hasattr(node, "min") and node.min is not None:
        print(f"    min:  {node.min}")
    if hasattr(node, "max") and node.max is not None:
        print(f"    max:  {node.max}")
    if hasattr(node, "state0") and node.state0:
        print(f"    state0: {node.state0}")
    if hasattr(node, "state1") and node.state1:
        print(f"    state1: {node.state1}")
#   .a_Bool (BOOL): value=False
#     desc: This is a bool
#   .on_off_bool (BOOL): value=False
#     desc: This is a bool with extended properties
#     EU:   Boolean
#     state0: Off
#     state1: On
#   .a_sint (SINT): value=0
#     desc: This is a sint or byte
#   .a_sint_with_props (SINT): value=0
#     desc: This is a SINT with extended properties
#     EU:   mm
#     min:  0
#     max:  25
#   .a_real (REAL): value=0.0
#     desc: a floating point value
#   .another_bool (BOOL): value=False
#   .a_dint (DINT): value=0
#   .a_nested_UDT (simple_udt): <struct>
#     desc: a nest UDT type
#   .an_aoi (GenericInput): <struct>
#     desc: a nested Add On Instruction type
#   .an_array (REAL): <array len=4>
#     desc: an array of two floating point values. Only 1D is allowed in UDTs.

# Drill into a nested UDT
nested_node = tag.members["a_nested_UDT"]  # StructNode
for name, child in nested_node.members.items():
    if hasattr(child, "value"):
        print(f"  {name} = {child.value}")
    elif isinstance(child, StructNode):
        print(f"  {name} = <struct>")
    elif isinstance(child, ArrayNode):
        print(f"  {name} = <array len={len(child)}>")
#   bool1 = False
#   bool2 = False
#   bool3 = False
#   bool4 = False
#   Dint = 0
#   real = 0
#   lint = 0
```

Use `isinstance(node, StructNode)` to check if a member is itself a structure before accessing `.members`.

### Per-operand metadata

Bit and member metadata (comments, engineering units, state labels, min/max, external logging) is stored per operand, keyed by the operand as Studio 5000 exports it (`.0` for bit 0, `.BOOL1` for a member). Tags, AOI local tags, and AOI parameters expose it through two read-only properties:

- `operand_comments`: operand → comment.
- `operand_metadata`: operand → the raw exported text for each key (`comment`, `min`, `max`, `engineering_unit`, `state0`, `state1`, `external_logging`).

Both are instance-only: they reflect the element's own entries and do not merge in entries from the AOI definition.

```python
dint_tag = project.programs["MainProgram"].tags["a_commented_dint"]
print(dint_tag.operand_comments)
# {'.0': 'this is bit 0', '.1': 'this is bit 1', '.10': 'this is bit 10'}
print(dint_tag.operand_metadata[".1"])
# {'comment': 'this is bit 1', 'engineering_unit': 'mm', 'state0': 'off', 'state1': 'on', 'external_logging': 'false'}

udt_tag = project.programs["MainProgram"].tags["a_simple_udt_with_overrides"]
print(udt_tag.operand_metadata[".DINT"]["max"])  # "2147483647"
```

**AOI instance inheritance.** Bit and member metadata written on an AOI parameter definition applies to every instance of that AOI. When a value is looked up, the first match wins:

1. The instance tag's own operand entry.
2. The AOI parameter definition's operand entry.
3. The parameter's own description/metadata.

```python
sequence = project.programs["MainProgram"].tags["sequence"]
print(sequence.operand_comments)  # {} (only the instance's own entries)
print(sequence.members["state"].bit(0).description)  # "running" (from SeqCtrl)
```

### Arrays

Array tags have `.elements`, `__len__`, `__iter__`, and subscript access:

```python
arr_tag = project.programs["MainProgram"].tags["a_2d_array"]
print(isinstance(arr_tag, ArrayTag))  # True
print(len(arr_tag))  # 6
print(arr_tag.dimensions)  # (2, 3)

# Iterate all elements (flat order)
for i, element in enumerate(arr_tag.elements[:4]):
    print(f"  [{i}] = {element.value}")
#   [0] = 0
#   [1] = 0
#   [2] = 0
#   [3] = 0

# Subscript by flat index
first = arr_tag[0]
print(first.value)
# 0

# Subscript by multidimensional tuple (Logix notation)
# For a 2D array, arr_tag[1, 2] accesses row 1, column 2
element = arr_tag[1, 2]
print(element.value)
# 0
```

### Special types: TIME, DATETIME, STRING

Some atomic types have special value representations:

```python
prog = project.programs["MainProgram"]

# TIME tags (Logix v37+): string literal like "T#1500us"
duration = prog.tags["duration"]
if isinstance(duration, TimeTag):
    print(duration.value)  # "T#0us"
    print(duration.unit)  # "us" or "ns"

# DATETIME tags (Logix v37+): string literal like "DT#1970-01-01-00:00:00.000_000Z"
datetime_tag = prog.tags["datetime"]
if isinstance(datetime_tag, DateTimeTag):
    print(datetime_tag.value)  # "DT#1970-01-01-00:00:00.000_000Z"
    print(datetime_tag.unit)  # "us" or "ns"

# STRING tags: quote-stripped text value
a_string = prog.tags["a_string"]
if isinstance(a_string, StringTag):
    print(repr(a_string.value))  # ''
    print(a_string.len)  # 0
    print(a_string.max_length)  # 82
    # Access LEN/DATA fields of the string structure
    for name, member in a_string.members.items():
        print(f"  {name}: {member.value!r}")
#   LEN: 0
#   DATA: ''
```

TIME/DATETIME types are only exported in projects with firmware v37+.

### Specialty tags: MESSAGE, MOTION_GROUP, AXIS_CIP_DRIVE

A few tag data types don't carry a normal scalar/structure/array value — Logix exports a single configuration block instead. Use `isinstance()` checks and specialty accessors:

```python
from py_l5x import MessageTag, MotionGroupTag, AxisTag

# MESSAGE tags — configure a CIP message instruction
msg_tag = project.tags["message_tag"]
if isinstance(msg_tag, MessageTag):
    params = msg_tag.message_parameters
    print(params.message_type)  # "CIP Data Table Write"
    print(params.connection_path)  # "AnotherPLC"
    print(params.local_element)  # "message_data"
    print(params.connected)  # True
    print(params.cache_connections)  # True

# MOTION_GROUP tags — coordinate CIP Motion servo axes
mg_tag = project.tags["ServosMotionGroup"]
if isinstance(mg_tag, MotionGroupTag):
    group = mg_tag.motion_group_parameters
    print(group.coarse_update_period)  # 2000
    print(group.auto_tag_update)  # "Enabled"

# AXIS_CIP_DRIVE tags — single EtherNet/IP servo axis
axis_tag = project.tags["testServo"]
if isinstance(axis_tag, AxisTag):
    axis = axis_tag.axis_parameters
    print(axis.motion_group)  # "ServosMotionGroup"
    print(axis.motor_catalog_number)  # "VPL-B0631T-C"
    print(axis.conversion_constant)  # 10000.0
    print(axis.position_units)  # "mm"
    print(axis.maximum_speed)  # 226.66667
    print(axis.actuator_type)  # "Screw"
    print(axis.motor_rated_output_power)  # 0.31
```

Each specialty tag class also has `special_data_format` and `special_data_attributes` properties for unmodeled tag types:

```python
# For any unrecognised specialty tag data type
if isinstance(tag, UnknownTag):
    print(tag.special_data_format)  # e.g. "SomeCustomFormat"
    print(tag.special_data_attributes)  # dict of <Data> element attributes
```

Specialty tags do NOT have `.value`, `.members`, or `.elements` — use `isinstance()` to branch and access the appropriate `.message_parameters` / `.motion_group_parameters` / `.axis_parameters` property instead.

## Programs, routines, and rungs

Programs are the main organizational units for logic in the controller. Each program contains local tags and one or more routines. Routines are where the actual logic lives — either in **ladder rung** format (RLL, relay ladder logic) or **structured text** (ST). A rung is a single line of ladder logic with contacts, coils, and logic blocks. Programs and routines can be disabled independently.

> At this time, only Ladder Logic and Structured Text are supported. Support for other program types is TBD.

```python
for prog_name, prog in project.programs.items():
    print(prog_name, "—", prog.main_routine_name)
# AnotherProgram — Main
# EventProgram — Main
# MainProgram — MainRoutine
# PeriodicProgram — main
# Robot — Main
# SafetyProgram — Main
# Unscheduled — Main

prog = project.programs["MainProgram"]
print(prog.disabled)  # False
print(prog.test_edits)  # False

# Routines
for rtn_name, rtn in prog.routines.items():
    print(f"  {rtn_name} ({rtn.type_})")
#   MainRoutine (RLL)
#   SequenceRoutine (RLL)

rtn = prog.routines["SequenceRoutine"]
print(rtn.type_)  # "RLL"

# Ladder rungs
for rung in rtn.rungs:
    print(f"  Rung {rung.number}: {rung.text}")
    if rung.comment:
        print(f"    Comment: {rung.comment}")

# Structured Text
st_rtn = project.programs["AnotherProgram"].routines["StructuredTextRoutine"]
print(st_rtn.st_code)  # full ST body as a string
for line in st_rtn.st_lines:
    print(line.number, line.text)

# Executable logic (RLL: each rung's neutral text; ST: code with comments stripped)
print(rtn.logic[:3])  # ['NOP();', 'NOP();', 'SeqCtrl(sequence,1,0);']
print(st_rtn.logic[:2])  # ['j := 0;', 'for i:=0 to 31 by 1 do']

# Comments (RLL: rung comments; ST: // and (* ... *) comments)
print(len(rtn.comments))  # 10

# Pretty-print all logic in a program (print_logic_text() also returns the text)
prog.print_logic_text()

# Pretty-print a single routine
rtn.print_text()
```

`Routine.as_text()` / `print_text()` and `Program.logic_text()` / `print_logic_text()` render ladder rungs as a header, an optional `Comment` block with the full (possibly multi-line) comment, and a `Logic` block. Rungs are separated by a blank line, and the `Comment` block is omitted when a rung has no comment:

```python
print(project.programs["AnotherProgram"].routines["io"].as_text())
# Rung 0 ---------------------------------
# Logic
# GenericInput(TestInput,Local:1:I.Pt00.Data);
#
# Rung 1 ---------------------------------
# Comment
# Example of writing a message to another PLC
# Logic
# MSG(message_tag);
```

## Tasks

Tasks are executors that schedule programs to run at specified intervals or on specific events. Each task collection holds a collection of programs it is responsible for scheduling and executing. These are the same as the program objects found in `Project.programs`, just organized by their parent task.

```python
for task_name, task in project.tasks.items():
    print(task_name, task.type_)
# EventTask EVENT
# MainTask CONTINUOUS
# PeriodicTask PERIODIC
# SafetyTask PERIODIC

task = project.tasks["MainTask"]
print(task.type_)  # "CONTINUOUS"
print(task.priority)  # 10
print(task.rate)  # None  (CONTINUOUS tasks have no fixed rate)
print(task.watchdog)  # 500

# Programs scheduled by this task
for prog_name in task.scheduled_program_names:
    print(f"  {prog_name}")
#   MainProgram
#   AnotherProgram
#   Robot
```

## Component exports

Studio 5000 can export individual components (a single Program, Routine, AOI, DataType, Module, Rung, or Tag) rather than an entire project. Component exports are wrapped in the same `<RSLogix5000Content>` envelope as full projects but carry a `TargetType` indicating what was exported (e.g., `"Program"`, `"Routine"`, `"Rung"`) and a `<Controller Use="Context">` section containing all dependencies (UDTs, AOIs, parent programs, etc.). `py_l5x` supports component exports through the same `load()` API and provides a `.target` property to quickly access the exported object.

```python
project = load("MainProgram_Program.L5X")
print(project)
# Project('Example_PLC')
#   Target:       Program 'MainProgram'
#   Processor:    —
#   Firmware:     —.—
#   ...
```

### Identifying the export type

```python
print(project.target_type)  # "Program", "Routine", "DataType", etc.
print(project.target_name)  # "MainProgram"
print(project.contains_context)  # True for component exports
```

### Accessing the exported object directly

As a shortcut, `project.target` resolves to the typed wrapper for whichever object was exported:

| `target_type`                  | `project.target` type |
| ------------------------------ | --------------------- |
| `"DataType"`                   | `DataType`            |
| `"AddOnInstructionDefinition"` | `AOIDefinition`       |
| `"Module"`                     | `Module`              |
| `"Program"`                    | `Program`             |
| `"Routine"`                    | `Routine`             |
| `"Rung"`                       | `Rung`                |
| `"Tag"`                        | `Tag`                 |
| `"Controller"` (full project)  | `None`                |

```python
# DataType export
p = load("A_UDT_DataType.L5X")
udt = p.target  # DataType instance
print(udt.name)  # "A_UDT"

# AOI export
p = load("Debounce_AOI.L5X")
aoi = p.target  # AOIDefinition instance
print(aoi.name, aoi.revision)  # Debounce 1.2

# Program export — full collection API still works
p = load("MainProgram_Program.L5X")
prog = p.target  # Program instance
print(prog.use)  # "Target"
rtn = p.programs["MainProgram"].routines["SequenceRoutine"]

# Routine export
p = load("SequenceRoutine_Routine_RLL.L5X")
rtn = p.target  # Routine instance
print(rtn.use)  # "Target"
print(len(rtn.rungs))  # 10

# Rung export (no TargetName in header; use target.number)
p = load("Rung2_from_SequenceRoutine.L5X")
rung = p.target  # Rung instance
print(rung.number)  # 2
print(rung.use)  # "Target"
print(rung.text)  # 'SeqCtrl(sequence,1,0);'

# Locate the target rung via the routine directly
rtn = p.programs["MainProgram"].routines["SequenceRoutine"]
rung = rtn.target_rung  # Rung | None
```

> Note that the project may still contain other objects. A program routine may have an AOI definition, for example. The `Project.type` property just shortcuts to the main content of the export.

### Context controller in component exports

The `<Controller>` element in a component export carries `Use="Context"` and omits firmware/processor metadata. `ControllerInfo.is_context` signals this:

```python
p = load("Debounce_AOI.L5X")
print(p.controller.is_context)  # True
print(p.controller.processor_type)  # None
print(p.controller.major_rev)  # None
print(p.controller.name)  # "Example_PLC"  (always present)
```

Dependency data (UDTs, AOIs, tags, etc.) that Studio 5000 exports as context for the target object are accessible through the standard collections (`project.data_types`, `project.aois`, …) even though they carry `Use="Context"` in the XML.

---

## Building from source

The project uses [uv](https://docs.astral.sh/uv/) for dependency management and build tooling.

### Prerequisites

Install `uv` if you don't have it. You can find their installation instructions [here](https://docs.astral.sh/uv/getting-started/installation/).

### Clone and set up

```bash
git clone https://github.com/your-org/py_l5x.git
cd py_l5x

# Create a virtual environment and install dev dependencies
uv sync
```

`uv sync` reads `pyproject.toml`, creates `.venv/` in the project root, and installs the package in editable mode along with the `dev` dependency group (pytest).

### Run the tests

```bash
uv run pytest
```

Or activate the environment first and use pytest directly:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pytest
```

### Build a wheel

```bash
uv build
```

This produces a `.whl` and a `.tar.gz` under `dist/`. Just to be safe, delete the `dist` folder before building a new release to prevent multiple version from being release in the `.whl` file.

The wheel can be installed in any Python environment:

```bash
pip install dist/py_l5x-0.1.0-py3-none-any.whl
```

### Lint

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and import sorting (configured in `pyproject.toml`):

```bash
uv run ruff check .
uv run ruff check --fix .   # auto-fix where possible
```

## Known Limitation

- Not all L5X components have wrappers/parsers yet. Known top level tags that are currently ignored include:
    - \<ParameterConnection\>
    - \<Trends\>
    - \<QuickWatchList\>
    - \<CommPorts\>
    - \<WallClockTime\>
        > Note that the top level Project object exposes the `Project.root` XML element so you can manually find any extra info you need using Python's build in [XML Element Tree](https://docs.python.org/3/library/xml.etree.elementtree.html).
- Similarly, some attributes may be missing or hard to find. Attributes for objects can vary wildly, so I've done my best to expose common ones via a little reverse engineering of example files.
    - As a fallback, all elements (Module, ProgramsCollection, etc.) also include a `_element` property that exposes the top level xml element.
- Not all features or specialty tag types are supported. For example:
    - Alarms
    - Motion Coordinate Groups
- There is no write support. `py_l5x` can only read L5X files. It cannot write back to them.

## Road Map

- [ ] Implement a write feature to allow for modifying an exported L5X file
- [ ] Implement a generate component feature to go along with write allowing users to create component imports using python.

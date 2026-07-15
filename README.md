# py_l5x

A pythonic interface for reading Rockwell Automation L5X files.

> [!IMPORTANT]
> **⚠️ Work in Progress**: This project is currently under active development. APIs are subject to change, and not all features may be fully implemented or tested.

`py_l5x` parses Rockwell Automation L5X exports from Studio 5000 Logix Designer and exposes the contents as a typed Python object hierarchy. It handles CDATA sections transparently, resolves packed-boolean bit members, and cross-references type definitions so that every tag's value tree carries full metadata (descriptions, engineering units, min/max bounds, state labels).

Both **full project exports** (an entire `.L5X` file exported from the controller) and **component exports** (a single Program, Routine, AOI, DataType, Module, Rung, or Tag exported in isolation) are supported through the same `load()` API.

## Installation

I don't yet have plans to upload this to PyPi. For now, download the `.whl` and install it with pip manually:

```bash
pip install py_l5x-0.1.0-py3-none-any.whl
```

or

```bash
uv add py_l5x-0.1.0-py3-none-any.whl
```

## Quick start

```python
from py_l5x import load

project = load("my_project.L5X")
print(project)
# Project('Example_PLC')
#   Target:       Full project
#   Processor:    5069-L306ERM
#   Firmware:     37.11
#   Data Types:   9
#   Modules:      5
#   AOIs:         6
#   Controller Tags: 5
#   Programs:     6
#   Tasks:        3
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
├── tags                → TagsCollection        (controller-level, keyed by name)
├── programs            → ProgramsCollection    (keyed by name)
│   ├── tags            → TagsCollection        (program-local, keyed by name)
│   └── routines        → RoutinesCollection    (keyed by name)
│       ├── rungs       → list[Rung]            (RLL routines)
│       └── st_lines    → list[StLine]          (ST routines)
└── tasks               → TasksCollection       (keyed by name)
```

All collections implement `Mapping[str, T]` so they support the usual `dict`-like access: `project.programs["MainProgram"]`, `"A_UDT" in project.data_types`, `list(project.tags)`, etc.

## Controller metadata

The `ControllerInfo` object exposes project-level metadata such as the controller name, processor type, firmware version, and project dates. For full-project exports, all metadata is populated; for component exports (single Programs, AOIs, etc.), this metadata is sparse or `None` since Studio 5000 does not include it in the export envelope.

```python
ctrl = project.controller

print(ctrl.name)                  # "Example_PLC"
print(ctrl.processor_type)        # "5069-L306ERM"  (None for component exports)
print(ctrl.major_rev)             # "37"             (None for component exports)
print(ctrl.minor_rev)             # "11"             (None for component exports)
print(ctrl.last_modified_date)    # "Thu Jul 09 10:25:47 2026"
print(ctrl.project_sn)            # "16#0000_0000"
print(ctrl.is_context)            # False (True when loaded from a component export)
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
print(udt.name)            # "A_UDT"
print(udt.family)          # "NoFamily"
print(udt.is_string)       # False

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
print(stype.is_string)     # True
print(stype.max_length)    # 8
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
print(aoi.name)                    # "Debounce"
print(aoi.revision)                # "1.2"
print(aoi.execute_enable_in_false) # True

# Parameters
for name, param in aoi.parameters.items():
    print(f"  {name}: {param.data_type} ({param.usage})")
#   EnableIn: BOOL (Input)
#   EnableOut: BOOL (Output)
#   state: BOOL (Output)
#   onDelay: DINT (Input)
#   offDelay: DINT (Input)

# Local tags
for name, local in aoi.local_tags.items():
    print(f"  {name}: {local.data_type} = {local.value}")
#   debounceOnTimer: TIMER = None
#   debounceOffTimer: TIMER = None

# AOI routines (same API as program routines — see below)
logic = aoi.routines["Logic"]
print(logic.as_text())
```

## Modules

Modules represent physical or logical I/O hardware (local processors, communication modules, analog/digital I/O, etc.) connected to the controller. Each module has ports (connection points), communication settings, and optional configuration/input/output tag payloads that define the data exchanged with the module. Note that in the L5X structure, the `Module` holds the tags. You will not find module tags in the controller level tags list.

> Warning: only a few modules have been tested. You results may vary with module parsing and how useful the available info is.

```python
for name, mod in project.modules.items():
    print(f"{name}: {mod.catalog_number}")
# Local: 5069-L306ERM
# Test_Input_Module: 5069-IB16/A
# ShopRobot: ETHERNET-MODULE
# AnotherPLC: 5069-L306ER
# ValveBank: EX600-SEN7/8

mod = project.modules["ShopRobot"]
print(mod.name)            # "ShopRobot"
print(mod.catalog_number)  # "ETHERNET-MODULE"
print(mod.inhibited)       # False
print(mod.ekey_state)      # "Disabled"

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

Tags are typed variables that hold data in the controller. Each tag can be a scalar (a single value like an integer or boolean), a structure (an instance of a UDT or AOI), or an array. The **value tree** (`TagNode`) is a hierarchical representation of a tag's data that lets you drill down into members, array elements, and nested structures while carrying full metadata (descriptions, engineering units, min/max, state labels) at every level.

### Accessing tags

```python
# Controller-level tags
for name, tag in project.tags.items():
    print(name, tag.data_type, tag.tag_type)
# ALLOWABLE_ALARMS robotAlarmCode Base
# consumed_tag DINT Consumed
# message_data DINT Base
# message_tag MESSAGE Base
# produced_tag DINT Produced

tag = project.tags["message_data"]

# Program-local tags
for name, tag in project.programs["MainProgram"].tags.items():
    print(name, tag.data_type)
# an_alias_tag
# an_input_param DINT
# an_int INT
# a_bool BOOL
# a_counter COUNTER
# a_udt_instance A_UDT
# ... (remaining tags)
```

### Tag properties

```python
tag = project.programs["MainProgram"].tags["a_udt_instance"]
print(tag.name)              # "a_udt_instance"
print(tag.data_type)         # "A_UDT"
print(tag.tag_type)          # "Base"
print(tag.external_access)   # "Read/Write"
print(tag.constant)          # False

# Alias tags
alias = project.programs["MainProgram"].tags["an_alias_tag"]
print(alias.tag_type)        # "Alias"
print(alias.alias_for)       # path of the aliased tag
```

### The value tree (`TagNode`)

Every tag's `.data` property returns a `TagNode` — a single unified node that can represent a scalar value, a structure, or an array:

```python
tag = project.programs["MainProgram"].tags["a_udt_instance"]
root = tag.data

print(root.kind)       # "structure"
print(root.data_type)  # "A_UDT"

# Drill into structure members
for name, node in root.members.items():
    print(f"  .{name} ({node.data_type}): {node.kind} = {node.value}")
    if node.description:      print(f"    desc: {node.description}")
    if node.engineering_unit: print(f"    EU:   {node.engineering_unit}")
    if node.min is not None:  print(f"    min:  {node.min}")
    if node.max is not None:  print(f"    max:  {node.max}")
    if node.state0:           print(f"    state0: {node.state0}")
    if node.state1:           print(f"    state1: {node.state1}")
#   .a_Bool (BOOL): scalar = 0
#     desc: This is a bool
#   .on_off_bool (BOOL): scalar = 0
#     desc: This is a bool with extended properties
#     EU:   Boolean
#     state0: Off
#     state1: On
#   .a_sint (SINT): scalar = 0
#     desc: This is a sint or byte
#   .a_sint_with_props (SINT): scalar = 0
#     desc: This is a SINT with extended properties
#     EU:   mm
#     min:  0
#     max:  25
#   .a_real (REAL): scalar = 0.0
#   .a_nested_UDT (simple_udt): structure = None
#   .an_array (REAL): array = None
#   ... (remaining members)

# Drill into a nested UDT
nested_node = root.members["a_nested_UDT"]  # structure TagNode
for name, child in nested_node.members.items():
    print(name, child.value)

# Shortcuts on Tag (delegates to .data)
print(tag.value)    # None  (structure, not scalar)
print(tag.members)  # same as tag.data.members
print(tag.elements) # []    (not an array)

# Bit access on a scalar integer
dint_tag = project.programs["MainProgram"].tags["a_commented_dint"]
print(dint_tag.value)  # 0
for i in range(3):
    bit = dint_tag.data.bit(i)
    print(f"  bit({i}): {bit.value}  desc={bit.description!r}")
#   bit(0): False  desc='this is bit 0'
#   bit(1): False  desc='this is bit 1'
#   bit(2): False  desc=''
```

`TagNode.kind` is one of `"scalar"`, `"structure"`, or `"array"`. Metadata properties (`description`, `engineering_unit`, `min`, `max`, `state0`, `state1`, `external_logging`) are available on every node and combine per-tag operand overrides with the member's type-definition defaults. Metadata tags that are not present will be set to `None`.

### Specialty tag data types (`MESSAGE`, `MOTION_GROUP`, `AXIS_CIP_DRIVE`)

A few tag data types don't carry a normal `Decorated`/`String` value tree — Logix instead exports a single configuration block. `py_l5x` exposes each of these through a dedicated typed wrapper (in `py_l5x.parsers.specialty_tags`) rather than through `tag.data`/`tag.value`:

```python
# MESSAGE tags — configures a CIP message instruction (e.g. MSG to another controller)
msg_tag = project.tags["message_tag"]
params = msg_tag.message_parameters   # MessageParameters | None
print(params.message_type)       # "CIP Data Table Write"
print(params.connection_path)    # "AnotherPLC"
print(params.local_element)      # "message_data"
print(params.connected)          # True
print(params.cache_connections)  # True

# MOTION_GROUP tags — a group of coordinated CIP Motion servo axes
mg_tag = project.tags["ServosMotionGroup"]
group = mg_tag.motion_group_parameters   # MotionGroupParameters | None
print(group.coarse_update_period)  # 2000 (µs)
print(group.auto_tag_update)       # "Enabled"

# AXIS_CIP_DRIVE tags — a single EtherNet/IP servo axis
axis_tag = project.tags["testServo"]
axis = axis_tag.axis_parameters   # AxisParameters | None
print(axis.motion_group)              # "ServosMotionGroup"
print(axis.motor_catalog_number)      # "VPL-B0631T-C"
print(axis.conversion_constant)       # 10000.0
print(axis.position_units)            # "mm"
print(axis.maximum_speed)             # 226.66667
print(axis.actuator_type)             # "Screw"
print(axis.motor_rated_output_power)  # 0.31
print(axis)  # multi-line summary, similar to `print(project.controller)`
```

Each wrapper exposes the most commonly used attributes as typed properties (with docstrings), plus `extra_attributes`/`attributes` fallbacks for anything not explicitly modeled — `AxisParameters` in particular carries well over a hundred drive/motor/tuning attributes, only the most useful of which get dedicated properties. `tag.data`/`tag.value` are `None` for these tag types since there's no value tree to walk.

The legacy `L5K` mirror some of these `<Data>` sections also export is intentionally ignored throughout — it's a redundant raw-text encoding of the same data already present in the specialty parameter element.

For any tag data type `py_l5x` doesn't yet recognise by name, `tag.special_data_format` reports the `<Data Format="...">` value and `tag.special_data_attributes` returns that element's raw attributes as a fallback:

```python
tag.special_data_format       # e.g. "Message", "MotionGroup", "Axis", or None for ordinary tags
tag.special_data_attributes   # dict of the <Data> element's own attributes, or None
```

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
# Unscheduled — Main

prog = project.programs["MainProgram"]
print(prog.disabled)           # False
print(prog.test_edits)         # False

# Routines
for rtn_name, rtn in prog.routines.items():
    print(f"  {rtn_name} ({rtn.type_})")
#   MainRoutine (RLL)
#   SequenceRoutine (RLL)

rtn = prog.routines["SequenceRoutine"]
print(rtn.type_)   # "RLL"

# Ladder rungs
for rung in rtn.rungs:
    print(f"  Rung {rung.number}: {rung.text}")
    if rung.comment:
        print(f"    Comment: {rung.comment}")

# Structured Text
st_rtn = prog.routines["InitRoutine"]
print(st_rtn.st_code)          # full ST body as a string
for line in st_rtn.st_lines:
    print(line.number, line.text)

# Pretty-print all logic in a program
prog.print_logic_text()

# Pretty-print a single routine
rtn.print_text()
```

## Tasks

Tasks are executors that schedule programs to run at specified intervals or on specific events. Each task collection holds a collection of programs it is responsible for scheduling and executing. These are the same as the program obejects found in `Project.programs`, just organized by their parent task.

```python
for task_name, task in project.tasks.items():
    print(task_name, task.type_)
# EventTask EVENT
# MainTask CONTINUOUS
# PeriodicTask PERIODIC

task = project.tasks["MainTask"]
print(task.type_)       # "CONTINUOUS"
print(task.priority)    # 10
print(task.rate)        # None  (CONTINUOUS tasks have no fixed rate)
print(task.watchdog)    # 500

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
print(project.target_type)      # "Program", "Routine", "DataType", etc.
print(project.target_name)      # "MainProgram"
print(project.contains_context) # True for component exports
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
udt = p.target                    # DataType instance
print(udt.name)                   # "A_UDT"

# AOI export
p = load("Debounce_AOI.L5X")
aoi = p.target                    # AOIDefinition instance
print(aoi.name, aoi.revision)     # "Debounce" "1.2"

# Program export — full collection API still works
p = load("MainProgram_Program.L5X")
prog = p.target                   # Program instance
print(prog.use)                   # "Target"
rtn = p.programs["MainProgram"].routines["SequenceRoutine"]

# Routine export
p = load("SequenceRoutine_Routine_RLL.L5X")
rtn = p.target                    # Routine instance
print(rtn.use)                    # "Target"
print(len(rtn.rungs))             # number of rungs

# Rung export (no TargetName in header; use target.number)
p = load("Rung2_from_SequenceRoutine.L5X")
rung = p.target                   # Rung instance
print(rung.number)                # 2
print(rung.use)                   # "Target"
print(rung.text)                  # neutral text for this rung

# Locate the target rung via the routine directly
rtn = p.programs["MainProgram"].routines["SequenceRoutine"]
rung = rtn.target_rung            # Rung | None
```

> Note that the project may still contain other objects. A program routine may have an AOI definition, for example. The `Project.type` property just shortcuts to the main content of the export.

### Context controller in component exports

The `<Controller>` element in a component export carries `Use="Context"` and omits firmware/processor metadata. `ControllerInfo.is_context` signals this:

```python
p = load("Debounce_AOI.L5X")
print(p.controller.is_context)       # True
print(p.controller.processor_type)   # None
print(p.controller.major_rev)        # None
print(p.controller.name)             # "Example_PLC"  (always present)
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

This produces a `.whl` and a `.tar.gz` under `dist/`. The wheel can be installed in any Python environment:

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
- There is no write support. `py_l5x` can only read L5X files. It cannnot write back to them.

## Road Map

- [x] Test more special tag types (CIP_AXIS, MESSAGE, etc.)
- [x] Test safety features (safety network numbers, safety routines, safety tags, etc.)
- [ ] Implement a write feature to allow for modifying an exported L5X file
- [ ] Implement a generate component feature to go along with write allowing users to create component imports using python.

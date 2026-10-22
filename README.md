# py_l5x

A pythonic interface for reading Rockwell Automation L5X files.

> [!IMPORTANT]
> **⚠️ Work in Progress**: This project is currently under active development. APIs are subject to change, and not all features may be fully implemented or tested.

`py_l5x` parses Rockwell Automation L5X exports from Studio 5000 Logix Designer and exposes the contents as a typed Python object hierarchy. It handles much of the file's quirks to create `dict` like collections of all your exports's tags, routines, modules, and the like. It also cross references different parts of the files to try and exposes as much metadata (comments, extended tag properties, etc.) as you'd expect to see in Studio 5000 but is spread across the `.L5X` file structure.

Both **full project exports** (a full PLC project) and **component exports** (a single Program, Routine, AOI, DataType, Module, Rung, etc.) are supported through the same `load()` function.

> [!NOTE]
> At this time, only reading L5X files is supported. Write support is planned in the future.  
> Ladder Logic and Structure Text are the only supported languages for routine logic.

## Installation

I don't yet have plans to upload this to PyPi. For now, download the latest `.whl` from the [releases](https://github.com/zwood16/py_l5x/releases) page and install it manually:

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

## Quick start

```python
from py_l5x import load

project = load("my_project.L5X")
print(project)
```

Which prints something along the lines of:

```bash
Project('Example_PLC')
  Target:       Full project
  Processor:    5069-L310ERMS3
  Firmware:     37.11
  Data Types:   9
  Modules:      17
  AOIs:         6
  Controller Tags: 9
  Programs:     7
  Tasks:        4
```

`load()` accepts either a `str` path or a `pathlib.Path`. It raises `FileNotFoundError` if the file does not exist and `ValueError` if the file is not valid XML.

## Project Hierarchy

A loaded project exposes everything through a tree of objects:

```
Project
├── controller          → ControllerInfo
├── data_types          → DataTypesCollection   (keyed by name)
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

## Inspecting Objects

Most objects (tags, data types and data type members, AOI parameters, Controller Info, etc.) print a multi-line summary. For example:

```python
tag = project.programs["MainProgram"].tags["an_int"]
print(tag)
```

```bash
IntegerTag('an_int', 'INT')
  name = 'an_int'
  tag_type = 'Base'
  data_type = 'INT'
  external_access = 'Read/Write'
  opc_ua_access = 'None'
  value: 0
  radix: 'Decimal'
```

Attributes that are present in the XML but not modeled by a field or property are listed under `Extra Attributes:` if they are present. This will be more common on large structures like Servo Axes where it is hard to cover all possible members in all version of Studio 5000.

## Using Collections

As mentioned, most objects in the project tree are collections that implement a Mapping. This means that all collections behave much like a normal python dictionary.

For example: you can iterate through all keys (names) of every program in a project:

```python
for name in project.programs:
    print(name)     # loops over all keys
```

```bash
AnotherProgram
EventProgram
MainProgram
PeriodicProgram
Robot
SafetyProgram
Unscheduled
```

Or iterate through all values (program objects):

```python
for program in project.programs.values():
    print(program.name)  # prints the same thing as the previous example
```

To access a single member of a collection you can use the name of the program, tag, etc. as the key. For example, here we pull the `MainProgram` out into a variable.

```python
# Get the main program object
main_program = project.programs["MainProgram"]

# or you can use get() in case MainProgram isn't a valid key
main_program = project.programs.get("MainProgram")
```

Many collections are nested in other objects following the [heirarchy shown above](#project-hierarchy). So using `main_program`, we can list all tags in that program or access a single one in the exact same way that programs were accessed:

```python
# print all tags in MainProgram
print(main_program.tags)
```

```bash
TagsCollection([
    'an_alias_tag',
    'an_input_param',
    'an_int',
    'an_output_param',
    'an_unsigned_dint',
    'an_unsigned_int',
    'an_unsigned_lint',
    'an_unsigned_sint',
    'a_2d_array',
    'a_3d_array',
    'a_bool',
    'a_bool_with_properties',
    'a_character',
    'a_commented_dint',
    ...
])
```

Then to access a single tag and get the the `description` defined on that tag:

```python
# Get the description from `a_commented_dint`
print(main_program.tags["a_commented_dint"].description)
```

```bash
a dint with bit comments
```

Or more directly you can chain together access:

```python
print(project["MainProgram"].tags["a_commented_dint"].description)
# prints the same thing as the previous example
```

## Controller Info

The `ControllerInfo` object exposes project-level metadata such as the controller name, processor type, firmware version, and project dates. For full-project exports, all metadata is populated and various amounts of extra attributes depending on safety, opc, time sync, etc. For [component exports](#component-exports) (single Programs, AOIs, etc.), this info is sparse or `None` since Studio 5000 does include the full XML structure, but much of the info is stripped out if its not relevant to the exported object.

```python
ctrl = project.controller

print(ctrl)
```

```bash
ControllerInfo('Example_PLC')
  name = 'Example_PLC'
  use = 'Target'
  processor_type = '5069-L310ERMS3'
  major_rev = '37'
  minor_rev = '11'
  project_creation_date = 'Tue Jun 30 10:14:37 2026'
  last_modified_date = 'Mon Oct 19 17:30:00 2026'
  project_sn = '16#0000_0000'
  safety_info: SafetyInfo(SafetyLevel='SIL3/PLe')
  time_synchronize: TimeSynchronize(PTPEnable=True)
  opc_ua_enabled_ports: 2
  ethernet_ports: EthernetPorts([1, 2])
  Extra Attributes:
    AutoDiagsEnabled = 'true'
    ...
```

## Tags

Tags are typed variables. Each tag can be a scalar (a single value like an integer or boolean), a structure (an instance of a UDT or AOI), or an array. In `py_l5x` tags are instances of typed classes (`IntegerTag`, `BoolTag`, `StructTag`, `ArrayTag`, `StringTag`, etc.), so you access value data directly on the tag as well as general Studio 5000 tag properties and type specific properties like min/max, a list of bits, etc.

```python
# print the value and description
a_tag = project.programs["MainProgram"].tags["a_commented_dint"]
print(f"{a_tag.name} = {a_tag.value} # {a_tag.description}")
```

```bash
a_commented_dint = 0 # a dint with bit comments
```

### Accessing Tags

Controller-scoped tags can be found in `project.controller_tags` which contains global tags without [module IO tags](#module-io-tags). This mirrors how global tags are listed in the L5X file structure.

```python
# Show global tags excluding Modules
for name, tag in project.controller_tags.items():
    print(name, tag.data_type, tag.tag_type)
```

```bash
ALLOWABLE_ALARMS robotAlarmCode Base
consumed_tag DINT Consumed
fromNormal_reset BOOL Base
message_data DINT Base
message_tag MESSAGE Base
produced_tag DINT Produced
ServosMotionGroup MOTION_GROUP Base
testServo AXIS_CIP_DRIVE Base
toSafety_reset BOOL Base
```

Similarly, `project.tags` includes the [module I/O tags](#module-io-tags) using their derrived global names. This is what the Controller Tags menu in Studio 5000 would show:

```python
# Check if the PLC has a local IO module with a configuration tag and print its type
print("Local:1:C" in project.tags)
print(type(project.tags["Local:1:C"]).__name__)
```

```bash
True
ModuleTagRef
```

A [Program's](#programs-routines-and-rungs) local tags are nexted under the program in a `tags` property:

```python
main_program = project.programs["MainProgram"]

# list the first 5 tags in MainProgram
for name, tag in list(main_program.tags.items())[:5]:
    print(name, tag.data_type)
```

```bash
an_alias_tag
an_input_param DINT
an_int INT
an_output_param REAL
an_unsigned_dint UDINT
```

### Tag Types and Properties

A `TagsCollection` returns one of several typed tag classes in `py_l5x`:

- `IntegerTag`
- `FloatTag`
- `BoolTag`
- `TimeTag`
- `DateTimeTag`
- `StringTag`
- `StructTag`
- `ArrayTag`
- `AtomicTag`
- `AliasTag`
- `MessageTag`
- `AxisTag`
- `MotionGroupTag`
- `UnknownTag`

All tags carry common metadata. These are valid for any tag found across the project.

```python
tag = main_program.tags["a_udt_instance"]
print(tag.name)
print(tag.data_type)
print(tag.tag_type)
print(tag.external_access)
print(tag.constant)
print(repr(tag.description))
```

```bash
a_udt_instance
A_UDT
Base
Read/Write
False
''
```

> [!Note]
> Tags are slightly different from [AOI Local Tags or Parameters](#parameters-and-local-tags) because of the XML differences in the L5X and slightly different available properties, but they closely resemble the structure and usage of Tags.

### Scalars: integers, booleans, floats

Scalar tags have a `.value` property and expose type-specific accessors:

```python
int_tag = main_program.tags["an_int"]
print(int_tag.value)
print(int_tag.data_type)
print(int_tag.radix)
print(int_tag.min)
print(int_tag.max)
```

```bash
0
INT
Decimal
None
None
```

Integer tags let you drill into individual bits or iterate over them. Each bit is a boolean which also carries over any bit comments or extended properties:

```python
dint_tag = main_program.tags["a_commented_dint"]

# iterate over the first 5 bits
for i, bit in enumerate(dint_tag.bits[:5]):
    print(f"bit({i}): {bit.value}  desc={bit.description!r}")

# access a single bit and print the description
print(f"This is bit 10's description: {dint_tag.bit(10).description}")
```

```bash
bit(0): False  desc='this is bit 0'
bit(1): False  desc='this is bit 1'
bit(2): False  desc=''

This is bit 10's description: this is bit 10
```

These tags can also have extended tag properties. Booleans can have state labels and numerical values (floats and integers) and can have min and max values.

```python
bool_tag = main_program.tags["a_bool_with_properties"]
print(bool_tag.value, bool_tag.state0, bool_tag.state1)

float_tag = main_program.tags["a_real_with_properties"]
print(float_tag.value, float_tag.min, float_tag.max)
```

```bash
False Off On
12.3 -10.0 400.0
```

Most properties (`description`, `engineering_unit`, `min`, `max`, `state0`, `state1`, `external_logging`) come from the tag-level `<Tag>` element in the L5X XML. Properties exist where they _can_ in the python objects of `py_l5x`, but the XML does not necessarily contain these values, so these values will be set to `None` or and empty string if the tag was not configured with these extended properties in Studio 5000. More specifically:

- `min` and `max` are only populated when the tag sets them; the data type's natural range is not assumed, so they return `None` otherwise.
- `description` and `engineering_unit` return `""` when absent (as do `state0` and `state1` on `BoolTag`),
- `external_logging` returns `None` if its not set

### Structures and Nested Members

Structure tags ([UDT](#data-types-udts) and [AOI](#add-on-instructions-aois) instances, built in objects like `TIMER`, etc.) have basic tag properties as well as a `.members` property containing a collection of tags contained in the structure.

```python
tag = main_program.tags["a_udt_instance"]
print(isinstance(tag, StructTag))
print(tag)
```

```bash
True
StructTag('a_udt_instance', 'A_UDT')
  name = 'a_udt_instance'
  tag_type = 'Base'
  data_type = 'A_UDT'
  external_access = 'Read/Write'
  opc_ua_access = 'None'
  members: [
    'a_Bool',
    'on_off_bool',
    'a_sint',
    'a_sint_with_props',
    'a_real',
    'another_bool',
    'a_dint',
    'a_nested_UDT',
    'an_aoi',
    'an_array'
  ]
```

Members of structures can be accessed the same way as any other collection and will return the appropriate type type:

```python
print(tag.members["a_sint_with_props"])
```

```bash
IntegerNode('SINT', path='.A_SINT_WITH_PROPS')
  value: 0
  radix: 'Decimal'
  external_access: 'Read/Write'
  description: 'This is a SINT with extended properties'
  min: 0
  max: 25
  engineering_unit: 'mm'
  external_logging: False
```

Nested structures can be also be drilled into the same way that the parent structure is:

```python
tag = main_program.tags["a_udt_instance"]
nested_node = tag.members["a_nested_UDT"]

for name, child in nested_node.members.items():
    print(f"{name} = {child.value}")
```

```bash
bool1 = False
bool2 = False
bool3 = False
bool4 = False
Dint = 0
real = 0
lint = 0
```

### Arrays

Array tags, similar to structure, have `.elements` property will all values in the array. Additionally, `__len__`, `__iter__`, and subscript access are defined for `ArrayTag` meaning the array data can be accessed similar to a python list.

```python
arr_tag = main_program.tags["a_2d_array"]
print(isinstance(arr_tag, ArrayTag))
print(len(arr_tag))
print(arr_tag.dimensions)

for i, element in enumerate(arr_tag.elements[:4]):
    print(f"[{i}] = {element.value}")


```

```bash
True
6
(2, 3)
[0] = 0
[1] = 10
[2] = 12
[3] = 33
```

Multi-dimensional arrays are flattened, but can still be indexed with Logix style notation:

```python
print(arr_tag[0].value)     # flat index
print(arr_tag[1, 2].value)  # row 1, column 2
```

### Per-Operand Metadata

Integer bits, structure and AOI members, and array elements can carry their own descriptions (comments) and extended properties (depending on the types). These can be accessed directly by selecting the bit or member. For example:

```python
print(main_program.tags["a_commented_dint"].bit(0).description)
```

```bash
this is bit 0
```

Or as a shortcut all member/bit descriptions can be gathered in a `dict` using `operand_comments` property.

```python
print(main_program.tags["a_commented_dint"].operand_comments)
```

```bash
{'.0': 'this is bit 0', '.1': 'this is bit 1', '.10': 'this is bit 10'}
```

For [UDTs](#data-types-udts) and [AOIs](#add-on-instructions-aois), any extended data or comments defined in the definition is overwritten by matching data in the tag instance.

### Special Types: TIME, DATETIME, STRING

Some atomic types have special value representations. `TIME` and date time (`DT`) tags (Logix v34+) have a string literal value and a `unit` to follow the IEC standards for time variables.

```python
duration = main_program.tags["duration"]
print(type(duration).__name__, duration.value, duration.unit)

datetime_tag = main_program.tags["datetime"]
print(type(datetime_tag).__name__, datetime_tag.value, datetime_tag.unit)
```

```bash
TimeTag T#0us us
DateTimeTag DT#1970-01-01-00:00:00.000_000Z us
```

`STRING` tags have a quote-stripped text value, with the `LEN` and `DATA` fields available as members:

```python
string_tag = main_program.tags["a_string"]

print(string_tag.value)
print(string_tag.members["LEN"])
```

```bash
Hello
IntegerNode('DINT', path='.LEN')
  value: 5
```

### Specialty Tags: MESSAGE, MOTION_GROUP, AXIS_CIP_DRIVE

A few tag data types don't carry a normal scalar/structure/array value — Logix exports a single configuration block instead. Specialty tags do NOT have `.value`, `.members`, or `.elements`.

Several of the more common types have many of their properties exposed:

```python
# MESSAGE tags configure a CIP message instruction
params = project.tags["message_tag"].message_parameters
print(params.message_type)
print(params.connection_path)
print(params.local_element)
print(params.connected)
print(params.cache_connections)
```

```bash
CIP Data Table Write
AnotherPLC
message_data
True
True
```

```python
# MOTION_GROUP tags coordinate CIP Motion servo axes
group = project.tags["ServosMotionGroup"].motion_group_parameters
print(group.coarse_update_period)
print(group.auto_tag_update)
```

```bash
2000
Enabled
```

```python
# AXIS_CIP_DRIVE tags represent a single EtherNet/IP servo axis
axis = project.tags["testServo"].axis_parameters
print(axis.motion_group)
print(axis.motor_catalog_number)
print(axis.conversion_constant)
print(axis.position_units)
print(axis.maximum_speed)
print(axis.actuator_type)
print(axis.motor_rated_output_power)
```

```bash
ServosMotionGroup
VPL-B0631T-C
10000.0
mm
226.66667
Screw
0.31
```

Printing the tag itself shows the format that was found:

```python
print(project.tags["message_tag"])
```

```bash
MessageTag('message_tag', 'MESSAGE')
  name = 'message_tag'
  tag_type = 'Base'
  data_type = 'MESSAGE'
  external_access = 'Read/Write'
  class_ = 'Standard'
  opc_ua_access = 'None'
  description = 'write to AnotherPLC'
  special_data_format: 'Message'
```

Any other specialty tag is an `UnknownTag`, which exposes `special_data_format` (e.g. `"SomeCustomFormat"`) and `special_data_attributes` (a dict of the `<Data>` element attributes) so you can still get at the raw info.

### Alias Tags

Alias tags expose the path they point to, but do not contain the actual value.

```python
alias = main_program.tags["an_alias_tag"]
print(alias.tag_type)
print(alias.alias_for)
```

```bash
Alias
Local:1:I.Pt01.Data
```

## Tasks

Tasks are executors that schedule programs to run at specified intervals or on specific events. Each task collection holds a collection of programs it is responsible for scheduling and executing. These are the same as the program objects found in `Project.programs`, just organized by their parent task.

```python
for task_name, task in project.tasks.items():
    print(task_name, task.type_)
```

```bash
EventTask EVENT
MainTask CONTINUOUS
PeriodicTask PERIODIC
SafetyTask PERIODIC
```

A task has its type, priority, rate and watchdog settings, and the names of the programs it schedules:

```python
task = project.tasks["MainTask"]
print(task.type_)
print(task.priority)
print(task.rate)      # CONTINUOUS tasks have no fixed rate
print(task.watchdog)

print("Programs:")

for prog_name in task.scheduled_program_names:
    print(prog_name)
```

```bash
CONTINUOUS
10
None
500
Programs:
MainProgram
AnotherProgram
Robot
```

## Programs, Routines, and Rungs

Programs are the main organizational units for logic in the controller. Each program contains local tags and one or more routines. Routines are where the actual logic lives — either in **ladder rung** format (RLL, relay ladder logic) or **structured text** (ST). A rung is a single line of ladder logic with contacts, coils, and logic blocks.

> [!NOTE]
> At this time, only Ladder Logic and Structured Text are supported. Support for other program types is not currently planned unless requested.

Program can be found under `project.programs` or under their respective tasks:

```python
print(project.programs)
print(project.tasks["MainTask"].programs)
```

```bash
ProgramsCollection([
    'AnotherProgram',
    'EventProgram',
    'MainProgram',
    'PeriodicProgram',
    'Robot',
    'SafetyProgram',
    'Unscheduled'
])
_ScheduledPrograms(['MainProgram', 'AnotherProgram', 'Robot'])
```

Every program names it's main routine (the entry point) with the `main_routine_name` property:

```python
for prog_name, prog in project.programs.items():
    print(prog_name, "-", prog.main_routine_name)
```

```bash
AnotherProgram - Main
EventProgram - Main
MainProgram - MainRoutine
PeriodicProgram - main
Robot - Main
SafetyProgram - Main
Unscheduled - Main
```

Programs hold their routines in a collection, and have a few flags:

```python
print(main_program.disabled)
print(main_program.test_edits)

for rtn_name, rtn in main_program.routines.items():
    print(f"{rtn_name} ({rtn.type_})")
```

```bash
False
False
MainRoutine (RLL)
SequenceRoutine (RLL)
```

### Ladder logic

RLL routines have a list of `rungs`. Each rung has a `number`, its neutral `text` (the ladder logic), and an optional `comment`:

```python
rtn = main_program.routines["SequenceRoutine"]

rung = rtn.rungs[2]
print(f"Rung {rung.number}: {rung.text}")
print(rung.comment)
```

```bash
Rung 2: SeqCtrl(sequence,1,0);
/////////   Sequence Status and Control   /////////

<
Note: the "mode" should typically be connected to the system mode (1/True for Auto)
...
>
```

### Structured text

ST routines have `st_code` (the full body as a string) and `st_lines`:

```python
st_rtn = project.programs["AnotherProgram"].routines["StructuredTextRoutine"]

# print the first 3 lines
for line in st_rtn.st_lines[:3]:
    print(line.number, line.text)
```

```bash
0 (*
1 Example of a structured text program. Loops through an inc a number
2
```

### Logic and comments

Both routine types expose `logic` (RLL: each rung's neutral text; ST: code with comments stripped) and `comments` (RLL: rung comments; ST: `//` and `(* ... *)` comments):

```python
print(rtn.logic[:3])
print(st_rtn.logic[:2])
print(len(rtn.comments))
```

```bash
['NOP();', 'NOP();', 'SeqCtrl(sequence,1,0);']
['j := 0;', 'for i:=0 to 31 by 1 do']
10
```

`Routine.as_text()` / `print_text()` and `Program.logic_text()` / `print_logic_text()` render ladder rungs as a header, an optional `Comment` block with the full (possibly multi-line) comment, and a `Logic` block. Rungs are separated by a blank line, and the `Comment` block is omitted when a rung has no comment. `print_text()` and `print_logic_text()` print the result, and `print_logic_text()` also returns the text:

```python
project.programs["AnotherProgram"].routines["io"].print_text()
```

```bash
Rung 0 ---------------------------------
Logic
GenericInput(TestInput,Local:1:I.Pt00.Data);

Rung 1 ---------------------------------
Comment
Example of writing a message to another PLC
Logic
MSG(message_tag);
```

## Data types (UDTs)

User-defined data types (UDTs) are custom collections of other [tags](#tags) (i.e. a struct). As all UDTs are defined globally, a single collection of UDTs contains all definitions:

```python
# print all User Defined Data Types
print(project.data_types)

# or loop over them
for name in project.data_types:
    print(name)   # prints the same thing
```

```bash
DataTypesCollection([
    'A_UDT',
    'GenericRobotInputs',
    'GenericRobotIO',
    'GenericRobotOutputs',
    'robotAlarmCode',
    'robotString',
    'robotUI',
    'robotUO',
    'simple_udt'
])
```

The data type itself is just the definition, so it contains a fairly small list of properties and fields. The members of the structure are available under the `members` property which contains a collection of [tags](#tags), each of which can contain all the information a PLC tag can carry.

```python

# Print the information in A_UDT
udts = project.data_types

print(udts["A_UDT"])
```

```bash
DataType('A_UDT')
  name = 'A_UDT'
  family = 'NoFamily'
  class_ = 'User'
  members:
    a_Bool: BIT
    on_off_bool: BIT
    a_sint: SINT
    a_sint_with_props: SINT
    a_real: REAL
    another_bool: BIT
    a_dint: DINT
    a_nested_UDT: simple_udt
    an_aoi: GenericInput
    an_array: REAL
```

Members can be accessed like any other collection:

```python
# access a single member and print its information
print(udts["A_UDT"].members["a_Bool"])
```

```bash
DataTypeMember('a_Bool', 'BIT')
  name = 'a_Bool'
  data_type = 'BIT'
  radix = 'Decimal'
  target = 'ZZZZZZZZZZA_UDT0'
  bit_number = 0
  external_access = 'Read/Write'
  description = 'This is a bool'
```

> [!NOTE]
> At this time, nested UDT's cannot be drilled down into like tags. You cannot see `a_nested_UDT`'s members from within `A_UDT`.

### Hidden Tags

If you print the members of a UDT, you may see tags you did not define with the name `ZZZZ...`.

```python
print(udts["A_UDT"].members)
```

```bash
BaseCollection([
    'ZZZZZZZZZZA_UDT0', # hidden padding member
    'a_Bool',
    'on_off_bool',
    'a_sint',
    ...
])
```

These are hidden tags that pad the UDT to fill in empty space. These can be largely ignored but are present as they are represented in the `L5X` XML.

## Add-On Instructions (AOIs)

Similar to [UDTs](#data-types-udts), Add-On Instructions are user defined instructions that contain both tags and logic in a routine. Each AOI has parameters (inputs/outputs), local tags, and one or more routines containing the logic.

All AOI definitions also live in single collection, keyed by name:

```python
for name, aoi in project.aois.items():
    print(name, aoi.revision)
```

```bash
Debounce 1.2
GenericInput 1.2
FanucAlarmLookup 1.0
FanucPNS 1.0
SeqCtrl 3.3
FanucRobot 1.4
```

### Parameters and Local Tags

The parameters of an AOI are contained in the `aoi.parameters` property, which is another collection of tag-like typed classes:

```python
aoi = project.aois["Debounce"]

for name, param in aoi.parameters.items():
    print(f"{name}: {param.data_type} ({param.usage})")
```

```bash
EnableIn: BOOL (Input)
EnableOut: BOOL (Output)
state: BOOL (Output)
onDelay: DINT (Input)
offDelay: DINT (Input)
```

Similarly, local tags (the AOI's internal variables) are in the `aoi.local_tags` property. Each one is a typed class like [tags](#tags) and parameters. So, for example, so you can use on `isinstance()` to check the type:

```python
from py_l5x import AOILocalStructTag

for name, local in aoi.local_tags.items():
    print(f"{name}: {local.data_type}")
    if isinstance(local, AOILocalStructTag):
        print(f"  Members: {list(local.members.keys())}")
    else:
        print(f"  Value: {local.value}")
```

```bash
debounceOnTimer: TIMER
  Members: ['PRE', 'ACC', 'EN', 'TT', 'DN']
debounceOffTimer: TIMER
  Members: ['PRE', 'ACC', 'EN', 'TT', 'DN']
```

Both parameters and local tag type-classes mirror those used by [tags](#tags) with the notable exception that strings and structs are not allowed as Input or Output parameters for AOIs.

`InOut` parameters and EnableIn/EnableOut (which have no default data), are plain `AOIParameter` objects that expose identity only: `name`, `data_type`, `usage`, `required`, `visible`, `description`, `tag_type`, and `is_inout`. Their per-operand comments are still available through `operand_comments`, however:

```python
seq = project.aois["FanucRobot"].parameters["seq"]
print(type(seq).__name__)
print(seq.is_inout)

for operand, comment in list(seq.operand_comments.items())[:3]:
    print(f"{operand}: {comment}")
```

```bash
AOIParameter
True
.FAULT.0: Robot fault did not reset when running
.FAULT.1: Robot did not stop (cstopi)
.FAULT.2: CMD Enable not on
```

### AOI Routines

AOI routines work the same as [program routines](#programs-routines-and-rungs). For example: here is the first few rungs of the `Logic` routine is shown:

```python
print(aoi.routines["Logic"].as_text())
```

```bash
Rung 0 ---------------------------------
Comment
Debounce: Appplies a debounce timer to the AOI rung in condition and returns a "filtered" state output...
Logic
NOP();

Rung 1 ---------------------------------
Logic
MOVE(onDelay,debounceOnTimer.PRE)RES(debounceOffTimer);

Rung 2 ---------------------------------
Comment
Set the output state if the AOI is enabled for at least the debounce On Time...
Logic
[TON(debounceOnTimer,?,?) ,XIC(debounceOnTimer.DN) OTL(state) ];

...
```

## Modules

Modules represent other hardware (other PLCs, communication modules, analog/digital IO, servo drives, etc.) connected to this project's controller. Each module has ports (connection points), communication settings, and optional configuration/input/output tag payloads that define the data exchanged with the module.

> [!Note]
> Only a few modules have been tested. Your results may vary with module parsing and how useful the available info is as it seems vary a lot device to device.

Like everything else, modules are a collection keyed by name:

```python
for name, mod in project.modules.items():
    print(f"{name}: {mod.catalog_number}")
```

```bash
Local: 5069-L310ERMS3
Test_Input_Module: 5069-IB16/A
Test_Safety_Input: 5069-IB8S/A
Fast_Local_Input: 5069-IB16F/A
ShopRobot: ETHERNET-MODULE
AnotherPLC: 5069-L306ER
ValveBank:
Test_Servo_Drive: 2198-H003-ERS2
PointIO: 1734-AENTR/B
PointIO_Input: 1734-IB8/C
PointIO_Output: 1734-OB8/C
PointIO_AnalogInput: 1734-IE2V/C
PointIO_AnalogOutput: 1734-OE2V/C
PointIO_SafetyInput: 1734-IB8S/B
PointIO_SafetyOutput: 1734-OB8S/B
Compact5000_IO_Adapter: 5069-AENTR
Remote_Output: 5069-OB16/B
```

A single module exposes its basic settings, its ports, and its communication connections:

```python
mod = project.modules["ShopRobot"]
print(mod.name)
print(mod.catalog_number)
print(mod.inhibited)
print(mod.ekey_state)

for port_id, port in mod.ports.items():
    print(f"Port {port_id}: {port.type} @ {port.address}")

if mod.communications:
    for cxn_name, cxn in mod.communications.connections.items():
        print(f"{cxn_name}: RPI={cxn.rpi}ms")
```

```bash
ShopRobot
ETHERNET-MODULE
False
Disabled
Port 2: Ethernet @ 192.168.0.3
Standard: RPI=10000ms
```

### Module IO tags

Module IO tags are also exposed under their Studio 5000 global names in `project.tags` to mirror how Studio 5000 shows the module connection. The name prefix depends on where the module is attached:

- **Local chassis:** `Local:<slot>:<suffix>` (e.g. `Local:1:C`)
- **Remote rack** (behind an adapter): `<AdapterName>:<slot>:<suffix>` (e.g. `PointIO:3:I`, `Compact5000_IO_Adapter:1:O`)
- **Network-attached:** `<ModuleName>:<suffix>` (e.g. `ValveBank:I`, `ValveBank:O`)

The suffix comes from the connection's `InputTagSuffix`/`OutputTagSuffix` when set, otherwise from the tag's data type, otherwise `I`/`O`. Configuration tags always use `C`.

Each entry is a `ModuleTagRef` which references the data in `project.modules` as these tags do not actually exist in the L5X as a `<Tag>` or similar despite what Studio 5000 shows. Note that because of this, the names are derrived as shown above and may not always be correct.

```python
ref = project.tags["ValveBank:I"]
print(ref)
```

```bash
ModuleTagRef('ValveBank:I', '_0007:EX600_SEN78_85D36DB4:I:0')
  kind: 'I'
  external_access: 'Read/Write'
  opc_ua_access: 'None'
  members: [
    'ConnectionFaulted',
    'Data'
  ]
```

Anything missing from both the reference and the wrapped tag raises an `AttributeError` naming `ModuleTagRef`. Module tag names always contain `:`, while Logix controller tag names cannot, so the two never collide in `project.tags`.

```python
try:
    ref.elements  # ValveBank:I is a structure, so it has no elements
except AttributeError as e:
    print(e)
```

```bash
'ModuleTagRef' object has no attribute 'elements'
```

You can also get to the same tags directly off the module, which is where they live in the L5X file itself:

```python
for name, ref in project.modules["ShopRobot"].tags.items():
    print(name, ref.kind)
```

```bash
ShopRobot:C C
ShopRobot:I I
ShopRobot:O O
```

## Component Exports

Studio 5000 can export individual components (a single Program, Routine, AOI, DataType, Module, Rung, or Tag) rather than an entire project. Component exports are wrapped in the same `<RSLogix5000Content>` envelope as full projects but carry a `TargetType` indicating what was exported (e.g., `"Program"`, `"Routine"`, `"Rung"`) and a `<Controller Use="Context">` section containing all dependencies (UDTs, AOIs, parent programs, etc.). `py_l5x` supports component exports through the same `load()` API and provides a `.target` property to quickly access the exported object.

For example, here is a program export. Much of the project/controller info is blank:

```python
project = load("MainProgram_Program.L5X")
print(project)
```

```bash
Project('Example_PLC')
  Target:       Program 'MainProgram'
  Processor:    —
  Firmware:     —.—
  Data Types:   3
  Modules:      2
  AOIs:         3
  Controller Tags: 0
  Programs:     1
  Tasks:        0
```

However, the `target_type` and `target_name` point to this being a program export for a program named `MainProgram`.

```python
print(project.target_type)
print(project.target_name)
print(project.contains_context)
```

```bash
Program
MainProgram
True
```

### Accessing the Exported Object Directly

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
project = load("A_UDT_DataType.L5X")
print(project.target.name)
```

```bash
A_UDT
```

> [!NOTE]
> The project may still contain other objects. A program routine may have an AOI definition, for example. The `Project.target` property just shortcuts to the main content of the export. You may need to check other collections in the project to see the full extent of the export.

---

## Building from source

The project uses [uv](https://docs.astral.sh/uv/) for dependency management and build tooling, so install `uv` if you don't have it. You can find their installation instructions [here](https://docs.astral.sh/uv/getting-started/installation/).

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

### Build a wheel

```bash
uv build
```

This produces a `.whl` and a `.tar.gz` under `dist/`. Just to be safe, delete the `dist` folder before building a new release to prevent multiple version from being release in the `.whl` file.

The wheel can be installed in any Python environment:

```bash
uv add /path/to/this/repo/dist/py_l5x-x.x.x-py3-none-any.whl
```

### Lint

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and import sorting (configured in `pyproject.toml`):

```bash
uv run ruff check .
uv run ruff check --fix .   # auto-fix where possible
```

## Known Limitation

### Not All XML Components Have Parsers

Not all L5X components have wrappers/parsers yet. This is includes several known top level XML tags: - \<ParameterConnection\> - \<Trends\> - \<QuickWatchList\> - \<CommPorts\> - \<WallClockTime\>

> Note that the top level Project object exposes the `Project.root` XML element so you can manually find any extra info you need using Python's build in [XML Element Tree](https://docs.python.org/3/library/xml.etree.elementtree.html).

### Some Attributes or Tags May Be Missing

Similarly, some attributes may be missing or hard to find. Attributes for objects can vary wildly, so I've done my best to expose common ones via a little reverse engineering of example files.

- As a fallback, all elements (Module, ProgramsCollection, etc.) also include a `_element` property that exposes the top level xml element.

Additionally, not all features or specialty tag types are supported. For example:

- Alarms
- Motion Coordinate Groups

These would need to be manually parsed using `project.root`.

### No Write Support

There is no write support. `py_l5x` can only read L5X files. It cannot write back to them for the time being. This is a planned feature in the future.

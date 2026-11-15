# L5X import format: what Studio 5000 actually requires

Results from importing hand-built L5X files with the Logix Designer SDK, then exporting the
result and reading it back. Each "Case" tag (E01, T06, ...) refers to a case in the experiment
harness (`scratch/sdk/gen.py`, not in git).

**Scope of verification:** Logix Designer **v37.00**, SDK 2.0.1. Base projects were
`tests/fixtures/example.L5X` (5069-L310ERMS3) and a blank 1756-L85E project. Imports used
`partial_import_from_xml_file` with OVERWRITE collision handling, unless a case notes otherwise.
Nothing here has been checked on other Logix versions yet.

## How to read failures

Studio reports problems at three different levels of severity, and two of them are easy to miss:

| What happens | How it shows up |
|---|---|
| **Import aborted** | The SDK raises `XMLSrv_E_IMPORT_ABORTED_NO_CHANGES` and nothing is changed. The ImportLog has the reason. |
| **Data dropped (warning)** | The import "succeeds" and the object is created, but its `<Data>` is discarded and defaults are used. The only trace is a warning in the ImportLog. |
| **Silently dropped** | The import succeeds, with no warning at all, and the data is lost. Seen with members in the wrong order (F2) and sparse array elements (T12). |
| **Accepted, broken later** | Logic errors (undefined tags, bad operands, unknown instructions, ST syntax) import cleanly and only fail at `build()`. The build reports only the first error, with no location. |
| **Crash** | Logix Services faults on the call after the import, and the SDK service has to be restarted (see "UDT dependencies"). |

The ImportLog is sent to the SDK event logger as `INFO ImportLog ...` lines, which contain an
XML `<ImportLog>` with `Exception Severity/Mnemonic/Text/Target` entries and a
`<Summary Warnings= Errors=>`. Any tool that drives imports should parse it and treat warnings
as failures.

## File envelope

| Question | Answer | Case |
|---|---|---|
| UTF-8 BOM, CRLF line endings | Not required. With or without both works. | E01, smoke test |
| XML declaration | Not required. | E02 |
| `SchemaRevision="1.0"` | **Required.** Without it the import aborts with `XMLSrv_E_INVALID_SCHEMA_REVISION`. | E03 |
| `ContainsContext="true"` | **Required** for the `<Controller Use="Context">` wrapper. Without it, or with `false`, `<Controller>` is ignored with a warning and nothing is imported. | E09, F7_3 |
| Minimum root attributes | `SchemaRevision="1.0" ContainsContext="true"` is enough. `TargetType`, `TargetName`, `SoftwareRevision`, `ExportDate` and `ExportOptions` are all optional. | F7_1 |
| Root with only `SchemaRevision` | Aborts: `Use="Context"` is invalid on `<Controller>` when there is no context. | E04 |
| `SoftwareRevision` 38.00 or 30.00 | Ignored. Both import into v37. | E05, E06 |
| `TargetType` doesn't match the content | Ignored. | E12 |
| `<Controller Name>` doesn't match the project | Ignored. | E07 |
| `Use` attributes | Optional. A file with no `Use` attributes at all imports. | E08, E11 |
| Several targets in one file | Works. Three tags with `Use="Target"` in one file all import. | E10 |
| Elements without a `<Controller>` wrapper | Rejected: "XPath not allowed in import XML". | F10 |
| Child element order | **Enforced.** For example, `Decorated` `<Data>` placed before `L5K` `<Data>` aborts with `XMLSrv_E_ELEMENT_OUT_OF_ORDER`. | T04b |

## `Use` semantics and collisions

| Use / option | Effect on an existing object | Case |
|---|---|---|
| `Target`/`Overwrite` + OVERWRITE | Replaces the object. **Tag values reset to defaults** when the file has no data. | T30, F9b, F9f |
| `Update` (tag, no `<Data>`) | Changes the given properties (for example the description) and **keeps stored values**. | F9a |
| `Update` (tag, full `<Data>`) | Changes the values and **keeps the description and operand comments**. This is the safe way to set values. | S07b |
| `Update` (tag, different `DataType`) | Changes the type (DINT[5] to REAL[5]). | F9e |
| `Update` (DataType) | **Replaces** the whole member list. It does not merge. | U25 |
| `Update` (Program) | Merges child routines: listed routines are added or overwritten, and the rest are kept. Tag values are kept. | R08, S05 |
| `Update` (Task with `<ScheduledPrograms>`) | **Replaces** the whole schedule list. Programs that aren't listed become unscheduled. | S01 |
| `Delete` | Deletes the object. | F9d, exp08 |
| DISCARD collision option | Keeps the existing object. | T31, U26 |
| CANCEL collision option | Aborts with `XMLSrv_E_ABORT_ON_NAME_COLLISION`. | T32 |

Notes on `partial_import_with_target_from_xml_file` (rename on import):

- It works with `x_path="Controller"` for tags (F8c), and with `Controller/Programs` for programs (S04).
- It does **not** work with a tag collection or tag XPath (F8a, F8b), a DataType with `Controller` (U15), or a Task XPath for programs (R01b, S02, S03). All of those fail with "allows only to import xPath related components".
- I haven't found a working way to schedule a program through this method. `<Tasks><Task Use="Update">` works, but only if the file lists every scheduled program.

## Tags and data

### General
- A tag needs only `Name` and `DataType`. Studio fills in TagType, Radix, Constant, ExternalAccess and OpcUaAccess (T15).
- **Leaving out `<Data>` entirely is always safe.** The tag gets type defaults, and that includes AOI parameter defaults for AOI-typed tags, nested ones too (T03, T05, T10, T18b, A14b). This is what you saw with TON tags.
- A tag of an unknown type aborts the import with `RxE_DATATYPE_NOT_FOUND` (T14).
- An alias to a tag that doesn't exist is accepted without complaint (T16c).
- Descriptions and `<Comments>` keyed by operand import as written (T19).
- Program scope can be reached by nesting `<Programs><Program Use="Context"><Tags>` (T23), or by importing a controller-scope file with `x_path=Controller/Programs/Program[@Name='X']/Tags`, which moves the tag into that program (T23b).

### Decorated data: all or nothing
- Structures must list **every visible member, in definition order, each with a `DataType`**. `Radix` is optional (F1, F3).
- A partial structure (T06, T09, T18), a missing `DataType` (T06b, T17), an unknown member name (T13), a type mismatch (T13b), a structure cut short (F2b), or an AOI structure without EnableIn/EnableOut (F3b) all **drop the tag's data with a warning**. The tag is still created with defaults.
- **Members in the wrong order are dropped silently**, with no warning (F2).
- Arrays need **every element, consecutive, each with an `Index`**. Sparse arrays are dropped silently (T12). A UDT array that is sparse or partial (T12c), short (F4b), or missing Index (F5) is dropped with a warning. Multi-dimensional arrays use `Index="[i,j]"` with `Dimensions="2,3"` (F4c).
- In Decorated data, BOOL members of UDTs are logical `BOOL` members. Hidden host SINTs and the TIMER `Control` word are not listed.
- A bad scalar value (`"abc"`) drops the data with a warning (T20). `16#FF` is accepted (T20b).
- If both L5K and Decorated are present and disagree, Decorated wins, provided L5K comes first (T04).

### L5K data (avoid)
L5K is positional over the **storage** layout, which includes hidden SINT hosts and the TIMER
`Control` DINT. A short list is padded with defaults and imports **without a warning**, so a
layout mistake silently stores bad values. For example, `[3000,0]` for a TIMER puts 3000 into
`Control` (F6b), and in A_UDT, `[1,0,5]` maps its first element to the hidden BOOL host (F6).
Only emit Decorated data.

### STRING
`<Data Format="String" Length="n"><![CDATA['text']]></Data>`. **`Length` is required**, and
the import aborts without it (T11c). This works for STRING and for custom string types (T11, T11d).
**`Length` is authoritative.** Studio cuts the text down to `Length` decoded characters
without any warning (exp11, first run).

Escapes are case-insensitive on import. Studio writes them back in this canonical form
(exp11, golden fixture `tests/fixtures/string_escapes_Tags.L5X`): LF → `$l`, CR → `$r`,
tab → `$t`, form feed → `$p`, `$` → `$$`, `'` → `$'`, and other bytes outside printable ASCII →
uppercase `$HH` (`é` → `$E9`). Printable ASCII, including `"`, is written as is, and `$7E`
becomes `~`. `$N` means CR LF, which is two characters. Raw tab and Latin-1 characters in the
CDATA are accepted. Empty strings: a root `Format="String"` holds `''`, while a nested `DATA`
member holds empty CDATA.

### Value text per radix
Studio accepts plain decimal (or `16#..`) input in any radix, and on export rewrites it in a
canonical form (exp09, golden fixture `tests/fixtures/radix_values_Tags.L5X`):
- Hex: `16#` and lowercase hex, zero-padded to the type width and grouped in 4s (`16#0000_00ff`).
- Octal: `8#`, padded and grouped in 3s (`8#00_000_000_377`).
- Binary: `2#`, grouped in 4s.
- ASCII: one `'...'` per value, one item per byte, big-endian, using `$HH` for non-printables (`'$00$FF'`).
- Negative values are written as two's complement in every non-decimal radix.
- REAL Exponential uses `%.8e` and LREAL uses 17 significant digits, both with a 3-digit exponent (`1.50000000e+000`).
- Float radix is written positionally for ordinary magnitudes and exponentially otherwise.
- REAL values are silently rounded to float32 (16777217 is stored as 16777216).

### Built-in type layouts
Exports from the SDK include `ProductDefinedTypes`. Exporting
`Controller/DataTypes/DataType[@Class='ProductDefined']` lists every built-in structure
(TIMER, COUNTER, CONTROL, ALARM, and so on) with its full member list, including hidden
members and bit targets. Its non-hidden members, in order, are exactly the Decorated layout.
This is the source for a built-in type table, so the table doesn't have to be written by hand.

## Rung literals change tag values
In RLL, operands such as TON/RTO PRE and ACC are stored in the tag. On import, the literal in
the rung text is **written into the tag, overriding any `<Data>` in the same file** (S08:
data PRE=5 and rung `TON(t,3000,0)` gave 3000). Importing a rung into an existing routine
**overwrites the existing tag's preset** (S09). Studio stores and exports the rung as
`TON(t,?,?)`. So when generating rungs, write `?` unless you mean to change presets.

## UDTs (DataType)

- A minimal member is just `Name` and `DataType`. `Dimension`, `Radix`, `Hidden` and `ExternalAccess` default sensibly. `Family` and `Class` are optional on the DataType itself (U02, U14).
- **BOOL members can be written as plain `DataType="BOOL"`**, and they import, round-trip and survive save and reopen (U01, P01). **But the resulting layout is unpacked**: 8 BOOLs plus a DINT take 12 bytes, while the same members in hidden-host form take 8 bytes, which is the layout GUI-created UDTs use (K01 vs K02). To get the standard layout, **emit the hidden SINT host plus `BIT`/`Target`/`BitNumber` form**. The host name is not validated (U03), but should follow the `ZZZZZZZZZZ<UDT><n>` convention.
- A `BOOL[n]` member is rounded up to a multiple of 32 without warning (U08b).
- Members of AOI, TIMER and STRING type work and add a `<Dependencies>` entry when exported (U11).
- A **member type that doesn't exist** is accepted without complaint and left unresolved (U04).

### UDT dependencies: the crash
When a file holds **two new UDTs, one used as a member of the other**, Logix Services **crashes
fatally on the next SDK call** unless the dependent UDT has a `<Dependencies>` block. The import
itself reports 0 warnings and 0 errors (U05, U05b, U05c). The SDK service stops, and
`sc start LdSdkService` is needed. With
`<Dependencies><Dependency Type="DataType" Name="..."/></Dependencies>` as the last child of
the dependent DataType, either order works (V02, V03). A dependency that **already exists in the
project** doesn't need the block (U21b, V04). Real exports always include it, and the target
comes first. **The builder must always emit `<Dependencies>`.** It's also likely needed for AOIs
that use new UDTs (A10 included it and worked; the case without it wasn't tested).

### Modifying a UDT in use
- Overwriting a UDT that tags use **keeps tag values, matched by member name**, through reorders, added members (which get defaults) and removed members. A changed member type is converted (DINT 11 became REAL 11.0). Tags of a UDT that contains the modified one are updated too (U22–U24).
- Importing the real `A_UDT` fixture (with UDT and AOI context) into a blank project works and builds (V01).

## AOIs

- Minimum: `Name`, plus `<Parameters>` and `<Routines>` with a `Logic` routine (A02). Studio adds **EnableIn/EnableOut**, `Revision="1.0"`, Created/Edited dates and users, and `SoftwareRevision`. If `Logic` is missing, a default one is created with a warning (A15).
- **`Usage` is required on every parameter** (A03 aborts without it).
- Defaults when a parameter leaves them out: `Required="false"` and **`Visible="false"`**. LocalTag `ExternalAccess="Read/Write"`, while GUI-made AOIs typically use `None`. The builder should set these explicitly.
- `DefaultData` is optional. A Decorated-only default works and carries through to new instances (A14, A14b).
- Logic can be ST (A04). Prescan, Postscan and EnableInFalse routines import, and the `Execute*` flags are taken from the attributes. Routines are kept even when their flag is false (A05, A05b).
- A local tag of a UDT that doesn't exist aborts with `XMLSrv_E_AOI_DEPENDENCY_MISSING` (A09). Unlike UDT members, AOIs do check dependencies.
- Revision is **not enforced**. A lower revision overwrites a higher one without warning (A13).
- Overwriting an AOI that is in use: **instance values are kept by parameter name**, and existing defaults are kept for parameters the file doesn't give defaults for. **Call sites are not updated.** If the number of Required parameters changes, the build fails with `RxCMP_E_AUDIT_INVALIDNOOFOPS` (A07). Overwriting also resets CreatedDate/CreatedBy (to `NT AUTHORITY\...` under the SDK).
- `Use="Update"` with only a RevisionNote/Revision is accepted (A11).

## Programs, routines, rungs

- A program needs only `Name` and `<Routines>`. Studio fills in the rest (R01c). A program imported with the generic import is **left unscheduled** (R01).
- A program file can carry new tags as context; they are created (R01, R02e).
- `partial_import_rungs_from_xml_file`: insert at a position, replace N rungs, or append (a position past the end appends) (R02–R02c). The generic import of a rung file also works (R02d).
- A routine can be imported into an existing program (R06), or copied and renamed with `import_target` and `x_path=` the program (R06b).
- Overwriting a program **replaces its routine list and resets tag values** to the file's data or defaults (R07). `Use="Update"` on the program, with `Use="Overwrite"` on the routine, changes one routine and keeps tag values (S05).
- Whitespace and newlines inside rung text are normalized (R09).

### Logic validation
| Problem | Result |
|---|---|
| Unbalanced brackets in RLL | Import aborts with `RxE_SYNTAX_ERROR` (X02, A16) |
| Undefined tag, unknown instruction (`FOO`), wrong operand type, ST syntax error, extra AOI arguments | **Imported**; caught only by `build()` (X01, X03–X06, A08) |
| `MOV(...)` in v37 rung text | Imported, then fails the build (`RxCMP_E_AUDIT_OUTPUTS`). **v37 L5X uses `MOVE`** (exp08 B2 vs B3; the fixtures also use `MOVE`). |

`build()` stops at the first error and reports no location. To find which rung or program is
at fault, build after each import and `Use="Delete"` between cases (exp08).

## Full-project round trip

`load()` followed by a minimal writer (ElementTree serialization, `<CDataContent>` turned back
into CDATA, UTF-8 BOM, CRLF) produces a file that **opens and builds in Studio unchanged**
(exp07a). Edits made directly to the element tree (rung text, a tag value in both L5K and
Decorated, a new tag with no data, a new UDT member, an AOI revision) open correctly with the
edited values (exp07b). The text differences from the original are cosmetic: ` />` instead of
`/>`, and no line wraps inside long start tags.

### Edits through the py_l5x API (exp10)
Edits made with `py_l5x` itself (`Project.write`, value setters, description and comment
setters inserted in schema order, stale L5K data removed) open in Studio, import with 0
warnings, build, and export with the edited values. This covers a full project
(example.L5X) and component re-imports (A_UDT, Debounce). Every edit was checked in the
exports: TIMER.PRE, a DINT, REAL and BOOL, UDT BOOL/REAL/nested members, a 2D array element,
STRING with escapes, a custom string, a string array element, an AOI-typed tag member, an
AOI parameter default, and tag, AOI, UDT and rung descriptions/comments.

### Structural edits through the py_l5x API (exp12)
Tags added with no `<Data>` (DINT, TIMER, UDT, AOI type, TIMER[3], INT[2,3] Hex, STRING,
Constant DINT, alias), added and removed program tags, a renamed tag, operand comments and
metadata, new RLL and ST routines (with inserted, removed and renumbered rungs and JSR
calls), a renamed routine, and a program component with an added tag and rung all open,
import and build cleanly. A routine that writes to a `Constant="true"` tag fails the build
with `RxCMP_E_AUDIT_BAD_CONSTANT_TAG_OPERATION`. Studio exports an empty routine as a
self-closed `<Routine .../>` with no content element. Operand entries come back sorted
(`[0]` before `[1].PRE`, `.DN` before `.PRE`). Max/Min/ExternalLogging entries are plain
text, while the other operand metadata is CDATA.

### Type layouts and structured values (exp13–exp15)
- Studio created a data-less tag for 216 of the 224 ProductDefined types on the 5069 safety controller. The ones it couldn't create were ALARM_CONDITION, ALARM_SET, the legacy AXIS_GENERIC/GENERIC_DRIVE/SERVO/SERVO_DRIVE types, MODULE, and MOTION_GROUP (the project allows only one, and it already exists). Of those 216, 180 are Decorated structures, 23 are scalars (including REF_TO_*), 3 are String types, and 10 use special formats (Message, Axis, Alarm, CoordinateSystem, BEO, EEO, HMIBC).
- AOI Decorated layout: the parameters in order, without `InOut` ones; local tags are excluded. EnableIn defaults to 1. UDT layout: the non-hidden members, with BIT members written as BOOL. A BOOL `DataValueMember` never has a Radix.
- BOOL arrays are rounded up to a multiple of 32 (BOOL[40] is stored as BOOL[64]).
- Tags created with complete generated values (TIMER, COUNTER, CONTROL, PID, UDT with nested UDT/AOI/array members, AOI-typed, 2D DINT, sparse TIMER[3], BOOL[40], STRING, custom string, STRING[2], UDT[2]) import, build and export with exactly the generated values, both in a full project and in a component built from an empty template.

## Not yet tested
- Logix versions other than v37 (the VM has v30–v37 installed; the SDK supports v31 and later).
- Whether a full-project L5X with a tag whose `<Data>` disagrees with a changed UDT still opens. In exp07b the `simple_udt` instance data didn't include the new member; the project opened, but the instance's value wasn't checked.
- AOIs depending on new UDTs without a `<Dependencies>` block; nested AOI dependencies.
- Module and I/O, alarms, safety, FBD and SFC (out of scope for now).
- What the Studio GUI import (as opposed to the SDK) does with the same files. I expect the same engine, but haven't verified it.

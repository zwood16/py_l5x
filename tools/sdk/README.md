# SDK verification harness

Developer tooling that imports L5X files into real Studio 5000 Logix Designer through the
Logix Designer SDK, then exports the result and checks it. It verifies the fixtures and
golden files that the pytest suite uses. The pytest suite itself stays OS- and
Rockwell-independent: **nothing in `tests/` may depend on this folder or on the SDK.**

Requirements: the Windows VM with Logix Designer v37 (reference) and v38, and the SDK (2.0.2) (see the `studio5000-sdk`
skill: `~/.claude/skills/studio5000-sdk/scripts/vm.sh`, workspace `C:\Users\zwood\ldsdk`),
plus the base projects `projects\base\example_base.ACD` (created from
`tests/fixtures/example.L5X`) and `projects\base\blank.ACD` (a blank v37 1756-L85E project).
The `exp00` and `exp03a` cases in `gen.py` recreate both. For v38: `projects\base\blank_v38.ACD` (exp30) and
`projects\base\example_base_v38.ACD` (exp30b, the example project converted to v38).

| File | Runs on | Purpose |
|---|---|---|
| `runner.py` | VM | Takes a manifest, opens one base project (an existing file, `{"create": {rev, proc, name}}` for a new blank project, or `{"convert": {path, rev}}` to convert a copy to a newer revision), runs the steps (`import`, `import_target`, `import_rungs`, `export`, `get`/`set` incl. `type: raw`, `build`, `save_as`) and writes `results.json`, including each step's SDK log and ImportLog. |
| `go.sh <dir>` | Linux | Pushes a case folder (`manifest.json` + L5X files) to the VM, runs it, and pulls `out/<run>` back into `results/<run>`. |
| `gen.py expNN ...` | Linux | Writes the case folders for the experiments (`exp01`–`exp33`). Each is described in `docs/import-format.md`. v38: exp30 (blank base, ProductDefined export, TIMER_T), exp30b (convert the example to v38), exp31 (per-type defaults, TIMER_T values/UDT/AOI/TON, v37 components into v38), exp33 (TIMER_T golden fixture). |
| `summ.py <run> [--data]` | Linux | Prints a summary per step: ImportLog warnings and errors, plus the exported target XML when `--data` is given. |
| `make_type_tables.py` | Linux | Builds the cumulative built-in type table `py_l5x/data/builtin_types.L5X.gz` and the golden fixtures `type_defaults_Tags.L5X` and `v38_timer_t_Tags.L5X` from harness results. To add a Logix version, run its per-type export (like exp31) and append it to `BUILTIN_SOURCES`. |
| `rt_writer.py` | Linux | Throwaway round-trip writer from Phase 0. Replace it with `py_l5x`'s writer once that exists. |

```bash
cd tools/sdk
python3 gen.py exp01 && ./go.sh exp01 && python3 summ.py exp01 --data
```

Ground rules:
- **Any ImportLog warning is a failure.** Studio drops tag data with only a warning, or sometimes with no warning at all, so compare the exported values too, not just whether the import succeeded.
- `build()` reports only the first error, and the build state is cumulative. To narrow down a failure, build after each import and remove the case again with `Use="Delete"` before the next one (see `exp08`).
- If Logix Services crashes (`LgxSrv_E_FATAL_ERROR`), `LdSdkService` stops. Restart it with `vm.sh cmd "sc start LdSdkService"`.
- Imports never touch the base ACDs on disk. The runner doesn't save unless a step says `save_as`, and that writes into `out/<run>/`.

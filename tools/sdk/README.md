# SDK verification harness

Developer tooling that imports L5X files into real Studio 5000 Logix Designer through the
Logix Designer SDK, then exports the result and checks it. It verifies the fixtures and
golden files that the pytest suite uses. The pytest suite itself stays OS- and
Rockwell-independent: **nothing in `tests/` may depend on this folder or on the SDK.**

Requirements: the Windows VM with Logix Designer v37 and the SDK (see the `studio5000-sdk`
skill: `~/.claude/skills/studio5000-sdk/scripts/vm.sh`, workspace `C:\Users\zwood\ldsdk`),
plus the base projects `projects\base\example_base.ACD` (created from
`tests/fixtures/example.L5X`) and `projects\base\blank.ACD` (a blank v37 1756-L85E project).
The `exp00` and `exp03a` cases in `gen.py` recreate both.

| File | Runs on | Purpose |
|---|---|---|
| `runner.py` | VM | Takes a manifest, opens one base project, runs the steps (`import`, `import_target`, `import_rungs`, `export`, `get`/`set` incl. `type: raw`, `build`, `save_as`) and writes `results.json`, including each step's SDK log and ImportLog. |
| `go.sh <dir>` | Linux | Pushes a case folder (`manifest.json` + L5X files) to the VM, runs it, and pulls `out/<run>` back into `results/<run>`. |
| `gen.py expNN ...` | Linux | Writes the case folders for the Phase 0 experiments (`exp01`–`exp08`). Each case is described in `docs/import-format.md`. |
| `summ.py <run> [--data]` | Linux | Prints a summary per step: ImportLog warnings and errors, plus the exported target XML when `--data` is given. |
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

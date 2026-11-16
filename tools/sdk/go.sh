#!/usr/bin/env bash
# go.sh <expdir>   expdir contains manifest.json + case files; dir name == run name
set -euo pipefail
S=/home/zac/.claude/skills/studio5000-sdk/scripts/vm.sh
HERE="$(cd "$(dirname "$0")" && pwd)"
d="$(cd "$1" && pwd)"; run="$(basename "$d")"
$S cmd "if exist projects\\$run rmdir /s /q projects\\$run & if exist out\\$run rmdir /s /q out\\$run" >/dev/null
$S put "$d" projects >/dev/null
$S run "$HERE/runner.py" "C:\\Users\\zwood\\ldsdk\\projects\\$run\\manifest.json"
mkdir -p "$HERE/results"; rm -rf "$HERE/results/$run"
$S get "out/$run" "$HERE/results/" >/dev/null || true

"""Summarize an experiment: import log exceptions + exported target data.

Usage: python summ.py exp01 [--data]   (--data prints the target's Data/Members XML)
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent


def import_log(lines):
    xml = "\n".join(
        l[len("INFO ImportLog ") :] for l in lines if l.startswith("INFO ImportLog")
    )
    out = []
    for m in re.finditer(
        r"<Exception Severity='(\w+)'[^>]*Mnemonic='(\w+)'.*?<!\[CDATA\[(.*?)\]\]>.*?(?:<Target>\s*(.*?)\s*</Target>|</Exception>)",
        xml,
        re.S,
    ):
        out.append(
            f"{m[1]}: {m[2]}: {m[3].strip()[:220]}  [{(m[4] or '').strip()[:80]}]"
        )
    s = re.search(r'<Summary Warnings="(\d+)" Errors="(\d+)"', xml)
    return out, (s.groups() if s else None)


def target_block(path: Path) -> str:
    txt = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    m = re.search(
        r'<(\w+) Use="Target"(.*?)\n</\1>|<(\w+) Use="Target"[^>]*/>', txt, re.S
    )
    if not m:
        return "(no target)"
    b = m[0]
    b = re.sub(
        r"<Data Format=\"L5K\">\s*(<!\[CDATA\[.*?\]\]>)\s*</Data>",
        r"L5K=\1",
        b,
        flags=re.S,
    )
    return b


def main():
    run = sys.argv[1]
    show = "--data" in sys.argv
    d = HERE / "results" / run
    res = json.loads((d / "results.json").read_text())
    for r in res:
        if r["op"] == "export":
            if show and r["ok"]:
                f = d / r["ret"]
                print(f"   --- {r['ret']}")
                for line in target_block(f).splitlines()[:40]:
                    print("      " + line)
            elif not r["ok"]:
                print(f"   --- export {r['id']}: MISSING")
            continue
        exc, summ = import_log(r["log"])
        status = "OK " if r["ok"] else "ERR"
        print(
            f"{status} {r['id']}  summary(w,e)={summ}"
            + ("" if r["ok"] else f"  {r['err'][:160]}")
        )
        for e in exc:
            print("     " + e)
        if (
            r["op"] not in ("import", "import_target", "import_rungs")
            and r.get("ret") is not None
        ):
            print("     ret:", r["ret"])


main()

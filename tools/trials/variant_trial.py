#!/usr/bin/env python3
"""Try candidate rewrites of one source block and score each against the ROM.

    python tools/trials/variant_trial.py TASK.json [--out RESULT.json]

TASK.json:
    {
      "unit": "mario/MoveBG/MapObjCorona",
      "function": "TBathtub::allowsTumble",
      "file": "src/MoveBG/MapObjCorona.cpp",
      "old": "<exact text of the block to replace, must occur once>",
      "candidates": [
        {"id": "a", "new": "<replacement text>", "note": "optional"},
        ...
      ]
    }

For each candidate the script replaces "old" with "new", builds the unit with
ninja, diffs the whole unit with objdiff, and restores the file. It never
touches git. The result lists, per candidate: whether it built, the target
function's match, and every other function in the unit whose match changed
(a candidate that helps the target but hurts a neighbour is not a fix).

The file is always restored, also on errors or Ctrl-C.
"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_decomp_diff():
    spec = importlib.util.spec_from_file_location(
        "decomp_diff", os.path.join(ROOT, "tools", "decomp-diff.py"))
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = ["decomp-diff"]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


def object_path(unit):
    with open(os.path.join(ROOT, "objdiff.json"), encoding="utf-8") as f:
        for u in json.load(f)["units"]:
            if u["name"] == unit:
                return u.get("base_path")
    raise SystemExit(f"unit {unit} not found in objdiff.json")


def scores(dd, unit):
    """Match percent of every function in the unit, keyed by name."""
    data = dd.run_objdiff(unit)
    out = {}
    for sym in data.get("left", {}).get("symbols", []):
        if not sym.get("instructions"):
            continue
        mp = sym.get("match_percent")
        if mp is None:
            continue
        name = sym.get("demangled_name") or sym.get("name")
        out[name] = round(float(mp), 2)
    return out


def build(obj):
    r = subprocess.run(["ninja", obj], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        tail = (r.stdout + r.stderr)[-1500:]
        return False, tail
    return True, ""


def find_function(table, name):
    hits = [k for k in table if name in k]
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--out")
    args = ap.parse_args()

    with open(args.task, encoding="utf-8") as f:
        task = json.load(f)
    path = os.path.join(ROOT, task["file"])
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
        original = f.read()
    old = task["old"]
    crlf = "\r\n" in original and "\r\n" not in old
    if crlf:  # Windows checkout: match the file's line endings
        old = old.replace("\n", "\r\n")
        for cand in task.get("candidates", []):
            cand["new"] = cand["new"].replace("\r\n", "\n").replace("\n", "\r\n")
    if original.count(old) != 1:
        raise SystemExit(f"'old' occurs {original.count(old)} times in {task['file']}; it must occur once")

    dd = load_decomp_diff()
    obj = object_path(task["unit"])

    ok, err = build(obj)
    if not ok:
        raise SystemExit("the unmodified file does not build:\n" + err)
    base = scores(dd, task["unit"])
    fname = find_function(base, task["function"])
    if fname is None:
        raise SystemExit(f"function {task['function']} not found in {task['unit']}")

    results = {"unit": task["unit"], "function": fname,
               "baseline": base[fname], "candidates": []}
    try:
        for cand in task.get("candidates", []):
            t0 = time.time()
            entry = {"id": cand.get("id"), "note": cand.get("note", "")}
            with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
                f.write(original.replace(old, cand["new"], 1))
            ok, err = build(obj)
            entry["built"] = ok
            if ok:
                now = scores(dd, task["unit"])
                entry["match"] = now.get(fname)
                entry["delta"] = round((now.get(fname) or 0) - base[fname], 2)
                entry["others"] = {k: [base.get(k), v] for k, v in now.items()
                                   if k != fname and base.get(k) != v}
            else:
                entry["error"] = err
            entry["seconds"] = round(time.time() - t0, 1)
            results["candidates"].append(entry)
            print(f"{entry['id']}: " + (f"{entry['match']}% ({entry['delta']:+}) "
                  f"{len(entry['others'])} other function(s) changed"
                  if ok else "build failed"), flush=True)
    finally:
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
            f.write(original)
        build(obj)

    results["candidates"].sort(key=lambda e: -(e.get("match") or -1))
    out = args.out or os.path.splitext(args.task)[0] + ".result.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

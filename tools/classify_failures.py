#!/usr/bin/env python3
"""Sort the nonmatching game functions by the kind of difference they have.

    python tools/classify_failures.py [--unit SUBSTR] [--json OUT] [--limit N]

Reads build/<version>/report.json for functions below 100%, runs
tools/decomp-diff.py on each, and puts each function in one bucket:

  frame-only   only stack offsets differ (we leave these)
  calls        a bl exists on one side only, or calls a different function:
               usually an inline expanded on one side and called on the other
  length       instructions only on one side, but no call difference
  branches     a branch or compare differs
  constants    an immediate or a constant-pool symbol differs
  fields       a load/store displacement differs on a non-stack base
  registers    only register numbers differ
  mixed        several of the above

Writes nothing to the source tree. Build first (ninja).
"""

import argparse
import collections
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIFF = os.path.join(ROOT, "tools", "decomp-diff.py")

LINE = re.compile(r"^([ ~|<>])\s+([0-9a-f]+) \| (.*?)\s*\| (.*)$")
BRANCH = re.compile(r"^(b|bl|blr|bctr|bctrl|blrl|b[a-z]{1,4}[+-]?|cmp\w*|fcmp\w*)$")


def ops(ins):
    p = ins.strip().split(None, 1)
    if not p:
        return "", []
    return p[0], [o.strip() for o in (p[1].split(",") if len(p) > 1 else [])]


def operand_kind(a, b):
    """Kind of difference between two operands of the same instruction."""
    ma, mb = re.match(r"\{?(-?0x[0-9a-f]+|-?\d+)\}?\((r\d+)\)", a), re.match(r"\{?(-?0x[0-9a-f]+|-?\d+)\}?\((r\d+)\)", b)
    # MWCC numbers literals and local statics with a running counter
    # (@1234, init$567); different numbers alone are not a real difference
    clean = lambda s: re.sub(r"(@|\$)\d+", r"\1N", s.replace("{", "").replace("}", ""))
    a, b = clean(a), clean(b)
    if a == b:
        return "registers"
    if re.fullmatch(r"[rf]\d+", a) and re.fullmatch(r"[rf]\d+", b):
        return "registers"
    m1, m2 = re.match(r"(-?\w+)\((r\d+)\)", a), re.match(r"(-?\w+)\((r\d+)\)", b)
    if m1 and m2:
        if m1.group(1) == m2.group(1):
            return "registers"
        if m1.group(2) == "r1" and m2.group(2) == "r1":
            return "stack"
        return "fields"
    if "@" in a or "@" in b:
        return "constants"
    if re.fullmatch(r"-?(0x)?[0-9a-f]+", a) and re.fullmatch(r"-?(0x)?[0-9a-f]+", b):
        return "constants"
    return "other"


def classify(text):
    kinds = collections.Counter()
    for line in text.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        mark, _, left, right = m.groups()
        if mark == " ":
            continue
        ins = left if left.strip() else right
        op = ops(ins)[0]
        if mark in "<>":
            kinds["calls" if op == "bl" else "length"] += 1
            continue
        lop, lops = ops(left)
        rop, rops = ops(right)
        if mark == "|":
            if lop == "bl" or rop == "bl":
                kinds["calls"] += 1
            elif BRANCH.match(lop) or BRANCH.match(rop):
                kinds["branches"] += 1
            else:
                kinds["length"] += 1
            continue
        # '~': same opcode, operands differ
        if lop == "bl":
            kinds["calls"] += 1
            continue
        if lop.startswith(("stwu", "stmw", "lmw")) or (lop == "addi" and "r1" in lops[1:2]):
            kinds["stack"] += 1
            continue
        if BRANCH.match(lop) and lop not in ("cmpw", "cmplw", "cmpwi", "cmplwi", "fcmpo", "fcmpu"):
            kinds["branch-target"] += 1
            continue
        for a, b in zip(lops, rops):
            if a != b:
                kinds[operand_kind(a, b)] += 1
    real = {k: v for k, v in kinds.items() if k not in ("stack", "branch-target", "registers")}
    if not real:
        if kinds.get("registers"):
            return "registers", kinds
        return "frame-only", kinds
    if len(real) == 1:
        return next(iter(real)), kinds
    if "calls" in real:
        return "calls", kinds
    top = max(real, key=real.get)
    if real[top] >= 0.7 * sum(real.values()):
        return top, kinds
    return "mixed", kinds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit")
    ap.add_argument("--json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--version", default=os.environ.get("DECOMP_VERSION", "GMSJ01"))
    args = ap.parse_args()

    report = json.load(open(os.path.join(ROOT, "build", args.version, "report.json")))
    todo = []
    for u in report["units"]:
        if not u["name"].startswith("mario/") or (args.unit and args.unit not in u["name"]):
            continue
        for f in u.get("functions", []):
            p = f.get("fuzzy_match_percent", 0)
            if 0 < p < 100:
                todo.append((u["name"], f["name"], f.get("metadata", {}).get("demangled_name", f["name"]),
                             int(f.get("size", 0)), p))
    if args.limit:
        todo = todo[: args.limit]

    rows = []
    for i, (unit, name, dem, size, pct) in enumerate(todo):
        r = subprocess.run([sys.executable, DIFF, "-u", unit, "-d", name, "--no-collapse"],
                           cwd=ROOT, capture_output=True, text=True)
        cls, kinds = classify(r.stdout)
        lost = size * (100 - pct) / 100
        rows.append({"unit": unit, "name": name, "dem": dem, "size": size, "pct": pct,
                     "lost": round(lost), "cls": cls, "kinds": dict(kinds)})
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(todo)}", file=sys.stderr, flush=True)

    by = collections.defaultdict(list)
    for r in rows:
        by[r["cls"]].append(r)
    print(f"{len(rows)} nonmatching game functions\n")
    print(f"{'bucket':12} {'count':>6} {'bytes lost':>11}")
    for k, v in sorted(by.items(), key=lambda kv: -sum(r["lost"] for r in kv[1])):
        print(f"{k:12} {len(v):6} {sum(r['lost'] for r in v):11}")
    for k in ("calls", "constants", "fields", "branches", "length", "mixed"):
        v = sorted(by.get(k, []), key=lambda r: -r["lost"])[:8]
        if v:
            print(f"\n{k}: biggest")
            for r in v:
                print(f"  {r['lost']:6}B  {r['pct']:6.2f}%  {r['unit']}  {r['dem'][:70]}")
    if args.json:
        json.dump(rows, open(args.json, "w"), indent=1)


if __name__ == "__main__":
    main()

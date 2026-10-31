#!/usr/bin/env python3
"""Pair MWCC's numbered local symbols between the target and our objects.

MWCC names function-local statics and local classes with a running counter,
e.g. `init$3720` or `TSetup1$2172ShadowUtil_cpp`. The counter counts every
anonymous entity seen so far in the TU, headers included. Our headers are
reconstructions, so our counters almost never land on the original values.
objdiff then can't pair those symbols: identical functions show up as one
"missing" and one "extra" symbol.

This script writes objdiff `symbol_mappings` for those symbols only. For
each unit, symbols that differ only in their counter (and in the mangled
length prefix that the counter's digit count changes) are paired in counter
order, but only when both sides have the same number of them and the same
symbol type letter. Anything ambiguous is left alone.

The mappings only affect how objdiff pairs symbols for diffing and progress.
The compiled objects keep their own names, so a unit with such symbols still
can't link-match until the counters line up.

Run it after the objects are built and before `objdiff-cli report generate`.
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NM = os.path.join(ROOT, "build", "binutils", "powerpc-eabi-nm")


def read_symbols(path):
    if not path or not os.path.exists(os.path.join(ROOT, path)):
        return {}
    out = subprocess.run(
        [NM, path], cwd=ROOT, capture_output=True, text=True
    ).stdout.splitlines()
    syms = {}
    for line in out:
        parts = line.split()
        if len(parts) >= 2:
            syms[parts[-1]] = parts[-2]
    return syms


COUNTER = re.compile(r"\$(\d+)")
LOCAL_CLASS = re.compile(r"(\d+)([A-Za-z_][A-Za-z_]*\d*)\$\d+")


def key(name):
    name = LOCAL_CLASS.sub(lambda m: "N" + m.group(2) + "$N", name)
    return COUNTER.sub("$N", name)


def order(name):
    return [int(n) for n in COUNTER.findall(name)]


def mappings_for(target, ours):
    only_t = {s: t for s, t in target.items() if s not in ours and "$" in s}
    only_o = {s: t for s, t in ours.items() if s not in target and "$" in s}
    groups_t = defaultdict(list)
    groups_o = defaultdict(list)
    for s, t in only_t.items():
        groups_t[(key(s), t)].append(s)
    for s, t in only_o.items():
        groups_o[(key(s), t)].append(s)
    result = {}
    for k, names_t in groups_t.items():
        names_o = groups_o.get(k)
        if not names_o or len(names_o) != len(names_t):
            continue
        for a, b in zip(sorted(names_t, key=order), sorted(names_o, key=order)):
            result[a] = b
    return result


def main():
    if not os.path.exists(NM):
        return 0
    path = os.path.join(ROOT, "objdiff.json")
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    changed = False
    for unit in config.get("units", []):
        target = read_symbols(unit.get("target_path"))
        ours = read_symbols(unit.get("base_path"))
        mapping = mappings_for(target, ours) if target and ours else {}
        new = mapping or None
        if unit.get("symbol_mappings") != new:
            unit["symbol_mappings"] = new
            changed = True
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())

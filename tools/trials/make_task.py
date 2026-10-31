#!/usr/bin/env python3
"""Make a trial task whose block is a whole function definition.

    python tools/trials/make_task.py UNIT FILE "Class::method(" OUT.json [--notes TEXT]

The block starts at the first line containing the given signature text and ends
at its matching closing brace. "function" in the task is the qualified name
from the signature, without return type and "(".
"""

import argparse
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("unit")
    ap.add_argument("file")
    ap.add_argument("signature")
    ap.add_argument("out")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    with open(os.path.join(ROOT, args.file), encoding="utf-8", errors="surrogateescape", newline="") as f:
        text = f.read()
    start = text.find(args.signature)
    if start < 0:
        raise SystemExit("signature not found")
    start = text.rfind("\n", 0, start) + 1
    brace = text.find("{", start)
    depth, i = 0, brace
    while True:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    end = text.find("\n", i) + 1
    name = args.signature.rstrip("(").split()[-1].lstrip("*&")
    task = {"unit": args.unit, "function": name,
            "file": args.file, "old": text[start:end], "candidates": []}
    if args.notes:
        task["notes"] = args.notes
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=1, ensure_ascii=False)
    print(f"wrote {args.out} ({end - start} bytes of source)")


if __name__ == "__main__":
    main()

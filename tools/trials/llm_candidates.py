#!/usr/bin/env python3
"""Ask a local model (Ollama) for candidate rewrites of one source block.

    python tools/trials/llm_candidates.py TASK.json [--n 8] [--model TAG]
        [--host http://localhost:11434]

TASK.json uses the variant_trial.py format; "candidates" may be missing or
already hold some entries. The script shows the model the block ("old"), the
function's objdiff diff and the project's rules, asks for N rewrites of the
block, and appends them to the task's "candidates" (ids m1, m2, ...). Then run
variant_trial.py on the same task file to score them.

Nothing the model writes is trusted: every candidate is built and scored, and
a person (or the reviewing agent) decides what is kept.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

RULES = """You are helping a matching decompilation of Super Mario Sunshine
(GameCube, Metrowerks CodeWarrior GC/1.2.5, C++98). The goal is C++ that a
Nintendo developer plausibly wrote in 2002 AND that compiles to the same
machine code as the original game.

Hard rules for every rewrite:
- Keep the block's behaviour identical.
- C++98 only: no auto, no range-for, no lambdas, no nullptr keyword.
- No fake tricks: no volatile, no unused locals or arrays added only to change
  the stack frame, no pointless casts, no #pragma, no asm, no goto.
- Use only names that already exist in the code you are shown. Do not invent
  functions, fields or helpers.
- Plausible variations are things like: splitting or merging statements,
  reordering independent statements, a named local versus an inline
  expression, if/else versus early return, a different but natural loop form,
  using an existing inline helper versus writing it out.

Read the diff: lines starting with '<' or '|' show what the original has,
'>' what the current code has. Aim each rewrite at a difference you can see.
"""


def diff_text(unit, function):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "decomp-diff.py"),
                        "-u", unit, "-d", function, "-C", "2"],
                       cwd=ROOT, capture_output=True, text=True)
    text = r.stdout
    return text[:12000] + ("\n... (diff truncated)" if len(text) > 12000 else "")


def ask(host, model, prompt):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.7, "num_ctx": int(os.environ.get("TRIAL_CTX", "16384"))},
    }).encode()
    req = urllib.request.Request(host.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            return json.loads(resp.read())["message"]["content"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Ollama error {e.code}: {e.read().decode(errors='replace')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--model", default=os.environ.get("TRIAL_MODEL", "qwen3-coder:30b"))
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    args = ap.parse_args()

    with open(args.task, encoding="utf-8") as f:
        task = json.load(f)

    prompt = (RULES
              + f"\nFunction: {task['function']} in {task['file']}\n"
              + (f"\nNotes from the reviewer:\n{task['notes']}\n" if task.get("notes") else "")
              + "\nThe block to rewrite (replace exactly this text):\n```cpp\n"
              + task["old"] + "```\n"
              + "\nCurrent diff against the original game (left = original, right = ours):\n```\n"
              + diff_text(task["unit"], task["function"]) + "```\n"
              + f"\nReturn JSON: {{\"candidates\": [{{\"new\": \"<full replacement for the block>\", "
              + f"\"note\": \"<one line: what changed and which diff line it targets>\"}}]}} "
              + f"with {args.n} different candidates. Keep the same indentation (tabs).")

    raw = ask(args.host, args.model, prompt)
    try:
        got = json.loads(raw).get("candidates", [])
    except json.JSONDecodeError:
        raise SystemExit("the model did not return valid JSON:\n" + raw[:2000])

    cands = task.setdefault("candidates", [])
    start = sum(1 for c in cands if str(c.get("id", "")).startswith("m")) + 1
    seen = {c["new"] for c in cands} | {task["old"]}
    added = 0
    for c in got:
        new = c.get("new") if isinstance(c, dict) else None
        if not new or new in seen:
            continue
        if not new.endswith("\n") and task["old"].endswith("\n"):
            new += "\n"
        seen.add(new)
        cands.append({"id": f"m{start + added}", "new": new,
                      "note": f"{args.model}: {c.get('note', '')}"})
        added += 1

    with open(args.task, "w", encoding="utf-8") as f:
        json.dump(task, f, indent=1, ensure_ascii=False)
    print(f"added {added} candidate(s) to {args.task}")


if __name__ == "__main__":
    main()

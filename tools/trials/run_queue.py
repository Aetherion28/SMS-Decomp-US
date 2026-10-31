#!/usr/bin/env python3
"""Work through a folder of trial tasks: ask the local model, then score.

    python tools/trials/run_queue.py TASK_DIR [--n 8] [--rounds 1] [--no-model]

For every TASK_DIR/*.json without a matching *.result.json:
  1. unless --no-model, ask the local model (llm_candidates.py) for --n
     candidates, --rounds times;
  2. score all candidates (variant_trial.py) and write *.result.json.

Results are written next to the tasks, so the folder can live in the
agent-mailbox repo and be pushed back for review. Safe to stop and restart:
finished tasks are skipped.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task_dir")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--no-model", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--log", help="send step output here and show a progress bar instead")
    args = ap.parse_args()
    log = open(args.log, "a", encoding="utf-8") if args.log else None

    def run(cmd):
        if log:
            log.flush()
            return subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
        return subprocess.run(cmd).returncode

    def bar(done, total, name, t0, step):
        if not log:
            return
        width = 30
        fill = int(width * done / total) if total else width
        el = time.time() - t0
        eta = ""
        if done:
            left = el / done * (total - done)
            eta = f" ETA {int(left // 3600)}h{int(left % 3600 // 60):02d}m"
        line = f"[{'#' * fill}{'-' * (width - fill)}] {done}/{total}{eta}  {step} {name}"
        sys.stdout.write("\r" + line[:110].ljust(110))
        sys.stdout.flush()

    tasks = sorted(p for p in glob.glob(os.path.join(args.task_dir, "*.json"))
                   if not p.endswith(".result.json"))
    def done(t):
        r = os.path.splitext(t)[0] + ".result.json"
        if not os.path.exists(r):
            return False
        with open(r, encoding="utf-8") as f:
            return bool(json.load(f).get("candidates"))

    todo = [t for t in tasks if not done(t)]
    t0 = time.time()
    for i, task in enumerate(todo):
        result = os.path.splitext(task)[0] + ".result.json"
        name = os.path.basename(task)[:-5]
        (log or sys.stdout).write(f"== {os.path.basename(task)}\n")
        if not args.no_model:
            ok = 0
            for r in range(args.rounds):
                bar(i, len(todo), name, t0, f"model {r + 1}/{args.rounds}")
                cmd = [sys.executable, os.path.join(HERE, "llm_candidates.py"), task, "--n", str(args.n)]
                if args.model:
                    cmd += ["--model", args.model]
                ok += run(cmd) == 0
            if ok == 0:
                (log or sys.stdout).write("model failed every round; task left for the next run\n")
                continue
        bar(i, len(todo), name, t0, "scoring")
        run([sys.executable, os.path.join(HERE, "variant_trial.py"), task, "--out", result])
    bar(len(todo), len(todo), "", t0, "done")
    if log:
        print()


if __name__ == "__main__":
    main()

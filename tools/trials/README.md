# Variant trials

Scripts that try many rewrites of one source block and score each against the ROM, so the slow "try a spelling, build, check" loop runs without an AI session.

| Script | Does |
|---|---|
| `variant_trial.py TASK.json` | Applies each candidate, builds the unit, scores the whole unit with objdiff, restores the file, writes `TASK.result.json`. |
| `llm_candidates.py TASK.json` | Asks a local model (Ollama) for more candidates and appends them to the task. |
| `run_queue.py DIR` | For every task in a folder: model candidates, then scoring. Skips tasks that already have a result. |

None of them touch git. The edited file is always restored, also on errors.

## Task format

```json
{
  "unit": "mario/Enemy/BathtubKiller",
  "function": "TBathtubKiller::isAboided",
  "file": "src/Enemy/BathtubKiller.cpp",
  "old": "exact text of the block, must occur once in the file",
  "notes": "optional hints for the model: what the diff shows, what was tried",
  "candidates": [
    {"id": "a", "new": "replacement text", "note": "what this tries"}
  ]
}
```

A result lists each candidate's match for the function, the change from the baseline, and every other function in the unit whose match changed.
A candidate that helps the target and hurts a neighbour is not a fix.

## Rules for using results

A score is not evidence.
Before a candidate is committed, a reviewer checks it against `AGENTS.md`: no fakematches, no invented names, no locals or casts whose only job is the frame, and the whole `ninja changes_all` report.

## Local model setup (Windows PC, 8 GB GPU, 48 GB RAM)

1. Install Ollama from https://ollama.com and start it.
2. Pull a coding model that fits (Mixture-of-Experts models run well with most of the model in system RAM):
   ```
   ollama pull qwen3-coder:30b
   ```
   Optional, stronger on paper: a 4-bit build of Qwen3.6-35B-A3B from Hugging Face (about 22 GB), for example `ollama pull hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:Q4_K_M`.
   Check the repository name on huggingface.co first; the tag above is not verified.
3. Raise Ollama's context so the prompt fits, and halve the cache memory:
   ```
   setx OLLAMA_CONTEXT_LENGTH 16384
   setx OLLAMA_KV_CACHE_TYPE q8_0
   ```
   Restart Ollama after setting them.
4. In the decomp checkout (it must build with `ninja`):
   ```
   python tools/trials/run_queue.py ..\agent-mailbox\local-model\tasks --n 8 --rounds 2
   ```
   Add `--model <tag>` to use another model, or `--no-model` to only score the candidates already in the tasks.
5. Commit and push the `*.result.json` files in the mailbox, and tell the Decomp chat.

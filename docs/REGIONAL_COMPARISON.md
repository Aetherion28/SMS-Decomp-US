# US compared with the original JP 1.0 release

This repository holds the US version of Super Mario Sunshine (`GMSE01`).
Everything below concerns that version only; the original JP 1.0 release is the reference it is compared against.

Measured on 2026-11-01 from the supplied US image.
Each percentage is weighted by target function size, not by the number of functions.

## Original executable overlap with JP 1.0

| Image | Exact bytes vs JP 1.0 | Including relocation-masked candidates vs JP 1.0 | Named-function code coverage |
|---|---:|---:|---:|
| US | 5.6004% | 87.6106% | 99.7652% |

An exact match requires the same paired function name, the same size, and an identical SHA-256 of the original linked function bytes.
Functions are paired by translation unit and mangled name; an unambiguous global name is the fallback when unit ownership differs.
Ambiguous names are not paired.
Functions with different sizes are marked changed.

A relocation-masked candidate requires the same size, identical bytes outside known PowerPC ELF relocation fields, and identical relocation positions and types.
Only fields identified by decomp-toolkit are masked.
Unknown relocation types are rejected conservatively.
**Relocation targets, referenced constants, strings, and data may differ, so these candidates are not proven behaviorally equivalent or ready to mark matching.**
Exact matches are included in the candidate-inclusive percentage.
No instruction sequence alignment, opcode-only scoring, register renaming, fuzzy threshold, or manual match assignment is used for this comparison.
The denominator is all named, nonzero-size functions in the target, including changed and unpaired functions.
The coverage column is the fraction of original executable code-section bytes covered by those functions.
Symbol ranges are checked for overlap to avoid double-counting aliases.
Uncovered bytes, including code padding and exception/vector regions not represented as functions, are excluded from overlap percentages and are not claimed to match.
No comparison of disc assets, audio, graphics, or gameplay behavior is included.

## Current source decompilation progress

These figures come from a fresh objdiff report against this version's original objects.
They are a separate measurement from original-executable overlap.
Fuzzy similarity is a diagnostic and does not establish correct behavior.
The normal matching build still uses original objects for unfinished translation units; a byte-identical rebuilt DOL does not mean the game is fully decompiled.

| Target | Source code matched | Fuzzy | Functions matched | Units complete |
|---|---:|---:|---:|---:|
| US | 52.51% | 99.11% | 10519 / 12905 | 394 / 732 |

Measured on 2026-11-01.
The source is shared with the other regional repositories; every change between releases is behind a version check, and this version builds with `VERSION_GMSE01`.

## Verification and provenance

The repository rebuilds a DOL whose SHA-1 equals this version's original executable (`config/GMSE01/build.sha1`, recorded in `assets/build-verification.json`).
`ninja baseline` and `ninja changes_all` were run against the previous commit; no function lost points.
Seven functions score lower than in the earlier upstream-derived snapshot, because this source removes upstream's `#pragma dont_inline` and fabricated helpers; they score the same as in the main JP project.
No ISO files are in Git.
This version's own executable and linker map are tracked under `orig/GMSE01/` so that the repository builds without the disc; nothing from any other version is tracked.
The US disc ships no linker map; the `marioUS.MAP` tracked here is the map of this same US executable as shipped on the Korean disc.

Toolchain: decomp-toolkit v1.8.4, objdiff-cli v3.8.1 and the repository's pinned MWCC compilers; the 2026-11-01 measurements were made on Linux.
The comparison tool records the original DOL SHA-256 hashes, base Git revisions, source-tree content hashes, and hashes of the configuration/symbol/split files.
This image's ISO SHA-256 and executable SHA-1/SHA-256 values are in `assets/disc-inventory.json`.
`assets/build-verification.json` records the expected and rebuilt DOL hashes.

## Maps and detailed results

- [Current decompilation progress](../assets/progress.html), with SVG preview in README.
- [Reuse candidates against JP 1.0](../assets/reuse.html).
- [Every function against JP 1.0, CSV](../assets/regional-comparison.csv).
- [Full comparison against JP 1.0, JSON](../assets/regional-comparison.json).

GitHub displays HTML as source; download the HTML file and open it in a browser to use the interactive map.
The maps contain their own data, styles, and scripts and work offline.
Source links open the corresponding private GitHub repository.
The progress map's function count also includes zero-size function symbols; executable-overlap analysis excludes them.

## Reproduce

Put the matching image or extracted files in `orig/GMSE01/`, configure the target, and run `ninja`.
Check the configured SHA-1 before interpreting any progress or overlap results.
Regenerate the repository's own progress map with:

```sh
python tools/progress_treemap.py
```

For the comparison with JP 1.0, install `pyelftools`, build this target and a JP 1.0 checkout first, and run:

```sh
python tools/regional_compare.py --baseline ../sms-ai-decomp --baseline-version GMSJ01
python tools/reuse_treemap.py
```

Use the original executable matching this repository's target hash.

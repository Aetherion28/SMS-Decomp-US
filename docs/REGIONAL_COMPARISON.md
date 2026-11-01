# Super Mario Sunshine regional code comparison

Measured on 2026-10-31 from the six supplied ISO files.
JP 1.0 is the original `sms-ai-decomp` target; PAL is the target of `SMS-AI-Decomp-PAL`.
Both references are included below.
Each percentage is weighted by target function size, not by the number of functions.

## Original executable overlap

| Supplied image | Exact bytes vs JP 1.0 | Including relocation-masked candidates vs JP 1.0 | Exact bytes vs PAL | Including relocation-masked candidates vs PAL | Named-function code coverage |
|---|---:|---:|---:|---:|---:|
| JP 1.0 | 100.0000% | 100.0000% | 5.2974% | 83.3110% | 99.7641% |
| PAL | 5.3250% | 83.7459% | 100.0000% | 100.0000% | 99.7635% |
| US | 5.6004% | 87.6106% | 6.5189% | 91.0926% | 99.7652% |
| Korean image | 5.6004% | 87.6106% | 6.5189% | 91.0926% | 99.7652% |
| JP 1.1 | 5.6359% | 86.2825% | 6.4519% | 94.3075% | 99.7623% |
| 3D All-Stars | 5.1212% | 80.4091% | 7.6014% | 91.9426% | 99.7625% |

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

These figures come from fresh objdiff reports against each target's original objects.
They are a separate measurement from original-executable overlap.
Fuzzy similarity is a diagnostic and does not establish correct behavior.
The normal matching build still uses original objects for unfinished translation units; a byte-identical rebuilt DOL does not mean the game is fully decompiled.

| Repository target | Source code matched | Fuzzy | Functions matched | Units complete |
|---|---:|---:|---:|---:|
| JP 1.0 | 52.96% | 99.15% | 10534 / 12881 | 411 / 736 |
| PAL | 52.47% | 99.11% | 10391 / 12751 | 403 / 730 |
| US | 52.09% | 99.09% | 10476 / 12905 | 394 / 732 |
| Korean image | 52.09% | 99.09% | 10476 / 12905 | 394 / 732 |
| JP 1.1 | 52.64% | 99.11% | 10372 / 12724 | 392 / 731 |
| 3D All-Stars | 51.67% | 98.91% | 10284 / 12718 | 391 / 730 |

Measured on 2026-11-01.
All regional repositories now share one source tree with the PAL repository; each change between releases is behind a version check (`VERSION_GMSJ01`, `VERSION_GMSE01`, `VERSION_GMSJ01_01`, `VERSION_GMSP01`, `VERSION_GMSP01_NX`, and `VERSION_GMSE01_KR` for the Korean image).
JP 1.0 is measured from the main project's committed README.

## Verification and provenance

Each repository rebuilds a DOL whose SHA-1 equals its own original executable (`config/<version>/build.sha1`, recorded in `assets/build-verification.json`).
The Korean target is verified against the executable extracted from the supplied Korean-named ISO, after correcting its stale read-only-data symbol layout.
`ninja baseline` and `ninja changes_all` were run in every repository against its previous commit.
Seven functions score lower than in the earlier upstream-derived snapshot, because this source removes upstream's `#pragma dont_inline` and fabricated helpers; they score the same as in the main JP project.
No ISO files were added to Git.

Toolchain: decomp-toolkit v1.8.4, objdiff-cli v3.8.1 and the repository's pinned MWCC compilers; the 2026-11-01 measurements were made on Linux.
The comparison tool records original DOL SHA-256 hashes, base Git revisions, source-tree content hashes, and hashes of the configuration/symbol/split files.
Complete ISO SHA-256 and executable SHA-1/SHA-256 values are in `assets/disc-inventory.json`.
`assets/build-verification.json` records expected and rebuilt DOL hashes.

The image named Korean reports disc ID `GMSE01`, disc number 0, and revision byte 48 (`0x30`).
Its title remains `Super Mario Sunshine`.
Its filename and header do not establish release provenance or language support.
These results apply to this exact supplied image, without assuming an official Korean release.

## Maps and detailed results

- [Current decompilation progress](../assets/progress.html), with SVG preview in README.
- [Reuse candidates against JP 1.0](../assets/reuse.html).
- [Reuse candidates against PAL](../assets/reuse-vs-pal.html).
- [Every function against JP 1.0, CSV](../assets/regional-comparison.csv).
- [Full comparison against JP 1.0, JSON](../assets/regional-comparison.json).
- [Full comparison against PAL, JSON](../assets/comparison-vs-pal.json).

GitHub displays HTML as source; download the HTML file and open it in a browser to use the interactive map.
The maps contain their own data, styles, and scripts and work offline.
Source links open the corresponding private GitHub repository.
The progress map's function count also includes zero-size function symbols; executable-overlap analysis excludes them.

## Reproduce

Put the matching image or extracted files in `orig/<version>/`, configure the desired target, and run `ninja` in each repository.
Check the configured SHA-1 before interpreting any progress or overlap results.
Regenerate the repository's own progress map with:

```sh
python tools/progress_treemap.py
```

For comparisons, install `pyelftools`, build both reference and target first, and run:

```sh
python tools/regional_compare.py --baseline ../sms-ai-decomp --baseline-version GMSJ01
python tools/reuse_treemap.py
python tools/regional_compare.py --baseline ../SMS-AI-Decomp-PAL --baseline-version GMSP01 --output assets/comparison-vs-pal.json
python tools/reuse_treemap.py --comparison assets/comparison-vs-pal.json --baseline-label PAL --basename reuse-vs-pal
```

Use the original executable matching this repository's target hash.
The Korean repository uses the `GMSE01` build key for its distinct image, not the standard US executable.
The inherited build CI image provides standard retail reference files; it does not provide this distinct Korean original.
Korean builds in CI therefore require provisioning the exact Korean reference separately, and must not silently substitute standard US files.

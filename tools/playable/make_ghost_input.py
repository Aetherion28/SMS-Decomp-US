#!/usr/bin/env python3
"""Write a files/ghost_input.bin for the ghost oracle (tools/playable/oracle.cpp).

This is the smoke-test writer, not the ghost converter: it builds a short
synthetic input so a fresh oracle DOL can be checked in Dolphin before any
real ghost is converted.

  python3 tools/playable/make_ghost_input.py out/files/ghost_input.bin
      --first-tick 400 --frames 600 [--seed 0x1234]

The synthetic input holds the stick forward for the whole run and taps A on
every 60th frame, starting at the frame whose last sim tick is --first-tick
(ticks are counted from the arming tick, 4 per frame at 60 Hz).

--csv FILE reads frames from a CSV instead, one record per line:
  buttons(hex),stickX,stickY,substickX,substickY,triggerL,triggerR,analogA,analogB

File layout: see the comment at the top of tools/playable/oracle.cpp.
"""

import argparse
import struct
import sys

MAGIC = b"SGIN"
PAD_BUTTON_A = 0x0100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--first-tick", type=int, default=400,
                    help="sim tick (from arming) that the first record's frame ends on")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--ticks-per-frame", type=int, default=4)
    ap.add_argument("--log-first", type=int, default=0)
    ap.add_argument("--log-last", type=int, default=0xFFFFFFFF)
    ap.add_argument("--seed", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--csv")
    args = ap.parse_args()

    records = []
    if args.csv:
        with open(args.csv) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                v = line.split(",")
                records.append((int(v[0], 16), *[int(x) for x in v[1:9]]))
    else:
        for i in range(args.frames):
            buttons = PAD_BUTTON_A if i % 60 == 30 else 0
            records.append((buttons, 0, 80, 0, 0, 0, 0, 0, 0))

    flags = 1 if args.seed is not None else 0
    hdr = struct.pack(">4sHHIIIIII", MAGIC, 1, flags, len(records),
                      args.log_first, args.log_last, args.seed or 0,
                      args.first_tick, 0)
    body = b"".join(struct.pack(">HbbbbBBBBH", *r, 0) for r in records)
    with open(args.out, "wb") as f:
        f.write(hdr + body)
    print(f"wrote {args.out}: {len(records)} records, first frame ends on tick "
          f"{args.first_tick}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

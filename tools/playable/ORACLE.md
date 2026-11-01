# Ghost oracle DOL

A playable build of the PAL decomp that replays a recorded pad input and
logs the game state every sim tick, so a replayed ghost can be compared
against the real game tick by tick.

## Build

```
python3 tools/build_playable.py --version GMSP01 --build-dir build_play --oracle
```

writes `build_play/GMSP01/playable/mario.dol`.
Everything is compiled with `-DSMS_ORACLE`, which turns on three hooks in the
sources (`JUTGamePad::read`, `TMarDirector::changeState`,
`TMarDirector::direct`) and links `tools/playable/oracle.cpp`.
Without the define the hooks are gone and the matching build is byte for byte
the retail DOL.

## Run (Dolphin)

1. Extract the PAL disc to a folder with Dolphin (right click the game,
   Properties, Filesystem, Extract Entire Disc), giving `sys/` and `files/`.
2. Replace `sys/main.dol` with the oracle DOL.
3. Put the input file at `files/ghost_input.bin`.
   For a smoke test without a real ghost:
   `python3 tools/playable/make_ghost_input.py files/ghost_input.bin`
   (stick held forward, A tapped every 60 frames, from tick 400 after the
   stage intro starts).
4. Set the game to 60 Hz (PAL60) so a frame is 4 sim ticks, as the input
   file assumes.
5. Turn on OSReport logging: View, Show Log and Show Log Configuration, tick
   `OSReport` (also called `OSReport HLE`), set the verbosity to Info, and
   enable the file writer. Dolphin finds `OSReport` by its code signature;
   if nothing appears, load the symbol map (Symbols, Load Symbol Map, pick
   `build_play/GMSP01/playable/mario.elf` via Load Other Map File, or the
   retail `marioEU.MAP`) and try again.
6. Boot `sys/main.dol` (File, Open, or drag the folder in) and enter the
   stage. The log starts at the first `O arm` line.

## Log lines

- `O arm tick=0 frame=0 tpf=4 recs=N first=F log=A-B seed=S loaded=1`
  written when the director enters the stage intro state (STATE_UNK1).
  This tick is tick 0; `tpf` is sim ticks per frame; `loaded=0` means the
  input file was not found or rejected (an `O error:` line says why) and the
  real controller stays in charge.
- `O state tick=T frame=F state=S` on every director state change.
  The GAME state is 4.
- `I frame=F tick=T rec=N b=.... x= y= cx= cy= l= r=` on every pad read
  after arming: the record applied to the coming frame (`rec=-` is neutral).
- `T tick frame state mode cue st=... p=x y z v=x y z fv= yaw= w= cp=x y z ct=x y z rng=`
  one per sim tick inside the log range: director state and mode, whether
  CUE_MOVE ran, Mario's status, position, velocity, forward speed, face yaw,
  FLUDD water, camera position and target, and the MSL `rand()` state.
  Every float is its raw 32-bit pattern in hex.

## Input file

`files/ghost_input.bin`, big-endian, as agreed with the viewer:

```
0x00 char[4] "SGIN"
0x04 u16     version = 1
0x06 u16     flags (bit 0: rng seed present)
0x08 u32     record count
0x0C u32     first logged tick
0x10 u32     last logged tick
0x14 u32     rng seed (if flag bit 0), applied with srand() at arming
0x18 u32     tick the first record's frame ends on
0x1C u32     reserved
0x20 records, 12 bytes each, one per frame:
     u16 buttons, s8 stickX, s8 stickY, s8 substickX, s8 substickY,
     u8 triggerL, u8 triggerR, u8 analogA, u8 analogB, u16 reserved
```

Record n feeds the frame whose last sim tick is `first + 4n`.
Before the first record and after the last the pad reads neutral.
Only controller port 0 is replayed.

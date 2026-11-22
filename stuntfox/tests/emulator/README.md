# Portable GBA smoke tests

This short integration gate runs the actual standalone or merged Stunt Fox ROM
in a stock mGBA libretro core. It cold-boots the game, sends real buttons, reads
state through the matching ELF symbols, and writes screenshots plus a JSON
report. It does not teleport entities, inject debug commands, or load savestates.

Install Pillow and mGBA's libretro core, set `MGBA_CORE` to the core's absolute
shared-library path, and put `llvm-nm` or `nm` on `PATH`. Use the ELF produced by
the same build as the ROM. From the repository root:

```sh
python3 stuntfox/build.py ORIGINAL.gba --merge --no-remixes -o merged.gba
python3 stuntfox/tests/emulator/smoke.py merged.gba \
  --elf stuntfox/build/merge/stuntfox-merge.elf --mode merge --out /tmp/sf-merged-smoke

python3 stuntfox/build.py ORIGINAL.gba -o standalone.gba
python3 stuntfox/tests/emulator/smoke.py standalone.gba \
  --elf stuntfox/build/stuntfox.elf --mode standalone --out /tmp/sf-standalone-smoke
```

The merge path checks a settings change across closing/reopening the page,
story start, walking, calling and boarding the Arwing, takeoff, pause/resume,
air bail-out, recovery, and walking afterward. The standalone path checks
driving, retry, Arwing entry/takeoff, return to the car, and continued rendering.
Its reported FPS is one scene's in-game counter, not a whole-game speed claim.

The script exits nonzero for failed checks and records the ROM and ELF SHA-256
values. These private-ROM tests do not run in public CI. The separate
`tests/s2/` scripts retain their historical `SP` harness requirements; this smoke
test needs no external `SP/v12` helper tree.

This gate does not certify a full campaign, native campaign saves, optional
remix audio, Pizza Boy A, or physical hardware. The 512-byte original/mod save
compatibility suite under `payback-mod/harness/` applies to that target only.

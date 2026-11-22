# Portable GBA integration tests

These tests run the actual standalone or merged Stunt Fox ROM in a stock mGBA
libretro core. They cold-boot the game, read state through the matching ELF
symbols, and write screenshots plus JSON reports. `smoke.py` uses real buttons
and read-only inspection throughout. The campaign, ending and space-walk tests
have explicit setup fixtures described below; none uses emulator savestates.

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

## Gameplay smoke

The merge smoke path checks a settings change across closing/reopening the page,
story start, walking, calling and boarding the Arwing, takeoff, pause/resume,
air bail-out, recovery, and walking afterward. The standalone path checks
driving, retry, Arwing entry/takeoff, return to the car, and continued rendering.
Its reported FPS is one scene's in-game counter and has that scene's scope.

## Native campaign saves

```sh
python3 stuntfox/tests/emulator/campaign_save.py merged.gba \
  --elf stuntfox/build/merge/stuntfox-merge.elf --out /tmp/sf-campaign-save
```

Every write, cold reader and interrupted-write recovery uses a separate OS
process and native 8 KiB EEPROM. The matrix covers campaign start and Save Now,
shop purchases, paint, all 31 game-setting sliders, controls, ragdolls, radio,
jet-pack ownership, chapter/act state, Stop followed by cold Continue, fallback
after an actual partial write, old zero-spare save compatibility, and expansion
from a 512-byte Payback profile while preserving its original bytes.

A ship-pose fixture shortens docking travel. The advanced scenario grants a
900-credit purchase budget and seeds chapter/act/receipt state; its purchase and
save still use real menus. The report identifies every setup write. See
[CAMPAIGN_SAVE.md](CAMPAIGN_SAVE.md) for the exact method, format and limits.

## Campaign ending and postgame

```sh
python3 stuntfox/tests/emulator/ending.py merged.gba \
  --elf stuntfox/build/merge/stuntfox-merge.elf --out /tmp/sf-ending
```

This fixture seeds earlier act completion, travels to the real final map, and
advances the final mission's objective predicates through existing debug
commands. Its payment, completion event, Ace unlock, docking and ending code
run normally. Real buttons exercise the completion cards, held-input behavior,
back/continue, pause/resume and station movement afterward. Instrumented travel
also checks that completed cities remain accessible without restarting the
ending. `--prepare-only` checks just the late-game setup.

This establishes the ending integration with a seeded late-game state. It does
not represent an earned playthrough of every act or certify the final battle's
difficulty.

## Space-walk assignments

```sh
python3 stuntfox/tests/emulator/eva.py merged.gba \
  --elf stuntfox/build/merge/stuntfox-merge.elf --out /tmp/sf-eva
```

The test uses station menus to reach the Nav board, checks campaign and
jet-pack requirements, walks to the workshop, confirms a paid purchase and
accepts the three assignments. Actual movement reaches the beacon checks,
physics performs the moon landing, and real Select input recalls and boards
the Arwing. It checks first-clear and repeat rewards, cancellation, the relay's
safe-return requirement, and a fresh-process native reload of earned receipts,
credits and jet-pack ownership.

Setup grants the missing 600 credits for the workshop purchase and shortens
travel by placing the ship near docking and the walker outside beacon contact
or above the moon post. It never seeds assignment state, completion receipts,
contact flags, rewards or boarding results. The report records these fixtures;
they leave travel duration and a natural uninterrupted playthrough unmeasured.

The board check also inspects captured pixels for all three first-clear stars;
this catches a valid receipt whose glyph is missing from the HUD font. To
inspect a native save earned by a previous full EVA run on a new build, use
`--inspect-save /path/to/previous-run/native.srm` with a new output directory.
This mode cold-boots that save, verifies its three receipts, 1,000 earned
credits and jet pack, then enters the board through real controls. It copies
the source save before running and records its hash.

## Reports and limits

Each script exits nonzero for failed checks and records the ROM and ELF SHA-256
values. These private-ROM tests do not run in public CI. The separate
`tests/s2/` scripts retain their historical `SP` harness requirements; this smoke
suite needs no external `SP/v12` helper tree. Native-save and EVA output
directories must be new or empty, so an earlier captured save is not overwritten.

These gates do not certify a full earned campaign playthrough, optional remix
audio, Pizza Boy A, or physical hardware. Native campaign acceptance covers
the merged engine's 8 KiB EEPROM; the separate 512-byte original/mod save
compatibility suite under `payback-mod/harness/` applies to its earlier target.

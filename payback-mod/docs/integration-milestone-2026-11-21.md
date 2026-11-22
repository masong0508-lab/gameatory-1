# Payback: Stunt Fox — integration milestone (2026-11-21)

## What is integrated

- Expanded 16 MiB GBA ROM, relocated column table, and 128×128 stadium map grid
- Stadium kicker, deck climb, whoops, tabletop, loop-trigger and boost-trigger columns
- Separate complete pointer grids for the existing story city, Neo Mute City free roam, and the Arwing space level
- Runtime Thumb hook for SELECT + A/B/L/R/UP/DOWN construction, driving stunts, cheat switches, and map transitions
- English UI replacements and configurable gravity/vehicle changes
- BPS packaging against the specified original European ROM

All original game content belongs to the user-provided source ROM. **Never add a Payback ROM to the public repository or CI artifacts.**

## Bugs addressed in this milestone

1. Runtime editor now checks for a valid EWRAM map grid before touching it.
2. Entity lookup checks both the entity count and pointer range instead of dereferencing a potentially invalid controlled slot.
3. Building from the edge of the city no longer reads an invalid target grid cell.
4. Cursor cleanup does not overwrite changes from unrelated game systems.
5. Stunt physics rejects off-map vehicle coordinates.
6. Neo Mute City treats elevated traffic-flagged streets as streets before checking height. This prevents scenery from replacing raised roadway lanes.
7. ARM build no longer hides link errors and works without `llvm-nm` by falling back to `nm`.
8. CI compiles the ARM editor from source, validates linker data placement, tests ROM-independent logic, and packages source/code only.

## Local reproducibility

Bring your own legally obtained **Payback (Europe) (En,Fr,De,Es,It).gba**.
Required SHA-1: `08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7`.

```sh
# Requires clang, ld.lld, llvm-objcopy, Python 3
sh payback-mod/asm/build.sh
python3 payback-mod/build.py "Payback (Europe) (En,Fr,De,Es,It).gba" \
    -o payback-stunt-fox.gba --bps payback-stunt-fox.bps

python3 -m unittest discover -s payback-mod/tests -p "test_*.py" -v
```

**Important:** `build.py` uses `paybackmod/editor.bin` from the working tree. Re-run `asm/build.sh` after any `editor.c` change; do not rely on the precompiled blob in an old checkout. GitHub Actions builds a fresh blob for its packaged toolkit.

## Validation achieved

- ROM-independent codec, BPS, bounds, and elevated road regression tests have been added to CI
- With a locally held, SHA-1 verified original ROM, a 16 MiB full integration image was generated
- A standalone BPS patch reconstructed the resulting image exactly, including output CRC and byte equality
- All stadium cells and the three stored map grids passed byte-level structural assertions
- Zero original ROM data is uploaded to the public repository or CI

## Remaining blockers before a release-ready label

- Real mGBA boot and long-form playthrough of menu, intro, city, space, garage, and stunt course
- Visual validation of loops, ramps, transitions, cars, and pixel presentation
- Frame pacing measurements on authentic GBA-class hardware/emulation
- Runtime tests for SELECT editing near city boundaries, vehicle exit during map swaps, and save/load transitions

**Status:** source-integrated experimental candidate, **not emulator-playthrough-verified or release-ready**.
# Historical integration checkpoint

This record describes the earlier structural-only build. For the canonical
emulator-tested build and current limitations, see
[the playability milestone](playability-milestone.md).


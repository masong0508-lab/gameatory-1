# Payback: Stunt Fox / Star-FlyBack

This repository contains three related targets. Choose a target before building;
their controls, save extensions and validation status differ.

| Target | What it contains | Start here |
| --- | --- | --- |
| `payback-mod/` | The 16 MiB GBA milestone: Payback's engine, stadium, rebuilt free-roam city, builder and helicopter-based Arwing | The play/build instructions below |
| `stuntfox/` | The larger GBA engine: custom rendering and physics, campaign, Fox Station, flight, space walks and radio; standalone or merged with Payback | [Stunt Fox README](stuntfox/README.md) |
| `ps1/` | The staged PlayStation translation, runtime and renderer; later stages include patches over earlier work | [Current PS1 status and handoff](ps1/STATUS.md) |

The [pre-port validation notes](docs/pre-port-validation.md) record the repaired
standalone build, full-world simulator, native-save compatibility and actual
GBA emulator checks, with artifact hashes and remaining acceptance work.

## GBA playability milestone

A Payback (GBA, Europe) mod with a stadium stunt park, a rebuilt free-roam city,
dash plates, speed-dependent loops, an in-game builder, and an Arwing space arena.
The Arwing uses Payback's existing helicopter model and controls.

The playability milestone fixes actual emulator-reproduced bugs in vehicle
selection, Arwing exits, map reloads, height writes, builder controls, and loop
entry/exit. **SELECT + START** adds a quick stadium retry while driving a car in
free-roam Mute City. The runtime and private ROM have been exercised in mGBA;
see [the playability notes](payback-mod/docs/playability-milestone.md) for the
test scope and limitations.

## Play

Open the built `.gba` in a GBA emulator and choose **Stunt Fox free roam**. Enter
a road vehicle with **L**, then hold **SELECT** and press **START** to go to the
stadium loop run-up. Hold **A** to accelerate through the dash plates and loop.
The stadium also has a kicker/whoops/tabletop lane and a raised-deck drop lane.

| Control | Action |
| --- | --- |
| A / B | Accelerate / brake or reverse |
| Left / Right | Steer |
| L | Enter or leave a vehicle; take off or land the Arwing |
| START | Pause |
| SELECT + START | Stop and retry at the stadium, in a free-roam city car |
| Hold SELECT, then A | Build a four-cell kicker ramp ahead |
| Hold SELECT, then B / R | Build a platform / raise it one step |
| Hold SELECT, then L | Clear to ground |
| Hold SELECT, then Up / Down | Place a loop plate / dash plate |

Builder changes last until a map change or level reload. The build cursor marks
the target two cells ahead; the outer boundary and game-generated RAM columns
are protected. Entering the parked stadium Arwing switches to space. Land and
leave it with L to return to the city.

## Build from your ROM

This repository contains tooling and generated runtime code. It does not contain
the original game or full patched ROM. Supply:

`Payback (Europe) (En,Fr,De,Es,It).gba`

Expected SHA-1: `08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7`.

```sh
python3 payback-mod/build.py "Payback (Europe) (En,Fr,De,Es,It).gba" \
  -o payback-stunt-fox.gba --bps payback-stunt-fox.bps --report build-report.json
```

The output is 16 MiB. Python's standard library is enough when using the bundled,
matching runtime. The builder verifies the source ROM, runtime bytes, source
hashes, hook location and table bounds. It refuses stale compiled runtime files.

After changing C, assembly, linker input or the runtime build script, rebuild
with Clang, LLD, and LLVM tools:

```sh
sh payback-mod/asm/build.sh
```

`--gravity normal|half|low` selects jump gravity; the default is half. The generated
JSON report records exact source/output/patch hashes, runtime provenance, map
allocation and remaining ROM space.

## Repository regression checks

The same command runs the ROM-free regression gates locally and in GitHub
Actions. It covers the Payback mod, Stunt Fox's content/arena generators,
campaign save recovery, mission VM and radio, and PS1 build integrity.
Install Python 3, GCC, Clang/LLD/LLVM 19, and `patch`, then install the Python
build dependencies below (NumPy and Pillow). CI uses Ubuntu 24.04 and LLVM 19
so compiler changes cannot silently alter the RAM budgets.

```sh
python3 -m pip install -r stuntfox/requirements.txt
python3 tools/check.py --report test-results.json
```

Use `--suite mod`, `--suite stuntfox`, or `--suite ps1` to run one group.
`--rom ORIGINAL.gba` explicitly enables the content/arena cases that need the
original game. The default run keeps those integration cases separate and
does not use a local ROM or atlas cache. No ROM is needed or uploaded by CI.

### GBA artifact and emulator checks

```sh
python3 -m unittest discover -s payback-mod/tests -p 'test_*.py' -v
python3 payback-mod/harness/verify_artifact.py ORIGINAL.gba MOD.gba MOD.bps
```

The ROM-free suite includes tests that execute the production C against mapped
synthetic GBA memory. Linux and a host C compiler are needed for those cases.
CI installs the compiler before running them and also compiles ARM7TDMI code.

For actual game execution, set `MGBA_CORE` and use the
[emulator harness](payback-mod/harness/README.md). It covers driving, loop
completion, builder actions, natural vehicle retry, Arwing flight and map
reloads. Tests use documented RAM positioning for repeatable setup and real
game buttons for the behaviors under test.

The milestone's native profiles and statistics saved by **Quit** now pass
28 checks across 11 fresh emulator processes, including original-game-to-mod
and mod-to-original compatibility. These are 512-byte EEPROM saves; the test
does not use emulator checkpoints. See [native save checks](payback-mod/harness/README.md#native-eeprom-saves-and-cold-boots)
for the exact scope and command.

Physical hardware and a complete story playthrough remain unverified. Live
builder edits still reset on map change or level reload. The larger `stuntfox/`
engine has its own campaign save extension and separate validation scope.

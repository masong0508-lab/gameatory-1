# ps1/rig: emulator test rig for the Payback PS1 port

A headless libretro frontend in Python (ctypes) that boots a disc image of the PS1 port under a PlayStation core, plays
it with scripted pad input and checks what happens by reading the game's state out of emulated RAM (at GBA addresses)
and the text the game drew (from the runtime's draw ring). Sessions go from power-on through the menus into a level and
test walking, vehicles, pause, quit, save and load, map changes, speed and long soaks; each run prints PASS / FAIL lines
and leaves a contact sheet, a button script and a `result.json`.

Three cores are used: PCSX-ReARMed (fast, with its own HLE BIOS) and the accurate SwanStation and Beetle PSX, which boot
the disc with openboot, our own test boot ROM (sources in `openboot/`). No Sony BIOS is used or needed.

**Results are emulator-only.** The port targets DuckStation on Android; a PASS here says what these cores do with the
disc, nothing more.

Details: `RIG.md` (sessions, checks, API, memory layout), `BOOTROM.md` (openboot, the accurate cores).

## Cores

Download the Linux x86_64 nightlies from the libretro buildbot,
<https://buildbot.libretro.com/nightly/linux/x86_64/latest/>:

| core | file | rig name |
|---|---|---|
| SwanStation | `swanstation_libretro.so.zip` | `swanstation` |
| Beetle PSX (mednafen_psx) | `mednafen_psx_libretro.so.zip` | `beetle` |
| PCSX-ReARMed | `pcsx_rearmed_libretro.so.zip` | `pcsx_rearmed` |

Unzip them into `ps1/rig/cores/` (or any directory, then `export RIG_CORES=that/directory`). The figures in `RIG.md`
were made with the nightlies of 2026-11-21 (sha256 `fc65bb2d662c3ad7...` SwanStation, `d4b51ac966085636...` Beetle,
`a989f7ba6c570a06...` PCSX-ReARMed). Other builds work the same, except that the guest TTY of PCSX-ReARMed is only
switched on for the binary listed in `ps1game.PCSX_PSXOUT`.

## openboot

```sh
cd ps1/rig
sh openboot/build.sh                    # clang (mipsel target), ld.lld, llvm-objcopy, python3; images in openboot/build/
mkdir -p system
for n in scph5500 scph5501 scph5502; do cp openboot/build/openboot.bin system/$n.bin; done
```

The three names are the ones the cores look for; the content is openboot. `system/` is the default; another directory
works with `export RIG_SYSTEM=that/directory`. The variants (`openboot_strict.bin` and the others) are described in
`BOOTROM.md`.

## From power-on into a level on SwanStation

```sh
cd ps1/rig
python3 tools/ob_session.py sessions/new_game_to_level.py --core swanstation \
    --disc /path/to/payback.cue --syms /path/to/payback.elf --path pad --save-state --out runs/sw_level
```

`--disc` is the raw image (`.cue` + `.bin`) of the build under test and `--syms` its ELF (optional, but without it the
presses use fixed lengths and the counters are missing). `--path pad` plays the menus with real pad presses only. The
session prints PASS / FAIL lines and exits 1 on any FAIL; `runs/sw_level/` gets the contact sheet, the button script and
`result.json`, and `--save-state` writes `states/level_start.state` for later sessions (`--from-state`). The same with
`--core beetle` runs it on Beetle PSX; without `tools/ob_session.py` and with `--core pcsx_rearmed` (the default) it runs on
the fast core. Every session in a row: `./run_all.sh DISC OUTROOT [SYMS] [CORE]`.

## Environment

| variable | default | what |
|---|---|---|
| `RIG_CORES` | `ps1/rig/cores` | directory of the three libretro cores |
| `RIG_SYSTEM` | `ps1/rig/system` | openboot as `scph5500.bin`, `scph5501.bin`, `scph5502.bin` (SwanStation, Beetle) |
| `RIG_STATES` | `ps1/rig/states` | default `--state-dir` of the sessions |
| `RIG_BUILD` | `ps1/rig/build` | where the two small C shims are compiled to (gcc) |
| `RIG_MGBA_HARNESS` | `ps1/stage7/integration/mgba` | the mGBA harness for `tools/gba_ref_intro.py` |
| `PS1GAME_LAYOUT` | none | moved guest windows of a build, e.g. `EW=0x801b0000,DL=0x8017c000` |
| `SOAK_FRAMES`, `ONLY` | 120000, all | `run_all.sh`: soak length, session letters to run |
| `OB_*` | per script | parameters of the `sessions_ob/` scripts for `tools/obrun.py` |
| `OUT` | `openboot/build` | `openboot/build.sh`: output directory |

A missing core or an incomplete openboot directory stops the run with a message that names the file and what to do.

## Keep out of the repository

Cores, openboot images, disc images, ELF files of builds, save states, memory card images, contact sheets, screenshots and
run logs (they hold the game's pictures and text). `.gitignore` covers the default directories (`cores/`, `system/`,
`build/`, `openboot/build/`, `states/`, `runs/`). The rig itself quotes no text of the game: see "Text" in `RIG.md`.

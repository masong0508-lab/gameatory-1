# PS1 test rig for the Payback port

Headless, scripted play of a disc image under a libretro core, with the game's state read out of emulated RAM at GBA
addresses. Written for and run with the fast core (`pcsx_rearmed`, its HLE BIOS, no BIOS file needed); the same sessions
run on the accurate cores (SwanStation, Beetle PSX) through `tools/ob_session.py` with our own boot ROM `openboot`
(`BOOTROM.md`). No Sony code or data is involved anywhere in the rig, and no Sony BIOS is used or needed.

The three cores are the Linux x86_64 nightlies of the libretro buildbot
(<https://buildbot.libretro.com/nightly/linux/x86_64/latest/>): PCSX-ReARMed (`pcsx_rearmed_libretro.so`), SwanStation
(`swanstation_libretro.so`) and Beetle PSX (`mednafen_psx_libretro.so`).

Everything takes the disc and the symbol file as parameters, so a new build is tested with the same commands. The figures
quoted below were measured on the release candidates "RC v2" and "rc4" (before the stage-19 fixes for accurate
emulators); the findings of those runs are not part of this directory. Every result of the rig is emulator-only: the
target of the port is DuckStation on Android.

All paths below are relative to this directory (`ps1/rig/`). Setting up the cores and openboot: `README.md`.

## Layout

| Path | What |
|---|---|
| `retro_ps1.py` | the ctypes libretro frontend (`Emu`): one `retro_run` = one frame, per-frame pad state, RAM, save states; finds the cores (`RIG_CORES`) and the openboot directory (`RIG_SYSTEM`) |
| `ps1game.py` | `Game(Emu)`: GBA memory helpers, text read-back, patient presses, pictures and contact sheets, memory card, save states, GPU/VRAM read-out, CPU position and call chain, page cache, counters, TTY with frame stamps |
| `payback.py` | `Payback(Game)`: the game's screens and flows (language, logos, title, slots, name, game menu, rampage, level), menu cursor, picture classes, steering; the GBA reference figures (`GBA_*`) and the text marks (see "Text") |
| `rigshim.c`, `liblog.c` | log sinks of the core: core log and guest TTY to files (compiled with gcc on first use into `build/`, or `RIG_BUILD`) |
| `sessions/*.py` | the sessions (below) |
| `run_all.sh` | every session in a row, one emulator process at a time, with a FAIL summary |
| `tools/ob_session.py` | runs any session on SwanStation / Beetle with openboot (section "Accurate cores") |
| `tools/obrun.py`, `tools/obrig.py`, `sessions_ob/*.py`, the other `tools/ob*.py` | the sampled sessions and tools of the work on the accurate cores (`BOOTROM.md`) |
| `openboot/` | sources of openboot, our own test boot ROM, and `build.sh` |
| `tools/gba_ref_intro.py` | what the GBA original does after the logos and in the intro entry (mGBA, your own cartridge dump): the reference the intro checks use |
| `tools/exp_intro.py` | experiment: how long the intro runs on a PS1 build, and whether Cross ends it |
| `tools/pause_probe.py` | probe: from a level state, Start, every complete 2D frame the rig sees while paused and after resuming, then pictures at growing intervals (how long the menu stays on the picture, when the HUD comes back) |
| `tools/mips1_lint.py`, `loaddelay.py`, `bioscalls.py`, `gpuwait_scan.py`, `gpuwait_classify.py` | static checks of an ELF / raw image: instructions the R3000A does not have, load-delay hazards, kernel call sites, GPU waits |
| `tools/iso2raw.py`, `patch_disc.py`, `patch_elf.py` | TEST-ONLY disc images: raw MODE2/2352 from a plain ISO, copies with words of the boot executable replaced, the matching ELF |

Made locally and never committed (`.gitignore`): `cores/` (the libretro cores), `system/` (openboot under the BIOS file
names), `build/` (compiled shims), `openboot/build/`, `states/` (save states), `runs/` (session outputs). States, card
images, pictures and contact sheets show or hold the game: keep them out of the repository.

Needs: python3 with Pillow (numpy is used when present), gcc (shims), the cores (`README.md`). For `tools/gba_ref_intro.py`:
libmgba and the repository's mGBA harness `../stage7/integration/mgba/emu.py` (or `RIG_MGBA_HARNESS`).

## Quick start

```sh
cd ps1/rig
DISC=/path/to/payback.cue          # the build under test (pcsx_rearmed also reads the plain 2048-byte ISO)
SYMS=/path/to/payback.elf          # its ELF (or nm output / linker map); optional, but most counters need it
./run_all.sh $DISC runs/all $SYMS                       # every session, about 30 minutes, one CPU core
# one session
python3 sessions/boot_to_title.py     --disc $DISC --syms $SYMS --out runs/a
python3 sessions/new_game_to_level.py --disc $DISC --syms $SYMS --out runs/b --save-state --state-dir runs/states
python3 sessions/in_level.py          --disc $DISC --syms $SYMS --out runs/c --from-state runs/states/level_start.state
# a subset, a longer soak
ONLY="a b c" ./run_all.sh $DISC runs/x $SYMS ;  SOAK_FRAMES=240000 ONLY=f ./run_all.sh $DISC runs/y $SYMS
```

`run_all.sh DISC OUTROOT [SYMS] [CORE]` writes `OUTROOT/<session>.log` and `OUTROOT/<session>/`, the states to
`OUTROOT/states`, and prints at the end every FAIL line of the sessions it ran with how often it came. The session
letters for `ONLY`:
a boot_to_title, b new_game_to_level (pad and assist path), j replay, d maps, e save_load, f soak, c in_level,
g state_check, h speed, i strict_cpu (fast core only).

Every session accepts `--disc` (.cue / .bin / .iso), `--core` (default `pcsx_rearmed`), `--out`, `--syms`, `--card`
(`blank` | `none` | path of a 128 KiB image), `--state-dir` (default `RIG_STATES`, else `states/`) and `--opt KEY=VALUE`
(a core option, repeatable). It prints `PASS ...` / `FAIL ...` lines (plus `NOTE` lines and indented detail; the detail
of each check is in brackets), exits 1 when anything failed, and leaves in `--out`:

- `sheet.png` contact sheet of every picture taken, `NNN_tag.png` the single pictures (caption = emulator frame + step)
- `result.json` all checks with their detail, counters, card summary, events, the TTY timeline
- `script.txt` the exact button script: one line per change of the held buttons, `f<frame>: BTN+BTN` / `(release)`
- `tty.log` guest TTY (the runtime's `dbg()` output), `tty_timeline.txt` the same lines with the emulator frame at which the
  rig read them (30 frames resolution; the periodic `present` lines left out), `core.log` the core's own log
- `card1.mcd` the memory card image at the end of the run

The outputs of an earlier run in the same directory (numbered pictures, sheet, result, script, timeline) are removed when a
session starts, so a directory never mixes two runs. Run **one emulator process at a time**: a session takes one CPU core.

## Sessions

| Session | What it does | Notable options | Emulated frames (RC v2) |
|---|---|---|---|
| `boot_to_title.py` | cold boot, language screen; branch 1 (from a saved language state): hands off through the three logos and the intro video, then Cross; branch 2: Cross during the second logo to the title menu; then every title entry is opened and left again, the intro entry last | `--entries` (names of `payback.TITLE_ENTRIES`), `--no-idle-branch`, `--intro-gframes`, `--intro-max-frames`, `--save-state` (writes `title.state`) | 100 000 |
| `new_game_to_level.py` | blank card, start entry, slot 1, name, rampage entry of the game menu, start line, until the level clock counts and the 3D city is drawn; prints the button script | `--path pad` (real presses) or `--path assist` (no input, the build's own menu assist), `--save-state` (`level_start.state` / `level_start_assist.state`) | 14 000 / 63 000 |
| `replay.py` | replays a `script.txt` blind (nothing read back) and compares the frame the level clock starts and the RAM at the recording's last frame with the recording | `--script`, `--assist off|keep`, `--expect-level` (default: from the recording's `result.json`), `--tail` | 16 000 |
| `in_level.py` | idle, walk, turn, weapons, fire, pause/resume (menu, clock, 3D view and HUD back), death and respawn, vehicle (steer towards the nearest parked one, L1, drive, L1) | `--idle-ticks` (300 = 10 s game time), `--idle-max-frames`, `--steps`, `--approach-frames`, `--no-teleport`, `--no-death`, `--from-state` | 240 000 |
| `maps.py` | R2 through the 11 maps and round to map 0, L2 back, R2 again; one start view per map, taken after two 3D frames of the new map | `--step-frames`, `--from-state` | 140 000 |
| `save_load.py` | process 1: profile on a blank card, play, pause, quit, second level, card directory and payload check; process 2 (new process, cold boot with that card): slot list shows the save, game menu without name entry, level starts | `--play-ticks` | 55 000 + 11 000 |
| `soak.py` | seeded random input in a level; clock, picture, counter and TTY checks; `inputs.txt` lists what was pressed | `--game-seconds`, `--max-frames`, `--seed`, `--with-l1`, `--from-state` | 130 000 |
| `state_check.py` | loads the states of `--state-dir` that belong to this disc and core in a fresh process and compares RAM + frame buffer with the fingerprint of the saving process; states of other builds are skipped with a NOTE | `--state` | 5 000 |
| `speed.py` | guest frames, clock ticks, presented frames, CD sectors, ROM cluster loads per 60 emulator frames in ten scenes, and which ROM clusters were fetched | `--frames` | 50 000 |
| `strict_cpu.py` | boots under the CPU interpreter (stops at instructions the R3000A does not have) and checks the ELF statically | `--patch-invalid` (experiment), `--frames` | 3 000 |

`--from-state` skips the boot. A state belongs to one core and one PSX.EXE: when it does not fit the disc under test the
session says so in a NOTE and cold boots instead. Without `--from-state` a session cold boots and plays the menus with the pad.

### What the checks mean

- In the bracketed detail `a > b` means "from a to b" (`lives 3 > 2`, `heading 0 > 432`).
- A check states what the GBA game does; FAIL means this build does not. Whether a FAIL is the port, a known limit of the
  build or the rig is decided by whoever reads the run, not by the session. Checks that are about speed say so (`idle
  (speed)`, `soak covered 600 s of game time`).
- The intro checks compare with the GBA original in GUEST frames (`payback.GBA_INTRO_TITLE_AFTER` = 4590,
  `GBA_INTRO_SKIP_AFTER` = 100, `GBA_VIEW_INTRO_BACK_AFTER` = 4620; measured with `tools/gba_ref_intro.py` on the
  cartridge). The budget is `--intro-gframes` (6000, the GBA length plus 30 %).
  Pictures are compared with `shape_diff` (0 = the same picture, also faded): to the three boot logos of branch 1 and to
  the title picture (two title pictures that differ only in the cursor line are 0.14 to 0.19 apart, other screens 0.3 or
  more). The intro entry samples the picture every 30 frames while the title menu is away and counts each kind (black,
  title, logo 1..3, other); a build that comes back at once is measured in guest frames against the GBA's 4620.
- Checks of the 3D view use `payback.view_state()` on the picture and, with symbols, the runtime's `st3_render` / `sf3_ok`.
  When the 3D view goes away the detail lists the renderer lines of the TTY with their frames (`SF3 CONFLICT cold load over
  renderer data, renderer off`, `sf3 re-init after overlay load`, `sf3_ok 1`, `COLD load ...`).
  The pause step of `in_level.py` also times the HUD after resuming (`hud_white()`: share of near-white pixels in
  the score corner, at least half of what it was before Start; sampled every 120 frames while it waits for the 3D view,
  then every 60): RC v2 brings the HUD back before the 3D view (on a grey picture), rc4 leaves the pause menu drawn over
  the 3D view until the HUD comes back. The picture of that moment goes on the sheet as `HUD back`.
- Rig interventions are always printed as `NOTE RIG INTERVENTION` or `rig: ...`: `in_level.py` writes health 0 to provoke a
  death, and moves the man next to the vehicle by a RAM poke when walking there would not fit the frame budget (it then
  measures that the level runs on normally at the new place before it presses L1; `--no-teleport` walks the whole way).
  The walk steers in a straight line by entity positions, one decision per pad poll, with no path finding: a wall on the
  way stops it (RC v2, `--no-teleport`: the man stood at 115712,42700, 26700 units short of the vehicle, from frame 47000
  to 125000). At about 1 % game speed the man turns about 400 heading units (25 degrees) in 24000 frames, so when the
  budget ends while he still turns towards the vehicle the session prints a NOTE instead of failing "closer".
  The menu assist plan of the build is blanked in RAM (`assist_off()`, symbols `KPL*`) so that only pad input drives the
  menus; `--path assist` and `replay.py --assist keep` leave it alone.

## Accurate cores (SwanStation, Beetle PSX) through `tools/ob_session.py`

```sh
python3 tools/ob_session.py sessions/new_game_to_level.py --core swanstation --disc $DISC --syms $SYMS \
        --path pad --save-state --state-dir runs/sw_states --out runs/sw_level
python3 tools/ob_session.py sessions/in_level.py --core beetle --disc $DISC --syms $SYMS \
        --from-state runs/be_states/level_start.state --out runs/be_in_level
./run_all.sh $DISC runs/sw_all $SYMS swanstation     # every session (strict_cpu is skipped)
```

- `ob_session.py [--sys DIR] SESSION.py ARGS...` runs the session unchanged; it only gives the `Game` the system directory
  (`--sys DIR`, else `RIG_SYSTEM`, else `system/`: openboot as `scph5500.bin`, `scph5501.bin`, `scph5502.bin`; a
  directory holding one of the variants of `BOOTROM.md` works the same way) and the core options of `tools/obrun.py`
  (`DEFAULT_OPTS`: SwanStation software renderer, `BIOS_PathNTSCU=scph5501.bin`, no fast boot, CD speed-ups 1, card 1 =
  libretro; Beetle interpreter, synchronous CD access, no BIOS skip, card through libretro). A missing or incomplete
  `RIG_SYSTEM` directory is an error, never a silent fall-back to the cores' built-in firmware; an explicit `--sys DIR`
  is used as given (an empty one runs the open-source BIOS the cores carry inside).
- The disc must be a raw image (MODE2/2352): the release `.cue`/`.bin`, or a data-track-only copy made from the ISO with
  `tools/iso2raw.py` (Beetle needs the 16 system-area sectors of a raw image of the project's own disc for that copy:
  `--sysarea-from`).
- Builds before stage 19 (RC v2, rc4) showed a black picture on both accurate cores: busy-waits on GPUSTAT bit 26 that
  never end on hardware, and MIPS II `teq` words after divisions. `tools/gpuwait_scan.py`, `tools/mips1_lint.py`,
  `tools/patch_disc.py` and `tools/patch_elf.py` find those and make TEST-ONLY patched copies (never to be shipped).
- What differs from the fast core: the guest TTY is read from openboot's ring in RAM (0x5000) instead of the core's log, so
  `maps.py` (MAPCHANGE lines) and the renderer lines work with openboot; with any other firmware there is no TTY.
  `Game.gpu()`, `vram_image()`, `display_image()`, `fb_sha1()`, `cpu()`, `backtrace()` and `cpu_where()` read
  pcsx_rearmed's save state layout and return None on the other cores (fingerprints then compare RAM and the core's
  picture). `strict_cpu.py` is a pcsx_rearmed check (its interpreter); the accurate cores are strict anyway.
- Wall-clock speed measured on the machine the rig was written on: SwanStation about 20x real time, PCSX-ReARMed about
  9x, Beetle about 6x. The same "one emulator process at a time" applies.
- After a state load the text that openboot's ring already held is skipped (it was printed before the state was saved).
  The ring's text goes to `tty.log` and `tty_timeline.txt` like the fast core's TTY.

## How the GBA memory sits in PS1 RAM

The runtime (`rt.c`) keeps the guest's memory at fixed PS1 addresses (the same in RC v2 and rc4); `ps1game.g2h()` does the
conversion and `g8/g16/g32/gs16/gs32/gread(gba_address)` read through it.

| GBA region | GBA address | PS1 address |
|---|---|---|
| EWRAM 256 KiB | 0x02000000..0x0203ffff | 0x801b0000 + offset |
| IWRAM 32 KiB | 0x03000000..0x03007fff | 0x801f0000 + offset |
| palette | 0x05000000..0x050003ff | 0x80180000 + offset |
| OAM | 0x07000000..0x070003ff | 0x80180400 + offset |
| VRAM 96 KiB | 0x06000000..0x06017fff | 0x80181000 + offset (offsets from 0x18000 mirror 0x8000 lower) |
| IO registers | 0x04000000.. | window 0x8017f000, not memory: the translated code's IO accesses trap into `io_read` / `io_write`; the register file is the C static `io[0x400]` (symbol `io`: 0x8001fcc8 in RC v2, 0x800216cc in rc4), read with `Game.io16(offset)` |
| ROM | 0x08000000.. | not in RAM as a whole: page table `rom_pg` (2048 pointers, one per 4 KiB page: 0x80020700 in RC v2, 0x80022100 in rc4); 56 pages resident (the "rompack" below the cache), the rest read from `ROM.BIN` on demand into the page cache at 0x80158000..0x8015ffff (8 pages = 2 clusters of 16 KiB, first in first out, 8 sectors per miss; owners in `slot_owner`, 32 bytes, in both builds). `Game.rom(offset, n)` reads the file on the disc, `Game.rom_cache()` lists the cached pages |
| draw ring | - | 0x8017c000: a u32 count, then 256 entries of 32 bytes from 0x8017c020 (routine id, r0..r3): the last 256 calls of the game's 2D routines and pruned stubs (id 2 = a glyph, 1 = `gfx_fade_flip`, 6 = page clear; see "Text") |

A build that moves a window: `PS1GAME_LAYOUT="EW=0x...,IW=0x...,DL=0x..."` in the environment.

Pointers to EWRAM objects that the game keeps in its own RAM can hold the PS1 address: the entity pointer table at GBA
0x03000c60 (PS1 0x801f0c60) held 0x801b9394 (= GBA 0x02009394) in the level states of both builds, while ROM pointers
(entity descriptors 0x08......) stay GBA addresses; `Game._entp()` accepts both forms. In the level states of both
builds the page table had 56 resident pages at 0x8011fc74..0x80157c73 and the rest absent or in the cache. The cache
size is a build constant (`-DNSLOT=8 -DPCACHE_ADDR=...` from `t/disc7.sh` / `t/mkrompages.py` of the build tree; rc4
exports it as `__ps1_pcache_start` / `__ps1_pcache_end` = 0x80158000 / 0x80160000; later builds use other values).

Game variables used (GBA addresses, the same in every build of the same game ROM):

| What | Address | Helper |
|---|---|---|
| level clock, 30 per second | 0x02001e00 (u32) | `level_clock()` |
| map id / grid id | 0x02001d40 / 0x02001e66 | `map_id()`, `grid_id()` |
| level end (3 target reached, 2 game over), respawn counter (80..0), lives | 0x02001e08, 0x02001e0c, 0x02001e4e | `level_end()`, `respawn()`, `lives()` |
| controlled entity index, last entity index, entity pointer table | 0x02001db8, 0x0300000c, 0x03000c60 | `controlled()`, `nentity()`, `entities()`, `player()`, `pos()` |
| entity record | +4 x, +8 y (2048 a cell), +0xc z, +0x12 heading (5760 a turn), +0x1c descriptor, +0x68 health, +0x10f state (2 on foot, 7 dead) | `entity(i)` returns a dict; `kind` is `vehicle` / `person` from the descriptor's class byte |
| title menu cursor (a stack slot, valid only in the title menu) | 0x03007e68 | `title_cursor()` |

Heading 0 walks towards +y; Left raises the heading and turns towards +x (`payback.heading_to(dx, dy)`).
The renderer's map (R2/L2) is not guest state: it is the runtime static `sf3_map_cur` and the TTY line `MAPCHANGE to N`.

## What needs `--syms`

Guest addresses and the text read-back work without symbols. Runtime statics are looked up by name in the symbol file
(ELF symtab, `nm` text, lld or GNU ld map); when a name is missing the helper returns `None` and the sessions skip that
check. `result.json` says whether the ELF matches the PSX.EXE on the disc (`syms_match_disc`); a mismatching file is
ignored with a WARNING.

| Symbols | Used for |
|---|---|
| `pad_polls` | `tap()`: hold a button exactly until the runtime has read the pad (else fixed 600-frame holds) |
| `g_gframes`, `g_pres`, `io_cyc`, `cd_sectors`, `rom_miss_count`, `cold_loads`, `st3_render` | speed table, guest-frame budgets (intro), stall detection, "two 3D frames since" waits |
| `slot_owner`, `slot_next` (or `rom_miss_last`) | which ROM clusters the page cache fetched (`speed()`, `rom_cache()`, `rom_cluster_last()`) |
| `g_pres`, `buf` | save states only at a moment when `present()` is not running (see "Save states") |
| `io` | `dispcnt()`, logo detection, the hands-off branch of `boot_to_title.py` |
| `KPL*` | `assist_off()`: blank the menu assist plan in RAM (always logged as a rig intervention). Without it the build's assist stays on. |
| `pp_fade_w` | `wait_fade()` (else picture comparison) |
| `sf3_ok` | 3D renderer on/off flag in the level checks |
| `ip_undef`, `ip_stat_undef`, `pad_fails`, `mc_err`, `pp_lost`, `sf3_retry`, `pp_nreset` | fault counters of the soak |
| any function symbol | `cpu_where()`, `backtrace()`: where the CPU is, by name |

## API in short (`ps1game.Game`, `payback.Payback`)

```python
from payback import *
g = Payback(disc, outdir, core='pcsx_rearmed', card='blank', syms='payback.elf')
g.boot_to_language(); g.assist_off()
g.pad_language_to_title(); r = g.pad_title_to_level()
level_view(g, r.get('st3_before'))                    # wait until the level's own 3D picture is on screen
g.level_clock(); g.player(); g.g32(0x02001e00)
g.wait_until(lambda: g.level_clock() > 300, 60000, buttons=['CROSS'])
g.snap('walked'); g.finish('my session')
```

- **Memory card** `card='blank'` gives a formatted empty card made by the rig (`MemCard.blank()`), `'none'` an empty slot,
  a path or bytes a card carried over (the file is not modified). `g.card_now()` is the card as it is in the emulated slot:
  `.files()` (name, blocks, block list, size, title, checksum), `.free_blocks()`, `.payback_save()` (magic, sequence,
  CRC, payload), `.summary()`. `g.save_card(path)` writes the image; `finish()` writes `card1.mcd`. `g.card_idle()` waits
  until the runtime stopped writing.
- **Input** `g.run(frames, buttons)`; every change is recorded with its emulator frame (`g.script`, `g.script_text()`).
  `g.tap(buttons, until=..., wait=...)` is a click: hold until the runtime polled the pad twice (never shorter than one
  poll, even when `until()` is already true), release, wait for the condition. Use it for menus: RC v2 reads the pad
  once per presented frame (`pad_polls` = `g_pres` in every run; every 1 to 2 guest frames in menus, every 30 to 40 s of
  console time in the level: 10 polls in 24000 frames), rc4 more often (1005 polls for 417 presents and 1803 guest
  frames in `in_level`; 69 polls in 24000 frames of the level); the language screen and the logos act on the release.
- **Waiting** `g.wait_until(pred, max_frames, buttons=(), step=1)` returns the frames waited or `None`;
  `g.settle()` (two identical drawn frames), `g.wait_fade()`, `g.wait_presented(n)` (n pictures presented),
  `g.ready()` (all three: call it before a screenshot of a menu, the picture lags the text by up to two guest frames),
  `g.wait_clock(ticks, max_frames)`, `payback.level_view(g, st3_before)` (the level's own 3D frames are on screen).
- **Text** `g.text()`, `g.screen()`, `g.text_lines()` (text, x, y, font), `g.on('PAUSED')`: the text the game drew in the
  last complete 2D frame, read from the draw ring, no pixels involved. `g.selected(items)` is the highlighted menu line,
  `g.menu_goto(target, items)` moves a menu cursor with checked taps. A frame older than 8 guest frames counts as gone.
  rc4 alternates on its pause menu (drawn over the 3D view) a frame with the text and a frame holding one stub entry
  (kind 32), so `text()` flips between the menu and `''` and `settle()` never settles there; read such a screen inside
  the `until` of `tap()` (as `in_level.py` does) or from `g._rframes` (`tools/pause_probe.py` logs every frame).
  The rig does not quote the game's text: single UI words a check needs (`PAUSED`, `Cancel`, `Done`, `OK`, `Yes`, `No`,
  `UNUSED`, `Credits`, `Accelerate`, the language names) are plain strings, everything longer is a `ps1game.Mark` (our
  own label, the length, and the sha256 of the lower-cased words). `on()`, `menu()`, `selected()`, `menu_goto()` and
  `wait_text()` take both and match as a case-insensitive substring; the marks of the menus and screens are in
  `payback.py` (`START`, `TITLE`, `GAME_MENU`, `PAUSE_MENU`, the headings). A new mark is made from the words as the
  screen shows them: `Mark('my label', len(words), hashlib.sha256(words.lower().encode()).hexdigest())`, with only the
  digest committed. Logs and `result.json` still hold the drawn text of the run, so keep run outputs private.
- **Pictures** `g.snap(tag)`, `g.sheet(path)`, `contact_sheet(items, path)`, `measures(im)` (fractions of lit, white and
  coloured pixels), `lit(im)`, `is_black(im)`, `ncolors(im)`, `diff(a, b)`, `shape_diff(a, b)`.
  `payback.view_state(im)` classes a picture: `city` (the 3D view of the level: at least 80 % of the pixels lit and 10.5 %
  coloured), `black`, `white` (level start fade), `dark` (text or a logo on black: pause menu, logos, the HUD without the 3D
  view), `menu` (the grey bridge photograph pages). The thresholds were set on the screenshots of RC v2; a frame wider
  than 320 pixels (Beetle's 350x240) is judged on its centred 320x224 area.
  `payback.Scan(g).run(frames, buttons)` plays while sampling the picture (longest stretch without `city` / with a black
  picture) and keeps the first picture of the worst stretch (`scan.evidence(tag)` puts it on the contact sheet).
- **GPU** `g.gpu()` (GP1 registers, display area, VRAM bytes, parsed from the core's save state), `g.vram_image()` (the
  whole 1024 x 512 VRAM), `g.display_image()` (the displayed frame buffer), `g.fb_sha1()`.
- **Save states** `g.save_state_file(path, note)` / `g.load_state_file(path)` / `g.state_fits(path)`, see below.
- **TTY** `g.tty()` (all text), `g.tty_lines('MAPCHANGE')`, `g.tty_faults()`, `g.tty_when('CONFLICT', since=frame)` (lines
  with the frame they were read at), `g.renderer_events(since)` (the renderer / overlay lines, short).
- **Diagnosis** `g.counters()`, `g.speed(frames)` (rates per 60 emulator frames and the ROM clusters fetched),
  `g.stalled(frames)`, `g.cpu()`, `g.cpu_where(samples)` (PC and RA as `function+offset`), `g.backtrace()` (PC, RA and
  the return addresses found on the stack), `g.rom_cache()`.
- **Checks** `g.check(ok, text, detail)` prints PASS/FAIL and records it; `g.note(text)`; `g.finish(name)` writes the
  outputs and returns the exit code.

## Save states

`save_state_file` steps to a frame where the runtime is not inside `present()`, saves, then proves the state in the same
process (run 20 frames, reload, run 20 frames, compare) and writes `PATH`, `PATH.json` (core, PSX.EXE sha1, fingerprint
after 20 frames, options) and `PATH.mcd` (the card: the core's state does not carry it).
`load_state_file` checks core and PSX.EXE, puts the card back, leaves `present()` in the running machine, then loads.
`sessions/state_check.py` repeats the proof in a fresh process. The fingerprint is the sha1 of the 2 MiB of RAM and the
sha1 of the displayed frame buffer read out of VRAM (`fb`). A state holds the game's RAM: it stays out of the repository.

Two properties of the fast core that the rig works around:

- It keeps a GP0 transfer in flight outside its state. A state saved or loaded in the middle of `present()` gives
  garbage commands afterwards; both a segfault inside the core's GPU code and a frozen guest were seen that way. Hence
  the safe point (`present()` counts `g_pres` at its start and toggles `buf` once at its end in both builds; the extra
  toggles in rc4's `present()` are inside test-only `#ifdef`s). Without the symbols `g_pres` and `buf` the rig cannot see
  it and relies on the reload proof only.
- After `retro_unserialize` it hands the frontend no new picture until the guest touches the GPU again, which in the
  level of RC v2 takes up to 30 s of console time. `Game.image()` therefore returns the frame buffer cut from VRAM while
  the core's picture is stale (`g.picture_stale()`), and fingerprints use the frame buffer.

## Things to know

- The fast core is **not cycle accurate**: instruction timing and CD latency are the core's model. Speed figures are
  "guest frames per 60 emulator frames in this core" = per second of emulated time, nothing more. The BIOS is the core's
  HLE BIOS. The core reports 60.00 frames per second (NTSC).
- The dynarec executes instructions the R3000A does not have. `strict_cpu.py` (interpreter) and `tools/mips1_lint.py`
  exist for that.
- Guest TTY: the HLE BIOS prints only when a config byte of the core is set; the rig sets it for the core binary it knows
  (table `PCSX_PSXOUT` in `ps1game.py`, keyed by the sha1 of the `.so`). With another pcsx_rearmed binary there is no TTY
  (the session header says `guest TTY off`) and the map numbers of `maps.py` and the renderer lines are not available.
- `gba_frame()` (runtime time base, `io_cyc / 280896`) wraps after 15290 GBA frames because `io_cyc` is 32 bits; use
  `gframes()` (`g_gframes`) for long budgets.
- Determinism: same disc, core, card, rig version and script give the same RAM hash and picture; the frame numbers in two
  runs of the same session are identical (`replay.py` checks it). A change of the rig that changes the timing of a press
  changes every later frame number: compare runs made with the same rig version only.
- Menus slide and fade in; a screenshot taken the moment the text is complete shows them half way. `ready()` waits.
- Throughput measured: 450 to 800 emulated frames per second with the fast core (one host core, shared machine).

## Adding a session

```python
#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *

def main():
    a = std_args('what it does', lambda ap: ap.add_argument('--from-state', default=None))
    g = open_game(a, 'my_session')
    if not start_level(g, a):                      # --from-state, else cold boot and the pad path
        return g.finish('my_session')
    c0 = g.level_clock()
    g.check(g.wait_clock(30, 9000) is not None, 'clock runs', 'from %d to %d' % (c0, g.level_clock()))
    g.snap('after one second of game time')
    return g.finish('my_session')

if __name__ == '__main__':
    sys.exit(main())
```

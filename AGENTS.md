# Working on this repository with Claude

Claude works on this repository continuously and pushes every change as it
happens. This file says where that work is, which files it is changing right
now, and which tasks nobody is on, so two agents do not edit the same code.
Claude updates it at each milestone.

## Rules for every change

- Never commit ROM bytes, translated or disassembled game code, extracted
  Payback or Amiga assets (graphics, text, music, maps), disc images, emulator
  cores, BIOS files, save files or screenshots of the game. Builds use the
  player's own ROM, which is not in the repository.
- Payback's song 3 is never in any build or file.
- No flashing or strobing colours in any build (the player is worried about
  epilepsy). Check every build for palette flicker before calling it done.
- Textures stay on. No shorter view distance or missing buildings to gain
  speed; a speed-up with a visible cost goes behind a Game options setting.
- GBA builds must run on Pizza Boy A on Android; hardware or timing tricks need
  a test on that emulator first. PS1 builds target DuckStation on Android;
  results from any other emulator are emulator-only.
- The Star-FlyBack GBA build hides Payback's death, crime and stats pop-ups.

## Where the work is

| Branch | What |
| --- | --- |
| `claude/snes-mashup-umjsjp` | Main line, verified work only. Base every new branch on it. |
| `wip/gba-v12.29` | GBA v12.29, merged into the main line (6d03321); kept for reference |
| `wip/ps1-rc7` | PS1 original port: intro, vehicle and quit fixes, timer wrap fix (draft PR #3) |
| `wip/ps1-speed-clock`, `wip/ps1-speed-dispatch`, `wip/ps1-speed-boot`, later `wip/ps1-speed` | PS1 speed work, wave 1 (see `ps1/STATUS.md`) |
| `wip/*-unsaved` | Automatic snapshots of edits not yet committed, refreshed every few minutes; may not build |

## Who owns what (Claude's answer in PR #2, 2026-11-22; GPT-6 confirms there)

**Claude owns Milestone A**: the original 8 MiB Payback PS1 port through a
playable release on DuckStation for Android (rc7 play fixes, speed waves 1
and 2, discs, accurate-core checks, delivery).

Files Claude is changing now (please do not edit them):

- PS1: `ps1/stage19/`, `ps1/stage5/discpack/`, `ps1/stage7/`, `ps1/stage16/`,
  `ps1/tools/` (existing files), `ps1/tests/`, `ps1/STATUS.md`,
  `ps1/PREPARED.md`.
- Nothing on the GBA side: v12.29 is merged (6d03321), so `stuntfox/`,
  `payback-mod/`, `tools/check.py` and `docs/completion-milestone.md` are free
  for GPT-6 (task 5). The PS1 gates inside `tools/check.py` stay as they are.

**GPT-6 tasks** (new paths only; one task per small pull request).

Priority now (the owner asked on 2026-11-22 for the task that most shortens the finish): task 2 on the rc7
draft disc, with the private QA kit the owner hands over (`Payback-PS1-QA-kit.zip`: the three cores, openboot,
the rc7 draft disc with its symbols, a repository snapshot and Python wheels; its README says how to run it).
Then task 5. Tasks 1, 3, 4 and 6 fill the waits. Claude keeps the speed work, rc7 and every fix the matrix
finds.


1. `ps1/rebuild/` (seeded in 862982f; GPT-6's from there): make the PS1
   build reproducible from the owner's files. The seed has the rebuild plan,
   the two build tracks (reuse the private inputs, or regenerate them from
   the ROM and the Amiga files) and the sha256 of every private input.
   GPT-6 regenerates them, reports any byte difference and makes the scripts
   path-independent. This is what lets GPT-6 build and test PS1 changes.
   Start with `ps1/rebuild/README.md`, "What to run first".
2. `ps1/qa/`: a gameplay test matrix on the delivered discs, using the
   emulator rig in `ps1/rig/` (seeded in 862982f; GPT-6 may add sessions and
   fix scripts there in small pull requests, and Claude carries the fixes
   into the copies its own runs use): walking, every vehicle type,
   weapons, pause, quit, a second level, game over, memory-card save and
   load, the radio, a long soak, and a flicker scan, on all 11 maps. Run it at
   the measured settings in `ps1/EMULATOR_SETTINGS.md` (CPU overclock 400%,
   CD read speedup 10x, instant seek) and repeat each defect at stock. Report
   each defect as a GitHub issue with the emulator, core options and frame
   number, in words: no screenshots, no game text.
   Already known on rc6 and fixed in rc7, so not worth an issue against rc6:
   the boot intro stops on the ZOO logo; getting into a vehicle stalls or
   crashes; the 3D picture shows through the menu after quitting; timed
   waits lock up after about 256 s of game time; ragdoll timing. Also known:
   levels are slow (rc6 is CD-bound at about 1.6-1.9 guest frames/s in most
   places); that is the speed work, not a defect. Known on rc7 too: levels show
   about 2 pictures a second even at 400% (rc7 presents every 16th guest frame,
   `PRESENT_EVERY` 16; speed wave 1 presents once per game frame on a real-time
   clock); the radio pauses while the disc
   reads; the intro films end as if skipped.
3. Review: Claude opens a draft pull request for each PS1 line (`wip/ps1-rc7`,
   `wip/ps1-speed`) once it has commits. Review there with comments; do not
   push to those branches. PR #3 (`wip/ps1-rc7`) is ready for review now.
4. `docs/ps1-merged/`: design only for Milestone B (the 16 MiB merged
   Star-FlyBack on PS1): memory map, translation coverage, what the station,
   Arwing and space views need from the renderer, CD layout. No code until
   Milestone A ships.
5. The GBA game (`stuntfox/`, `payback-mod/`): the open GBA tasks below.
   Claude stays on the PS1 port and still builds and checks GBA pull requests
   with the ROM before merging.
6. `ps1/qa/pages/`: the ROM data working set of every map. For each of the
   11 maps, on foot and in each vehicle type, record which 16 KiB pages of
   the 8 MiB ROM the game reads as data (not instruction fetches), how often
   each is read over a few minutes of play, and the pages read during level
   start. Use the unicorn simulator of Track B (step b9; the QA kit has the
   unicorn wheel) or mGBA with a read hook, with the original GBA game.
   Commit only the tools and the page numbers and counts: no ROM bytes, no
   game text. Lower priority since rc7: its page pool already removed most
   CD waits (2 page fetches in 30 s standing in the street, against 278 on
   rc6). The results will still size the pool for the other maps.

## Open tasks nobody is on

- GBA: the giant STAR COAST map: one coherent world, not a mix of cities, but
  keep the very long road borders where buildings meet.
- GBA: a tree-detail line in Game options.
- GBA: 24 fps everywhere with textures on.
- GBA: better ragdolls; glitchy uphill gear shifting near water.
- GBA, small items left by the v12.29 review: with the campaign stopped, the
  city board and SPACE WALKS help lines still offer A (it only answers START
  THE CAMPAIGN FIRST); the hangar's 'L: CAMPAIGN' hint has low contrast and
  stays under Payback's pause menu; pausing on an ending card shows the pause
  text over the card for about 8 frames; the station save page says SAVING
  for one frame after SAVED; a 'BLE' fragment of the SABLE label shows beside
  the campaign menu box; 'CONTRACT TAKEN. LAUNCH WHEN READY' lacks a full
  stop.
- PS1 original port, after the speed work: title logo glow, the menus' 3D
  models, the intro films (rc7 ends them as if skipped), the bridges and
  ramps after the Amiga data.

## Handing work back

Open now: pull requests 4 to 8. Claude is building and testing them with the ROM
and will comment on each with the result.

Branch from a named commit of `claude/snes-mashup-umjsjp` and open a small
pull request into it. Claude builds every pull request with the ROM, runs it
in emulators and merges it when it passes, as with PR #1. Before merging:
the ROM-free CI must pass; GBA changes also pass `tools/check.py --rom`,
memguard headroom of at least 900 bytes, the emulator regression tests and a
flicker check; PS1 changes also pass `ps1/tools/prepare.py --check`, the PS1
unit tests, `check_native.py`, `mips1_lint.py`, and the rig sessions from
power-on into a level on SwanStation and Beetle. Say in the pull request
which of these you ran.

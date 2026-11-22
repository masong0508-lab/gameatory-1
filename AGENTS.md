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
| `wip/gba-v12.29` | GBA v12.29: review fixes after PR #1, being finished |
| `wip/ps1-rc7` | PS1 original port: intro, vehicle and quit fixes, timer wrap fix |
| `wip/ps1-speed-clock`, `wip/ps1-speed-dispatch`, `wip/ps1-speed-boot`, later `wip/ps1-speed` | PS1 speed work, wave 1 (see `ps1/STATUS.md`) |
| `wip/*-unsaved` | Automatic snapshots of edits not yet committed, refreshed every few minutes; may not build |

## Files Claude is changing now (please avoid them)

- PS1: everything under `ps1/stage19/`, `ps1/tools/source_manifest.json`,
  `ps1/tools/check_native.py`, `ps1/tests/`, `ps1/STATUS.md`.
- GBA: `stuntfox/src/` (station, campaign, HUD and space-walk code),
  `stuntfox/tools/memguard.py`, `tools/check.py`, `stuntfox/tests/`.

## Open tasks nobody is on

- GBA: the giant STAR COAST map: one coherent world, not a mix of cities, but
  keep the very long road borders where buildings meet.
- GBA: a tree-detail line in Game options.
- GBA: 24 fps everywhere with textures on.
- GBA: better ragdolls; glitchy uphill gear shifting near water.
- PS1 original port: title logo glow, the menus' 3D models, the intro films
  (rc7 ends them as if skipped), the bridges and ramps after the Amiga data.
- PS1: the Star-FlyBack additions, after the original port is complete.

## Handing work back

Branch from `claude/snes-mashup-umjsjp` and open a small pull request into it.
Claude builds every pull request with the ROM, runs it in emulators and merges
it when it passes, as with PR #1. PS1 builds need translation inputs made from
the ROM that are not in the repository, so say in the pull request how you
tested a PS1 change.

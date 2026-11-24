# Payback PS1, rc10: the final release of the original game

rc10 is the last release of the plain Payback port (branch `rc10`, see `STATUS.md`, section "Stage19 rc10"). The
Star-FlyBack mods are built on top of it later.

rc10.1 (same file names, rebuilt): sprite graphics could stay stale after certain changes of the sprite tiles (the
change check could miss two changes that cancelled); the check is now nonlinear plus an independent second check.
Nothing else changed; speed as rc10. Replace the rc10 files with these.

rc10.2 (same file names, rebuilt): the sprite change check is stronger again. A new attack on rc10.1 found sprite edits
it missed (for example one pixel moved two rows down in the right-hand column of a tile, about 1 in 744 such edits),
and a missed change stayed on the screen for good. Now each 2 KiB block of the sprite tiles is checked with two
independent nonlinear checks, and every block a sprite uses is sent to the PS1 again at least every 2 seconds. What it
guarantees: a change to any single word of the sprite tiles is always seen, and a change the check does miss is
corrected within 2 seconds. What it does not guarantee: two or more changed words can in principle fool both checks at
once; 150 million structured test changes found no such case. The menus are also faster without overclock (language
32.9, title 16.0, game menu 30.5 pictures a second; rc10.1 22.0 / 15.1 / 21.8), because fully transparent sprite tiles are
no longer drawn; the level runs as in rc10.1. Replace the older files with these.

## The files

| file | what it is |
| --- | --- |
| `payback_rc10.chd` | the disc for DuckStation, North America (one file; use this one) |
| `payback_rc10.cue` + `payback_rc10.bin` | the same disc as cue/bin (keep both in one folder, open the `.cue`) |
| `payback_rc10E.chd` | the Europe disc (PAL); `payback_rc10E.cue` is kept for reference, its `.bin` is not shipped |
| `payback_rc10.elf`, `.exe`, `.nm.txt` | the program and its symbol list, for bug reports only |

The discs are built on your own machine from your own Payback (Europe) GBA ROM. They contain data derived from it:
for your own use only, never share or upload them. Payback's song 3 is not on the disc.

## Run it in DuckStation for Android

1. BIOS. DuckStation has no built-in BIOS. Dump the BIOS of your own PlayStation and put it in DuckStation's BIOS
   folder (Settings > BIOS). Region: the `payback_rc10` disc is North America (NTSC-U), so it needs a US BIOS (for
   example SCPH-1001, SCPH-5501, SCPH-7001). The `payback_rc10E` disc is Europe (PAL) and needs a European BIOS (for
   example SCPH-5502, SCPH-7502). If DuckStation says no BIOS was found for the region, the BIOS and the disc do not
   match.
2. Settings > BIOS > Fast Boot: on. It skips the PlayStation logo, which the game does not need. (Our tests boot
   through a free replacement BIOS, not a Sony BIOS, so the boot with Fast Boot off has not been seen here.)
3. Add the folder with `payback_rc10.chd` to the game list and tap the game.
4. Memory card: Settings > Memory Cards, port 1 "Per-game" or "Shared". Saves from rc8 and rc9 load in rc10.
5. Renderer: any (Software, OpenGL, Vulkan) at any resolution. Leave PGXP off: the port uses plain GTE output, and
   PGXP's texture correction can make the 2D layer and the HUD look wrong.

## Settings

Set these in the game's own settings (long-press the game > Game Properties) or globally. DuckStation's speed
display must stay at 100 %: when the phone cannot hold the overclock, the game gets slower, not faster.

| phone | CPU overclock (Console > Enable Clock Speed Control) | CD-ROM read speedup | CD-ROM seek speedup | what you get |
| --- | --- | --- | --- | --- |
| normal phone (recommended) | 400 % | 10x | Infinite | the GBA's speed in SwanStation: 30 game ticks and 30 pictures a second, level reached in about 10 s (Beetle PSX at 400 %: 28-29.4 ticks, 27-29 pictures) |
| weaker phone | 200 % | 2x | (none) | the game at 27.5-29 ticks a second (92-97 % of the GBA), 24-27 pictures a second in the level, 30-34 in the menus |
| weak phone | 150 % | 1x | (none) | 26-28 ticks a second, 17-26 pictures a second |
| no overclock | 100 % | 1x | (none) | 26-29.7 ticks a second (the game runs at 87-99 % of the GBA's speed, walking 87-94 %), 11-15 pictures a second in the level, 16-33 in the menus |

The lowest setting that gets to the GBA's speed: 300 % CPU with read speedup 2x is within a few per cent (27.5-29.9 ticks,
26-29.8 pictures); 400 % reaches it in SwanStation (in Beetle PSX it stays 1-6 % below). Read speedup 10x is clean from 150 % CPU on; at 100 % CPU use 7x or
less (from 8x the drive retries and loading gets slower). Above about 600 % places run faster than the GBA, and save
states made at 600 % or more do not load at 100 %.

All numbers are measured in emulated time in SwanStation (DuckStation's libretro version, the closest to DuckStation)
and Beetle PSX, not on a phone; the table's ranges are SwanStation's unless Beetle is named. Every level picture stays
on the screen for at least two TV frames (the GBA game's own step), so the motion is even at every setting.

## Controls

| PS1 pad | Payback (GBA) |
| --- | --- |
| Cross | A |
| Circle or Square | B |
| L1 / R1 | L / R |
| Start / Select | Start / Select |
| D-pad or left stick | D-pad |

## Known limits

- The intro films (the DSI logo film and the "View intro" film) are skipped: the PS1 cannot play them at a usable
  speed in this port. Cross skips the logos as on the GBA.
- Without overclock the level shows 11-15 pictures a second and the menus 16-33; the game itself runs at 87-99 % of
  the GBA's speed (walking 87-94 %). The pictures are always whole (no tearing, no black frames).
- The Credits take about 5 minutes at 100 % CPU (GBA: 2 min 12 s), 100 s at the recommended setting.
- After "Return to game" in the pause menu the level can take up to 2 s to move again at 100 % CPU (the disc reads
  the parts of the level the menu pushed out of memory); at the recommended setting it is a quarter of a second.
- The radio (CD audio) pauses while the disc reads level data and comes back when it is quiet.
- A Cross tap shorter than one game frame can be missed in the pause menu: hold it a moment.
- Not tested on a real PlayStation or on a phone; only in emulators.

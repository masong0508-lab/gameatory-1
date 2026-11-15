# Star-FlyBack PS1 (release candidate)

Files: `Star-FlyBack PS1 (release candidate).cue` + `.bin` (keep them in the same folder; the cue points at the bin by name).
593 MiB, 58.8 min, MODE2/2352: data track 1, then 14 CD-DA tracks (2 to 15).

**Status in one line:** this is a release candidate for a *tech demo of the live city*, not a full game. It was only ever run in the PCSXR emulator (HLE substitute BIOS, on a PC). It has not been run in DuckStation, with a real BIOS, or on hardware. Treat every statement below as emulator-only unless it says otherwise.

## What it is
The disc is built from your own Payback (Europe) ROM and your own Amiga Payback files, plus the remix MP3s. The Payback code is translated at build time to PS1 code; the world is drawn by a PS1 renderer (textured, GTE) for the 11 Star-FlyBack maps. The disc contains data derived from your ROM and Amiga files: for your own use only, never share or commit it. Payback song 3 is not on it.

## Run it in DuckStation on Android
1. Install DuckStation. In Settings > BIOS, point it at a PS1 BIOS dump you made from your own console (SCPH-1001 / 5501 / 7001 or similar; DuckStation has no built-in BIOS and I cannot supply one).
2. Settings > Game List: add the folder that holds the `.cue` and `.bin`, then tap the game. Open the `.cue`, not the `.bin`.
3. Leave the renderer on Software or OpenGL/Vulkan at native resolution. Turn off any "PGXP" and "texture filtering" options if the picture looks wrong (the build uses plain GTE output).
4. Memory card: Settings > Memory Cards > Port 1 = "Per-game" or "Shared". The game looks for a formatted card in slot 1, then slot 2.
5. Not tested in DuckStation: audio (CD-DA), pad mapping, speed. If something is off, tell me what you see.

## What happens on boot
It starts straight in the live Freedom City level (it resumes a saved game state from the disc). There is no title screen or menu on this disc. The title-boot version did not reach a level in the emulator, so it is not the release candidate.

## Controls (PS1 pad; digital or analog)
| Button | Action |
|---|---|
| D-pad / left stick | move / steer (Payback's own controls) |
| Cross | Payback A (action, accelerate) |
| Circle | Payback B |
| Start / Select | Payback Start / Select (Select is also the radio modifier, see below) |
| L1 / R1 | Payback L / R |
| **L2 / R2** | previous / next of the 11 maps, loaded from the CD (a couple of seconds). The view moves to the new map's start point |
| **R3** (press the right stick) | toggle first person (eye height, your own body and car are hidden) |
| Triangle in a car | bail out of the car (ragdoll) |

Android touch overlay has no R3 or L2/R2 by default: use a gamepad, or map them in DuckStation's controller settings.

## Radio (hold Select, then press)
| Keys | Action |
|---|---|
| Select + R1 | next track in the current mode |
| Select + L1 | previous track |
| Select + Triangle | stop / start |
| Select + Square | switch mode: REMIXES (tracks 2-12), ALL SONGS (2-15), ORIGINALS (13-15: the three Star-FlyBack songs) |

The radio does not start by itself: press Select + R1 to begin. Playback goes on to the next track when one ends (checked in the emulator).

## Save
Memory-card save code (file BESLES-99901SFBACK, 2 blocks, EEPROM image) is compiled in. It was verified on earlier stage 2/3 test discs in PCSXR. It was **not** verified in this build.

## Known limits
- Emulator-only checks, none on a real BIOS or hardware. Speed on a real console or DuckStation is unknown: PCSXR needed about 2.7 s of wall time per presented frame here, which is the emulator, not a measure of the console.
- Not in this port: Arwing, space / moon / asteroids / planet views, Fox Station, game settings, hangar. They exist only in the Stunt Fox ARM code, which is not translated; the PS1 renderer has no space or station drawing. The disc runs plain Payback logic (Freedom City) with the Star-FlyBack city drawing. The v12.26 merged ROM is used only to dump the 11 city maps.
- Map change is renderer-side: the guest game keeps running Freedom City logic whatever map you view.
- Loops (24-quad helix) and first person were checked in PCSXR with a forced test camera/flag, not through the real R3 pad press. R3 on the pad is unverified.
- Ragdolls: work in the live view (about 167 renderer lines per doll). Six dolls on the ground cost about 1.28 M instructions per 30 fps frame, which is 4.6x over the 25% budget I set, so heavy ragdoll scenes will drop frames. The bail-out and pedestrian-hit triggers are compiled in but unverified; the ragdoll world is approximate.
- Coverage: translated code that neither the simulator nor my PCSXR runs touched ends in a deliberate panic (RT_MISS). The soak had none through about 97 presented frames; longer play can still hit one. Cold-code headroom is about 4 KiB.
- The interpreter-fallback build that would remove that risk is not finished (it differs from the reference after about 1,094 frames), so it is not in this disc.
- No flashing or strobing was found in a 300 s capture (see below); 5 fps capture of a slow emulator, not a hardware measurement.

## Verification done for this exact disc (PCSXR 1.9.94, HLE BIOS, 300 s scripted run)
- L2 loaded map 10 (298 CD sectors), R2 then loaded map 0 (310 sectors), HUD showed MAP 10 / MAP 0.
- Select+R1 started track 3, Select+Triangle stopped it (CD-DA play command seen).
- Presented frames 1 to 65+ with no RT_MISS, prim count 356 to 369, overflow 0.
- Flash check on the capture (800x600, 5 fps, 97 distinct frames, each treated as 1/30 s): 0 opposing mean-luminance swings above 10%; the biggest mean-luminance step between neighbouring frames was 0.04 outside the first frame from black and the final kill of the emulator. Five scene-change events (boot, two map loads, one walking view change, end) each moved more than 25% of the pixels, none came back. No black or white frames on map loads.

## Rebuild
Code only is in `stunt-fox/ps1/stage7/integration` plus the patches in `stage7/loops_fp` and `stage7/ragdoll_g2` (see their APPLY.txt / README). `stage7/release` has the flash-check script and the verification run script. Needs your ROM, the Amiga files and the remix MP3s.

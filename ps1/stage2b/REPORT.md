# Stage 2b report (revision 2): PS1 Freedom City renderer

All numbers are PCSXR (HLE substitute BIOS, GL plugin, Xvfb) numbers. No real PS1, no real BIOS. PCSXR charges 2 cycles per instruction (measured: a 6-instruction
loop = 12 cycles/iteration), so "engine lines" (1 line = 2146 cycles) are emulator lines; real-hardware timing was not measured.

## Changes in this revision
- Cracks: shared vertices now round identically (one tier rule for proj() and the ground grid); ground cells next to a finer neighbour get the neighbour's
  vertices on the shared edge (fan stitching); sunk-ramp water gets a flat underlay. tests/crack.py counts thin magenta slivers with DEBUG_UNDERLAY.
- Olive polygon (pose 7): the ROM's average colour for the water tile is olive; the converter now uses the true texel average (blue). Far ramps are drawn per cell colour.
- Distant walls: one textured quad per wall, tile repeated through the GPU texture window (E2h, 32-texel window), instead of a flat tan quad.
- Flash logger: read after the flip. PCSXR's GL plugin returns zeros for read-backs of the upper buffer (y 0..239), so the in-ROM log only works every second frame;
  the verdict comes from tests/flashcap.sh (60 Hz screen grab) + tests/flashstat.py.
- Debug counters, timers and benchmarks removed from sf.c (STATLOG prints one line per 64 frames: eng lines, fps, prims, LOD, worst lines, frames over budget).
- Speed: -O3 + inline threshold; per-axis (binary) subdivision; lattice sharing for wall/top/ramp cells; exact off-screen test for near-plane-crossing pieces
  (the biggest single gain, output unchanged); per-cell ground grid from the depth spread; box occlusion by wall coverage (bounding sphere); near-to-far sectors.
  LOD (adaptive, 2 fields = 456 lines) now changes only the subdivision error (2/3/4/6 px) and the ground grid caps. Reach stays 12288, no building is dropped.

## Engine lines per frame, HUD off, fixed LOD, poses 0..7
| build | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| before (stage 2b r1) | 648 | 591 | 412 | 510 | 565 | 625 | 651 | 592 |
| after, LOD 0 (2 px) | 525 | 526 | 353 | 376 | 521 | 443 | 408 | 310 |
| after, LOD 2 | 452 | 457 | 286 | 326 | 436 | 374 | 387 | 270 |
| after, LOD 3 | 434 | 437 | 262 | 301 | 426 | 376 | 374 | 265 |
30 fps needs <= 456. LOD 0 meets it in 3 of 8 poses; LOD 3 in 8 of 8; LOD 2 in 6 of 8 (452 / 457 for poses 0 / 1).

## Adaptive build (default ISO), scripted car drive, HUD on
1920 frames: 30.0 fps by the game clock throughout, worst frame 477 lines, 2 frames over 456 and 1 frame shown later than 2 fields (all while LOD settled).
LOD sat at 1..3. The host ran the emulator at about 14 distinct pictures per second in the 60 Hz grab (host limited), so 30 fps is the game clock, not wall clock.

## Against the GBA frames (same camera, edge F1 / block MAE; before | LOD 0 | LOD 3)
foot_start 0.82/12.2 | 0.80/12.1 | 0.82/12.0;  street 0.82/9.6 | 0.81/9.4 | 0.80/9.8;  cross 0.81/24.9 | 0.77/19.2 | 0.76/19.7;
ramp 0.61/8.9 | 0.60/9.1 | 0.63/9.9;  bridge 0.84/7.3 | 0.84/7.3 | 0.78/9.5;  water 0.83/4.4 | 0.80/4.4 | 0.69/5.4.
Cross MAE improves (brick walls). LOD 3 costs water and bridge edge agreement; LOD 3 images differ from LOD 0 by a mean 0.9..4.5 of 255.

## Crack test (DEBUG_UNDERLAY, LOD 0, 8 poses)
Thin magenta pixels: 542 before, 202 after. 154 of the 202 are one 4 px strip where the far ground stops (pose 2), not a crack; excluding it 388 -> 48.

## Flash check (60 Hz grab of the final build, HUD on)
Car drive 40 s: mean luminance 86.2..87.5, largest frame-to-frame change 0.6/255, no block changed by > 60 levels, 0 opposite-sign swings >= 10%.
Fly demo 40 s: two single changes of 43/255 (one up, one down, 8.8 s apart) where the camera passes the map edge; no pair inside a second, so no strobing.
Not checked: a person looking at it; real display.

## Still open
- 30 fps is reached only through LOD 2..3 (ground and walls show more affine bend near the camera). LOD 0 at 2 px costs 353..526 lines.
- Hairline slivers remain in poses 1, 6, 7 (a few px) inside the quadtree pieces of boxes and ramps (T-junctions there are not stitched).
- GBA kicker pose failed; GBA bridge/water poses approximate; no GBA high view. No real-hardware run.

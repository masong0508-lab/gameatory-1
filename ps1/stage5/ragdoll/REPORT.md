# Stage 5: ragdolls on PS1 (solver port, scripted ramp throw)

All timings are PCSXR (HLE substitute BIOS, GL plugin, Xvfb) or instruction counts on a MIPS-I model. EMULATOR-ONLY: no real PS1, no real BIOS, no real-hardware timing. Real-hardware figures below are labelled ESTIMATE.

## What was built
- `src/ragdoll_ps1.c`: the reference solver (stuntfox tools/ragdoll_ps1_ref.c, 18 joints, 17 capsules, ranges, hinges, braces, motors, surfaces, sweeps, car box, sleeping) compiled with the stage 2b clang flags. Same API, same Q12.20 integer maths. The reference needs 64-bit divide and a 31-step loop sqrt, which the R3000 has neither of, so the port has three levels (RP_LEVEL):
  - 0: the reference verbatim (64-bit divide by a bit loop in `rt.inc`).
  - 1: bit-identical to the reference: exact divide by chunked 32-bit DIVU, isqrt starting at the right bit, early-outs that cannot change a result (speed clamp by squared length, car box reject, path-box reject in the world's sweep).
  - 2 (disc default): fast: reciprocal sqrt from a 192-entry table plus one Newton step (len and normalise without a divide), distance constraints skipped inside a tolerance band (rest/2^13 for equalities), per-pair constant reciprocals. Not bit-identical to the reference.
  - Tuning macros: RP_ITER (passes/substep, ref 3), RP_NS_BASE/RP_NS_DIV/RP_NSMAX (substeps, ref 4/5/12), RP_HINGE_LAST (hinges only in the last pass), RP_COLL_LAST (contacts only in the last pass; tried, rejected). `rp_doll.lod` (0..2): 1 drops hinges and self contact, 2 also one pass fewer, one substep fewer and no bone-ball contacts.
  - Disc default "c5" = level 2, ITER 3, NS 3/10/6, hinges in the last pass, LOD by rank among dolls faster than 2 m/s (two nearest full).
- Test scene (`src/scenario.inc`, 720 frames at 60 Hz, then it restarts): a car climbs a 14 degree ramp at 20 m/s, the driver bails out at the lip (car speed plus a kick and spin), the car lands and brakes into five pedestrians who become ragdolls as it reaches them, a building 92 m out and a low wall flank the road. The world (ramp floor, boxes, sweeps) is test code, not the game's.
- Drawing (`src/app.c`): per frame the camera follows the action, 15x9 ground lattice (ramp included), two boxes + the car box, each doll = 17 capsule ribbons + joint caps + octagon head + blob shadow, all projected with the GTE (RTPS, 1/256 m units relative to the camera), painter's ordering table, DMA2 linked list, double buffered 320x240. Flat colours only (no textures in this test disc). The two bars at the top are the solver cost (orange) and the rest of the frame (cyan), 1 px = 2 emulator lines, the white tick = one 60 Hz field (263 lines).

## Correctness
- PC: `tools/host_test.c` runs the scenario against the reference and against the port. RP_LEVEL 0 and 1 give an identical trace (hash + pelvis position of every doll every 10th frame, 720 frames, 6 dolls, 8079 substeps): `tests/trace_ref.txt` = `trace_l0.txt` = `trace_l1.txt`.
- PS1 (emulator): the level 1 disc finishes the 720 frames with combined hash 2317f95c = the PC reference's. The c1 and c5 discs give fe66791b and 184db407 = the PC builds of the same configs (clang-mips and gcc-x86 agree bit for bit). So the port runs correctly on the R3000 code path; level 2 differs from the reference only by its own approximations.
- Level 2 vs reference (PC metrics over the scenario, `tools/host_quality.c`): bones' worst stretch c5 0.17 / c1 0.12 / reference 0.21 (during the car impact), nothing below the floor, nothing inside a solid, all dolls fall asleep (c5), end positions within about 3 m of the reference's (the pile-up is chaotic). Cheaper settings measured and rejected: 2 passes (stretch 0.44..0.47), 2 substeps at low speed (8 cm into the floor, stretch 0.54), contacts only in the last pass (stretch 0.73). LOD 2 on every doll: stretch 0.51 (fine for a far doll, not for the nearest).

## Cost (the headline: not cheap enough yet)
Instructions executed per frame, exact for the compiled MIPS-I code (`tools/mipsprof.py`, mult/div counts included in its output), frame 120 = one doll in flight at about 25 m/s, frame 190 = all six dolls moving, car pushing:

| config | frame 120 (1 doll) | frame 190 (6 dolls) | note |
|---|---|---|---|
| level 0 (reference verbatim) | 10.15 M | not run | bit-loop 64-bit divide |
| level 1 (bit-exact) | 2.45 M | 12.1 M | chunked DIVU, exact sqrt |
| c1 (level 2, ref passes) | 0.55 M | 2.79 M | |
| c5 (disc default) | 0.31 M | 1.74 M | 3 substeps min, 6 max, hinges last |
| c5, every doll LOD 1 | 0.27 M | 1.52 M | |
| c5, every doll LOD 2 | 0.12 M | 0.67 M | |

Emulator lines (hblank lines, 263 per 60 Hz field; PCSXR cost model, about 2.6 emulator cycles per executed instruction here, so these overstate an R3000 that issues about 1 instruction per cycle by that factor). Whole 720-frame scenario, 3369 doll-steps, average over all frames including the ones before any doll exists:

| config | solver lines/frame avg | worst frame | one doll in flight (frame 120) |
|---|---|---|---|
| level 1 | 3903 | 12783 | 2430 |
| c1 | 1153 | 3848 | not logged |
| c5 | 907 | 2084 | 369 |
| c5 + LOD (disc) | 893 | 2050 | 369 |

Rendering on the disc (ground lattice, 3 boxes, 6 dolls, about 260 prims): 66 lines average, 69 worst (emulator), CPU side only. GPU fill time was not measured (the emulator does not model it).
ESTIMATE for real hardware (instructions x 1.0 to 1.3 cycles at 33.87 MHz, no cache-miss model): c5 one doll in flight 9..12 ms, six dolls moving 51..67 ms, bit-exact port 72..94 ms per doll in flight. A 60 Hz frame is 16.7 ms.
Timer note: the 16-bit sysclk/8 counter wraps at 524288 cycles, a single doll step can exceed that; `app.c` unwraps it with the hblank counter (an earlier run without that was discarded).

## Where it stands
- Done: solver ported, bit-exact against the reference (level 1) on PC and in the emulator; a fast level; per-frame cost measured by two independent means that agree (instruction count x 2.6 = emulator cycles within about 15%); a playable looping test disc; screenshots.
- Not done / not met: the stage 5 target of several full-body ragdolls cheap per frame. With this solver one doll in flight uses most of a 60 Hz frame, six moving dolls a few 30 Hz frames, so at 30 fps about two nearby dolls are affordable, the rest must sleep or use LOD, and the disc runs in slow motion while six are moving. The LOD policy as written saved only about 2% on this scene (few frames have more than two fast dolls); forced LOD 2 saves 60%.
- Where the instructions go (level 2): the constraint loop 27%, the step body and contacts 32%, the test world callbacks 24%, the car box 6%, hinges 7%. Ideas not tried: a 32-bit Q12/Q16 core in doll-local coordinates (most of the cost is 64-bit multiplies), a rigid torso (the 11 braces + 6 ranges), GTE MVMVA for the car-local transforms and dot products (the solver does not use the GTE at all today; only the drawing does), hand-scheduled assembly for `distance_c`, broad-phase hints from the game world, stepping far dolls at 30 Hz.
- Not integrated: skinned meshes (rp_frame), hurt/event hooks, car damage, the real world queries from the Star-FlyBack city (the test world is a ramp and two boxes), pad control, sound.
- Not checked: real BIOS, DuckStation/ReARMed, real hardware, memory use beyond "fits" (the disc EXE is 104 KB, a doll is about 0.8 KB). Flashing: the scene colours are fixed, only the camera moves smoothly and the two thin bars at the top change length; no flash analysis was run on this disc.

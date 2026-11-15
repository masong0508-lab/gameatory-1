# Stage 5: ragdoll speed pass ("f1" = c5 + RP_FAST + budget governor)

EMULATOR-ONLY: PCSXR 1.9.94 (HLE substitute BIOS, GL plugin, Xvfb) for the disc runs, a MIPS-I instruction-count model (unicorn, `tools/mipsprof.py`) for instruction counts, gcc on the PC for traces. Nothing ran on a real PS1 or with a real BIOS. Anything in ms is an ESTIMATE (instructions x 1.0..1.3 cycles at 33.87 MHz; a second column adds 8 cycles per multiply and 35 per divide, the R3000's multiplier and divider latencies the old report left out). One 30 fps frame = 33.3 ms = 1.13 M cycles; 25% = 8.3 ms = about 280 k cycles.
All costs below are per 30 fps frame = two 60 Hz ticks of simulated time (what a 30 fps game has to pay per frame), unless marked "per tick".

## Result in one table (instructions per 30 fps frame, bench model; the GTE ops are counted as 18/19/10 instruction equivalents)
| case | shipped c5 | f1 (this work) | est. R3000 time f1 | vs 25% budget (8.3 ms) |
|---|---|---|---|---|
| six dolls IN FLIGHT (new test SC_AIR6: 6 dolls thrown 14 m up, 150 ticks, no car) avg | 3 295 k | 159 k (max 161 k) | 4.7..6.1 ms (6.0 ms with mult/div model: 203 k) | MET, 14..18% of a frame (c5: 97 ms, 3 frames) |
| six dolls moving on the ground and under the car, the old frame-190 scene (ticks 170..300) avg / max | 3 013 k / 3 509 k | 1 824 k / 2 461 k | 54 ms avg (69 ms mult/div model) | NOT MET, 6.5x over; best quality-safe result, see "what is left" |
| one doll in flight at 25 m/s next to the car (tick 120), per tick | 306 k | 223 k | 6.6 ms per tick | (a lone doll near the car is "hot": full solver) |
| whole 720 tick scenario, average per 30 fps frame | 1 562 k | 527 k | | 3.0x less |
Emulator (PCSXR cost model, 1 line = 1 hblank, 263 lines per 60 Hz tick, overstates the R3000 about 2.6x): SC_AIR6 solver lines per tick average 1548 -> 87 (17.8x); main scenario average 890 (c5 + app LOD, as shipped) -> 277 (3.2x), worst tick 2042 -> 1322.

## What was done (all in `src/ragdoll_ps1.c` under RP_FAST=1, `src/scenario.inc` for the game-side policy, `src/gte_rp.h`)
1. GTE (gte_rp.h): SQR gives the sum of squares of a constraint vector (vector in 2^-14 m units, 16 bit) in one command instead of three 64-bit multiplies; MVMVA does the car world->local transform (matrix 1.3.12). PC and the instruction model use a C model of exactly those operations; the console build uses the real COP2 commands. The solver clobbers RT/V0/IR/MAC: set the camera after rp_step (app.c does).
2. Tighter inner loop (`distance_c`): the band test comes from the GTE sum; a violation under about 20% is corrected without a root or divide: factor (l-t)/l = 1-(1+2x)^-1/2 = x-1.5x^2+2.5x^3 with x=(s-t^2)/2t^2 from per-constraint constants, applied with 32 bit multiplies (unit test `tools/t_dist.c`: mean residual after one application 1%); a bigger violation takes the old exact path. (A first version with only x/(1+x) or only x left stretched bones 3x more often and was dropped; 3 terms match the exact path's quality.)
3. World queries once per substep, not per pass: floor plane + "solid near" per joint (ball of r+0.16 m+travel), the contact passes use the cached plane, skip solids and sweeps where nothing is near, skip the car box unless the doll is within 6 m, hinge frame once per pass, self-contact cube reject, car hit normal from the matrix (no multiplies).
4. Sleeping fixed: a sleeping doll was woken every tick by a PARKED car within 8 m and stepped for 24 ticks again (two dolls did this for 330 ticks: 709 k instructions/tick for nothing). Now only a moving car wakes it. Sleeps at 0.4 m/s joint speed after 10 quiet ticks (was 0.17 / 24).
5. Adaptive substeps: a doll that ended the last tick clear of floor, solids and the car by more than it can travel takes 1 substep (c5: 3..6).
6. Budget governor (the game side, `sc_policy` in scenario.inc, -DPOLICY): pedestrians are not in the solver until the car is within 3.6 m (held); dolls are ranked by distance to the camera target: 2 nearest full detail, the next 4 lod 1 (no hinges/self contact), a doll within 7 m of a moving car keeps lod 1 at least; a doll that rp_free_flight() says nothing can touch for 2 ticks is stepped at 30 Hz (dtf=2, 1 substep, lod 2) on alternate ticks; a far doll lying slow (8+ joints in contact, under 1 m/s) goes to sleep. New solver controls: rp_doll.dtf, .held, .air, lod 3, rp_free_flight().
Rejected after measuring (PC `tools/host_quality.c`, bone samples over 10% stretch of 57 273): ranges only in the last pass 30 (c5: 7); 30 Hz stepping of ground dolls 482; lod 3 for far ground dolls 44..949 and a 0.7 stretch; linear-only correction 22 with a 1.29 stretch.

## Quality (PC, scenario of 720 ticks, 6 dolls; reference = stuntfox ragdoll_ps1_ref.c)
| | reference | c5 | f1 |
|---|---|---|---|
| bone samples over 10% / over 25% stretch | 1 / 0 | 7 / 0 | 15 / 0 |
| worst bone stretch | 0.208 | 0.166 | 0.199 |
| deepest into the floor | 0 | 0 | 1.0 cm (one 30 Hz flight step landing) |
| inside a solid box | 0 | 0 | 0 |
| substeps in all | 8079 | 7317 | 3532 |
| SC_AIR6 worst stretch / samples over 10% | | 0.005 / 0 | 0.095 / 0 |
All dolls come to rest and sleep. The driver's pelvis vs the PC reference (m, ticks 110/150/200/240/end): c5 0.11/0.44/1.03/1.66/3.28, f1 0.14/0.54/1.26/2.06/5.01; the five pedestrians end 0.4..0.8 m from the reference's except doll 1 (2.9 m): the pile-up is chaotic, as in the c5 report. Traces: tests/trace_ref.txt, trace_c5.txt, trace_f1.txt (`tools/cmp_trace.py`). Spikes of joint speed to 70..80 m/s when the stopped car pins a lying doll exist in the reference (98 m/s) too; f1 72.6, c5 40.
Bit agreement: f1 disc in PCSXR finishes with combined hash 97b81e7f = the PC build with the C GTE model (also SC_AIR6: 85e449e6 on both), i.e. the real COP2 path and the model agree. c5 (RP_FAST=0, no policy) still gives the shipped 184db407 on PC.
Screenshot: ps1_stage5_ragdoll_fast_screenshot.png (frame ~270, dolls intact). No flashing: scene colours fixed, camera smoothed, only the two bars at the top change length (unchanged from the c5 disc).

## What is left
- The ground/impact case is 6.5x over the 25% budget. Per substep the cost is still ~45 k instructions (lod 0): 103..141 constraint calls at ~130 instructions, 18 joints x 3 passes of contact work, ~30% in 64-bit Q20 `mul`. Quality-safe policies (ranks, lod 1, hot) only get 1.8 M; every cheaper policy tried stretched limbs (see rejected). Ideas not done: 32-bit Q12/Q16 core in doll-local coordinates (most of what is left is 64-bit multiply), rigid torso (11 braces + 6 ranges gone), hand-scheduled `distance_c`, impact-time promotion with fade-out of far dolls (this "fewer dolls at once, fade-out" lever was not built: it would drop visible dolls), world broad-phase hints from the game.
- Real GTE timing was not measured (emulator only); the mult/div column is a model, not a measurement.
- rp_free_flight() and `held` are used by the test scene only; the game's own pedestrian AI would own `held`.
- A car parked on top of a sleeping doll no longer pushes it (only a moving car wakes it).
Tooling note: unicorn segfaults on `emu_start` without a `count`; mipsprof.py passes one.

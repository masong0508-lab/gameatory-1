# Stage 6: live-level sf3 renderer cost cut (638 -> 355 hblank lines mean)
EMULATOR-ONLY: PCSXR 1.9.94, HLE substitute BIOS, GL plugin (never real hardware / real BIOS). 1 line = 1 emulator hblank line; 30 fps budget = 456. Lines are instruction-count driven (div/mul/RTPS cost about 5-8 instructions each in this model), not real R3000 timings.
Scope: the live level of the stage 4 disc (snapshot resume, Freedom City, player on foot, 7-8 entities). "host" = sf3_frame() lines (renderer + list send); gather3 measured separately.
## Result, live disc, same timeline both runs (first 43 odd render frames)
| | n | mean | median | max | frames > 456 |
|---|---|---|---|---|---|
| before (stage 4 s4 disc, lod 0/1) | 43 (earlier 17-sample run: 638) | 606 | 620 | 738 | 98% |
| after (this disc) | 43 | 355 | 328 | 655 | 7% (3) |
gather3: 1.9 lines mean (not a cost problem). Heading sweep without the guest (PROFSPIN, 12 headings x many frames, same pose): lod0 528, lod1 472, lod2 417, lod3 383 mean; shipped-policy ref 539.
## What was changed (sf3.c; patches in sf3.patch, rt.patch, build.patch)
1. Stage 5 clipfix applied to proj(): bound 32768. On this level it saves ~58 lines at lod 3 (heading sweep: 442 -> 383, prims 370 -> 341).
2. LOD no longer shortens the view (reach = REACH always, as stage 5); governor = stage 5 (budget FIELDS*263-70 = 456, calm 75). View distance and buildings unchanged, textures unchanged. Only subdivision error / ground grid vary with LOD.
3. ground_draw: only rings <= 6 visited (rings >= 7 never drew) and the per-cell frustum test uses incremental dot products (exact, bit-identical): ground phase 227 -> 162 (-65). ground_cell: skip the neighbour-LOD loop when no finer neighbour can exist (bit-identical).
4. Entities/car: car_draw frustum-sphere cull (r 330, conservative; only skips faces that would be Q_SKIP); obox projects each corner once. Entity phase 39 -> 12.
5. Profiling leftovers out of the shipped path: TICKS8 section timers and c_* counters compile away unless -DPROF (they cost ~15 lines).
6. clip_poly: one plane value per vertex, no modulo (identical output; tiny gain).
Identity: steps 3, 4 (obox), 6 verified by FNV hash of every primitive word + OT per frame (fixed LOD 3, 250+ frames, 100% equal, tools/ident.sh); the car cull changes only off-screen output.
## Where the remaining lines go (lod 3, profile build): city ~205 (near wall lattices ~100, far walls 16, ramps 36), ground ~150 (fan quads at LOD ring borders ~47, row projection/ocode ~50), HUD 3, sky 5.
## Not done / caveats
- Mean is below budget but lod sits at 3 for most live samples (45-frame calm dwell), so near ground looks more affine-warped than at lod 1; at lod 0 the sweep mean is still 528 (> 456). A cheaper wall lattice / fan quad would be the next lever.
- Spikes up to 655 (heading sweep max 561 at lod 3). 30+ samples are all on one standing pose (the live scenario does not reach the car); GPU fill time is not modelled by the emulator. TESTFAST not used.
- Build: stage4 pipeline (t/mk_disc.sh with EXTRA="-DPRINT_EVERY_SF3=1"); SF3SRC env selects another sf3.c. Profile: tools/spin.sh NAME SECS -DPROF (spin build freezes the guest and turns the player).

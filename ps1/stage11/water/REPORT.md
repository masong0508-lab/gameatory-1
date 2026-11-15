# Stage 11: water, shore and bridge accuracy pass (Star-FlyBack PS1)

Everything below is measured in pcsxr 1.9.94 (HLE BIOS, GL plugin, Xvfb). Emulator-only: no real PS1 hardware was used.
No Payback/Amiga data or ROM is in the repo. The checker and converter take the player's own files on the command line (tests/pipeline.sh).

## What was wrong and what changed
1. Data holes: cells with no ground and no box (289 over the maps: 0:82 1:29 2:43 3:40 5:2 7:73 8:14 9:4 10:2). tools/waterfix.py fills them. Maps 0-3 pick the tile by the Amiga texture name of that cell (class 65 = water); other maps use the nearest neighbour tile. The checker now reports 0 holes on every map.
2. Ramp side walls (sf.c draw_ramp): a wall now runs to the neighbour cell's surface at each end of the slope, so bridge ramps no longer show the island behind them.
3. Far water (sf.c far_water): water beyond the ring-7 ground and the 12288 ramp reach is drawn as flat water-coloured quads at y 0 (greedy rectangles, 20 quads at most seen, cap 160) instead of the grey island lid. The rectangle list is rebuilt only when the camera cell changes: the uncached version cost about 100 scanlines a frame.
4. Converter: MAPS.BIN gains two 2 KB bit masks a map (wbits street water, rbits sunk water).

## Numbers (before = stage 5 converter and renderer, after = this pass)
- Base poses (45: shore, bridge, edge on every map, magenta underlay + exact ray caster): hole px 2231 -> 928 (hairline slivers <= 2 px wide: 743 -> 717); far-water-as-island px 2849 -> 1054.
  Per map hole px before/after: m0 810/37, m1 149/149, m2 108/104, m3 222/160, m5 21/21, m6 236/145, m7 132/72, m8 0/0, m9 541/228, m10 12/12.
- Hole poses (21 poses aimed at the filled cells): hole px 63458 -> 2712. 2209 of the rest is one pose (map 8, cell 67,90): the island lid shows under a raised ramp.
- Sweeps (6 shore sweeps x 20 steps of 64 units): hole px 776 -> 295, hole spikes 3 -> 1 (map 0, last step, 49 px), water-pixel dropouts 0.
- Static flicker, 141 fixed poses with forced LOD, consecutive screenshots: 0 differing px (the third grab sometimes lands on the next pose, so only the first pair is used).
- Tour (11 maps x 4 views, first lap): worst view 459 scanlines before, 461 after (map 0 view 1, both already at the lowest LOD); no prim overflow. The same tour without the cache measured 658 worst.
- Amiga comparison (grids 0-3, checker --amiga): map 2 water identical (1610 cells, 0 differences). Map 0: Amiga-only water 40, PS1-only 148, 14 of 1296 water cells differ by more than 64 height units (largest 7808, a cluster near cells 20-22,44-45), 52 Amiga-only deck cells. Map 1: 7 Amiga-only deck cells, 24 PS1-only water. Map 3: 913 PS1 water cells where the Amiga grid has none (design addition, left as is).

## Not fixed
- Hairline slivers (about 717 px over 45 poses) at ramp/box T-junctions, mostly maps 1, 3, 6, 9.
- Map 2: 733 px of ramps rising out of the water 13 to 16 cells away are not drawn (beyond the ramp reach), the lid shows there.
- Maps 4 to 10 have no Amiga reference; they are checked against the GBA world data only.
- The Amiga-only water, deck and height mismatches in map 0 and 1 are reported, not changed.
- LOD adaptation makes screenshots differ frame to frame; the flicker numbers use forced LOD.

## Re-run
tests/pipeline.sh ROM ELF AMIGA DUMPS WORK (see the comments in it). tools/water_check.py is the code-only checker (classification, Amiga comparison, pose generator).

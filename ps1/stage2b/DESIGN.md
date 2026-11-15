# Stage 2b design: Stunt Fox engine + Freedom City on the PS1 GPU/GTE

Status: design only. Sources: `notes/engine.md` (E), `notes/world.md` (W), `notes/ps1.md` (P), `notes/ref/gba_ref.json`.
"Proven" = seen in PCSXR by the note writers. "Estimate" = arithmetic, UNMEASURED; the build agent replaces it with a measurement.
All paths below are under `SP/v12/ps1/stage2b/` (SP = session scratchpad). Nothing derived from the ROM goes to the repo or `/mnt/project-files/stunt-fox/`.

## 0. Decisions in one table
| Topic | Decision |
| --- | --- |
| Output | `sf2b.iso`: one PS-EXE with all data linked in (no CD driver yet), pad-driven car/fly camera in map 0. Final copy to `/mnt/project-files/builds/ps1/` once M4 passes. |
| World data | Converter reads `world0/world.bin` + `tiles.npz` (already proven identical to the cartridge). The SFW4 blob is loaded UNCHANGED except that tile ids in `ctex/btex/dtex` become atlas slot numbers. A sidecar adds ground mask, tile averages, flat colours. |
| Textures | 384 tiles, 8 bit, one 256-entry CLUT (+ fog CLUT ladder), 6 pages of 256x256 in VRAM, uploaded once at boot. |
| Ground | One quad (n x n sub-quads) per ground cell in the BG list, drawn before everything; textured to 6144 units, flat beyond. |
| Projection | GTE, H=181, camera-relative vertices, two precision tiers (x4 within 4096 units, x1 beyond), OFX/OFY + 0x8000 for round-to-nearest. Near plane 32, clipped on the CPU. |
| Depth | The engine's key (z>>5, 1024 buckets) into a 1024-entry OT, add-at-head; separate FIFO BG list first. Pieces of a subdivided polygon inherit the parent's key. |
| Culling | The engine's sector walk, but by nearest point of the item, not its centre; conservative radii; reach 12288 on foot or in a car (GBA: 10240). |
| Warp / jitter | Subdivision by screen error, one shared vertex cache so every vertex is projected and rounded once, exact integer UV steps, 1/256 unit camera precision. Residual: GPU vertices are whole pixels (3.6). |
| 30 fps | `frame_flip(oy,2)`; two prim buffers, two OTs; adaptive LOD driven by the last frame's scanline count. |
| Test | Scripted pad + fixed poses, 7 GBA reference poses, crop-and-scale comparison, flash log from VRAM read-back. |

## 1. World data conversion
### 1.1 Tool: `tools/mkps1world.py` (python3 -I, numpy only)
Input: `world0/` (world.bin, world.json, tiles.npz) and, for tables that exist only in the built ELF, `stuntfox-merge.elf` (`pb_pmap`, `pb_mesh`, `pb_shade`, `pb_avg`;
`stuntfox/gen/` does not exist until a build, so read the ELF symbols; fall back to palette.c's formula with weights 3,4,2). Output dir `build/w0/` (derived, scratchpad only):
| File | Content |
| --- | --- |
| `WORLD.SFW` | SFW4 blob, ids in `ctex/btex/dtex` replaced by slot (0..383), 0xffff stays. 473,668 bytes, read as is (little endian, aligned, `world.h` unchanged). |
| `ATLAS.VRM` | 6 pages x 256x256 texels, 8 bit, in VRAM word order (2 texels a word), a 12-byte header per upload rect (x,y,w,h). 196,608 words. |
| `CLUT.BIN` | 256 x u16 palette (1.3) + 8 fog rows (1.4). 4.5 KB. |
| `SIDE.BIN` | `gmask` 16384 bits (2 KB); `slot_id[384]` u16; `avg555[384]` u16 (tile average, from tiles.npz); `mesh[384]` u8 (draw flat); `flat[16][4][4]` u32 GP0 colours = palette[pb_pmap[m*16+l*4+f]] (the GBA look); fog colour. |
| `FONT.VRM` | 8x8 font, 4 bit, 96 glyphs drawn by the tool (no external font), with its CLUT. |
| `manifest.json` | sizes, page layout, hashes, slot table; the test harness reads it. |
Slot order = ascending tile id (stable, debuggable). The map with the most tiles has 386 (map 8): 7 pages, still inside the VRAM plan.
### 1.2 VRAM layout (arithmetic from P section 2; proven only in the small, M1 proves it whole)
Frame buffers (0,0) and (0,240), 320x240 each. CLUT strip (0,480): row 480 = main CLUT at x=0, rows 481..487 = fog steps. Pages: `pg = slot/64`,
`tpage = TPAGE(320+128*(pg%5), 256*(pg/5), 1, 0)`, `u = (slot%8)*32`, `v = (slot/8%8)*32`. Map 0 fills 6 of the 10 page positions; the rest (4 pages and the two 64-word columns) holds
models, the HUD font (page at x=960,y=0) and a second CLUT. Upload by DMA2 block mode from RAM (our own LoadImage: GP0 A0 + DMA); P section 10 says the polling version is slow, so M1 builds the DMA path.
### 1.3 CLUT
`CLUT[i] = rgb555(pal[i])`, red and blue swapped from the ROM order (W section 6). An entry equal to 0x0000 is transparent on the GPU, so it is stored as 0x8000 (black with the stp bit; opaque polygons ignore stp). Index 0 is drawn black as on the GBA.
### 1.4 Fog ladder
Row f (0..7) = every entry blended toward the fog colour (22,26,30)<<3 by f/8. Textured polygons beyond 4096 pick `CLUT(0,480+f)`, `f = min(7, (z-4096)*8/8192)`. A PS1 extra: the GBA never fogs tiles. M3 builds without it (`-DFOG_TEX=0`), M5 enables it if it looks clean.
### 1.5 Ground mask (`gmask`)
The GBA fills one island polygon at y=0 under everything; the PS1 draws a quad per cell, so the converter marks visible ground: a cell is ground iff no box with `base==0` and no non-deck ramp covers it and `ctex != 0xffff`.
Decks over open air (`base != 0`) do not clear the bit (the street under a bridge stays drawn). Water cells are ramps (tile 0x317), not in the mask. Check: the converter draws its own top-down from `gmask` and diffs it against `world0/preview.png`; the street-level screenshots then cover the rest.
### 1.6 RAM budget, map 0 (estimate)
PS-EXE image ~1.05 MB (code 150 KB, blob 474 KB, atlas 197 KB, side 20 KB; the atlas region becomes heap after the upload). Two prim buffers 2 x 128 KB, two OTs 2 x 4 KB, vertex cache 48 KB, stack 16 KB: about 1.45 MB of 2 MB.
The seven per-cell arrays (352 KB, mostly zeros) are kept; stage 3 can pack them if RAM gets tight.

## 2. Renderer structure (`src/`, plain C, clang flags of P section 1 INCLUDING `-mno-check-zero-division`)
Files: `gte.h` (macros, P 4), `gpu.h` (packets, OT, DMA; from `ps1test/ps1.h`), `cam.c`, `vcache.c`, `ground.c`, `city.c` (sector walk, boxes, lots, ramps, trees, props), `clip.c`, `model.c`, `sky.c`, `hud.c`, `pad.c`, `drive.c`, `main.c`.
Engine maths (`fx.c`, sin_table) is compiled from the repo path with `-I` (read only). Frame order mirrors `sf_draw` (E section 5):
1. `pad_read`; `drive_step(ticks)` at fixed 60 Hz steps (ticks from the hblank counter, max 4); camera update to `cam.pos` (s32, units<<8) and `cam.m` (M3 1.14 with `r` negated: the mirror, E section 3).
2. `begin_frame`: clear OT and BG list, vertex-cache stamp++, GTE rotation rows `(r>>2, -(u>>2), f>>2)`, TR 0, H 181, OFX = (160<<16)+0x8000, OFY = (120<<16)+0x8000, ZSF3/ZSF4 for OT keys (E section 10).
3. `sky_draw`: 9 flat quads on the BG list from the `r_sky` band-edge equation (E section 8), palette colours; the draw-area clear gives the horizon colour.
4. `ground_draw` (BG, FIFO), own vehicle, `city_draw`, props, trees, entities (models), then `hud_draw` last with no depth.
5. `gpu_idle`; `ot_send`; `frame_flip`. Prim buffers alternate: build N+1 while the GPU draws N (needed on hardware; harmless in PCSXR).
Culling is never by NCLIP/winding (E section 4: winding is inconsistent and the camera is mirrored): box faces by the camera-side plane test, models by normal . (v0 - cam) in model space, ground and tops always up-facing.

### 2.1 Camera-relative transform, two precision tiers
For a world point `p` (s32 units) whole-unit `d = p - (cam.pos>>8)` is fine far away, but within 4096 units one unit is up to 1.8 px at z=100, so near vertices use quarter units: `d4 = (p<<2) - (cam.pos>>6)`
(cam.pos is units<<8, so the camera moves in 1/256 unit steps and the picture does not step with it).
- Tier A: `max(|dx|,|dy|,|dz|) < 4096`: GTE input `d4` (<= 16383 per axis; after rotation <= 28.4k, under the IR saturation of 32767); SZ is 4x real z.
- Tier B: farther: input `d` (reach + sector radius stays under 32767); SZ is real z. Both tiers store real z (`SZ>>2` in tier A) in the cache entry, so keys, fog and clipping do not care.
- Near plane `NEAR = 32`. The GTE divide saturates below z=23 at x4 with H=181 (E section 10), so tier A is valid down to 32. Any vertex with `z < 32` goes to the CPU clipper (3.4). Tier B is 4096+ away, never near.
- Models: matrix elements scaled x4 (elements stay under 4.0, limit 8.0) and TR = t x4 (s32) in tier A, so the local s16 vertices stay as stored. Tier chosen per instance by its distance.
### 2.2 Vertex cache (`vcache.c`)
Direct mapped, 4096 entries x 12 bytes `{u32 key; s16 sx,sy; s16 z; u8 flags; u8 stamp}`. Key = world lattice point `(x>>7, y>>7, z>>7)`; all cell, tile and sub-tile corners up to n = 8 are multiples of 128 (n = 16 uses a second 64-lattice cache).
A vertex is projected once per frame (RTPS, ~15 cycles) and every polygon touching it uses the same integers. This is the "consistent rounding" rule: neighbours share bit-identical vertices, so no cracks from independent rounding and no per-polygon shimmer.
Estimate: 3,000 projections a frame = 45k cycles + ~40 cycles of cache logic each = 165k cycles worst case.

## 3. Ground, tiles, subdivision (the part that decides the look)
### 3.1 Which cells
For each cell in the 25x25 window around the camera cell (reach 12): keep it if `gmask` is set, its nearest point is within 12288 (Chebyshev), and the bounding box of its projected corners is not entirely off-screen
(near the camera the frustum plane tests of E section 3 on camera-space corners). Off-screen cells are dropped before any sub-quad exists; cells crossing the near plane go to the clipper.
### 3.2 Level of detail by ring
Ring `d` = Chebyshev distance of the cell from the camera cell: `n = 8` for d<=1, 4 for d==2, 2 for d==3..4, 1 for d>=5 (ratios 2:1 only). Every cell in a ring has the same `n`, so there are no T-junctions inside a ring.
On a ring boundary the finer side's edge vertices lie on the coarse side's straight edge (a straight 3D line projects to a straight line), so only integer rounding (<= 1 px) can open a crack. Affine error for a cell straight ahead
(P section 5 formula `L*(zmax-zmin)/(2(zmax+zmin))`): about 1.9 px at z 5000 with n=1, about 1 px at z 2500 with n=2. Cells at the screen edge are steeper, so `n` is raised one level when the error measured from the 4 cached corners exceeds 2 px.
Cracks: the BG list starts with one flat ground-colour quad under the lower screen (debug builds paint it magenta so test 7.4 can count crack pixels). If cracks exceed 0.1% of ground pixels, M6 adds a stitch fan (the coarse border quad split into 3 triangles through the shared mid vertex).
### 3.3 Texture mapping
`u,v` are exact multiples of `32/n` texels from the tile origin (n is a power of two, so UVs are integers: no UV rounding wobble). The last vertex of a tile uses 31 instead of 32 (texel 32 would be the next tile in the page).
If the seam test (7.3) shows seams, the fallback is a guard ring in the atlas (tile pitch 33, the extra column/row copies the tile's own edge).
Floors: `texel = tile[((z>>5)&31)*32 + ((x>>5)&31)]`, tile `ctex[(x>>10)*128 + (z>>10)]`, u from x, v from z. Walls: u from s (along the side from its low corner, always toward +x/+z), v from t (down from the top edge), tile
`btex[16*box + 4*side + min(3, s>>5)]`; v wraps every 1024, so a tall wall is one tile-quad row per 1024 units (E section 8).
Lighting: tops use the raw texture command (bit 0 set); walls modulate grey 74/92/110/128 (-x, +z/-z, +x, light 3). Tiles with `mesh[slot]`, ground and roofs beyond `TEX_FAR 6500`, walls beyond `TEX_WALL_FAR 5000` draw flat `avg555`
(a far wall = one flat quad per face); far flats are mixed toward the fog colour by the engine's 4 fog steps on the CPU.
### 3.4 Near-plane clip and big polygons (`clip.c`)
Polygons with any vertex `z < NEAR`, any |IR| >= 32000, any |sx| or |sy| outside -1023..1023, or a screen box over 1023 x 511, are clipped in camera space (Sutherland-Hodgman against z >= 32, `t` as 0.12 like `cut12`),
projected on the CPU (`sx = 160 + x*181/z`, reciprocal table), UVs interpolated, emitted as a triangle fan. Only the few sub-quads that cross the plane are clipped (method proven in P section 5, `clipquad`), so a wall beside the camera never disappears.
### 3.5 Walls, roofs, ramps
Same machinery: tile quads (1024 x 1024 units) with `n` from the 2 px rule, one `n` per face (no inner T-junctions), the face's own key. Visibility (E section 7): tops when `cam.y > top`; a side when the camera is beyond its face plane; undersides below decks.
Decks grow g = 6 + z/128 units (hides seams). Ramps: top quad key -2 (farthest z), tiled or flat, sides light 1/0 by camera side, sunk floors get `sunk_side` walls.
### 3.6 Warp and jitter plan: what can and cannot be removed
Removed: affine warp (3.2, 3.5: error about 1 px, under 2 px), cracks and neighbours that disagree (2.2), texel crawl from fractional UV (3.3), stepping of the camera (1/256 unit and the x4 tier), round-down bias (OFX/OFY + 0x8000 rounds to nearest instead of truncating).
Not removable on the GPU: vertices are integers, so a slowly moving edge steps by a pixel. With shared vertices and subdivision that is a 1 px edge crawl, not the PS1 look of whole polygons sliding. If that is still disliked, the optional fix is 640x240 hi-res (half-pixel horizontally,
double fill): `-DHIRES=1`, evaluated at M6, not the default.
### 3.7 Estimated primitive counts (foot_start pose, UNMEASURED)
Ground ~430 quads after sub-quad cull (4 cells x 64 + 5 x 16 + 10 x 4 + ~50 x 1 in view); walls and roofs ~60 faces x 8 tile quads x 1.5 = ~700; trees, rails, props ~150; models ~150. Total 1,400 to 2,000 quads. Cap `MAXQ = 2200`; over the cap the ring thresholds move one step (4.3).

## 4. Visibility, draw distance, depth, budget
### 4.1 Reach and no missing buildings
Reach `R = 12288` on foot and in cars (GBA on foot 10240). In the air the GBA formula `view = 16*1024 - min(alt,3000)`, capped at 16384 (E section 7). Each rule defends against a skipped building:
1. Sectors chosen by square: every 8x8-cell sector whose square comes within `R + 1024` of the camera (Chebyshev). The GBA's `slack -4096` is not used.
2. Items distance-tested by the nearest point of their box, not the centre, so a 4x4 building does not vanish while its near corner is inside the reach.
3. Sphere tests use the GBA radii (`max(w,d)*3/4 + h/2`; sector sphere 7000 at y 1500) plus 10%; a sphere straddling a plane is never rejected, only one fully outside.
4. Items listed in several sectors are drawn once with `u16 stamp[]` (frame number) per item type; no bitset clear.
5. Hysteresis: the reach grows at once and shrinks only after 30 frames, so nothing pops while turning.
6. Pool overflow: when `MAXQ` is hit the far items go first (LOD shift), never the near ones; the player's car is submitted first.
7. Test 7.2 T4 compares skylines with GBA frames: a missing building lowers the skyline in some column.
### 4.2 Depth ordering
OT = 1024 entries, entry = `clamp(key>>5, 0, 1023)` with the GBA key rules (mean z; -2 = farthest z for ramps, loops, back faces; a wall and its windows share a key; a tree's pieces use the foot's z). Packets are inserted at the head,
so the newest is drawn first inside an entry (the GBA order). Ground goes to the separate FIFO BG list before the OT; it is flat and non-overlapping so it needs no sorting, and cars and people never sort against it.
Pieces of a subdivided polygon carry the parent key. Known limit, same as the GBA: one z per polygon, a long wall can mis-sort against a car beside it.
### 4.3 Frame budget at 30 fps (estimates)
One frame = 526 hblank lines = 1.13 M cycles (P section 7). Per-item costs from P section 9 (loop C 221 cycles a quad in PCSXR; real hardware estimated 200 to 230):
| Item | Cycles |
| --- | --- |
| Sector and item walk (30 sectors, ~700 items tested, ~250 drawn) | 90 k |
| Vertex projection (up to 3,000 cached vertices) | 165 k |
| Quad emit (1,500 quads x ~120 beyond the projection) | 180 k |
| Models (30 entities x 25 faces x 150) | 110 k |
| Clip, HUD, sky, pad, input | 60 k |
| Engine total | ~600 k = 53% of a 30 fps frame |
That leaves ~500 k cycles for the translated Payback logic later (PS1_PLAN guesses 20-50% of the CPU at 24 fps). GPU fill (estimate): at most 2.5 x overdraw x 77k px = 190k px, 8-bit CLUT textured roughly 15-20 Mpx/s on hardware = ~10 ms, overlapped with the CPU.
Adaptive LOD: if `HLINES` per frame exceeds 480 for 10 frames, `lod_bias` moves the rings outward one step and the reach drops to 10240; under 380 for 60 frames it moves back. The HUD shows fps (30/20/15 from flips) and engine lines.
If the engine alone is over 60% at the first measurement, fallbacks in order: reach 10240; walls flat beyond 3000; n max 4; ground beyond ring 4 flat; 20 fps flip (`frame_flip(oy,3)`).

## 5. Input and a drive / fly camera (`pad.c`, `drive.c`)
Pad: `pad_read` from P section 8 (digital id 0x41 proven; DualShock 0x73 analog: left stick steers, right stick looks, d-pad as fallback; analog is untested).
Mapping: Cross accelerate, Square brake/reverse, Left/Right steer, Triangle toggle CAR/FLY, L1/R1 camera zoom, Select cycle HUD, Start reset to the start pose (9728, 403, 2070).
CAR: speed in 1/256 units a step, steer rate scaled by speed, yaw 65536 a turn (heading 0 = +z), lateral damping as grip. Ground height: `hi` of the cell table (index x*128+z) sampled at the 4 corners and the centre of the 224 x 470 footprint, slope from the cell shape (ramp formula, E section 6),
`deck` top when the car is within 64 units above it, water (shape 6): drag 0.9 and rest at surface - 40. Collision: a footprint sample whose ground is more than 48 above the car's y blocks that axis (axes tested separately, so the car slides along walls), plus the `wall` edge bits (a flagged cell edge stops a car).
The car is drawn with the real saloon model (`looks[]`); the chase camera uses E section 11 values (820/300/110/250, eased by 1/4, pulled in by ground height).
FLY: free camera; d-pad/left stick move, Cross/Square up/down, L2/R2 speed; only box tops stop it (bounce), so the whole city can be inspected for the screenshot tests. Both share `cam`.
Scripted pad (`-DSCRIPT=file.h`): a table `{frame, buttons, lx, ly}`, frame-count driven (not wall clock), so every run repeats exactly.

## 6. HUD, disc layout, runtime interface
### 6.1 HUD
Text as textured 8x8 sprites (`GP0 0x64`) from the font page, sent after the OT so it is never sorted. Lines: `FPS 30  ENG 412L  Q 1432` and `X 9728 Z 2070 Y 403  H 0  CELL 9,2  MODE CAR`. Solid colours, no blinking; numbers refresh twice a second.
### 6.2 Disc (ISO9660 via `genisoimage`, as `hello/mkiso.sh`)
`SYSTEM.CNF` (`BOOT = cdrom:\SF2B.EXE;1`, `STACK = 801FFF00`) and `SF2B.EXE` holding code + `WORLD.SFW` + `ATLAS.VRM` + `CLUT.BIN` + `SIDE.BIN` + `FONT.VRM` via `.incbin` (4-aligned). One file needs no CD driver; the CD reader of stage 3 later
moves the same blobs to disc files (names reserved `WORLD0.SFW`, `ATLAS0.VRM`). Load address 0x80010000, data after code, `.bss` after the data.
### 6.3 The interface the Payback logic calls
In the GBA build Payback's world renderer is replaced by the `sf_frame` hook (keyhook.s) which calls `sf_draw` (merge.c). The only use of 0x03000580 in the repo is `radiodec.s`, which calls a Payback IWRAM routine there (the music pass), so there is no `gfx_view3d` source to read.
Treat the name as OUR PS1 entry, bound by the stage-1 translator in place of the `sf_frame` hook (the address in the task text could not be verified; to confirm with the translator owner):
```c
typedef struct { s32 pos[3]; M3 m; s16 focal; u8 mode; u8 flags; } SfView;   /* pos units<<8; m = engine matrix, already mirrored */
typedef struct { s32 x,y,z; u16 yaw; s16 pitch; u8 model, paint, scale_q, flags; u16 id; } SfEnt;   /* entity_pos units, E section 2 */
void gfx_view3d(const SfView *v, const SfEnt *ents, int n_ents, const SfHud *hud);   /* builds and queues one frame */
void gfx_world_select(int map);      /* loads that map's WORLD + ATLAS */
```
Payback records convert on the translator side with `entity_pos` (x = E_X>>1, z = E_Y>>1, y = ((19904 - h)>>1) + yoff, heading = s16 * 11651 >> 10). Stage 2b's `drive.c` fills the same structs, so stage 3 only swaps the caller.

## 7. Tests (run by the build agent; emulator runs use `xvfb-run -a` and a copy of `ps1test/run.sh`; never touch `~/.pcsxr/pcsxr.cfg` or `stage2/`)
### 7.1 Pose mode
`-DPOSE=k` renders pose k of `gba_ref.json` (foot_start, walk_0..5: cam_pos, r, u, f, focal 136) as a fixed frame after 3 warm-up frames, with a 320x213 test viewport (draw area rows 0..212, OFY = 107) so the field of view equals the GBA's
(H 181 on 320 px = 136 on 240 px; 213 rows scale by 0.75 to the GBA's 160). The harness takes the screenshot (`import -window root`, cropped to the emulator window).
### 7.2 Comparison with the GBA (`tests/cmp.py`)
GBA shots from `notes/ref/`, or new ones from the mgba harness (`scratchpad/work`, emu.py/scenes.py) at the same pose. Both scaled to 240x160, HUD/man/car masked by per-pose rectangles. Metrics:
- T1 structure: Sobel edge maps, F1 within 3 px; gate at M2 = 0.5, at M3 = 0.6 (the first measurement sets the baseline; later changes may not lose more than 0.05).
- T2 colour: mean absolute error of 8x8-block averages <= 24/255 on unmasked blocks (Payback palette parity).
- T3 texel: ground pixels of the lower 40% match Payback's addressing (logic of `notes/ref/texcheck.py`) within one texel for >= 80% (the GBA gets 93%).
- T4 skyline: per column the topmost non-sky row; the PS1 may be higher (it draws buildings the GBA drops past its reach; list them) but never lower by more than 3 rows within 10240 units: the "no missing buildings" check.
Output `tests/out/pose_k_ps1.png`, `_gba.png`, `_diff.png`, `report.json`; the agent reads the images itself.
### 7.3 Warp and seam tests
A synthetic atlas page (`-DTESTATLAS`): a tile with a 1-texel red border and a diagonal line; read the shot for kinks along cell diagonals and seams at cell borders; the count of border-coloured columns must equal the number of cell borders.
### 7.4 Crack test
Magenta underlay; count magenta pixels in the ground area at poses 0..6 and over a 300-frame scripted drive. Pass: under 0.1% of ground pixels and under 40 pixels in any single frame.
### 7.5 Flash check (the user must not see flashing or strobing)
The test build logs per frame `lum_mean` and `lum_max_block_delta`, computed from a VRAM read-back of the displayed frame (GP0 0xC0, every 4th pixel; slow, so the test ignores real time). Scripted 600-frame drive, including the start pose and a 180-degree turn.
Pass: `|mean(t) - mean(t-1)| <= 8/255` for every pair; at most 3 sign changes of a delta above 3/255 in any 30 frames (no strobing); no frame where over 25% of the 8x8 blocks change luminance by more than 60/255. No palette animation; water drifts one texel every 16 ticks only.
Logs in `tests/out/flash_*.log`.
### 7.6 Other
Determinism (two scripted runs give identical frame hashes); pool and `MAXQ` overflow counters in the log stay 0 at the poses; engine lines per frame (min/mean/max) logged each run; converter checks (slot table against `tiles.npz`, gmask against preview, blob bytes equal apart from the id fields); one real-key run via xdotool (arrows, z, x, s, v) at M4.

## 8. Milestones for the build agent (each ends with a screenshot the agent reads and a short note in `NOTES.md`)
- M0 Skeleton: copy `ps1test/{ps1.h,crt0.s,ps1.ld,build.sh,run.sh}` to `src/`, add `-mno-check-zero-division`, ISO script, empty 30 fps loop, HUD font. Pass: ISO boots, text readable, 3 consecutive shots identical, a padded 1 MB EXE loads under the HLE BIOS.
- M1 Data: `mkps1world.py` + converter checks; the boot code uploads atlas + CLUT; a test screen shows page 0 and the palette as swatches, compared with `world0/atlas.png`. Fallback: if DMA upload misbehaves keep the polling loader and accept a longer boot.
- M2 Ground: pose foot_start, sky bands, ground rings with the vertex cache, near clip; compared with `gba_foot_start.png` (T1-T3 on the lower half). Fallback: n=1 everywhere plus underlay, then fixed 4-level subdivision without the cache.
- M3 City: sector walk, boxes (tops and 4 sides), lots, ramps, decks, wall tile quads, depth OT; 7 poses compared; skyline, crack and seam tests; per-pose budget measurement. Fallback if over budget: reach 10240, walls flat beyond 3000.
- M4 Control: pad, fly then car with cell-height and wall-edge collision, chase camera, position HUD, 600-frame scripted drive, flash check, 30 fps line count. Fallback: car with ground height from `cell.hi` only (no slopes or decks).
- M5 Extras: vehicle and people models through the GTE, trees (3-polygon cut-outs), rails, benches/lamps, tile fog ladder, water drift, the `gfx_view3d` wrapper with a small scripted traffic list. Fallback: models as flat boxes.
- M6 Polish and ship: stitch fan if cracks exceed 0.1%, LOD hysteresis, optional hi-res trial, performance pass, final flash and pose runs; copy `sf2b.iso` to `/mnt/project-files/builds/ps1/` (nothing else); `RESULTS.md` with measured numbers replacing every estimate here.
General fallbacks: if the two-tier GTE path misbehaves, use tier B only (whole units) with NEAR 100 (P section 4); if textured ground costs too much, flat ground beyond ring 3; if flips are unstable, 20 fps. Every milestone keeps the previous ISO.

## 9. Risks and open questions
1. Real hardware timing is unmeasured (PCSXR draws in zero time): the budget comes from instruction counts. Ask the user to run the M4 disc in DuckStation or on hardware and report the HUD lines.
2. UV `-1` and texel bleed on real GPUs (7.3 decides). 3. The `gfx_view3d` binding must be confirmed with the stage-1 translator owner (6.3). 4. The HLE BIOS must load a ~1 MB EXE (M0 proves it).
5. Roof and deck mapping, `dtex`, sunk floors and the night palette are not verified against the GBA (E section 12); M3 checks roofs and decks by screenshot from the bridge view of `world0/check_view_bridge.png`.

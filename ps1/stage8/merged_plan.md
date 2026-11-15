# Star-FlyBack on PS1: translating the merged v12.26 ROM instead of plain Payback (scout plan, 2026-11-15)

Scope: plan + numbers, no big build. What was run: the stage 7 translator front end and emitter (static, no link), libmgba (GBA side) profiling, ELF/object analysis. **Nothing in this scout was run on a PS1 or in PCSXR.** Every "PS1" figure below is an estimate from GBA-side counts and translator word counts and is labelled so. Scripts and two small patches (code only): `stage8/merged_scout/`.

Rules kept: no Payback code/assets/ROM/audio in the repo, Payback song 3 stays out, no flashing, Payback's tiles stay as textures, bore-gba untouched.

Inputs: `Star-FlyBack v12.26.gba` (32 MiB), checked byte for byte: the Stunt Fox blob at 0x081b0000 (0x9895c bytes) is identical to the `--merge --no-remixes` link of the repo at HEAD (eea8bd1); the ELF of that link (`stuntfox-merge.elf`) is the ground truth for code/data boundaries. (v12.26 adds only the remix audio above 8 MiB: 23.8 MiB non-empty above 8 MiB with the remixes, 7.5 MiB without. The PS1 build should translate the `--no-remixes` ROM: radio goes to CD-DA.)

## 1. What the merged ROM is, in code bytes (ELF mapping symbols)

| | Thumb | ARM | data in the same span |
|---|---|---|---|
| `.text` at 0x081b0000 (ROM) | 227,502 B (~110K insns) | 860 B (lld veneers, memcpy/idiv glue) | 381,570 B (tables, models, literals) |
| `.hot`..`.hot11` (IWRAM overlays) | 0 | 13,848 B (3,525 insns incl. 38 umull/smull) | 340 B |
| Payback (unchanged, 0x08000000..0x0807c9e0) | 329,450 B (156,988 insns reachable from the entry; 214,181 with the stage 2 orphan/pointer heuristics) | IWRAM image 27.5 KiB (6,392 insns) | |

Stunt Fox Thumb bytes by module: merge.c 47.5 K, spacegame 36.9 K, citydraw 15.8 K, spacewalk 14.6 K, mission 13.8 K, s2core 13.6 K, sgx 11.4 K, render 6.4 K (+4.0 K ARM), ragdoll 10.2 K, campaign 7.7 K, props 7.6 K, save 7.4 K, physics 5.9 K, station 5.4 K, planet 4.9 K, ship 4.5 K, car 4.2 K, settings 3.9 K, radio 2.9 K, msn_draw 2.5 K, tex (6.9 K ARM), model 1.2 K ARM. The ARM part is the software rasteriser's inner loops, kept in IWRAM (glyph, clip, poly, raster, wall_edges, tex_wall, tex_rows, tex_hspan, tex_occlude, tex_frame, model_draw, divq/recip ...).

**Thumb/ARM split of the translation universe: 324,317 Thumb insns (97%) + ~10.4 K ARM (3%).** SF adds 110,296 Thumb + 3,525 ARM insns to Payback's ~221 K (+50%).

## 2. Translator prototype on the merged ROM (stage 7 `t2m.py`/`disc.py`, pruned stubs as in stage 7)

Discovery (36 s), then analysis + emission (4 s), same code path as the Payback build:

| run | insns | note |
|---|---|---|
| Payback only (baseline, same heuristics) | 220,981 (214,577 Thumb + 6,392 ARM + stubs) | matches stage 2's 226 K |
| merged, stock `disc.py` | 321,449 | SF Thumb 100,478 |
| merged, + TBH recognizer (patch) | 339,021 | SF Thumb 117,890, of which 7,754 are data decoded as code |
| merged, + ELF-guided cleanup (build has the ELF) | **331,267** | SF Thumb 110,296; uncovered code 0.6% (1.3 KB) |
| SF IWRAM overlays, separate pass | 3,525 ARM | 13,984 of 14,044 section bytes decoded, 0 undecodable |

Translated size, MIPS-I words (no link; the model of stage 2 with inline region guards): Payback 615,816 words (2,406 KiB, 2.79 words/insn); merged 893,646 words (**3,491 KiB**): the SF Thumb part adds +277,830 words (**1,085 KiB**, 2.52 words/insn); SF IWRAM overlays 11,171 words (**43.6 KiB**, 3.17/insn). Whole merged universe about **3.45 MiB**, 1.7x the PS1's total RAM. Hazard nops added: 20.6 K (2.3%).

### New constructs found (all absent or unseen in Payback), with status

1. **Thumb-1 inline offset tables (TBB/TBH emulation): 48 sites** (`add rX,pc; ldrb/ldrh rX,[rX,#4]; lsls rX,#1; add pc,rX`, table inline). The stock discovery stops at `add pc`, so everything only reachable through the table was silently dropped: **16.7% of SF code (38 KB) was never decoded** (e.g. most of `world_draw` and `st_hud`). Patched recognizer (table size from the preceding `cmp`/`bhi`) closes it to 0.6%. The translator already emits `add pc` through the generic hash lookup (works, costs ~25 insns per dispatch); a native MIPS jump table is a later optimisation.
2. **IWRAM code versioning.** SF lends its ARM hot code over Payback's IWRAM image at the same addresses (merge.ld: hot, hot2/3/5/6b/9 lent for the length of `sf_frame`, hot4/6/7/8/10/11 stay ours; `merge.c hot_install/hot_restore` copy it in and out every frame). The translator keys code by guest address, so two versions collide. Plan: translate the SF version at alias addresses, resolve calls statically (the SF Thumb callers reach it through lld veneers with constant targets), make `hot_install/hot_restore` set a 3-flag version state in the runtime, and let the lookup for IWRAM entries consult the flags (Payback's IRQ/mixer path runs outside our frame). The copy loops themselves become dead data moves.
3. **lld veneers** (`ldr pc,[pc,#-4]`, `bx` through a literal): 57 unique `ldr pc` sites. Handled as indirect jumps today; resolve the literal statically.
4. **Pointer arithmetic that assumes guest addresses** (translator logs `lsr>=24` as "unsafe": 354 sites vs 148 in Payback). Most of the +206 are packed-field shifts (progress words, `w[1]>>24`) that are harmless, but at least one is real: `tex.c:83` accepts a tile pointer only if `ptr>>24` is 8, 6, 3 or 2, which fails for a host-pointer IWRAM tile (Payback keeps some tiles in fast RAM; `PB_TEXTAB` 0x02002c60). Also `render.c PIDX/PPTR` keeps polygon-pool pointers as 16-bit word indices `(ptr>>2)&0xffff` relative to 0x02000000: valid only if the host EWRAM base is 256 KiB aligned (stage 7 has it at 0x801b0000: not aligned). Both disappear if render.c/tex.c internals are replaced at the API boundary (section 4), otherwise EWRAM must move to a 0x40000-aligned base and the region-extract needs a helper.
5. **Address space**: ROM windows assume 8 MiB (`inrange`, `ROMPG` 2048 pages, ROM.BIN 8 MB). The merged ROM keeps worlds/station/campaign blobs at 0x08800000..0x09000000 (7.5 MiB above 8 MiB). ROM page table must cover 16 MiB (4096 entries) and ROM.BIN grows to 16 MiB. The 5-9 MiB of remix audio is not needed.
6. No new unsupported instructions: the translator emitted all 331 K + 3.5 K insns without a raise; remaining non-translatable ops are the same 2 `msr`, 1 `swi` (BIOS 5, handled) as Payback, and 38+1 `umull/smull` which it already handles. Unresolved indirect: 2,475 raw sites listed vs 959 (the lists are not de-duplicated; real SF: 148 `bx lr`, 482 `bx rN`, 48 `add pc`, 7 `mov pc`).
7. A monolithic link of 893 K words fails (`branch out of range`, ±128 KiB): the same as the plain Payback translation; the partition into hot blob + cold groups from stage 2-7 is mandatory. Its resident/cold selection needs a ranking from the merged profile (see 5).

## 3. How the Stunt Fox world is drawn on the GBA (and what the profile says)

All SF 3D is in software into the mode 4 bitmap (240x160, 8 bit, Payback's palette, page flipped): polygon pool + 1024 depth buckets, painter's order, polygons clipped to the frustum in camera space inside `r_poly`, textured floors/roofs/walls via Payback's 32x32 tiles by scan-line routines (`tex.c`). The entry points are few: `r_begin/r_poly/r_polyn(<=26 verts)/r_poly_tex(PT_FLOOR,GROUND,WALL + TexFloor/TexWall)/r_poly2d/r_sky(bands)/r_pixel/r_back/r_flush_bg,fg/r_flip/r_end`, models through `model_draw` (flat colour `COLOR(material,light,fog)`, sun-lit, back-face culled), 2D through `d_text/d_cat/d_num` (~280 call sites), `d_fill/d_rect/d_panel/d_hline/d_vline/d_pixel`, pre-inked text strips (`hudline`) and the title card (a 90 KB image into the page). Palette comes from Payback's PAL (`r_pmap`, `pb_pmap`).

| scene | what SF draws |
|---|---|
| City, on foot / car | citydraw.c: boxes, ramps, loops, trees, props as flat polys; ground/roofs/walls with Payback tiles (PT_*), sky bands, people and cars as models, ragdolls |
| Arwing, low | the same plus the Arwing model, foes, shots, beacons/rings (msn_draw), radar and HUD text (draw2d) |
| Planet / space | `planet.c`: the sag of the island into a sphere (disc limb up to 26 vertices, 24 ring polygons, atmosphere bands as `r_sky`), stars via `r_pixel` (40), asteroids/moon/station as models; space.c sky by altitude |
| Fox Station / hangar | the hangar is a docked view of the Arwing model with a 2D menu panel; rooms are models seen from inside (flat shades, no tiles, no fog, fixed cameras), crew and walker, names over doors; `d_panel` darkens what is under it |
| Game settings / title | pure 2D text and the burning-logo title card, slow hardware fades |
| Payback's own 2D (hearts, score, minimap, phone) | Payback BG/OBJ tiles and OAM, not SF |

### Measured on the GBA side (libmgba, v12.26, instruction-level; GBA-only, "guest" = ARM/Thumb instructions)
Per 60 Hz vblank frame, and per game tick (vblanks per Payback key read). The CPU is never idle: Payback busy-waits.

| scene | guest insns / frame | of it SF rasteriser+hot ARM | not rasteriser | vbl / tick | guest insns / tick (all, not-raster) | polys |
|---|---|---|---|---|---|---|
| city on foot | 117.4 K | 77.5 K (66%) | 39.9 K | 3.93 | 461 K / 157 K | 58 |
| Arwing low | 117.0 K | 70.9 K | 46.1 K | 4.21 | 492 K / 194 K | 75 |
| space (climb 25,600+) | 107.7 K | 41.7 K | 66.0 K | 2.15 | 232 K / 142 K | 18 |
| hangar | 122.3 K | 92.0 K | 30.3 K | 2.78 | 340 K / 84 K | 92 |
| station room | 66.5 K | ~0 | 66.5 K (Payback's clear/copy loop 0x0807c730 alone 39 K) | 2.0 | 133 K | 60-74 |

Time-box note: ~60-120 frames per scene, start-of-map scenes, low polygon counts (stage 3 measured 123-483 prims on real snapshots); a profile of missions, combat, the campaign and the settings screen was not taken (settings reached only by code reading).

Where SF's non-raster time goes (per vblank frame, city): Payback Thumb 13.6 K, SF citydraw 5.5 K, **radiodec 2.8 K (stubbed on PS1: CD-DA)**, merge 1.9 K, tex 1.9 K, render 1.4 K; space: planet 5.4 K, draw2d 3.7 K, msn_draw 2.3 K, spacegame 2.2 K.

### GBA ROM-side coverage (union of 12 short scenes, touched instructions)
city on foot: SF 12.5 K insns, Payback 13.3 K; + Arwing low: SF 19.1 K; + air/planet/space: SF 26.8 K; + hangar/station: SF **28.6 K** of 110.3 K (26%). Payback alone over the stage 7 suite (story, rampage x9, 4x40,000-frame walks): 78.7 K of 226 K insns touched (35%). Short samples are lower bounds; SF's long tail (missions, boss/foe types, campaign, spacewalk, settings, save) is unsampled. Function-granular hot sets (functions carrying 99% of executed insns): 54-82 K static insns per scene, union over the scenes 93.5 K (425 functions); at block granularity the touched union is about 49 K insns.

## 4. Recommended architecture: translate the logic, replace the rasteriser at its API (B1), with a page-upload bring-up path (B0)

The sf3 renderer in stage 3-7 is a separate C rewrite that reads dumped worlds. For the merged ROM there are two options:
- **B2 (extend sf3 by hand)**: reimplement planet, station, hangar, Arwing, settings in C beside the city. Duplicates SF's scene code and keeps map logic out of sync. Rejected as the main route.
- **B1 (chosen)**: translate SF's Thumb logic as is (physics, car, ship, spacegame, station, mission, campaign, settings, save) and **stub the render back end at the `r_*`/`d_*` boundary** with GTE/GPU code, exactly as stage 2 stubbed Payback's blitters (`RT_STUB` with id + args). SF's scene traversal (citydraw, planet, space, stationdraw, model_draw) stays translated, so every scene SF can draw is drawn without new per-scene code.
- **B0 (bring-up and permanent fallback)**: leave the translated software rasteriser running and upload the mode-4 page + 256-colour CLUT (GBA 5-5-5 has the same bit layout as the PS1's) as one 8 bit texture each present. Gives every scene (title card, settings, hangar menu, station) at once, at about GBA speed (estimate below), and is what the 2D-only screens keep using.

### What the GPU back end must do, per scene
- `r_poly`: camera-space V3 polygons (3-16 verts, already frustum-clipped by SF today; the stub must clip/guard-band itself because the GPU drops polygons wider than 1023 or taller than 511): GTE RTPT/RTPS or CPU projection, fan into F3/F4, OT slot from `key` (SF's 1024 buckets map to the OT), `bg` list first. Colour = PAL shadow[r_pmap[color]] (RGB555 direct). Mostly what sf3.c already does (`clip_poly`, `put_f4`, 1024-entry OT, painter order).
- `r_poly_tex`: `TexFloor{k,kinv,tab}` (a tile id per cell, plane at height k) and `TexWall{w,a,b,tile[4],lut,skip}`: floor/ground into per-cell textured quads, walls per 1024 units. Needs a tile atlas keyed by Payback tile id (0x318 ids, `PB_TEXTAB`) built at disc-build time from the user's ROM (the sf3 atlas is per map, 448 slots), the reverse map pointer -> id for the wall tiles, and the `pb_shade`/`lut` darker variant as a second CLUT row. "Textures stay": satisfied.
- `r_polyn` (planet limb, 26 verts) + `r_sky` bands: triangle fans and flat/gouraud strips; huge polygons are cut to the guard band. `r_pixel` (stars): dot primitive.
- Models/Arwing/station rooms: nothing new (`model_draw` calls `r_poly`).
- `d_*` / `hudline` / settings / title: either font-atlas quads (64-glyph 4 bit font, plus rects; `d_panel` = 50% black semi-transparent quad) or B0 for whole 2D screens.
- Fades (palette fades, BLDY, title card fades): a full-screen black/white quad with a capped rate; the flash rule (no opposing luminance swings > 10%, nothing brighter than the title card's slow fades) must be re-checked per scene (sf has `flash_*` tests for arena/boss/station; the PS1 capture check from stage 7 release applies).
- Payback's own OBJ/BG 2D (hearts, score, minimap, phone, ticker): needs the PPU-lite (OAM sprites to GPU quads, BG tiles as 8x8 sprites). Not done in any stage so far; it is needed by plain Payback too. Highest risk piece shared with the old plan (R3).
- Resolution: SF projects for 240x160 (FOCAL 136, 121/81 half-extents); PS1 render at 320x240 with focal scaled, or 240x160 letterboxed; decide once for all scenes.

## 5. CPU, estimated for the PS1 (R3000 33.8 MHz) from the GBA counts

Assumptions: dynamic expansion 3.0-3.5 MIPS insns per guest insn (static words/insn: Thumb 2.5-2.8, ARM IWRAM 3.2-3.5; 20-30 K 9-word memory guards dominate the Thumb count), effective ~25 M R3000 insns/s (0.75 IPC, I-cache misses). The dynamic factor was NOT measured in this task.

| path | city | space | hangar |
|---|---|---|---|
| B0: everything translated incl. software raster: guest insns/s on GBA (full load) | 7.1 M/s (15.3 ticks/s) | 6.5 M/s (27.9 ticks/s) | 9.4 M/s (21.6 ticks/s) |
| same on PS1 at 3.2 factor | ~23 M/s = **~90%** of the R3000 | ~21 M/s = ~83% | ~30 M/s = >100% |
| B1: non-raster guest insns/tick x3.0 | 157 K x 3.0 = 0.47 M/tick: 14 M/s at 30 ticks/s (56%), 9 M/s at 20 | 142 K: 12.8 M/s at 30 | 84 K: 7.6 M/s at 30 |
| + GPU back end, 150-250 insns per primitive at 300-500 prims | +0.1 M/frame | | |

Reading: B0 runs at about GBA speed (city ~15 fps, hangar ~20) and is a fallback and bring-up path, not a target. B1 leaves room for 20-30 ticks/s; removing radiodec (-11 K guest insns per tick) and the 39 K/frame Payback clear loop in the station is part of that. The game's time base (SF's speed governor, Payback's clock tied to ticks, `GAME SETTINGS` speed) must be read before changing the tick rate: the GBA runs the city logic at ~15 ticks/s.

## 6. RAM (2 MiB), stage 7 layout vs merged B1

Stage 7 release (from `ps1.ld`/`sfmem.h`, not re-measured): C runtime 96 K at 0x10000, helper + ROM page table 8 K, hot blob + overlay pool 0x43000..0x131b04 (~950 K, fixed home, no eviction), page cache 64 K, ragdoll 100 K, draw ring/IO/PAL/OAM 20 K, guest VRAM shadow 96 K, sf3 renderer 92 K, EWRAM 256 K, IWRAM 32 K, SF3W world window 238 K (shares the overlay span), stack 12 K. Full, with a cold-code headroom of 4 KiB.

Merged B1 proposal (KiB):

| block | KiB | note |
|---|---|---|
| C runtime + interpreter fallback + stack | 96 + 16 + 12 | interp.c exists (s7cov), not finished |
| helper table, ROM page table for 16 MiB | 8 + 16 | |
| guest EWRAM + IWRAM | 256 + 32 | SF's state lives inside Payback's EWRAM (merge.ld keep/scr/poola) |
| shadows: PAL, OAM, IO, VRAM | 3 + 96 | VRAM = bitmap pages + OBJ tiles for B0 and PPU-lite |
| GPU back end code + prim buffer (32) + OT (4) + stamps | ~150 | sf3's world window (238 K) is not needed: SF reads its worlds from ROM pages |
| ROM page cache (worlds, tables, tile data) | 128 | 16 K clusters |
| ragdoll: SF's own `ragdoll.c` (Thumb 10 KB) or the PS1 solver (stage 7 g2) behind an `rag_tick` stub | 0-100 | measure; the PS1 solver is faster |
| **left for translated code** | **~1,150** | resident core + paged overlays |

Working sets against that arena (translated size at 2.5-2.8 words/insn x 4 B): city 54 K..58 K function-granular insns ~ 600 KiB; space 80 K ~ 850 KiB; hangar/station ~ 550 KiB; block-touched union of all scenes ~ 515 KiB; Payback's long-run coverage alone was ~870 KiB, SF's likely 450-700 KiB, together 1.4-1.7 MiB with the long tail. So: it does not fit as one fixed-home pool (stage 2-7), but it fits per scene. Needed:
- **true overlay eviction** (LRU, replacement), prefetch by mode (map load, climb through ~12,000, docking, hangar, station room), CD ~300 KB/s: a scene's 0.5-0.85 MiB is a 2-3 s load hidden by the existing transitions (launch, docking, map change). Seeks 150-300 ms.
- **variable-size / splittable groups.** 16 KiB fixed groups do not hold SF's giant functions: 11 SF functions translate to more than 16 KiB (sf_draw 9.3 K insns ~ 92 KiB, sg_tick 62 KiB, world_draw 53 KiB, st_hud 28 KiB, sgx_tick_foe, car_update, rag_tick ...: 36 K insns, a third of SF). Split them at labelled blocks (trampolines) or give groups up to 96 KiB.
- **interpreter fallback finished** (tail code that no coverage run touches ends in RT_MISS panic today; SF's tail is larger than Payback's). `s7cov/interp` (interp.c, asm slabs, host test + fuzz) differs from the reference after ~1,094 frames (stage 7 release README): finishing and soaking it comes before the long-tail coverage hunt.
- per-scene hot ranking from this profile at **function entry counts**, not touched sets (the stage 7 `mkresident` takes any touched function as hot: 198 K insns resident on the merged ROM, which cannot link).

## 7. Milestones

| | content | exit test | size |
|---|---|---|---|
| M0 | this scout | numbers + patches | done |
| M1 translator on merged | ELF-guided discovery, TBH tables (native jump tables later), veneer resolve, IWRAM version flags (hot_install/restore = flags), 16 MiB ROM window, unsafe-`lsr` triage, partitioned link; ARM vs MIPS lockstep on the merged ROM (unicorn harness exists) | 400 ticks city + Arwing launch: IO log, draw list, EWRAM/IWRAM/PAL/VRAM snapshots, 0 diffs | 2 agents |
| M2 bring-up, B0 | page-upload present; title card -> level; Arwing, space, hangar, station, settings visible; radio/saves stubbed | all scenes visible in PCSXR (slow is fine); no RT_MISS in a scripted tour | 1-2 |
| M3 GPU back end, B1 | city first (compare with sf3 and with B0 frame by frame), then models/Arwing, planet/sky/stars, text/HUD, fades; Payback tile atlas by id | per scene: prims, no overflow, picture matches B0 within tolerance; instruction counts per tick <= budget in section 5 | 2 |
| M4 paging + coverage | eviction, split groups, prefetch, interpreter fallback finished; coverage suite on the merged ROM (extend `s7cov/cov/suite.py` with Arwing, space, station, missions, combat, settings, spacewalk, save) | 40,000-frame random runs on mGBA give the cold list; PS1-side run without RT_MISS panic through the scripted tour | 2 (parallel with M3) |
| M5 audio, saves, PPU-lite | SF radio -> CD-DA, Payback SFX, SF `save.c` EEPROM image -> memory card, Payback OBJ/BG 2D | radio keys, save/load round trip in PCSXR, HUD/phone visible | 1-2 |
| M6 perf, flash, release | tick-rate pass, flash capture check per scene, README/BUILD, emulator-only label | 300 s scripted capture, 0 opposing luminance swings > 10% | 1-2 |

M1 and M2 can start together (the page-upload path needs only a translated SF + the runtime), M3 and M4 run in parallel after M1.

## 8. Risks

1. **RAM / paging (high).** 3.45 MiB universe, 1.4-1.7 MiB working set, 1.15 MiB arena; needs eviction, split groups, and a finished fallback. Failure mode: RT_MISS panic or CD stalls in a scene change.
2. **ROM data reads (high, unmeasured).** SF's world, tile and model tables are ROM reads; stage 2 noted the ROM fast path in `RT_MEMRD` disabled and a slow C path; SF reads worlds every frame. 973 static ROM-constant sites + dynamic ones. Needs a resident copy of the current map's tables and a fast path, measured on the translated side.
3. **IWRAM versioning (medium).** Wrong version = executing Payback's code in SF's frame or the reverse; the copy loops use words read back as data (`hot_mine`). The flag design must be lockstep-verified through a level, a pause, a death and an Arwing boarding (the same events merge.ld's comment says were watched).
4. **Pointer-model hazards (medium).** `tex.c` region check, `render.c` 16-bit pool indices (aligned EWRAM base or stub), 206 new `lsr #24` sites to triage; any code comparing pointers to region constants.
5. **Texture path (medium).** Atlas by tile id from the user's ROM at build time, palette/shade variants as CLUT rows, VRAM budget with 320x240 double buffer; water image outside the tile table (`PB_WATER`).
6. **PPU-lite for Payback's 2D (high, shared with plain Payback).** Needed for HUD/minimap/phone/menus in every scene.
7. **Game time base (medium).** GBA city ticks at ~15/s; a faster PS1 tick must keep SF's speed governor and Payback's clock consistent.
8. **Coverage of the long tail (medium).** SF's missions/combat/campaign code is only ~26% sampled; without the fallback a rare path panics.
9. **Dynamic expansion unmeasured (medium).** The 3.0-3.5x factor and the 25 M insns/s are assumptions; the first lockstep sim of M1 gives the real count per tick (unicorn MIPS counts), PCSXR cannot give timing.
10. **Emulator-only (all).** No real BIOS, DuckStation or hardware anywhere; PCSXR with the HLE BIOS is the only PS1 target and its speed says nothing about a console.

## 9. Honest gaps of this scout
- No PS1/PCSXR run; no link of the merged translation (the partitioned link needs a hot ranking that was only prototyped, sections 6-7); the dynamic MIPS/guest ratio is an assumption.
- GBA profile: 11 short scenes at map start, one map (Freedom City), no missions/combat/settings/spacewalk/save; the settings screen and title card are described from code, not measured.
- TBH recognizer is a prototype in discovery only (verified by ELF coverage 16.7% -> 0.6%, not by an ARM-vs-MIPS lockstep).
- RAM budget rows other than the stage 7 ones are proposals; the ragdoll and GPU code sizes are carried over from stage 7.
- Screenshots of the scenes (used to confirm the scenes were reached) contain Payback graphics and stay in the scratchpad, not in the repo.

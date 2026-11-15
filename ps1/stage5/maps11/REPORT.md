# Stage 5: all 11 world maps on the stage 2b PS1 renderer (maps11)
Emulator-only: PCSXR 1.9.94, HLE substitute BIOS, GL plugin. 1 line = 1 emulator hblank line (30 fps needs <= 456). Not run on hardware or a real BIOS.
## What changed vs stage 2b
- tools/mkps1world.py --all: converts world0..world10 (tools/dumpworld.py --rom BUILT.gba --map N --out mapsDIR/worldN) into one MAPS.BIN (header sector + per map WORLD.SFW, ATLAS.VRM, SIDE.BIN, CLUT.BIN, each sector aligned) and FONT.VRM. Side tables grown 384 -> 448 slots (map 8 has 386 tiles). Start point per map comes from the dump.
- VRAM: atlas pages at (320+128*(pg%5), 256*(pg/5)); the most pages is 7 (map 8), so every map fits with CLUT rows (0,480..487) and font (960,0). No page overlap checked by the layout arithmetic and by 11 screenshots.
- sf.c: polled CD reader (ReadN, double speed), per-map load into fixed RAM windows (world 0x800A0000, atlas staging 0x80120000, side, clut), atlas uploaded by DMA, world pointers re-derived. Cost per map: 270..435 sectors (0.55..0.9 MB: world + atlas + side + clut); load runs in the main loop (the last frame stays on screen while loading). tools/mkiso_maps.py patches MAPS.BIN's LBA into the EXE inside the ISO.
- Map switcher: START held + R1 = next map, START + L1 = previous (START alone = back to the map's start pose). HUD shows MAP n. -DAUTOTOUR: every map, 4 views (start point turned 90 degrees), 64 frames each, log line per view. Pad path of the switcher NOT exercised in the emulator (the tour calls the same load_map()).
## Result (all 11 maps load from CD, 0 CD errors, 0 primitive overflows, textures correct on every map; see the montage files in builds/ps1)
| map | tiles/pages | adaptive LOD: avg lines per view (v0..v3) | worst | fixed LOD 0 worst | fixed LOD 3 worst | max prims |
|---|---|---|---|---|---|---|
| 0 | 384/6 | 400 457 277 454 | 457 | 587 | 457 | 377 |
| 1 | 255/4 | 408 363 228 463 | 463 | 583 | 463 | 417 |
| 2 | 262/5 | 269 308 355 328 | 355 | 354 | 270 | 310 |
| 3 | 106/2 | 389 363 445 443 | 446 | 445 | 350 | 330 |
| 4 | 276/5 | 353 328 380 398 | 398 | 398 | 311 | 378 |
| 5 | 269/5 | 373 439 412 384 | 440 | 460 | 346 | 344 |
| 6 | 112/2 | 348 396 361 408 | 408 | 427 | 311 | 358 |
| 7 | 351/6 | 375 434 286 329 | 496 | 496 | 377 | 322 |
| 8 | 386/7 | 414 444 272 833 | 833 | 932 | 834 | 594 |
| 9 | 278/5 | 307 353 183 432 | 440 | 482 | 426 | 355 |
| 10 | 377/6 | 287 455 432 348 | 455 | 515 | 434 | 337 |
Views v0..v3 are the same start point, yaw +0/90/180/270 degrees from "toward the map centre", fly camera 403 units up, HUD on.
## Fails / over budget
- Map 8, view 3 (start point looking +z at a big red/blue textured wall close up): 833 lines at adaptive LOD (LOD 3), 749 in a static shot, 594 prims: runs at about 20 fps. LOD 3 is the cap, so it needs engine work (near-wall subdivision / many small quads), not a shorter view.
- Map 7 view 1: one frame group at 496 lines (adaptive, LOD 2) before LOD settles; fixed LOD 0 is over budget in maps 0, 1, 5, 7, 8, 10 in some views (as in stage 2b), LOD 3 holds 456 everywhere except map 0 v1 (457), map 1 v3 (463) and map 8 v3.
- Also open: several start points sit against a wall, so the start-view screenshots are close-ups; the loading frame is frozen, not a loading screen.
## Build
python3 -I tools/dumpworld.py --rom BUILT.gba --map N --out maps/worldN (N=0..10); python3 -I tools/mkps1world.py --all maps ELF ROM build/maps; ./build.sh TAG [-DAUTOTOUR -DSTATLOG -DMAP0=n -DFORCELOD=k]. ELF = the stuntfox-merge.elf of the same build as ROM (pb_* tables, sin_table). Needs the user's ROM; nothing derived from it is in this directory.

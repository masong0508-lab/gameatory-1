# Stage 5b: map 8 view 3 / maps 0,1,7 over budget: cause and fix (code-only; sf.c is maps11's with one change)
Emulator-only (PCSXR 1.9.94, HLE BIOS, GL plugin). 1 line = 1 emulator hblank line, budget 456 for 30 fps. No hardware.
## Cause
Not subdivision, overdraw or the clipper itself. proj() has a second tier for vertices more than 4600 units from the camera and rejects those beyond 18000 with
`((dx+18000)|(dy+18000)|(dz+18000)) >= 36000`. OR-ing offsets is only an exact range test for a power-of-two bound: valid vertices
(e.g. dy 6000, dz 14800) gave an OR above 36000, so they came back z=0 and the whole quad became Q_CLIP.
Map 8 v3: tall towers 12000 to 16000 units ahead whose side wall lies 512 units from the view line (graze) were treated as near walls (perpendicular distance < TEX_WALL_FAR) and every cell went
down the slow path (outside4, split to 1/4 cell, CPU clip, 3 to 5 triangles each): 80 clip calls, 69 clipped leaves, 4 boxes about 100 lines each (390 of 750 lines), 594 prims.
Profile by counters (city 612 lines, ground 125) and NOCLIP (750 -> 586) pointed there.
## Fix
Bound changed to 32768 (exact for the OR; GTE IR and 16-bit packing allow it). Nothing else: no view/reach/building change, textures unchanged. proj_range.patch.
## Result (adaptive LOD, avg/max lines per view v0..v3, 64 frames per view, first lap of the tour; before = maps11 table)
| map | before avg v0..v3 | after avg v0..v3 | after worst | max prims |
|---|---|---|---|---|
| 0 | 400 457 277 454 | 399 456 277 392 | 456 | 362 |
| 1 | 408 363 228 463 | 391 396 254 446 | 446 | 434 |
| 2 | 269 308 355 328 | 324 342 356 329 | 356 | 310 |
| 3 | 389 363 445 443 | 390 364 438 438 | 439 | 318 |
| 4 | 353 328 380 398 | 351 329 379 389 | 389 | 376 |
| 5 | 373 439 412 384 | 372 439 413 381 | 440 | 344 |
| 6 | 348 396 361 408 | 348 397 362 409 | 409 | 358 |
| 7 | 375 434 286 329 | 372 428 329 335 | 428 | 282 |
| 8 | 414 444 272 833 | 414 445 273 444 | 446 | 420 |
| 9 | 307 353 183 432 | 332 402 184 381 | 415 | 401 |
| 10 | 287 455 432 348 | 313 455 432 348 | 455 | 337 |
All 44 views at or under 456 (map 0 v1 456 exactly, so no margin there); 0 primitive overflows, 0 CD errors. Map 8 v3 now 30 fps, a previously dark/brown far building shows its real texture.
Caveat: lap 2 of the tour (LOD already settled) not re-measured cleanly (a stray earlier emulator run polluted that log); GPU fill time is not modelled by the emulator.
Build: as maps11 (build.sh TAG -DAUTOTOUR), with this sf.c. Discs in builds/ps1 (stage 5b names); screenshot ps1_stage5b_map8_view3_fixed.png.

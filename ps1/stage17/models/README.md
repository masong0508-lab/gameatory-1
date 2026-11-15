Stage 17 models: low-poly GTE models for the player, pedestrians, police and 8 vehicle classes. Code only, no Payback assets.
Against the stage 13 renderer: sf3.c.patch, rt.c.patch (diff -u), models.h (new, goes in sf/).
Build flags: -DMODELTOUR=3 -DMT_HOLD=40 -DMT_R=1000 (test tour, prints "MT scene ..."), -DOLDMODELS (old billboard/box baseline), -DFIXLOD=1 (pin world LOD).
Renderer fits the .sf region: text 81829 + bss 11940 = 93777 of 94208 bytes.
VRAM: texture page (960,256) 4bpp, v < 128; CLUT rows at x 960, y 448..481 (34 rows). Textures generated at map load.
Emulator-only. The tour disc contains the ROM: do not commit it.

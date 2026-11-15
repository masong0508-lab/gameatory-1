Stage 18 (agent B) models patch: code only, no Payback assets. Apply to stage17 sf/models.h (patch -p0 style, diff -u).
Slimmer wheels (hub quad + 12-unit tread top, was a 5-face 24-unit slab; radius 38->31, sport 28->25), far wheels only on the camera side, wider shade contrast (34..138 /128 was 50..122), MAXT0V 3->2, LOD distances 1000/2400 -> 800/1800, no shadow at lod 2.
Renderer still fits (disc builds; ld asserts pass). EMULATOR-ONLY (PCSXR HLE), MODELTOUR=3 tour, -DFIXLOD=1.
NOT done: items 1-3 (glow/logo, menu 3D models, BLDY fades), per-class cached display lists, proportion changes beyond wheels/shading.

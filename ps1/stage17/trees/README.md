# Stage 17 trees (PS1): Gouraud tiered firs, faceted broad trees, distance LOD (code only)

No Payback code, assets, ROM or audio here. EMULATOR-ONLY (PCSXR, HLE BIOS). Apply on top of the stage 13 tree (patch -p1):
- patches/sf_sf3_trees.patch: sf/sf3.c. Trees (kind 0/1) go through tree17(): Gouraud-shaded triangles (one carries four grass lights, lit upper left),
  firs are 3 tiers (near, z < 2600) / 2 (middle, < 4200) / 1 cone (far) with a ragged lower edge, broad trees a 10-gon fan with a ragged rim and leaf flecks (near) or a 6-gon fan (far),
  all submitted last-drawn-first into the same depth bucket (the OT is head-inserted), no extra textures or VRAM. Also the test-only sf3_treepose() (-DTREETEST).
- patches/ps1rt_rt_treetest.patch: rt.c, test-only -DTREETEST=n: after n renders, 6 fixed poses at Freedom City's park trees, 240 renders each, prints TREEPOSE lines.
- scripts/build17.sh NAME SF3SRC: builds the test disc (map 0 via the stage 13 ck0 pad plan). Before = stage 13 sf3.c plus the sf3_treepose hook only.
- lines_before.txt / lines_after.txt: renderer lines per frame (456 = 30 fps budget) at the 6 poses, 6th and last render: within 1% (610/611, 416/419, 322/323, 475/480, 221/224, 727/727 at render 6; 841 vs 843 at pose 5 in both).
Screenshots and the tour disc: builds/ps1 ("stage 17 trees").

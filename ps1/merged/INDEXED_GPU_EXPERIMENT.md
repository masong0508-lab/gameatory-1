# Experimental indexed GPU frame backend (B3)

**Not a release candidate.** Keep the software native B3 path as the default.
This work is an integrated hardware raster prototype, not the final sf3 city
renderer and not achievement of 30 FPS on stock hardware.

The producer keeps one palette index in each 16-bit VRAM pixel
(0x0100 | index), with two pages and a 64-tile cache. The opaque guest
palette is applied using three 8-bit textured quads into a decode scratch
surface, which is scaled onto the display; ordinary guest HUD composition
remains. This avoids full-frame GPU readback during normal city rendering.
Materialization before unsupported paths, pause and display-mode transitions
preserves a software fallback. Flight and rooms remain on the existing path.
Hardware integer rasterization and affine UV interpolation are not yet
pixel-identical to the original. Do not enable for ordinary releases.

VRAM halfword rectangles (x, y, w, h):
- Scene 0: 320, 0, 240, 160
- Scene 1: 320, 256, 240, 160
- Identity and shade CLUTs: 320, 160, 256, 4
- 64-tile 8-bit atlas: 576, 0, 128, 256
- Palette-decoded scene: 704, 0, 240, 160

They require exclusive ownership and the software city build (-DNOSF3);
the build rejects mismatched producer/runtime flags. Do not combine with
the existing sf3 world/model texture layout.

Private reproduction using the already-provisioned B3 source build workflow:
- Assemble using ps1/tools/prepare.py; verify 196 source files.
- SFNAT_PROFILE=b3 SFNAT_COMPACT_MATH=1 SFNAT_FASTSPAN=1
  SFNAT_GPU_FRAME=1 for native compilation.
- Re-run placement with the actual native section sizes, 40 expanded
  cache pages for this measured configuration and a matching 40-page
  private seed list. Never override the placement protection.
- Build the merged executable with -DMERGED_NATIVE -DNOSF3 -DB3_GPU_FRAME
  and the existing B3 cache, input and audio flags.
- Run the ordinary city route on both cores with stock clocks as well as
  the accelerated baseline. Record new native frame flips, not display
  refreshes; compare page mappings to the owner's private ROM locally.

Synthetic probe: ps1/qa/b3_indexed_probe.c uses the same compile/link and
private scratch carrier procedure as b3_gpu_probe.py. Compile this C file
instead of b3_gpu_probe.c, link with hello/crt0.s and hello/ps1.ld.
The eight-u32 results symbol begins with 0xb300beef on completion and
the second word must be zero. Both SwanStation and Beetle matched all
38,400 expected indexed pixels. This verifies palette conversion only.

## Measured city walking results

| Candidate | SwanStation stock | Beetle stock | SwanStation accelerated |
|---|---:|---:|---:|
| Stable native B3 (48 extra pages) | 4.096 | 2.448 | 19.830 |
| Initial GPU (44 extra pages) | 4.046 | stalled | 13.636 |
| FIFO synchronization fix (44 extra pages) | 3.946 | 2.148 | 14.585 |
| Wider-wall experiment (40 extra pages) | 3.347 | 2.248 | 14.336 |

The initial linked-list path stalled on Beetle. The command-boundary
submission fix and cache invalidations removed that stall; the second
candidate still failed the stock SwanStation pause-clock check once.
The final wider-wall candidate passed 12/12 city checks on each of the
three configurations, all sampled cache mappings matched, and materialized
indices had no invalid marker. It nevertheless regressed the FPS baseline.
No eight-column wall group met the conservative acceptance checks in the
measured routes; the grouping code consumed memory but did not save
primitives. Do not count it as an optimization. The final candidate
linked within RAM and passed 109,757 MIPS instruction words with zero
unsupported instructions. The 1,020-byte native data image was checked
against the private GBA initial data.

No release is approved: visual equivalence, physical console/Android,
all maps, flight, campaign and long-duration stability remain unverified
for this backend. Next work should move whole wall/floor polygon
generation to efficient native 3D geometry instead of making further
small changes to the existing hundreds of software-generated spans.
All game assets, ROMs, compiled executables, audio, generated translations,
screenshots and emulator binaries stay private.

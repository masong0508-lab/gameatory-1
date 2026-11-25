# Projective wall and transfer experiments

Not a release candidate. Stable software native B3 remains the default.
The optional indexed GPU backend now accepts convex clipped walls directly:
homogeneous near/far and horizontal tile-boundary clipping, triangulation,
and adaptive subdivision with a bounded affine texture error. A bounded
64-triangle budget rejects the plan before raster submission. Missing and
distant tiles retain the flat material color. Geometry, texture distance,
and gameplay are not intentionally reduced. Exact pixel parity is not
established: integer vertex rounding, affine interpolation and subdivision
can introduce seams or sampling differences. Floors still use spans.

Set SFNAT_GPU_FRAME=1 and SFNAT_PROJECTIVE_WALL=1 in the private native
build. SFNAT_GPU_BULK=1 is a separate **unaccepted** transfer experiment:
cached exact shade-palette bytes, minimal mip texture uploads, and request
mode DMA for primitive groups. Leave it off for accurate-core testing;
Beetle stalls at the first GPU frame in the tested bulk configuration.
The old software path and previous GPU backend remain selectable.
The compiler now discovers its own resource directory.

Local ROM-free tests: 500 randomized walls (460 accepted, 40 atomic
rejections, 270 subdivided, maximum doubled rounded pixel-area deviation
200 of 76800). Two planner tests and seven packed executable identity
tests pass. Rig ELF checks now compare PT_LOAD by load address rather than
runtime virtual address; all 50 file-backed load segments match for
each private candidate after decompression. The prepared source manifest
has 197 entries. Both candidates link within RAM with 44 extra cache
pages and match all 1020 initial data bytes. Projective 105404 and bulk
105729 instruction words checked, zero unsupported.

## Private city route measurements

Walking window: 1200 emulator frames with UP, preceded by 600 idle frames.
Stock settings use default core clock; accelerated SwanStation uses the
same recommended settings as the existing stable preview. Starting state
and warmup differ from previous baseline runs; use these as indicative
measurements, not a matched performance claim.

| Configuration | Stable B3 (previous test) | Projective | Projective + bulk |
|---|---:|---:|---:|
| SwanStation stock | 4.096 | 3.091 | 3.290 |
| Beetle stock | 2.448 | 2.847 | stalled |
| SwanStation accelerated | 19.830 | 14.904 | 18.892 |

Each completed route walked, turned, paused with a stable clock and
resumed. All mapped ROM pages compared byte-for-byte (projective 110,
108, 101 respectively; bulk 109, 108 on SwanStation). No invalid
palette indices, runtime fault or cache integrity error in completed
runs. Projective stock SwanStation accepted 447 walls, rejected none,
emitted 3057 triangles. Accelerated accepted 1209, rejected 3, emitted
19100 triangles. Bulk stock walking used 2 shade palette uploads and
118 cross-epoch exact palette hits. Bulk accelerated walking used 1
upload and 787 hits. GPU DMA stalls on Beetle (wait state 4, zero
gameplay clock advance through the idle, walk and turn windows). Its run
was stopped and is not counted as a pass. Neither candidate qualifies
as a replacement for stable B3; the 30 FPS stock target remains open.
Private disc/ROM data and images are not included here. No new release.
Further work: replace floor spans, reduce per-frame setup and guest
translation costs, and fix GPU transfer synchronization on accurate cores.

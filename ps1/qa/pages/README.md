# Original Payback PS1: ROM-data working sets by map and vehicle

**Project assignment:** `AGENTS.md` task 6. **Status:** profiler tooling and one
honest historical reference sample; **NOT** a completed 11-map/vehicle census.
Claude retains ownership of the PlayStation runtime and speed branches. All
new code here lives in `ps1/qa/pages/`, independent of those live files.

The aim is to help determine which original-8-MiB GBA cartridge **data pages**
need to live in the PlayStation's constrained resident RAM, in order to avoid
unnecessary CD seeks without reducing city geometry, texture quality or view
distance. The distinction matters: a data read of a ROM page is **not** an
instruction fetch, and the number of reads to a page is **not** the number of
CD cache misses. Temporal locality and the actual cache policy still need
to be measured on the disc.

## Current verified reference — only one map/route

`map00_reference_partial.json` records the 58 distinct 4 KiB page IDs and
326,470 data-read counts from the owner's **original** Track B `f1` level
trace (`touched_f1.pkl.rompages`), not from any private ROM bytes. It is
provenance-tagged with the trace's SHA-256 and can be reproduced by
`from_reference.py`. The boot-inclusive reference touches 99 distinct 4 KiB
pages, but they cannot all be attributed to a particular level and are not
provided as per-map scene samples.

- The single known level run started on map 0. **Controlled entity category was
  not independently recorded** by the historical script, so the published
  sample is explicitly `mode=unclassified` (not asserted to be on foot).
- This one trace covers only part of that level's run. It does **not** measure
  all 11 maps, every car/tank/bike/boat type, or all the loading transitions.
- The 58 original 4 KiB pages collapse to 30 different **16 KiB** groups.
  Group 213 receives the largest read weight on that one route; this is not a
  recommendation to pin it universally. The map coverage gate correctly
  reports maps 1–10 missing and no observed vehicle descriptors.
- No copyrighted game text, music, map geometry, ROM bytes, BIOS, translated
  guest instructions, emulator states, or screenshots have been committed.
  **Only page numbers, read counts and test tools** appear in this directory.

## Run a new instrumented Track B scene

This path needs a **private prepared PS1 source tree**, a matching privately
built `f1` simulator EXE/ISO/ELF and a local Unicorn runtime. It does not run
from the public repository alone. First use `ps1/rebuild/README.md` to
regenerate or reuse the private inputs, then run in the same toolchain:

```sh
# Outside the public Git checkout. The original 8 MiB ROM is required for
# classifying the currently controlled entity; it is NEVER published.
python3 ps1/qa/pages/sim_capture.py \
  --tree /private/ps1-prepared \
  --variant f1 \
  --rom /private/Payback-Europe.gba \
  --max-gba-frame 1500 \
  --output-dir /private/page-runs/scene1

# Convert the older Track B sample, if its private .rompages file is present:
python3 ps1/qa/pages/from_reference.py \
  /private/touched_f1.pkl.rompages \
  --map 0 --mode unclassified --phase combined \
  --output /private/page-runs/historical.json

# Inspect candidate resident 4 KiB pages and ranked 16 KiB groups without
# treating this as measured FPS or a successful 11-map census:
python3 ps1/qa/pages/working_set.py \
  /private/page-runs/scene1/map*.json \
  --budget4k 56 --require-11-maps \
  --require-mode foot --require-mode vehicle_007 --require-complete-matrix \
  --output /private/page-runs/cache-candidates.json
```

`working_set.py` returns **exit 3** if the mandatory `--require-11-maps` gate
is unmet, or if `--require-complete-matrix` is set and any required mode is
missing from any map. Replace `vehicle_007` in the example with every vehicle
descriptor that must be covered (repeat `--require-mode` for each).

Run a separate, actually executed scene for **each map and vehicle
class** and pass all of their capture JSON files to the analyzer. The profiler
classifies the selected entity as `foot` or an exact `vehicle_###` descriptor
index based on the running guest's RAM and the owner's original descriptor
table; it does not guess real-world vehicle names. An `unclassified` capture
never counts as evidence of on-foot or vehicle-type coverage.

### Coverage and accuracy limits

- The Unicorn hook is attached to the production guest ROM-read helper
  `h_memrd`, exactly as the established `t/snapdump.py` trace does. It counts
  **CPU data accesses**, including those to cached pages; a CD miss can serve
  many accesses. ROM-origin DMA or native/inlined reads may **not** be counted.
  Full game data-read coverage needs a native GBA bus-read hook or additional
  probes on its DMA paths. Do not infer a missing page is never accessed.
- The `pre_level` capture is the **last 30 `present()` intervals** before a
  newly running level. It may include the last menu and is a load-transition
  approximation, **not** a complete level-load census.
- Classification follows the runtime's observed map ID and controlled entity
  at each presented frame. A fast transition may lag that classification by
  one present; travel and vehicle shifts must be corroborated with private
  snapshots or guest state traces.
- The script does **not** magically navigate all maps or enter all vehicles.
  Claude must set up a test variant/route in the private simulator (or provide
  an mGBA input script with a proper read hook). Treat an unvisited map or
  unobserved `vehicle_###` as **missing**, never as a zero-read sample.
- The map ID from original game data is 0–10, and ROM data page indexing uses
  0–2047 4 KiB pages (`page = (guest_address & 0x01ffffff) >> 12`). For a
  16 KiB grouping, `group = page >> 2` (0–511). The **16 MiB merged GBA game**
  is a later port and is out of scope.
- Ranking treats each observed scene equally, rather than letting one long
  driving route drown out other maps. These are **read-frequency candidates**
  for testing, not optimized CD layouts or verified RAM budgets. The actual
  2 MiB PS1 memory map, renderer buffers, ragdolls and page cache still need
  explicit linker checks and before/after emulator measurements.

## Repeatability and tests

```sh
python3 -m unittest discover -s ps1/qa/pages -p 'test*.py' -v
```

The tests are ROM-free and cover mirrored addresses, 4 KiB page boundaries,
invalid counts, safe parsing of legacy primitive-only pickle dictionaries,
16 KiB aggregation, per-scene fairness, map coverage, descriptor-ID
classification and the rolling pre-level window. Arbitrary pickle globals,
constructors and non-primitive opcodes are rejected **before deserialization**.

### Requested private results for Claude's PS1 speed milestone

For **each map 0–10**: on-foot route, level start, each actually reachable
vehicle descriptor class, and several minutes of repeatable play. The private
collection report should identify duration, map/descriptor, and tool build
provenance, plus which ROM data-read paths were instrumented (CPU, DMA).
Only the **sanitized page IDs/counts** and aggregate coverage findings should
be attached to a GitHub PR. Use a separate internal/private store for frame
traces or any output that contains game content. Claude can then compare
candidate resident groups against a **measured real CD cache-miss timeline**
and performance (guest frames and presented pictures separately) before
changing the native renderer or cache behavior.
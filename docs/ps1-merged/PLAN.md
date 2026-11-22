# Milestone B design: merged Star-FlyBack on PlayStation 1

**Status: architecture proposal, not implementation or a playable-disc claim.**  
**Authoring baseline:** `claude/snes-mashup-umjsjp` at `fa521590bbe9dffdf6afea8e66a69c63c8177c7e`, 2026-11-22.  
**Ownership:** per [AGENTS.md](../../AGENTS.md) / [collaboration PR #2](https://github.com/masong0508-lab/gameatory-1/pull/2), Claude owns the original 8 MiB PS1 release (Milestone A) and all current PS1 runtime/speed branches. GPT-6 owns **design only** in this directory until Milestone A ships. No source, build manifest, linker, or protected asset should be changed on the strength of this document.

## Decision gate: what must be finished first

The **original 8 MiB Payback PS1 port** must reach accepted playability on DuckStation for Android, with usable controls, normal-speed menus and gameplay, memory-card saves, radio/audio, level changes, recoverable CD errors and measured screenshot/frame performance. SwanStation/Beetle are development evidence, not a substitute for the owner's Android result. Claude's rc7 and speed branches handle this; avoid backporting Milestone B into them mid-flight.

Only after Milestone A passes should a new PS1 branch start the **merged Star-FlyBack guest**, preserving the last good original-game ISO as a rollback baseline. Keeping the two scopes separate makes regressions attributable.

## Inputs and address-space expansion (first blocking design question)

The present PS1 build expects the **8 MiB** original European Payback ROM and refuses larger guests, deliberately. The merged builder [`stuntfox/build.py`](../../stuntfox/build.py) patches that game and adds its own code, eleven world datasets, station/campaign content and optional radio streams. The GBA linker puts new hooks/code at `0x081b0000`, and the relocation moves map columns above the original ROM boundary. This is **a new guest to translate**, not just the old disc with an extra data file.

| Guest cartridge image | Size | Distinct 4 KiB ROM pages | Nominal GBA address interval | Reason to support |
| --- | ---: | ---: | --- | --- |
| Original Payback (Milestone A) | 8,388,608 B | 2,048 | `0x08000000..0x087fffff` | Existing proven baseline |
| Merged build without expanded radio content | Verify exact output; commonly 16 MiB | 4,096 at 16 MiB | `0x08000000..0x08ffffff` | First Milestone B target |
| Merged build with optional remixes/edits | May be 32 MiB | 8,192 at 32 MiB | `0x08000000..0x09ffffff` | Later optional target, not assumed |

The builder has `ROM_SIZE = 0x2000000` for radio packaging; therefore **do not hard-code 16 MiB as the only possible merged image**. Inspect the actual generated image, its SHA-256 and the selected audio options. The private ROM, extracted maps, game text, BIOS, disc, saves and translated/disassembled guest bytes must never be committed.

### Known code-path limit

The current source [`ps1/stage19/ps1rt/rt.c`](../../ps1/stage19/ps1rt/rt.c) declares `rom_pg[2048]` and applies `pg &= 2047` in `rom_page`. A merged address at or above `0x08800000` therefore **aliases an unrelated page of the first 8 MiB** if the 8 MiB preflight were merely bypassed. This is a correctness blocker independent of performance. The runtime's `rom_read`, translated load paths, DMA `g2h`/copy, cold/interpreter fallback, resident-page builder, CD image layout and tests must agree on the same address translation before any merged image boots.

**Proposed safe interface, not code:** define the guest ROM span from a validated build manifest (8/16/32 MiB), compute a bounded 4 KiB page number with the documented GBA ROM mirror policy, and reject page indices outside the selected size. For the 16 MiB gate, prove page 0, page 2047, page 2048 and page 4095 each retrieve their *own* expected bytes, including a read that straddles pages 2047–2048. Check all load types and DMA source ranges. Extend to 8192 pages only after a 32 MiB audio build is available.

### Do not simply double pointer tables

The 8 MiB `rom_pg[2048]` pointer table is already **8 KiB on a 32-bit target**. A naive `rom_pg[4096]` would be **16 KiB (+8 KiB)**; extending it to 8,192 pages would be 32 KiB. The documented ROM-free native checks have had just a few KiB free in the runtime and renderer regions, and rc7/speed changes can alter those numbers. A table enlargement without a new measured RAM layout will overflow existing physical allocations.

**Candidate to benchmark after Milestone A:** a bounded page-to-frame mapping (`u8` or `u16` index plus empty sentinel) with frame descriptors holding PS1 RAM pointers, page ID, and CLOCK-use bit. For example, a 16 MiB `u8[4096]` map occupies 4 KiB instead of 16 KiB, but only works if the cache can represent all resident/slot frames and invalid entries without collisions. The old runtime's 62 resident pages plus slot count are *not* a guarantee for every level; measure the new working set. Check read latency on cache hits, cold-miss behavior, duplicate page ownership and hot loop speed before choosing this design. Do not add a per-byte table walk in the translated hot path without measurements.

## Guest translation and overlays

[`ps1/STATUS.md`](../../ps1/STATUS.md) documents the current hybrid execution path: translated guest functions, cold code overlays and an interpreter fallback. The merged game adds Thumb/ARM hooks, assembly trampolines and data tables that do not exist in the original 8 MiB translation. They need their own provenance and coverage data.

1. Freeze the owner's exact merged GBA ROM SHA-256 and build options (including GBA update commit and radio/Amiga options) in a **private** manifest. Regenerate the guest-function census, translation metadata, calls/veneer map, cold table, boot state, ROM pages, and source-side relocation manifest from that image. No stale original-ROM offsets are accepted as proof.
2. Enumerate original functions affected by the Stunt Fox injection and all code reachable from `sf_frame`, `sf_keyhook`, `sf_phys`, game settings, station, mission interpreter and save interceptors. Explicitly cover translated interworking and Thumb return-state semantics.
3. Treat new code and old Payback IWRAM overlays as separate lifetime classes. [`stuntfox/src/merge.ld`](../../stuntfox/src/merge.ld) documents `hot` through `hot11`, shared `keep`, `scr`/`scr2`, and music state; emulation must preserve their **guest-visible** read/write behavior, not just their addresses.
4. Add lockstep traces for boot, city load, phone/menu, vehicle enter/exit, Arwing summon, docking, station entry, EVA, campaign save/reload, pause and restart. Track guest register, flag, mode and memory differences at checkpoints. Label any synthetic test assist as such.
5. Only then determine which hook functions must be native PS1 code versus translated/emulated guest code. Do not shortcut the translation by silently omitting stations, physics or menus.

**Gate:** a guest trace never resolves an injected code address to an original guest page, unresolved cold loads have a documented fallback, and all guest-address boundaries are fuzzed across the 8 MiB seam. Full chip images and translated game code stay private.

## Physical PS1 RAM / VRAM / CD budgets

The PlayStation has a constrained **2 MiB main RAM** budget for this port, and the source reserves additional native renderer, game-state, scratch, cache and translation regions; validate against the actual assembled rc7/speed `ps1.ld` and symbols, not this proposal. Previous documented ROM-free checks occupied about 96 KiB of a 98 KiB runtime allocation and about 92 KiB of a 94 KiB renderer allocation, so capacity is a **blocking measurement**.

| Region/system | Required behavior | Acceptance check |
| --- | --- | --- |
| Guest EWRAM/IWRAM/palette/VRAM/OAM | Preserve Payback and Star-FlyBack guest address mappings and overlay lifetimes | Guest register/memory lockstep, no corruption after level and menu transitions |
| Runtime + translated hot/cold code | Fit physical linker regions without runtime data overwrites | Strict linked symbol bounds; test that overflowing each region fails the build |
| Page cache + renderer scratch | No overlap with guest heap, model data, decompression, PPU, and ragdoll regions | Reproduce release build's exact linker map and all conflict tests |
| PS1 VRAM textures / 2D page / 3D models | Keep textures on and draw every necessary surface; preserve GPU uploads across pages | Nonoverlap map, 4bpp/8bpp upload checks, native-resolution screenshots |
| World assets and stage/mission content | Load the correct world, mission tables and station content each time | Every one of eleven map slots plus station/space transitions |
| CD data/audio | Page read and CD-DA sequencing must coexist with minimal seeks and no corrupt resume | Trace page misses, track location, retry episodes, audio gaps and FPS by scene |

**Performance:** PS1 rc6's CD-bound normal route is documented at roughly 1.3 guest frames/s and ~0.1 presented pictures/s, with one 3D presentation per sixteen guest frames. Claude measured the virtual-clock polling, expensive cold dispatch and page misses and is solving them in **Milestone A**. Milestone B must reuse that faster engine and preserve responsiveness rather than layering more CD-bound guest calls on top. Always report **game-logic frames/s separately from presented pictures/s**. No strobing/flickering flashes; never hide textures, buildings or shorten draw range simply to inflate figures. Reduced-detail settings must be opt-in.

## Rendering and controls: scope beyond the original guest

Star-FlyBack adds presentation paths not covered by simply drawing Payback's streets:

- **City/driving:** the patched 3D world renderer, buildings and roofs, stair/ramp and deck occlusion, vehicle models (including police), pedestrians/ragdolls, correct car suspension/physics, collision feedback and HUD.
- **Arwing/space:** boarding/flight, rockets/lasers, particles, planet view, spacewalk EVA, the moon/rocks/beacons, shield, docking and the hangar's scene. Check the entire altitude transition, including bailout and reboarding.
- **Fox Station:** room geometry and cameras, crew/dialogue, mission/contract boards, shop/paint/medals, full-screen menus and the three-card finale. Mixed 2D HUD and native 3D scene must not overwrite each other or leave stale overlays.
- **Campaign:** 11 map slots, story missions/challenges, Ace/postgame, manual save, password fallback, purchases and spacewalk receipts. Check persistence through quit, power cycle, game over and partial save.

Map the 10-button GBA input semantics (A, B, D-pad, L, R, SELECT, START) explicitly onto PS1 digital and optional analog controls. Avoid collisions between Select-to-summon/dock, Payback phone playback, menu confirmation and pause; confirm what Cross/Circle do on the owner's DuckStation Android configuration. The final button sheet belongs to the actual build, not an untested proposed layout.

**Save format decision still required:** the GBA campaign has a versioned 260-byte `Prog` image and an extended 32-byte ship equipment image. The PS1 memory-card format for the original game is different from GBA EEPROM. Design a separate PS1-native container with checksum, version, slot handling and migration/power-loss recovery; **do not claim byte-compatible transfer or silently overwrite the original PS1 save**. Validate first save, update, reload, interrupted write and fallback before release.

**Audio:** separate original cartridge song control, optional radio remixes/edits and CD-DA stream layout. Respect the owner's explicit prohibition on song 3 anywhere in a build. Do not force a constant seek/resume loop between ROM-page reads and CD audio; test with music enabled and disabled. No copyrighted assets or disc images are stored in Git.

## Disc build pipeline (proposed Milestone B dependency chain)

Use Claude's finished Milestone A pipeline as the authority and reuse the private-input/rebuild work in `ps1/rebuild/` rather than writing another disc packager in this documentation branch:

```text
Owner's legal Payback source + selected Star-FlyBack source and optional Amiga data
  -> SHA-verified private GBA merged image and content manifest
  -> guest census/translation + boundary coverage + boot-state parity
  -> validated ROM pages, code overlays, world/mission/asset partitions
  -> MIPS-I runtime/native 2D/3D with strict 2 MiB allocation assertions
  -> deterministic two-pass sector placement + PS1 EXE/ISO + hashes
  -> SwanStation/Beetle regression -> DuckStation Android owner acceptance
```

Source-only CI must reject a missing private input early, never publish stale objects/ISO after a failed command, and never upload licensed game data or user saves. The current public `prepare.py --check`, `ps1/tests`, `check_native.py` and `mips1_lint.py` are mandatory starting gates; add Milestone B-specific 16 MiB boundary and dynamic-content tests without weakening them.

## Proposed release gates and responsibility

| Gate | Evidence | Owner |
| --- | --- | --- |
| A0: original 8 MiB PS1 accepted on DuckStation Android | Usable in-level play, verified controls, measured FPS, pause/restart/vehicle, audio and card saves | **Claude + owner**, Milestone A |
| B1: merged input identity | Exact private merged ROM hash, size and options; all inputs documented; no protected Git content | New Milestone B branch after A |
| B2: 16 MiB ROM/page identity | First/last and 8 MiB-seam pages and cross-page reads, CD fetch and cache eviction | Milestone B |
| B3: translated guest coverage | New hooks reachable with correct ARM/Thumb semantics; stable menu/intro/level locksteps | Milestone B |
| B4: memory and graphics | Physical 2 MiB linker/VRAM budgets, complete textured scene paths and no flash | Milestone B |
| B5: campaign and save | Station, Arwing, spacewalk, missions and native card save/read including power-cycle | Milestone B |
| B6: acceptance | All eleven maps, long soak, radio on/off, natural gameplay and DuckStation Android performance | **Claude + owner**, final signoff |

### Decisions to settle with Claude before code

1. Is the initial merged PS1 target exactly the **16 MiB no-remix ROM**, postponing optional 32 MiB audio? Confirm the SHA and whether Amiga map-derived data is supplied.
2. Which memory budget and cache algorithm survive rc7/speed wave 2, and how much RAM is truly available for 4096-page addressing?
3. How will the added Thumb code be translated or dispatched, and which Star-FlyBack renderer functions will be reimplemented as native PS1?
4. Where do the merged world/mission and station resources live on disc, and how will prefetch avoid starving CD-DA?
5. What save-container migration contract and controller layout should the user approve before implementation?

This document is a **handoff for future work**, not authorization to edit Claude-owned PS1 paths or to declare a playable merged PS1 build.

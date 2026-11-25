# ps1/merged: Stunt Fox compiled natively for the PS1 (Milestone B, stage B2)

Star-FlyBack is Payback with Stunt Fox (`stuntfox/`) linked into the ROM. Milestone B1 ran the whole merged ROM through the
translator, so Stunt Fox's C ran as translated or interpreted ARM. B2 compiles Stunt Fox's C for MIPS I instead and runs it
next to translated Payback. Payback code stays as it was. Nothing here contains Payback code or data, and nothing here is
generated from the ROM: the build reads guest addresses from the private GBA build of Stunt Fox (its ELF), never ROM bytes.
The generated files (`sfnat.o`, `sfnat_gen.c`, linker scripts) live only in the build directory.

## Pieces

| file | what it does |
|---|---|
| `include/gba.h` | It shadows Stunt Fox's `gba.h` for the native build. The registers and types stay the same. `IWRAM_CODE`, `HOT*` and `COLD` become plain functions. The scratch sections keep their names. |
| `libc/` | Freestanding `string.h`, `stdint.h` and `stdlib.h`. `memcpy` and its relatives become the guest-aware `__sf_` versions. |
| `natbuild.py` | It builds the native module: clang to LLVM IR per file, then `irmem.py`, then `pin.py`, then `llvm-link`, `opt` and MIPS-I code. It writes `sfnat.o` with every symbol prefixed `sfn_`, plus `sfnat_gen.c` (the guest-address to native entry table and the guest-call stubs) and `sfnat_syms.ld` (ROM symbols). |
| `irmem.py` | It gives the IR the GBA's memory semantics, as described below. |
| `pin.py` | It places every Stunt Fox variable at the host image of its GBA address. |
| `sfmem.c` | The helpers that `irmem.py` calls: loads, stores, copies, the function-pointer map, and `h2g`/`g2h`. |
| `sfport.c` | C ports of the ARM assembly that the C calls on hot paths: `fill.s`, `rechash.s` and `texrun.s` (the tile span loops). |
| `sfglue.h` | The runtime side, included by `interp_glue.h`. It covers guest to native (`sf_hle` in `ip_hle`), native to guest (`sf_guest_call`), the native stack, and the slow paths `sf_rd` and `sf_wr`. |
| `place.py` | It sets where native code goes in RAM and writes `ps1_native.ld` and `sfnat_place.h`. |
| `datacheck.py` | A build check run by `build.sh`: the `.data` image equals the GBA build's, the chooser call sites of `sf_pick_rand` stay interpreted. It prints the free bytes of R1. |
| `sf3stub.c` | An empty unit. sf3 and `doll.c` are not linked in B2. |

## Memory model

Translated Payback uses t2m model 'P'. Its registers and memory hold host addresses for guest RAM: EWRAM is at
`0x801b0000`, IWRAM at `0x801f0000`, PAL, OAM and VRAM at `0x80180000`. They hold guest addresses for ROM and IO. Payback's
RAM can also hold guest-form RAM pointers that come from its ROM tables.

For the native Stunt Fox module, `irmem.py` applies these rules:

- **Loads and stores.** An access whose address is provably host (an alloca, a native global, or a GEP of one) stays a
  plain access. Every other access calls `__sf_ld*` or `__sf_st*`. Those use the pointer directly when its value is at
  least `0x80000000`. Otherwise they go through `sf_rd`/`sf_wr`: the ROM page table, IO, or guest-form RAM.
- **Constant addresses.** A constant guest RAM address becomes its host address.
- **Pointer to number.** `ptrtoint` becomes `__sf_h2g`, so a pointer used as a number is a guest address. Stunt Fox
  compares and hashes pointers this way, for example `(u32)g < 0x02000000`. `inttoptr` becomes `__sf_g2h`. A pointer
  compared with a constant is compared in guest form.
- **Calls through pointers.** These go through `__sf_fnmap`. A native pointer is used as it is. A Stunt Fox function
  address is looked up in the entry table. Anything else becomes a guest call.

## Data

`pin.py` places Stunt Fox's variables at the host images of their GBA addresses. It matches each variable by file and
name in the GBA ELF's symbol table, including gcc's and clang's split statics. This has three effects:

- The interpreted assembly hooks (`keyhook.s`, `guard.s`, `cart32.s`, `radiodec.s`) see the same memory.
- Payback's pointers into Stunt Fox's data stay valid.
- The lockstep check with mGBA can compare variables by address.

`.data` keeps its GBA layout and its initial image, which `merge.c start()` copies as on the GBA at every level start. The image
holds every file's variables, also those of the files interpreted from the ROM (`settings.c`, `spacegame.c`, `spacewalk.c`,
`campaign.c` and others): `natbuild.py` takes the GBA build's `.data` bytes (`gba_data.bin`, build directory only), and `place.py`
fills from them every byte that no native variable covers. Without that, the start of a level set those variables to 0 (0 credits,
0 missiles, 0 shield, auto-aim off). `datacheck.py` fails the build if any byte of the linked image differs from the GBA build's. Read-only data that the
ROM holds at a unique GBA address is read from the ROM, not linked again. The exceptions are the renderer's per-pixel tables
(`erecip`, `sin_table`, `rtab`, `pb_avg`, `font_tiles`).

## Entry and exit

- **Guest to native.** The ROM's patches call Stunt Fox functions by their GBA addresses. Translated code reaches them
  through `RT_MISS`, then `h_miss`, then `interp_enter`. Interpreted code reaches them by its branch. Both paths end in
  `ip_hle`, where `sf_hle` checks the entry table. On a match it calls the native function with r0-r3 and twelve guest stack
  words, on the native stack.
- **What is excluded.** Stunt Fox's IWRAM functions (`0x03...`) are never entries. On the PS1 those addresses hold
  Payback's own IWRAM code, because `hot_install` copies nothing. `natbuild.py` keeps every function that the ROM patches
  or the interpreted assembly name (`@llvm.used`), so the guest never falls back to the GBA copy.
- **Return address.** `__builtin_return_address(0)` in native code is the guest lr of the entry (`sfglue.h`). That is a guest
  address only when the caller runs in the interpreter. Translated code passes a host return address. `merge.c sf_pick_rand`
  tells its two callers in Payback's chooser apart this way. Their call sites (0x0803cf6a and 0x0803cf74) lie in cold group 43,
  above `SF_NAT_LO`, so they are interpreted. `datacheck.py` fails the build if a layout change makes them translated.
- **Native to guest.** `sf_guest_call` calls the translated entry if there is one, otherwise the interpreter. A call into
  Stunt Fox's assembly (`pb_music`, `radio_seg`) goes through a generated stub.

## Build

`tools12/build_msb.sh NAME -DMERGED_NATIVE` with `SFNAT=<natbuild output>` set. `build.sh` then links `sfnat.o`,
`sfnat_gen.o` and `sf3stub.o` with `ps1_native.ld` in place of sf3 and `doll.c`. Without `SFNAT`, the B1 build is unchanged.

## Runtime modes in a level

Without sf3, `sf3_ok` stays 0. Under `-DMERGED_NATIVE`, `rt.c` therefore keys its level-time modes on `nat_lvl` instead. `nat_lvl` is
set when the level clock advances between two pictures while the entity table is there. It is cleared when the guest leaves the
level: the entity count is -1 and the clock stands still for three pictures. The modes are the one ROM page pool (`rom_pool`), the
arming of the pause block, presents at Payback's limiter, and the 100 ms fallback. A new picture is a page flip (DISPCNT bit 4). The
slow path (`h_memrd`/`h_memwr`) takes a host address only inside native Stunt Fox's regions and the guest RAM images. It refuses any
other host address and counts it in `nat_wild_n`, with a `BADRD host` or `BADWR host` line on the TTY.

## B3 phase 1: native gameplay hot-set and linked RAM census

B3's working candidate defaults to `SFNAT_PROFILE=b3`. For a private
controlled comparison, set `SFNAT_PROFILE=b2` to restore the old native file
and constant selection. Both use the same original GBA build and 2 MiB PS1
link constraints. The B3 candidate adds native `marker.c`, `loops.c`,
`hudline.c` (the existing portable C implementation), and `settings.c`:
these run during city gameplay, HUD and options interaction instead of going
through interpreted guest code and CD-backed instruction reads. Small immutable
palette/mesh and gameplay setting tables stay in native read-only storage.
The remaining model/mission/space/station code and large generated tables
continue using their current paths until scene-specific measured sizes and
coverage justify moving them. No new framebuffers or changed geometry.

```sh
SFNAT_PROFILE=b3 python3 ps1/merged/natbuild.py /private/stuntfox /private/gba-build /private/b3-native
```

Use the existing private place/build scripts with that output. `natbuild.py`
records `b3_native_census.json` (native files, retained tables, section sizes
and dispatch entries). The placer includes section alignment, literal data,
both dispatch tables, and the actual GBA .data image length in its estimate;
it records `b3_placement_census.json`. `datacheck.py` writes the actual linked
runtime, cold runtime, R1/R2/R3 used/free byte counts and native stack bounds to
`b3_linked_ram_census.json`, and still fails on .data mismatches. These numeric
reports remain in the private output directory. Do not commit any generated
code, symbol listings, ROM-derived tables or assets.

This is an **unmeasured B3 candidate**. The previous B2 private measurements
were 15–21 physical ROM page misses per tick at stock and about 0.5 ticks/s.
Repeat the exact B2/B3 pad tour at stock and recommended settings and compare
physical ROM misses/tick, guest ticks/s, changed pictures/s, input latency,
stack/region headroom, and identical gameplay/HUD/save behavior. The goal is
less than one miss per tick at stock; do not mark it achieved from a build or
from the native table list. The sf3 city backend and scene-aware residency
remain separate subsequent B3 changes. Revert to the B2 profile for diagnosis
if the candidate fails; never weaken physical RAM guards.

## B3 phase 2: optional compressed ROM working set

An independently measured private B2 experiment used the existing 69-frame
pool, a 56-page preferred set, and 30 independently compressed pages
(20,913 B including their index entries). SwanStation at 400% CPU/10x/instant
seek, identical controller windows: original B2 walk 18.44 ticks/s, 3.69
flips/s, 20.89 physical misses/tick; preferred CLOCK 26.42 ticks/s, 5.38
flips/s, 12.93 misses/tick; compressed experiment 31.70 ticks/s, 7.28
flips/s, 7.06 misses/tick. Idle and camera samples improved too. Every valid
page frame matched the private ROM at each sample end; zero decode errors
or runtime faults. Stock walking still failed to move within 1,800 frames
(0.50 -> 0.83 ticks/s), and the <1 miss/tick target remains open.
These are private B2 binary experiments with the bank preloaded by the
rig, not measurements of a linked B3 release or its loading time.

This source implementation is optional and uses no fixed experimental
addresses. Generate a private cache from an exact merged ROM and fresh
physical-miss scene profile (see `../msb/residency.py`; add the
`rom_sha256` field containing the exact ROM digest):

```sh
python3 ps1/merged/b3_cache_pack.py --rom /private/sfb_merged.gba \
  --profile /private/b3-physical.json --out /private/b3-cache \
  --r1-bytes 8192 --r3-bytes 6144 --rt-bytes 2048 --hot 56
export B3CACHE_DIR=/private/b3-cache
# Run natbuild.py, place.py, then the existing merged-native build recipe.
```

The dependency-free packer verifies every encoded page against its source,
ranks by scene-normalized misses per stored byte, and excludes packed pages
from the preferred set. Generated headers and cache metadata stay private.
The placer charges the exact R1/R3 payload plus alignment, and the normal
physical linker assertions also cover the runtime payload, index, mask
and decode code. If it does not fit, reduce budgets and regenerate; do not
move guest windows or weaken the 2 MiB guards. The build verifies the ROM
hash, generated header hash and matching placement sizes. Unset
`B3CACHE_DIR` for the previous runtime. Original Payback builds do not
enable this path.

Only an active native level uses the preferred CLOCK/packed restore;
pause-block loading, menus and ordinary CD fallback are unchanged.
A malformed block is discarded and fully reread before a mapping is
published. `b3_cache_hits` and `b3_cache_errors` are separate from
physical CD request counts. Validate the linked candidate against B2
and B3-without-cache, all scene transitions, pause, save, both accurate
cores, frame pacing and flicker. The native city GPU backend remains
unfinished; the software-renderer page-flip rates above are not 30 FPS.

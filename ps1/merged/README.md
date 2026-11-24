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

`.data` keeps its GBA layout and its initial image, which `merge.c start()` copies as on the GBA. Read-only data that the
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
- **Native to guest.** `sf_guest_call` calls the translated entry if there is one, otherwise the interpreter. A call into
  Stunt Fox's assembly (`pb_music`, `radio_seg`) goes through a generated stub.

## Build

`tools12/build_msb.sh NAME -DMERGED_NATIVE` with `SFNAT=<natbuild output>` set. `build.sh` then links `sfnat.o`,
`sfnat_gen.o` and `sf3stub.o` with `ps1_native.ld` in place of sf3 and `doll.c`. Without `SFNAT`, the B1 build is unchanged.

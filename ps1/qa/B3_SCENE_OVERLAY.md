# B3 flight/station shared code slot

This is the first executable overlay subsystem, not a completed city renderer.
The supplied private B2 ELF contains a 396,448-byte boot image ending at
0x800a80d0; its translated blob ends at 0x80047430. A 136 KiB scene slot
[0x800ab800,0x800cd800) lies below the 234 KiB city world window.
The slot intersects cold groups 25 through 33. Reserving it permanently
changes the maximum prefix of translated cold groups from 41 to 25,
ceiling 0x800ab430; 16 additional groups must use interpretation.
This trades native cold-code coverage for RAM, and needs a gameplay profile.
It is not 136 KiB of extra physical RAM, and the current native code and
GPU world/list conflicts still need relocation.

The loader's resident controller may switch only from the outer dispatcher,
after native call depth and outstanding leases are zero. Its synchronous
claim callback must drain prior GPU/CD DMA and invalidate any dispatch
entries for the slot without touching the displayed buffer. Keep writable
variables in resident guest RAM. Never export or cache raw overlay function
pointers: acquire by scene and entry ID, call synchronously, release after
return. Direct calls between routines within one overlay are fine; calls
across scenes must go through the resident dispatcher. On bad header the
old scene remains; on payload/CRC/sync failure the slot is unavailable until
reloaded. No partially loaded instructions execute.

The fixed-address SOV1 packer accepts only linked, nonwritable allocated
sections within the exact slot, with a global executable symbol for each
entry ID. It emits a 2 KiB validated header and padded image sectors.
CRC32 covers the complete entry header and payload (integrity checking,
not cryptographic authentication). Do not publish generated overlays, ELFs
or data; they may contain ROM-derived code/assets. Do not discard writable
sections to make a real overlay appear to fit.

## ROM-free and private executable probe

The exact production `scene_overlay.h`, `scene_overlay.py`, and
`b3_scene_overlay_probe.c` were tested with synthetic MIPS-I code:
```c
/* flight.c */
int scene_tick(int credits){ return credits+17; }
int scene_aux(int v){ return v*3; }
/* station.c: separate compilation */
int scene_tick(int credits){ return credits-9; }
int scene_aux(int v){ return v*5; }
```
Link each at 0x800ab800 using Clang/LLD for MIPS I (no GP/PIC, no delay-slot
filler), with .text/.rodata only. Check real writable sections, no unresolved
references, and run the MIPS-I lint. For the synthetic fixture only, empty
compiler metadata/GOT/data sections can be discarded. Pack with:
```sh
python3 ps1/merged/scene_overlay.py --elf /private/flight.elf --out /private/flight.ovl \
  --scene 1 --address 0x800ab800 --capacity 0x22000 --entry 1:scene_tick --entry 2:scene_aux
python3 ps1/merged/scene_overlay.py --elf /private/station.elf --out /private/station.ovl \
  --scene 2 --address 0x800ab800 --capacity 0x22000 --entry 1:scene_tick --entry 2:scene_aux
```
Each synthetic image is two sectors. Include those files via assembly
`.incbin` as `flight_blob` and `station_blob`, link the probe with
`ps1/hello/crt0.s` and `ps1/hello/ps1.ld`, and boot in a private
scratch QA carrier with a synthetic replacement EXE. Read the 20 words
at symbol `results`. The probe copies synthetic sectors through the
same production loader API, then actually calls the MIPS code at the
shared address and invokes the BIOS FlushCache service. It does not
measure real CD loading latency or execute the game.
Expected first 19 words:
```
b30f1a9e 1 1 117 21 1 1 1 1 1 91 35 1 117 4 9 4 3 1
```
First word hex, remaining decimal. Both SwanStation and Beetle at
stock matched every result in independent local runs. Guard bytes were
intact, the stale tail cleared, bad header preserved flight, bad payload
invalidated it, and reloading station then flight executed the correct
instructions. The three successful scene loads performed three instruction
cache flushes. The source-only tests cover additional read/claim/sync
failure paths, aliasing scratch, and packer rejects.

Use `scene_layout.py --elf ... --native-lo ...` to compute the candidate
slot and cold-code boundary. The optional `B3_SCENE_LO` runtime reservation
limits cold_all, cold_find, the translated cell fix, and permanent
dispatch linking from startup. Existing B2 uses the unchanged SF_NAT_LO
limit; original rc10 is unchanged. The public disc build rejects the
experimental flag until an actual scene-aware linker, dispatcher and CD
file integration have passed the GPU layout check. Remaining: partition
native flight/station modules with resident imports, place native core
outside the world/list windows, connect actual sector read/claim/sync
callbacks, preserve current frame during transitions, and run the full
tour at stock and recommended settings.

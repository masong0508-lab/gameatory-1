# Payback PS1 port, stage 2: pruned logic on the PS1 GPU, CD streaming, overlay loader
Run: ../run_pcsxr.sh out/payback.iso shot.png 60   (PCSXR, HLE BIOS, xvfb).  Build: ps1rt/build.sh (needs ROM, local only).
## Status
- The "stall at tick 155" was not a hang. The guest was in a palette-fade loop that polls VCOUNT (about 224 R3000 insns per read via
  RT_CC/C helper); HUD updated only from the vblank stub, so it looked frozen. Proof: write log of ps1sim == ARM reference for all 5125
  writes up to that point and read-address trace == unicorn lockstep for 268K reads; ticks keep rising (io_nd 170 -> 413 in 1.5G insns).
  Fix: the C IO model presents a frame whenever VCOUNT crosses 160 (every 16th crossing is drawn). HUD now counts guest frames.
- PCSXR, production ISO (10 min wall): guest tick 155 -> 1127, guest frames 62864, presents 4015, drawlist 4553, no RT_MISS, no halt
  (ps1_tick1127_final.png). Early phase is slow (a palette fade: about 1 tick per 65 frames), later ticks come faster.
  PCSXR runs about 150 GBA frames per second wall clock early on (about 7.5 MIPS emulated R3000, 2-cycle BIAS).
  Unicorn PS1 sim (real payback.exe): 413 ticks in 1.5G insns, no RT_MISS.
## Pruned
5 stubs (fade_flip 0x0806c82c, blit_image 0x08028ac4, effect 0x080234be, blit_image_m4 0x08028c08, view3d 0x03000580) record (id,r0..r3)
into a 256-entry ring. Static translation 226K insns; hot blob 5.9K insns (80 KB); cold overlay 85K insns (952 KB, 389 groups).
## Lockstep (ARM reference vs MIPS translation, unicorn), pruned + overlay build
400 ticks: io log 6054/6054, draw list 3825/3825, EWRAM/IWRAM/PAL/VRAM/OAM snapshots 0 diffs. Overlay stress split (half of the hot
functions moved to overlay): 400 ticks, 8971 RT_MISS calls, 2 overlay loads, 0 mismatches (found+fixed: function fall-through
=> functions merged into placement groups; lr-constant returns into overlay code => dynamic path).
## RAM layout (PS1)
C runtime 0x80010000-0x80028000; helper table 0x80028000; hot blob 0x80030000; overlay pool 0x80043xxx-0x80131b04 (16 KiB groups, fixed
home addresses, boot image area reused after start); ROM page cache 0x80138000 (64 x 4 KiB, FIFO, 16 KiB clusters); draw ring 0x8017c000;
IO shadow 0x8017f000; PAL 0x80180000; OAM 0x80180400; VRAM 0x80181000; EWRAM 0x801b0000; IWRAM 0x801f0000; RT_CC stack 0x801fff90; C sp 0x801fd000.
## Disc layout (genisoimage, 2048 B sectors): PSX.EXE (915 KB: C rt, hot blob, boot image, 73 pre-seeded ROM pages, overlay table), ROM.BIN (8 MB
GBA ROM, pages fetched on a ROM-page miss), COLD.BIN (952 KB overlay code). LBAs are patched into the EXE (two-pass build).
## CD streaming (polling driver, 1F801800.., IRQ masked): Setmode 0x80, Setloc, ReadN, 8 sectors per miss, Pause. In PCSXR: overlay
test (38 cold groups) loaded 2 groups = 16 sectors with 3393 RT_MISS calls; ROM page loads in the 73-page working set: 0 (not exercised
by the scripted path; the stream-only build, no pre-seeded pages, works but each miss takes about 1 s in PCSXR: seek dominated).
## Draw
HUD + per-blit boxes (last 64 draw calls, fading by age, position/size from the call + ROM image descriptor) + the game's PAL as a 16x16
swatch grid + EWRAM frame variable. Shots: ps1_tick1127_final.png, ps1_tick240.png, ps1_overlay_test_tick230.png (overlay stress ISO). The GL plugin sometimes
shows a half-drawn frame in a screenshot (identical stripes-only frames), so run_long.sh takes 5 shots; a VRAM-to-VRAM copy did not work in it.
## CPU load, 33.8 MHz R3000 (unicorn counts + PCSXR root counter)
About 102K R3000 insns per guest frame (median 102.8K, max 345K), incl. VCOUNT busy-wait and helper overhead: about 36 percent of a
60 Hz frame at 2 cycles/insn (PCSXR BIAS); PCSXR root-counter measure 126 hblank lines per guest frame (48 percent, includes HUD drawing).
Overlay test split: 191K insns/frame (RT_MISS binary search on every cold call; a hot-path cache would remove it).
## Not done / blockers
- Cold code that is not in the 3000-tick coverage was never executed on the production ISO (0 overlay loads).
- Overlay eviction (pool is fixed-home, no replacement); I-cache flush uses BIOS A0:44, untested on hardware.
- ROM fast path in RT_MEMRD still disabled (failed on PS1 for an unknown reason); VCOUNT read costs 224 insns.
- Unaligned guest accesses, EEPROM persistence, mixer/IWRAM generated code, real BIOS/DuckStation/hardware, GTE, SPU, real pad: untested.

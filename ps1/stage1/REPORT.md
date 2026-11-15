# PS1 port, stage 1: Thumb/ARM -> MIPS-I static translator (t2m) + lockstep verification

Scope: whole Payback ROM (Thumb 219,839 insns + ARM 6,851 insns in ROM and the 27.5 KB IWRAM image) translated to R3000 code, GTE untouched.
All numbers below come from `payback_B` build (memory model B) on unicorn-ARM vs unicorn-MIPS; ROM/translated output stay in scratchpad only.

## What exists (tools in /mnt/project-files/stunt-fox/ps1/stage1/, code only)
- armdec.py (own Thumb/ARM decoder), disc.py (code discovery), semantics.py, mips.py (encoder, assembler, hazard pass, linker), t2m.py (translator),
  gbaenv.py (GBA stub: I/O log, DMA3 immediate, keypad, VCOUNT/DISPSTAT/timers), unitfuzz.py, lockstep.py, fuzzfn.py, wtrace.py, profile.py.
- Translator features: reg map r0-r7 $16-23, r8-r12 $11-15, sp $30, lr $31; explicit NZCV $4-7 plus lazy flags fused into branches (liveness over CFG);
  global constant propagation/folding; load-delay-safe (hazard pass, 0 violations after link); ldm/stm, mul/mull/swp, hi-reg forms, conditional execution;
  host-pointer memory model (EWRAM/IWRAM/IO/PAL/OAM/VRAM/SRAM windows, sp-relative and known-region fast paths); bx/mov pc via hash lookup RT_BX
  (1018 indirect sites found, 67 jump tables resolved at translate time); `bx pc` ARM/Thumb veneers resolved statically; unresolved target traps at RT_MISS,
  swi at RT_SWI (only 1 swi site in the whole ROM); RAM-resident code template (see below) aliased to its translated ROM copy.

## Translated size
- 226,690 guest insns -> 335,753 MIPS words = 1,343,012 B (1,247 KB code + 64.5 KB hash table of 2,907 lookup entries); 1.48 words/insn static
  (10,418 hazard nops, 40,556 insns constant-folded, 14,853 conditional branches with fused flags). Does not fit 2 MB RAM next to the engine as-is: needs
  code overlays or pruning (coverage of the whole ROM by the scenes run so far was not measured).

## Verification results
1. Instruction level (unitfuzz, random ARM+Thumb snippets, regs/NZCV/memory): 6,973 executed, 1 mismatch (pointer-valued random ldr result, test artifact), 971 skipped (ARM faults).
2. Whole boot lockstep (lockstep.py; sync at every DISPCNT write; compared: full I/O write sequence incl. DMA3 programming, EWRAM/IWRAM/PAL/VRAM/OAM images with host pointers normalised):
   3,000 sync points with scripted pad input (idle/START/A/DOWN+A), 14,044 I/O writes, 467.9M ARM insns vs 962.4M MIPS insns: **0 I/O mismatches, 0 RAM word mismatches**
   (64 full snapshots, plus first 4 syncs). Same result without input. The game does not reach VBlankIntrWait; it busy-waits on VCOUNT/DISPSTAT.
3. Function-level differential fuzz (fuzzfn.py; 2,106 function entries x 8 trials from the live boot state, same random args/stack on both sides):
   3,771 executed trials: 3,586 identical (95.1%); 185 differ: 33 with integer-only args (14 functions), 152 with RAM-pointer args. Skipped: 9,856 ARM-side faults/wild pointers,
   2,940 ARM timeouts, 273 unaligned accesses (ARM rotate semantics not implemented), 8 trials into RT_MISS. Causes of the remaining differences, from traces:
   a) constant ambiguity of model B: a folded constant that equals a region base (e.g. `movs r5,#0xc0; lsls r2,r5,#18` = 0x03000000 used as an INTEGER in a compare) is mapped to a host
   pointer; seen in 0x802d27c, 0x802d514 and similar. b) pointer arithmetic on random pointer args (shifts of pointers, base+oversize index) in the pointer trials.
   c) runtime-generated ARM code in IWRAM (0x800adac family writes instruction words 0xe4d3xxxx with patched offsets and runs them): not translatable statically.
   Fixed during this work: IWRAM code-pointer vs data ambiguity (RT_BX now accepts host IWRAM window), `bx pc` veneers, adr-style `sub rd,pc,#imm`, volatile pc-relative
   literal slots (self-modifying data in the template), ROM-resident template needing a RAM-copy alias.

## Profile (profile.py, boot + mode-3 renderer scene, per "step" = one DISPCNT write = 155,968 ARM insns, about 1.7 GBA frames of ARM time)
- MIPS 320,789 insns/step = 2.06x ARM dynamic expansion (static 1.48x; loops dominated by shifted/flag-heavy ARM ops).
- Share of MIPS insns: software span renderer template (RAM-code copy of ROM 0x0806c294) 77.1%, IWRAM blit loop 0x03005eb8 12.4%, renderer driver 0x0806c82c 6.3%
  => renderer/engine-equivalent = 95.8%; Payback game logic (ROM code + runtime lib + other) = 4.2% (13.4k MIPS insns/step).
- R3000 @33.8688 MHz: all 320.8k insns/step = 9.5 ms at CPI 1.0 (57% of a 60 Hz frame), 14.2 ms at CPI 1.5. Logic alone = 0.40 ms/step (CPI 1.0).
  I-cache (4 KB) misses of the 1.3 MB code are not modelled; the renderer loop body is ~1 KB so it would cache, game logic would not.

## What is unsupported / approximated
- Runtime-generated or runtime-copied ARM code: only the one known copy template (memcpy at 0x0807c808 -> alias table ALIAS0, RT_BX maps host IWRAM address back); generated code (0x800adac) traps nowhere, it silently misses (RT_MISS returns): needs an ARM interpreter fallback or per-site templates.
- Unaligned LDR/STR/LDM rotate semantics, SWP byte ops on odd addresses, BIOS calls (1 site), IRQ delivery (not needed to boot), timers beyond a counter stub, DMA beyond immediate transfers.
- 92 locations that decode as undefined/garbage during discovery are dropped (data in code regions); GTE not touched.

## Next-stage blockers
1. Constant typing (pointer vs integer) for folded region-valued constants; either a small type inference (reaches address operand => pointer) or switch to base+offset addressing.
2. Runtime-generated code (find all sites: stores of 0xe4xxxxxx/0xe5xxxxxx words to RAM) and ARM interpreter fallback.
3. 1.3 MB code vs 2 MB PS1 RAM: overlays/dead-code pruning; I-cache behaviour of translated logic; replace renderer (96% of cycles) by our engine as planned.
4. RT_MISS/RT_SWI must become real handlers; unaligned access policy; IRQ/VBlank wait emulation for the real main loop (boot only exercised the intro/fade path).

## Not tested
Real PS1 hardware/emulator execution (all on unicorn-MIPS with flat kseg0 windows); interrupts; a run into actual gameplay (scripted pad only reached the scenes reachable by START/A/DOWN in 3,000 steps);
SRAM/EEPROM saving (stubbed as constant 1 bits); 16-bit/32-bit timer behaviour; sound registers (log only).

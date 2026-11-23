ENTRY(_start)
SECTIONS{ . = 0x80010000;
 .text : { *(.text.start) *(.text*) *(.rodata*) *(.data*) *(.sdata*) }
 . = ALIGN(4); __bss_start = .; .bss : { *(.bss*) *(.sbss*) *(COMMON) } __bss_end = .;
 ASSERT(. < 0x80028000, "C runtime overlaps the helper table at 0x80028000")
 /* rc8: the dispatch tables of speed wave 1 (D1 dsp_mcache 4 KB, D2 dsp_lq 1 KB) are BSS arrays inside this bound; wave 1 had them at 0x80028400,
    which .rtcold fills. */
 /* rc7: one-time and fault-only runtime code (RTCOLD in rt.c and interp_glue.h) in the RAM between the helper table (0x80028000..0x80028010, t2m cfg.HELP)
    and 0x8002a000 (t2m cfg.ROMPG, the D3 ROM page table rom_pg, 0x8002a000..0x8002c000; the interpreter stacks start at 0x8002c000): nothing else uses it.  It is
    part of the EXE image, so the BIOS loads it and flushes the cache with the rest of the program before main runs. */
 . = 0x80028040; __rtcold_start = .; .rtcold : { *(.rtcold.text*) *(.rtcold.rodata*) *(.rtcold.data*) } __rtcold_end = .;
 ASSERT(__rtcold_start >= 0x80028010, "cold runtime code overlaps the helper table")
 ASSERT(__rtcold_end <= 0x8002a000, "cold runtime code overlaps the ROM page-table area at 0x8002a000")
 . = 0x80030000; .blob : { *(.blob) }
 . = ALIGN(16); .bootimg : { *(.bootimg) }
 ASSERT(. <= 0x8011c000, "translated blob or boot image overlaps the cold table at 0x8011c000")
 . = 0x8011c000; .coldtab : { *(.coldtab) }
 . = ALIGN(16); .rompack : { *(.rompack) }
 ASSERT(. <= __ps1_pcache_start, "resident ROM pages overlap the page cache")
 /* the city renderer (stage 3; its sections carry the .sf prefix) sits above the guest VRAM shadow, in space nothing else uses */
 /* stage 7: the ragdoll solver (rd/doll.c, sections prefixed .dl) sits in the page-cache space that stage 7 gave up (NSLOT 16): __doll_addr from the build */
 . = DEFINED(__doll_addr) ? __doll_addr : 0x80163000; __doll_start = .; .doll : { *(.dl.text*) *(.dl.rodata*) *(.dl.data*) *(.dl.sdata*) }
 . = ALIGN(16); __dlbss_start = .; .dlbss : { *(.dl.bss*) *(.dl.sbss*) } __dlbss_end = .;
 ASSERT(__ps1_pcache_end <= __doll_start, "ROM page cache overlaps ragdoll code")
 ASSERT(. <= 0x8017a000, "ragdoll code overlaps PPU scratch")
 /* PPU palette/row storage and cold-veneer scratch are explicit allocations.
    The old fixed 0x801abc00 area is occupied by the stage17/18 renderer. */
 . = 0x8017a000; .ppuscratch (NOLOAD) : {
   __ppu_start = .; . += 0x1000;
   __veneer_scratch = .; . += 0x1000;
 }
 ASSERT(. == 0x8017c000, "PPU scratch overlaps the draw ring")
 . = 0x80199000; .sf : { *(.sf.text*) *(.sf.rodata*) *(.sf.data*) *(.sf.sdata*) *(.sfro) }
 . = ALIGN(16); __sfbss_start = .; .sfbss : { *(.sf.bss*) *(.sf.sbss*) } __sfbss_end = .;
 ASSERT(. < 0x801b0000, "renderer overlaps guest EWRAM")
 /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.gnu.attributes) *(.pdr) *(.comment) *(.mdebug*) }
}

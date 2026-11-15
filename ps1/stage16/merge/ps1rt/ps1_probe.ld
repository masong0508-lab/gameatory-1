ENTRY(_start)
SECTIONS{ . = 0x80010000;
 .text : { *(.text.start) *(.text*) *(.rodata*) *(.data*) *(.sdata*) }
 . = ALIGN(4); __bss_start = .; .bss : { *(.bss*) *(.sbss*) *(COMMON) } __bss_end = .;
 
 . = 0x80030000; .blob : { *(.blob) }
 . = ALIGN(16); .bootimg : { *(.bootimg) }
 . = 0x8011c000; .coldtab : { *(.coldtab) }
 . = ALIGN(16); .rompack : { *(.rompack) }
 /* the city renderer (stage 3; its sections carry the .sf prefix) sits above the guest VRAM shadow, in space nothing else uses */
 /* stage 7: the ragdoll solver (rd/doll.c, sections prefixed .dl) sits in the page-cache space that stage 7 gave up (NSLOT 16): __doll_addr from the build */
 . = DEFINED(__doll_addr) ? __doll_addr : 0x80163000; .doll : { *(.dl.text*) *(.dl.rodata*) *(.dl.data*) *(.dl.sdata*) }
 . = ALIGN(16); __dlbss_start = .; .dlbss : { *(.dl.bss*) *(.dl.sbss*) } __dlbss_end = .;
 ASSERT(. < 0x8017c000, "ragdoll code overlaps the draw ring")
 . = 0x80199000; .sf : { *(.sf.text*) *(.sf.rodata*) *(.sf.data*) *(.sf.sdata*) *(.sfro) }
 . = ALIGN(16); __sfbss_start = .; .sfbss : { *(.sf.bss*) *(.sf.sbss*) } __sfbss_end = .;
 ASSERT(. < 0x801b0000, "renderer overlaps guest EWRAM")
 /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.gnu.attributes) *(.pdr) *(.comment) *(.mdebug*) }
}

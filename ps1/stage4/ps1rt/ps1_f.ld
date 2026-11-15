ENTRY(_start)
SECTIONS{ . = 0x80010000;
 .text : { *(.text.start) *(.text*) *(.rodata*) *(.data*) *(.sdata*) }
 . = ALIGN(4); __bss_start = .; .bss : { *(.bss*) *(.sbss*) *(COMMON) } __bss_end = .;
 ASSERT(. < 0x80028000, "C runtime overlaps the helper table at 0x80028000")
 . = 0x80030000; .blob : { *(.blob) }
 . = ALIGN(16); .bootimg : { *(.bootimg) }
 /* the city renderer (stage 3; its sections carry the .sf prefix) sits above the guest VRAM shadow, in space nothing else uses */
 . = 0x80199000; .sf : { *(.sf.text*) *(.sf.rodata*) *(.sf.data*) *(.sf.sdata*) *(.sfro) }
 . = ALIGN(16); __sfbss_start = .; .sfbss : { *(.sf.bss*) *(.sf.sbss*) } __sfbss_end = .;
 ASSERT(. < 0x801b0000, "renderer overlaps guest EWRAM")
 /* TEST-ONLY sim layout: cold tables above the cold pool (pool may run to 0x80800000) */
 . = 0x80800000; .coldtab : { *(.coldtab) }
 . = ALIGN(16); .rompack : { *(.rompack) }
 /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.gnu.attributes) *(.pdr) *(.comment) *(.mdebug*) }
}

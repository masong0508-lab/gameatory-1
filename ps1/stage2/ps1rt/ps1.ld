ENTRY(_start)
SECTIONS{ . = 0x80010000;
 .text : { *(.text.start) *(.text*) *(.rodata*) *(.data*) *(.sdata*) }
 . = ALIGN(4); __bss_start = .; .bss : { *(.bss*) *(.sbss*) *(COMMON) } __bss_end = .;
 ASSERT(. < 0x80028000, "C runtime overlaps the helper table at 0x80028000")
 . = 0x80030000; .blob : { *(.blob) }
 . = ALIGN(16); .bootimg : { *(.bootimg) }
 . = ALIGN(16); .coldtab : { *(.coldtab) }
 . = ALIGN(16); .rompack : { *(.rompack) }
 /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.gnu.attributes) *(.pdr) *(.comment) *(.mdebug*) }
}

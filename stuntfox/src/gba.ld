/* Stunt Fox memory map: code and data in ROM, hot code in IWRAM, big buffers in EWRAM. */
ENTRY(_start)
/* model_draw and the polygon clipper use substantial local arrays. Keep at least
   3 KiB below the system SP even when code grows; never borrow the IRQ/BIOS area. */
__stack_top = 0x03007f00;
__stack_irq_top = 0x03007fa0;
__stack_reserve = 0xc00;
MEMORY {
    rom   (rx)  : ORIGIN = 0x08000000, LENGTH = 32M
    iwram (rwx) : ORIGIN = 0x03000000, LENGTH = 0x7300
    ewram (rw)  : ORIGIN = 0x02000000, LENGTH = 256K
}
SECTIONS {
    .crt0 : { KEEP(*(.crt0)) } > rom
    .text : { *(EXCLUDE_FILE(*.iw.o) .text EXCLUDE_FILE(*.iw.o) .text.*) *(.coldtext) } > rom
    .rodata : { *(.rodata .rodata.*) . = ALIGN(4); } > rom
    .iwram : {
        __iwram_start = .;
        *(.iwram .iwram.*)
        *.iw.o(.text .text.*)
        *(.iwram_data)
        *(.data .data.*)
        . = ALIGN(4);
        __iwram_end = .;
    } > iwram AT > rom
    __iwram_lma = LOADADDR(.iwram);
    .bss (NOLOAD) : { __bss_start = .; *(.bss .bss.* COMMON) . = ALIGN(4); __bss_end = .; } > iwram
    .sbss (NOLOAD) : { __sbss_start = .; *(.sbss .sbss.*) . = ALIGN(4); __sbss_end = .; } > ewram
    .assets : { . = ALIGN(4); *(.assets) } > rom
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) }
}
ASSERT(__bss_end <= __stack_top - __stack_reserve, "standalone IWRAM leaves less than 3 KiB for the system stack")

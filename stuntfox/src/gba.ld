/* Stunt Fox memory map: code and data in ROM, hot code in IWRAM, big buffers in EWRAM. */
ENTRY(_start)
MEMORY {
    rom   (rx)  : ORIGIN = 0x08000000, LENGTH = 32M
    iwram (rwx) : ORIGIN = 0x03000000, LENGTH = 0x7e00
    ewram (rw)  : ORIGIN = 0x02000000, LENGTH = 256K
}
SECTIONS {
    .crt0 : { KEEP(*(.crt0)) } > rom
    .text : { *(EXCLUDE_FILE(*.iw.o) .text EXCLUDE_FILE(*.iw.o) .text.*) } > rom
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

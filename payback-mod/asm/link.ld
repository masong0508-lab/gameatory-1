SECTIONS {
    . = 0x081b0000;
    .text : { *(.text.hook) *(.text*) *(.rodata*) }
    . = ALIGN(4);
    cols = .;
    maps = cols + 4 * 85;
}

SECTIONS {
    . = 0x081b0000;
    .text : { *(.text.hook) *(.text*) *(.rodata*) }
    . = ALIGN(4);
    cols = .;
}

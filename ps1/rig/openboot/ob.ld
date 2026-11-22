/* ob.ld: openboot.  The reset code executes in place in the ROM (KSEG1); the resident services and the loader
   are linked for RAM at 0x80002000 and stored in the ROM behind the reset code (copied by start.S). */
ENTRY(_reset)
MEMORY {
    ROM (rx)  : ORIGIN = 0xBFC00000, LENGTH = 0x80000
    RES (rwx) : ORIGIN = 0x80002000, LENGTH = 0x3000
}
SECTIONS {
    .rom : { KEEP(*(.rom.reset)) . = ALIGN(16); } > ROM
    .res : {
        __res_start = .;
        KEEP(*(.res.vec)) *(.res.text*) *(.text*) *(.rodata*) *(.data*) *(.sdata*) *(.got*) *(.sbss*) *(.bss*) *(COMMON)
        . = ALIGN(4);
        __res_end = .;
    } > RES AT> ROM
    __res_lma = LOADADDR(.res);
    /DISCARD/ : { *(.reginfo) *(.MIPS.abiflags) *(.pdr) *(.comment) *(.gnu.attributes) *(.mdebug*) *(.note*) *(.eh_frame*) }
}

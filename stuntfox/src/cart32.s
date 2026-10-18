@ A 32 MiB cartridge (the radio's remixes are at its top): its EEPROM answers only at
@ 0x0DFFFF00-0x0DFFFFFF, the rest of 0x0D000000 up being ROM. Payback's EEPROM library builds
@ 0x0D000000 in four places (movs rN, #0xd0; lsls rN, rN, #20); the build makes each a call to
@ one of these (each of those functions has saved lr). Carts of 16 MiB and less, and emulators,
@ answer there too.
    .syntax unified
    .thumb
    .section .text.sf_eep, "ax", %progbits
    .align 2
    .global sf_eep_r0, sf_eep_r4
    .thumb_func
sf_eep_r0:
    ldr r0, =0x0dffff00
    bx lr
    .thumb_func
sf_eep_r4:
    ldr r4, =0x0dffff00
    bx lr
    .ltorg

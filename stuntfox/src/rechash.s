@ MERGE build only. u32 rec_hash(const u8 *rec, u32 h): a hash of one of Payback's entity records
@ (0x168 bytes) for sf_phys (merge.c), bar two words that change on vehicles at rest and that its
@ physics never reads: +0x14 (a parked helicopter's rotor) and +0x64 (a wreck's clock). Thumb
@ from ROM is fetch bound: four words a load, and none of the compiler's spills.
    .syntax unified
    .thumb
    .section .text.rec_hash, "ax"
    .global rec_hash
    .thumb_func
rec_hash:
    push {r4-r7}
    ldr r2, =0x9e3779b1
    movs r3, #13
    ldmia r0!, {r4-r7}          @ +0x00
    eors r1, r4
    rors r1, r3
    muls r1, r2, r1
    eors r1, r5
    rors r1, r3
    muls r1, r2, r1
    eors r1, r6
    rors r1, r3
    muls r1, r2, r1
    eors r1, r7
    rors r1, r3
    muls r1, r2, r1
    ldmia r0!, {r4-r7}          @ +0x10 (+0x14 left out)
    eors r1, r4
    rors r1, r3
    muls r1, r2, r1
    eors r1, r6
    rors r1, r3
    muls r1, r2, r1
    eors r1, r7
    rors r1, r3
    muls r1, r2, r1
    movs r4, #0x40
    adds r4, r0
    mov ip, r4                  @ (the end of this run)
1:  ldmia r0!, {r4-r7}
    eors r1, r4
    rors r1, r3
    muls r1, r2, r1
    eors r1, r5
    rors r1, r3
    muls r1, r2, r1
    eors r1, r6
    rors r1, r3
    muls r1, r2, r1
    eors r1, r7
    rors r1, r3
    muls r1, r2, r1
    cmp r0, ip
    blo 1b
    ldmia r0!, {r4-r7}          @ +0x60 (+0x64 left out)
    eors r1, r4
    rors r1, r3
    muls r1, r2, r1
    eors r1, r6
    rors r1, r3
    muls r1, r2, r1
    eors r1, r7
    rors r1, r3
    muls r1, r2, r1
    movs r4, #0xf0
    adds r4, r0
    mov ip, r4                  @ (the end of this run)
2:  ldmia r0!, {r4-r7}
    eors r1, r4
    rors r1, r3
    muls r1, r2, r1
    eors r1, r5
    rors r1, r3
    muls r1, r2, r1
    eors r1, r6
    rors r1, r3
    muls r1, r2, r1
    eors r1, r7
    rors r1, r3
    muls r1, r2, r1
    cmp r0, ip
    blo 2b
    ldmia r0!, {r4, r5}         @ +0x160
    eors r1, r4
    rors r1, r3
    muls r1, r2, r1
    eors r1, r5
    rors r1, r3
    muls r1, r2, r1
    movs r0, r1
    pop {r4-r7}
    bx lr
    .pool

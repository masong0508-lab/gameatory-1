@ Inner loops for Payback's tiles (ARM, IWRAM; MERGE build). See tex.c.
@
@ A texture position is packed in one word: bits 31..27 the column of the 32 x 32 tile and
@ 26..16 its fraction, bits 15..11 the row and 10..0 its fraction, so one add steps both and
@ each wraps around its tile by itself. Every texel covers 2 x 2 pixels.
    .syntax unified
    .section .iwram2, "ax"
    .arm

@ void tex_hrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, int row2)
@ n texels along a row from dst (even), each also written row2 bytes further (240: the next
@ row, 0: none).
    .global tex_hrun
    .type tex_hrun, %function
tex_hrun:
    push    {r4-r8, lr}
    ldr     r4, [sp, #24]           @ tile
    ldr     r7, [sp, #28]           @ row2
    mov     r5, #0x3e0
    cmp     r1, #0
    ble     3f
    tst     r1, #1
    beq     2f
    and     r6, r5, r2, lsr #6      @ odd count: one first
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    strh    r6, [r0, r7]
    strh    r6, [r0], #2
    subs    r1, r1, #1
    beq     3f
2:  and     r6, r5, r2, lsr #6      @ two a turn
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    and     r8, r5, r2, lsr #6
    orr     r8, r8, r2, lsr #27
    ldrb    r8, [r4, r8]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    orr     r8, r8, r8, lsl #8
    strh    r6, [r0, r7]
    strh    r6, [r0], #2
    strh    r8, [r0, r7]
    strh    r8, [r0], #2
    subs    r1, r1, #2
    bgt     2b
3:  pop     {r4-r8, lr}
    bx      lr

@ void tex_hrun4(u32 *dst, int n, u32 uv, u32 duv, const u8 *tile, int row2)
@ the same with one texel for every four pixels (close up), dst word aligned
    .global tex_hrun4
    .type tex_hrun4, %function
tex_hrun4:
    push    {r4-r7, lr}
    ldr     r4, [sp, #20]           @ tile
    ldr     r7, [sp, #24]           @ row2
    mov     r5, #0x3e0
    subs    r1, r1, #1
    blt     2f
1:  and     r6, r5, r2, lsr #6
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    orr     r6, r6, r6, lsl #16
    str     r6, [r0, r7]
    str     r6, [r0], #4
    subs    r1, r1, #1
    bge     1b
2:  pop     {r4-r7, lr}
    bx      lr

@ void tex_vrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, const u8 *lut, int row2)
@ n texels down a column two pixels wide, two rows each (the second only if row2 is 240);
@ lut, if not 0, darkens them.
    .global tex_vrun
    .type tex_vrun, %function
tex_vrun:
    push    {r4-r9, lr}
    ldr     r4, [sp, #28]           @ tile
    ldr     r7, [sp, #32]           @ lut
    ldr     r8, [sp, #36]           @ row2
    mov     r5, #0x3e0
    mov     r9, #480
    cmp     r1, #0
    ble     3f
    cmp     r7, #0
    beq     2f
1:  and     r6, r5, r2, lsr #6
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    ldrb    r6, [r7, r6]
    orr     r6, r6, r6, lsl #8
    strh    r6, [r0, r8]
    strh    r6, [r0], r9
    subs    r1, r1, #1
    bgt     1b
    pop     {r4-r9, lr}
    bx      lr
2:  and     r6, r5, r2, lsr #6
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    strh    r6, [r0, r8]
    strh    r6, [r0], r9
    subs    r1, r1, #1
    bgt     2b
3:  pop     {r4-r9, lr}
    bx      lr

@ void tex_mrun1(u8 *dst, int n, u32 uv, u32 duv, const u8 *mip, int row2)
@ tex_mrun for a tile's 16 x 16 averages, the level most used
    .section .iwram10, "ax"
    .global tex_mrun1
    .type tex_mrun1, %function
tex_mrun1:
    push    {r4-r8, lr}
    ldr     r4, [sp, #24]           @ mip
    ldr     r7, [sp, #28]           @ row2
    mov     r5, #0xf0
    cmp     r1, #0
    ble     3f
1:  and     r6, r5, r2, lsr #8
    orr     r6, r6, r2, lsr #28
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    strh    r6, [r0, r7]
    strh    r6, [r0], #2
    subs    r1, r1, #1
    beq     3f
    and     r6, r5, r2, lsr #8
    orr     r6, r6, r2, lsr #28
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    strh    r6, [r0, r7]
    strh    r6, [r0], #2
    subs    r1, r1, #1
    bne     1b
3:  pop     {r4-r8, lr}
    bx      lr

@ void tex_vrun4(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, const u8 *lut)
@ n texels down a column two pixels wide, four rows each (close up)
    .section .iwram3, "ax"
    .global tex_vrun4
    .type tex_vrun4, %function
tex_vrun4:
    push    {r4-r9, lr}
    ldr     r4, [sp, #28]           @ tile
    ldr     r7, [sp, #32]           @ lut
    mov     r5, #0x3e0
    mov     r9, #960
    subs    r1, r1, #1
    blt     2f
1:  and     r6, r5, r2, lsr #6
    orr     r6, r6, r2, lsr #27
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    cmp     r7, #0
    ldrbne  r6, [r7, r6]
    orr     r6, r6, r6, lsl #8
    add     r8, r0, #480
    strh    r6, [r0, #240]
    strh    r6, [r8]
    strh    r6, [r8, #240]
    strh    r6, [r0], r9
    subs    r1, r1, #1
    bge     1b
2:  pop     {r4-r9, lr}
    bx      lr

@ void tex_mrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *mip, int row2, u32 lv)
@ tex_hrun from a tile's averages (tools/mkmip.py), found from the same texture position: lv holds
@ the mask of the row's bits (bits 7..0), the row's shift (23..16) and the column's (31..24)
    .section .iwram7, "ax"
    .global tex_mrun
    .type tex_mrun, %function
tex_mrun:
    push    {r4-r10, lr}
    ldr     r4, [sp, #32]           @ mip
    ldr     r7, [sp, #36]           @ row2
    ldr     r10, [sp, #40]          @ lv
    and     r5, r10, #0xff          @ the row's bits
    mov     r9, r10, lsr #24        @ the column's shift
    mov     r10, r10, lsr #16
    and     r10, r10, #0xff         @ the row's shift
    cmp     r1, #0
    ble     3f
    tst     r1, #1
    beq     2f
    and     r6, r5, r2, lsr r10     @ odd count: one first
    orr     r6, r6, r2, lsr r9
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    strh    r6, [r0, r7]
    strh    r6, [r0], #2
    subs    r1, r1, #1
    beq     3f
2:  and     r6, r5, r2, lsr r10     @ two a turn
    orr     r6, r6, r2, lsr r9
    ldrb    r6, [r4, r6]
    add     r2, r2, r3
    and     r8, r5, r2, lsr r10
    orr     r8, r8, r2, lsr r9
    ldrb    r8, [r4, r8]
    add     r2, r2, r3
    orr     r6, r6, r6, lsl #8
    orr     r8, r8, r8, lsl #8
    strh    r6, [r0, r7]
    strh    r6, [r0], #2
    strh    r8, [r0, r7]
    strh    r8, [r0], #2
    subs    r1, r1, #2
    bgt     2b
3:  pop     {r4-r10, lr}
    bx      lr

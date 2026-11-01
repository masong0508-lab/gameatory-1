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
@ row, 0: none). Only tex_walk calls it (and the three below): tile in r12, row2 in r11.
    .global tex_hrun
    .type tex_hrun, %function
tex_hrun:
    push    {r4-r8, lr}
    mov     r4, r12                 @ tile
    mov     r7, r11                 @ row2
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
    mov     r4, r12                 @ tile
    mov     r7, r11                 @ row2
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
    mov     r4, r12                 @ mip
    mov     r7, r11                 @ row2
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
    mov     r4, r12                 @ mip
    mov     r7, r11                 @ row2
    ldr     r10, [sp, #36]          @ lv (tex_walk pushes it with a pad word)
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

@ void tex_walk(u8 *d, int n, s32 X, s32 Z, s32 dX, s32 dZ, u32 ix, u32 iz, int row2, int color)
@ n pairs of pixels of a floor from d, the ground under the first at X, Z (units * 256), stepping dX, dZ
@ a pair; ix, iz: 2^30 / |dX|, |dZ|. Split at the city cells' edges (a piece ends where the next pair
@ is in another cell), each piece one run of its cell's tile: a texel for every pair, for every two
@ when a pair steps little (close up), or of the tile's averages far off (tex_mrun1, tex_mrun); a cell
@ with no tile, or a span off the map, is flat (tex.c). The runs take the tile in r12 and row2 in r11.
@ r4 X, r5 Z, r6 dX, r7 dZ, r8 d, r9 n left, r10 m (the piece).
    .macro PACKUV rd, rt                @ the texture position of X, Z: columns at 31..16, rows at 15..0
    mov     \rd, r4, lsl #14
    mov     \rd, \rd, lsr #16
    mov     \rd, \rd, lsl #16
    mov     \rt, r5, lsl #14
    orr     \rd, \rd, \rt, lsr #16
    .endm
    .section .iwram, "ax"
    .global tex_walk
    .type tex_walk, %function
@ stack: 0 duv, 4 lv, 8 quad, 12 mlv, 16 moff, 20 tex_tab, 24 tile; args from 72 (36 + 36: 8-byte aligned at every bl; word 32 is padding): dX, dZ, ix, iz, row2, color
tex_walk:
    push    {r4-r11, lr}
    sub     sp, sp, #36
    mov     r8, r0
    mov     r9, r1
    mov     r4, r2
    mov     r5, r3
    ldr     r6, [sp, #72]
    ldr     r7, [sp, #76]
    mov     r0, r6, lsl #14             @ duv = PSTEP(dX << 3, dZ << 3)
    mov     r0, r0, lsr #16
    mov     r0, r0, lsl #16
    mov     r1, r7, lsl #3
    add     r0, r0, r1, asr #5
    str     r0, [sp, #0]
    mov     r0, #1                      @ quad: a pair steps under a texel's quarter, one sample for every four
    cmp     r6, #0x1000
    movge   r0, #0
    cmn     r6, #0x1000
    movle   r0, #0
    cmp     r7, #0x1000
    movge   r0, #0
    cmn     r7, #0x1000
    movle   r0, #0
    str     r0, [sp, #8]
    ldr     r1, =tex_camy               @ lv: the level of the tile's averages (MIP_STEP, lower from 3000 up)
    ldr     r1, [r1]
    sub     r2, r1, #0xb00
    sub     r2, r2, #0xb8
    cmp     r2, #0
    movlt   r2, #0
    ldr     r3, =6000
    cmp     r2, r3
    movgt   r2, r3
    rsb     r2, r2, #0x3000
    cmp     r6, #0
    rsblt   r0, r6, #0
    movge   r0, r6
    cmp     r7, #0
    rsblt   r3, r7, #0
    movge   r3, r7
    cmp     r3, r0
    movgt   r0, r3
    mov     r1, #0
1:  cmp     r0, r2
    blt     2f
    cmp     r1, #3
    bge     2f
    add     r1, r1, #1
    mov     r0, r0, asr #1
    b       1b
2:  str     r1, [sp, #4]
    adr     r0, 3f                      @ the level's mask and shifts for tex_mrun
    ldr     r0, [r0, r1, lsl #2]
    str     r0, [sp, #12]
    mov     r0, #320
    cmp     r1, #2
    moveq   r0, #256
    cmp     r1, #1
    moveq   r0, #0
    str     r0, [sp, #16]
    ldr     r0, =tex_tab
    ldr     r0, [r0]
    str     r0, [sp, #20]
    b       .Lseg
3:  .word   0x1b0603e0, 0x1c0800f0, 0x1d0a0038, 0x1e0c000c
.Lseg:
    cmp     r9, #0
    ble     .Lret
    mov     r0, r4, asr #18             @ the cell
    mov     r1, r5, asr #18
    orr     r2, r0, r1
    cmp     r2, #128
    bhs     .Lout
    mov     r10, r9                     @ m: pairs until the next cell
    cmp     r6, #0
    beq     1f
    ldr     lr, [sp, #80]
    movgt   r2, r0, lsl #18
    addgt   r2, r2, #0x40000
    subgt   r2, r2, r4
    suble   r2, r4, r0, lsl #18
    addle   r2, r2, #1
    umull   r3, r11, r2, lr
    mov     r3, r3, lsr #30
    orr     r3, r3, r11, lsl #2
    add     r3, r3, #1
    cmp     r3, r10
    movlt   r10, r3
1:  cmp     r7, #0
    beq     2f
    ldr     lr, [sp, #84]
    movgt   r2, r1, lsl #18
    addgt   r2, r2, #0x40000
    subgt   r2, r2, r5
    suble   r2, r5, r1, lsl #18
    addle   r2, r2, #1
    umull   r3, r11, r2, lr
    mov     r3, r3, lsr #30
    orr     r3, r3, r11, lsl #2
    add     r3, r3, #1
    cmp     r3, r10
    movlt   r10, r3
2:  add     r1, r1, r0, lsl #7          @ i = cx * 128 + cz
    ldr     r2, [sp, #20]
    add     r2, r2, r1, lsl #1
    ldrh    r2, [r2]                    @ its tile id
    cmp     r2, #0x318
    bhs     .Lflat
    ldr     r3, =0x02002c60             @ Payback's pointer to it, if it is in RAM or ROM
    ldr     r3, [r3, r2, lsl #2]
    mov     r11, r3, lsr #24
    cmp     r11, #8
    bhi     .Lflat
    mov     lr, #0x14c                  @ bank 2, 3, 6 or 8
    mov     lr, lr, lsr r11
    tst     lr, #1
    beq     .Lflat
    ldr     lr, [sp, #4]
    cmp     lr, #0
    beq     .Lplain
    ldr     r11, =pb_mipof
    add     r11, r11, r2, lsl #1
    ldrh    r11, [r11]
    cmp     r11, #0
    beq     .Lplain
    sub     r11, r11, #1                @ its averages
    mov     r12, #336
    mul     r2, r11, r12
    ldr     r12, =pb_mip
    add     r12, r12, r2
    ldr     r2, [sp, #16]
    add     r12, r12, r2
    PACKUV  r2, r3
    mov     r0, r8
    mov     r1, r10
    ldr     r3, [sp, #0]
    ldr     r11, [sp, #88]
    cmp     lr, #1
    bne     1f
    bl      tex_mrun1
    b       .Lnext
1:  ldr     lr, [sp, #12]
    stmfd   sp!, {r0, lr}               @ lv at +4, the other word keeps sp 8-aligned
    bl      tex_mrun
    add     sp, sp, #8
    b       .Lnext
.Lplain:
    str     r3, [sp, #24]
    ldr     lr, [sp, #8]
    cmp     lr, #0
    beq     .Lone
    cmp     r10, #3
    blt     .Lone
    tst     r8, #2
    beq     1f
    PACKUV  r2, lr                      @ the first pair, to be word aligned
    mov     r0, r8
    mov     r1, #1
    ldr     r3, [sp, #0]
    ldr     r12, [sp, #24]
    ldr     r11, [sp, #88]
    bl      tex_hrun
    add     r0, r8, #2
    sub     r1, r10, #1
    PACKUV  r2, lr
    ldr     r3, [sp, #0]
    add     r2, r2, r3
    b       2f
1:  mov     r0, r8
    mov     r1, r10
    PACKUV  r2, lr
    ldr     r3, [sp, #0]
2:  stmfd   sp!, {r0, r1, r2}           @ e, k, uv: two pairs a word
    mov     r1, r1, lsr #1
    mov     r3, r3, lsl #1
    ldr     r12, [sp, #36]
    ldr     r11, [sp, #100]
    bl      tex_hrun4
    ldmfd   sp!, {r0, r1, r2}
    tst     r1, #1
    beq     .Lnext
    ldr     r3, [sp, #0]                @ and the last pair on its own
    sub     lr, r1, #1
    mla     r2, lr, r3, r2
    mov     lr, r1, lsr #1
    add     r0, r0, lr, lsl #2
    mov     r1, #1
    ldr     r12, [sp, #24]
    ldr     r11, [sp, #88]
    bl      tex_hrun
    b       .Lnext
.Lone:
    PACKUV  r2, lr
    mov     r0, r8
    mov     r1, r10
    ldr     r3, [sp, #0]
    ldr     r12, [sp, #24]
    ldr     r11, [sp, #88]
    bl      tex_hrun
    b       .Lnext
.Lflat:                                 @ no tile: the cell's colour (r1: its index)
    mov     r2, r1
    mov     r0, r8
    mov     r1, r10
    ldr     r3, [sp, #88]
    ldr     r12, =tex_flat_cell
    mov     lr, pc
    bx      r12
.Lnext:
    add     r8, r8, r10, lsl #1
    mla     r4, r10, r6, r4
    mla     r5, r10, r7, r5
    sub     r9, r9, r10
    b       .Lseg
.Lout:                                  @ off the map
    mov     r0, r8
    mov     r1, r9
    ldr     r2, [sp, #92]
    ldr     r3, [sp, #88]
    ldr     r12, =tex_flat_pairs
    mov     lr, pc
    bx      r12
.Lret:
    add     sp, sp, #36
    pop     {r4-r11, lr}
    bx      lr
    .ltorg

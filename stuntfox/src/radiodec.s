@ The car radio's remixes: the stream decoder (tools/radenc.c has the format) and the hooks in
@ Payback's sound interrupt (src/radio.c). Thumb in ROM: IWRAM has no room for it, and the
@ interrupt runs at any moment, so it cannot borrow any. It runs on the samples times the
@ volume (the predictors have whole coefficients, so that is exact), which leaves 5-8
@ instructions a sample, unrolled so that the cartridge's prefetch keeps up.
    .syntax unified
    .thumb

@ registers while decoding: r0 out, r1 a, r2 b (they swap roles every sample, so each sample's
@ value lands where the older one was), r3 volume, r4 code word, r5 step * volume, r6 codes,
@ r8 next frame head, r11 the state, r12 the heads' end

.macro CODE b, i, R                 @ sample i's signed code
  .if \b == 4
    .if (\i % 8) == 7
      asrs \R, r4, #28
    .else
      lsls \R, r4, #(28 - 4 * (\i % 8))
      asrs \R, \R, #28
    .endif
  .else
    .if (\i % 16) == 15
      asrs \R, r4, #30
    .else
      lsls \R, r4, #(30 - 2 * (\i % 16))
      asrs \R, \R, #30
    .endif
  .endif
.endm

.macro SMP b, k, i, A, B            @ one sample: B = pred(k, A, B) + code * step, then out
  .if (\b == 4 && (\i % 8) == 0) || (\b == 2 && (\i % 16) == 0)
    ldmia r6!, {r4}
  .endif
  .if \k == 0
    CODE \b, \i, \B
    muls \B, r5
  .else
    .if \k == 2
      subs \B, \A, \B
      adds \B, \A
    .elseif \k == 3
      subs \B, \A, \B
    .endif
    CODE \b, \i, r7
    muls r7, r5
    .if \k == 1
      adds \B, \A, r7
    .else
      adds \B, r7
    .endif
  .endif
  asrs r7, \B, #16
  strb r7, [r0, #\i]
.endm

.macro SETUP b                      @ the next frame: its step (times the volume) and predictor
    mov r7, r8
    ldrb r4, [r7]
    adds r7, #1
    mov r8, r7
    lsls r7, r4, #26
    lsrs r7, r7, #24
    ldr r5, =radio_step
    ldr r5, [r5, r7]
    muls r5, r3
    lsrs r7, r4, #6
    lsls r7, r7, #2
    ldr r4, =radio_t\b
    ldr r7, [r4, r7]
    bx r7
.endm

.macro FRAME b, k
    .section .text.radio_v\b\()_\k, "ax", %progbits
    .align 2
    .thumb_func
radio_v\b\()_\k:
    .irp i, 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30
      SMP \b, \k, \i, r1, r2
      SMP \b, \k, (\i + 1), r2, r1
    .endr
    adds r0, #32
    cmp r8, r12
    bne 1f
    ldr r7, =radio_done
    bx r7
1:  SETUP \b
    .ltorg
.endm

@ void radio_seg(u8 *out, struct radio *r, int vol): one segment (480 samples) from r->p into
@ out; r->a and r->b are the last two samples times vol (1-256). Moves r->p, r->a, r->b on.
    .section .text.radio_seg, "ax", %progbits
    .align 2
    .global radio_seg
    .thumb_func
radio_seg:
    push {r4-r7, lr}
    mov r4, r8
    mov r5, r9
    mov r6, r10
    mov r7, r11
    push {r4-r7}
    mov r11, r1
    movs r3, r2
    ldr r6, [r1, #0]
    ldr r2, [r1, #8]
    ldr r1, [r1, #4]
    ldrb r7, [r6]
    adds r6, #1
    mov r8, r6
    adds r6, #15
    mov r12, r6
    cmp r7, #4
    bne 2f
    SETUP 4
2:  SETUP 2
    .ltorg

    .thumb_func
radio_done:
    mov r7, r11
    str r6, [r7, #0]
    str r1, [r7, #4]
    str r2, [r7, #8]
    pop {r4-r7}
    mov r8, r4
    mov r9, r5
    mov r10, r6
    mov r11, r7
    pop {r4-r7}
    pop {r0}
    bx r0

    .irp k, 0, 1, 2, 3
      FRAME 4, \k
      FRAME 2, \k
    .endr

    .section .rodata.radio_t, "a", %progbits
    .align 2
radio_t4:
    .word radio_v4_0, radio_v4_1, radio_v4_2, radio_v4_3
radio_t2:
    .word radio_v2_0, radio_v2_1, radio_v2_2, radio_v2_3
radio_step:                         @ round(2 ^ ((s + 2) / 4)), as in tools/radenc.c
    .word 1, 2, 2, 2, 3, 3, 4, 5, 6, 7, 8, 10, 11, 13, 16, 19
    .word 23, 27, 32, 38, 45, 54, 64, 76, 91, 108, 128, 152, 181, 215, 256, 304
    .word 362, 431, 512, 609, 724, 861, 1024, 1218, 1448, 1722, 2048, 2435, 2896, 3444, 4096, 4871
    .word 5793, 6889, 8192, 9742, 11585, 13777, 16384, 19484, 23170, 27554, 32768, 38968, 46341, 55109, 65536, 77936


@ Payback's sound interrupt, in place of its call to its music pass (0x08075da8: r0 the music
@ half of the next buffer, r1 its channel list, r2 its volume table, r4 the mixer in IWRAM)
    .section .text.sf_mus, "ax", %progbits
    .align 2
    .global sf_mus
    .thumb_func
sf_mus:
    ldr r3, =radio + RADIO_ON
    ldrb r3, [r3]
    cmp r3, #0
    bne 1f
    bx r4                           @ Payback's own song (or none): its music pass, as ever
1:  push {r4, lr}
    bl radio_irq
    pop {r4}
    pop {r0}
    bx r0
    .ltorg

@ ... and in place of its call to its sequencer (0x08075d4a, which takes no arguments): the keys
@ for the radio's chord (radio_keys), then, while a remix plays, nothing to play (and never
@ the song's notes)
    .section .text.sf_seq, "ax", %progbits
    .align 2
    .global sf_seq
    .thumb_func
sf_seq:
    push {lr}
    bl radio_keys
    pop {r3}
    mov lr, r3
    ldr r3, =radio + RADIO_ON
    ldrb r3, [r3]
    subs r3, #1
    cmp r3, #3
    bcc 1f
    ldr r3, =0x08075dd1
    bx r3
1:  bx lr
    .ltorg

@ void pb_music(u8 *out): Payback's music pass, as its interrupt calls it
    .section .text.pb_music, "ax", %progbits
    .align 2
    .global pb_music
    .thumb_func
pb_music:
    push {r4, lr}
    ldr r1, =0x0300046c
    ldr r2, =0x0863eda8
    ldr r4, =0x03000580
    bl 1f
    pop {r4}
    pop {r0}
    bx r0
1:  bx r4
    .ltorg

    .equ RADIO_ON, 14               @ offsetof(struct radio, on), as in radio.h

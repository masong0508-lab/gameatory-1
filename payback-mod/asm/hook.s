@ Called from the game loop in place of the keypad reader (bl at 0x0800e9a8).
    .syntax unified
    .thumb
    .section .text.hook, "ax"
    .global hook
    .thumb_func
hook:
    push {r4, r5, r6, lr}
    adds r5, r1, #0             @ r1 = decoded button struct
    ldr r4, =0x08072f69     @ original keypad reader
    bl call_r4
    adds r6, r0, #0             @ preserve the original reader's result
    mov r4, sp                 @ the original game may only guarantee 4-byte alignment
    movs r0, #7
    mov r1, sp
    bics r1, r0
    mov sp, r1                 @ explicitly align the C call to 8 bytes
    adds r0, r5, #0
    bl editor
    mov sp, r4
    adds r0, r6, #0
    pop {r4, r5, r6}
    pop {r1}
    bx r1
    .thumb_func
call_r4:
    bx r4
    .pool

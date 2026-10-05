@ Called from the game loop in place of the keypad reader (bl at 0x0800e9a8).
    .syntax unified
    .thumb
    .section .text.hook, "ax"
    .global hook
    .thumb_func
hook:
    push {r4, r5, lr}
    adds r5, r1, #0             @ r1 = decoded button struct
    ldr r4, =0x08072f69     @ original keypad reader
    bl call_r4
    adds r0, r5, #0
    bl editor
    pop {r4, r5}
    pop {r0}
    bx r0
    .thumb_func
call_r4:
    bx r4
    .pool

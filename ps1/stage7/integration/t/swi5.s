.arm
.global _s
_s:
 push {r0-r3,r12,lr}
 mov r0,#0x04000000
 ldr r1,=0x03007ffc
 ldr r1,[r1]
 mov lr,pc
 bx r1
 ldr r1,=0x03007ff8
 ldrh r2,[r1]
 orr r2,r2,#1
 strh r2,[r1]
 pop {r0-r3,r12,lr}
 bx r12
.ltorg

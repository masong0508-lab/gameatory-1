.set noreorder
.section .text.start,"ax"
.global _start
_start:
  lui $sp,0x0080
  jal main
  nop
  break

.set noreorder
.section .text.start,"ax"
.global _start
_start:
  mfc0 $t0,$12
  lui $t1,0x4000        # SR.CU2: enable the GTE
  or $t0,$t0,$t1
  mtc0 $t0,$12
  nop
  lui $sp,0x801f
  ori $sp,$sp,0xd000
  la $t0,__bss_start
  la $t1,__bss_end
1: sltu $t2,$t0,$t1
  beq $t2,$zero,2f
  nop
  sw $zero,0($t0)
  b 1b
  addiu $t0,$t0,4
2: jal main
  nop
3: b 3b
  nop

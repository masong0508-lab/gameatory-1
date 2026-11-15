#!/usr/bin/env python3
"""ldcheck.py ELF: find MIPS-I load-delay hazards (a load whose destination is read by the very next instruction)."""
import re, subprocess, sys
out = subprocess.run(['llvm-objdump', '-d', '--no-show-raw-insn', sys.argv[1]], capture_output=True, text=True).stdout.splitlines()
import os
lim = 0xffffffff
for l in subprocess.run(['llvm-nm', sys.argv[1]], capture_output=True, text=True).stdout.splitlines():
    q = l.split()
    if len(q) == 3 and q[2] == 'world_blob': lim = int(q[0], 16)
ins = []
for l in out:
    m = re.match(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)', l)
    if m and int(m.group(1), 16) < lim: ins.append((m.group(1), m.group(2), m.group(3)))
LOADS = {'lw', 'lh', 'lhu', 'lb', 'lbu', 'lwl', 'lwr', 'mfc0', 'mfc2', 'cfc2'}
bad = 0
for i in range(len(ins) - 1):
    a, op, args = ins[i]
    if op in LOADS:
        d = re.match(r'(\$\w+)', args).group(1)
        n = ins[i + 1]
        regs = re.findall(r'\$\w+', n[2].split('#')[0])
        if n[1] in LOADS and n[1] in ('lwr', 'lwl') and op in ('lwl', 'lwr') and regs and regs[0] == d: continue
        if n[1] in ('sw', 'sh', 'sb', 'lw', 'lh', 'lhu', 'lb', 'lbu', 'lwl', 'lwr', 'swl', 'swr'): used = regs[1:] + (regs[:1] if n[1].startswith('s') else [])
        elif n[1] in ('mtc2', 'ctc2', 'mtc0', 'jr', 'jalr', 'beqz', 'bnez', 'bltz', 'bgez', 'blez', 'bgtz'): used = regs
        else: used = regs[1:] if len(regs) > 1 else regs
        if d in used and d != '$0':
            bad += 1; print('HAZARD', a, op, args, '->', n[0], n[1], n[2])
BR = ('j', 'jal', 'jr', 'jalr', 'b', 'beq', 'bne', 'beqz', 'bnez', 'bltz', 'bgez', 'blez', 'bgtz', 'bgezal', 'bltzal', 'bc2f', 'bc2t', 'bnel', 'beql', 'bltzl', 'bgezl', 'blezl', 'bgtzl', 'bal')
for i in range(1, len(ins)):
    if ins[i - 1][1] in BR and ins[i][1] in LOADS:
        bad += 1; print('DELAY-SLOT LOAD', ins[i - 1][0], ins[i - 1][1], '|', ins[i][0], ins[i][1], ins[i][2])
print('hazards:', bad)

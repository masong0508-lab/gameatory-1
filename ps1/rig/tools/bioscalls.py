#!/usr/bin/env python3
"""bioscalls.py ELF : static list of every BIOS call site (jalr to 0xA0/0xB0/0xC0, syscall, break) in a PS1 ELF,
with the function number loaded into $9 and what the enclosing function keeps at [sp+0..15] (the words a real
kernel function with N parameters may destroy: psx-spx 'Parameters, Registers, Stack')."""
import re, subprocess, sys, collections
elf = sys.argv[1]
txt = subprocess.run(['llvm-objdump', '-d', '--no-show-raw-insn', elf], capture_output=True, text=True).stdout
funcs = []; cur = None
for l in txt.splitlines():
    m = re.match(r'^([0-9a-f]{8}) <(.+)>:$', l)
    if m: cur = [m.group(2), int(m.group(1), 16), []]; funcs.append(cur); continue
    m = re.match(r'^\s*([0-9a-f]{8}):\s+(\S+)\s*(.*)$', l)
    if m and cur: cur[2].append((int(m.group(1), 16), m.group(2), m.group(3).strip()))
tot = collections.Counter(); rows = []
for name, addr, ins in funcs:
    sp0 = [(a, op, args) for a, op, args in ins if op in ('sw', 'sh', 'sb', 'lw', 'lh', 'lhu', 'lb', 'lbu', 'swl', 'swr', 'lwl', 'lwr') and re.search(r', 0x[0-9a-c]\(\$(sp|fp)\)$', args)]
    frame = next((args for a, op, args in ins[:6] if op == 'addiu' and args.startswith('$sp, $sp, -')), None)
    r8 = r9 = None
    for i, (a, op, args) in enumerate(ins):
        if op in ('addiu', 'ori', 'li') and args.startswith('$8, $zero, '): r8 = int(args.split(', ')[2], 16)
        if op in ('addiu', 'ori', 'li') and args.startswith('$9, $zero, '): r9 = int(args.split(', ')[2], 16)
        if op == 'jalr' and args.strip() in ('$8', '$ra, $8') and r8 in (0xa0, 0xb0, 0xc0):
            key = '%s(%02Xh)' % ({0xa0: 'A', 0xb0: 'B', 0xc0: 'C'}[r8], r9 if r9 is not None else -1)
            tot[key] += 1; rows.append((key, name, a, frame, sp0))
        if op in ('syscall', 'break'):
            tot[op + ' ' + args] += 1; rows.append((op + ' ' + args, name, a, frame, sp0))
print('call sites by service:', dict(tot))
seen = set()
for key, name, a, frame, sp0 in rows:
    if (key, name) in seen: continue
    seen.add((key, name))
    low = sorted({(args.split(', ')[1], op, args.split(', ')[0]) for _, op, args in sp0})
    print('%-10s in %-22s first site %08x frame %-16s [sp+0..12] users: %s' % (key, name, a, frame, ' '.join('%s:%s %s' % (o, op, r) for o, op, r in low) or '-'))

#!/usr/bin/env python3
"""Run build/bench_L.elf on unicorn (MIPS32 LE; R3000 code is a subset) and count executed instructions.
usage: mipsprof.py LEVEL [frame0 nframes]   -> per-frame instruction counts for the window, per-function histogram, mult/div counts
Instruction counts are exact for this code; cycles on a real R3000 are NOT measured (mult 6..13, div 36 extra cycles, cache misses, load delays)."""
import sys, subprocess, struct
from unicorn import *
from unicorn.mips_const import *
L = sys.argv[1]; f0 = int(sys.argv[2]) if len(sys.argv) > 2 else 0; nf = int(sys.argv[3]) if len(sys.argv) > 3 else 720
elf = f'build/bench_{L}.elf'
syms = []
for ln in subprocess.run(['llvm-nm', '-n', '--defined-only', elf], capture_output=True, text=True).stdout.split('\n'):
    p = ln.split()
    if len(p) == 3 and p[1] in 'tTwW': syms.append((int(p[0], 16), p[2]))
mark = [a for a, n in syms if n == 'mark'][0]
d = open(elf, 'rb').read()
# minimal ELF32 load
phoff, = struct.unpack_from('<I', d, 0x1c); phentsize, phnum = struct.unpack_from('<HH', d, 0x2a); entry, = struct.unpack_from('<I', d, 0x18)
uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
uc.mem_map(0, 16 << 20)
for i in range(phnum):
    t, off, va, pa, fs, ms, fl, al = struct.unpack_from('<IIIIIIII', d, phoff + i * phentsize)
    if t == 1 and fs: uc.mem_write(va, d[off:off + fs])
import bisect
addrs = [a for a, n in syms]
cnt = {}; ops = {'mult': 0, 'div': 0, 'load': 0, 'store': 0}
state = {'on': False, 'n': 0}
cache = {}; freq = {}
def blockinfo(addr, size):
    k = (addr, size)
    if k in cache: return cache[k]
    code = bytes(uc.mem_read(addr, size)); o = {'mult': 0, 'div': 0, 'load': 0, 'store': 0}
    for j in range(0, size, 4):
        w = struct.unpack_from('<I', code, j)[0]; op = w >> 26
        if op == 0:
            f = w & 63
            if f in (0x18, 0x19): o['mult'] += 1
            elif f in (0x1a, 0x1b): o['div'] += 1
        elif op in (0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26): o['load'] += 1
        elif op in (0x28, 0x29, 0x2a, 0x2b, 0x2e): o['store'] += 1
    nm = syms[bisect.bisect_right(addrs, addr) - 1][1]
    cache[k] = (size // 4, o, nm); return cache[k]
def hook(uc, addr, size, ud):
    if not state['on']: return
    n, o, nm = blockinfo(addr, size)
    state['n'] += n; cnt[nm] = cnt.get(nm, 0) + n; freq[(addr, size)] = freq.get((addr, size), 0) + 1
    for kk in o: ops[kk] += o[kk]
pc = entry; frame = 0; hid = None; per = []; last = 0
uc.reg_write(UC_MIPS_REG_SP, 0x800000)
while True:
    try: uc.emu_start(pc, mark)
    except UcError as e:
        print('stopped:', e); break
    if uc.reg_read(UC_MIPS_REG_PC) != mark: break
    pc = uc.reg_read(UC_MIPS_REG_RA)
    if f0 <= frame < f0 + nf:
        if hid is None: hid = uc.hook_add(UC_HOOK_BLOCK, hook); uc.ctl_flush_tb(); state['on'] = True; last = state['n']
        else: per.append((frame - 1, state['n'] - last)); last = state['n']
    elif hid is not None:
        per.append((frame - 1, state['n'] - last)); uc.hook_del(hid); hid = None; state['on'] = False
    frame += 1
    if frame > f0 + nf + 1 and hid is None: break
tot = sum(n for f, n in per)
print(f'level {L}: frames {f0}..{f0+nf-1}: {tot} instructions, avg {tot//max(1,len(per))}/frame, max {max([n for f,n in per] or [0])}/frame')
print('per frame:', ' '.join(f'{f}:{n}' for f, n in per[:60]))
print('top functions:')
for nm, c in sorted(cnt.items(), key=lambda x: -x[1])[:14]: print(f'  {nm:24s} {c:10d} {100*c/max(1,tot):5.1f}%')
print('mult/div/loads/stores:', ops)

if '--lines' in sys.argv:
    insn = {}
    for (a, s), c in freq.items():
        for j in range(0, s, 4): insn[a + j] = insn.get(a + j, 0) + c
    keys = sorted(insn)
    out = subprocess.run(['llvm-symbolizer', '--obj=' + elf, '--no-inlines'] + [hex(k) for k in keys], capture_output=True, text=True).stdout.split('\n\n')
    lines = {}
    for k, o in zip(keys, out):
        p = o.strip().split('\n')
        if len(p) >= 2:
            loc = p[1].split(':'); key = loc[0].split('/')[-1] + ':' + loc[1]
            lines[key] = lines.get(key, 0) + insn[k]
    print('top source lines (instructions):')
    for k, c in sorted(lines.items(), key=lambda x: -x[1])[:25]: print(f'  {k:28s} {c:10d} {100*c/max(1,tot):5.1f}%')

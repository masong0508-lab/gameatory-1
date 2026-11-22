#!/usr/bin/env python3
"""patch_disc.py --cue IN.cue --patches P.json --out DIR [--name NAME]: TEST-ONLY copy of a disc image with words of the boot
executable replaced (patch list: [{addr, old, new}] as written by gpuwait_scan.py --json).  Single MODE2/2352 data track.
Every old word is verified; EDC/ECC of the touched sectors are regenerated (ECMA-130) when the source image carries valid ones.
"""
import argparse
import json
import os
import re
import struct

ECC_F, ECC_B, EDC = [0] * 256, [0] * 256, [0] * 256
for _i in range(256):
    _j = ((_i << 1) ^ (0x11d if _i & 0x80 else 0)) & 0xff
    ECC_F[_i] = _j
    ECC_B[_i ^ _j] = _i
    _e = _i
    for _ in range(8):
        _e = (_e >> 1) ^ (0xd8018001 if _e & 1 else 0)
    EDC[_i] = _e


def edc(data):
    e = 0
    for b in data:
        e = (e >> 8) ^ EDC[(e ^ b) & 0xff]
    return e


def ecc_block(src, major_count, minor_count, major_mult, minor_inc):
    size = major_count * minor_count
    out = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = src[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = ECC_F[a]
        a = ECC_B[ECC_F[a] ^ b]
        out[major] = a
        out[major + major_count] = a ^ b
    return out


def fix_sector(sec, zero_addr=True):
    """mode 2 form 1: EDC over sub-header + data; ECC with the address bytes taken as zero (the standard for mode 2),
    or with the real address bytes (zero_addr=False: what some image builders write)"""
    s = bytearray(sec)
    struct.pack_into('<I', s, 0x818, edc(s[0x10:0x818]))
    head = bytearray(4) if zero_addr else s[0x0c:0x10]
    s[0x81c:0x81c + 172] = ecc_block(head + s[0x10:0x81c], 86, 24, 2, 86)
    s[0x8c8:0x8c8 + 104] = ecc_block(head + s[0x10:0x8c8], 52, 43, 86, 88)
    return bytes(s)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cue', required=True); ap.add_argument('--patches', required=True); ap.add_argument('--out', required=True); ap.add_argument('--name', default=None)
    a = ap.parse_args()
    cue = open(a.cue).read()
    m = re.search(r'FILE\s+"([^"]+)"', cue)
    binp = os.path.join(os.path.dirname(os.path.abspath(a.cue)), m.group(1))
    assert 'MODE2/2352' in cue, 'only MODE2/2352 images'
    d = bytearray(open(binp, 'rb').read())
    def user(lba, n=1): return b''.join(bytes(d[(lba + i) * 2352 + 24:(lba + i) * 2352 + 24 + 2048]) for i in range(n))
    pvd = user(16)
    assert pvd[1:6] == b'CD001'
    rl, rs = struct.unpack_from('<I', pvd, 158)[0], struct.unpack_from('<I', pvd, 166)[0]
    root = user(rl, (rs + 2047) // 2048)
    files, p = {}, 0
    while p < len(root):
        n = root[p]
        if not n:
            p = (p // 2048 + 1) * 2048
            continue
        files[root[p + 33:p + 33 + root[p + 32]].decode('latin1').split(';')[0].upper()] = (struct.unpack_from('<I', root, p + 2)[0], struct.unpack_from('<I', root, p + 10)[0])
        p += n
    boot = 'PSX.EXE'
    if 'SYSTEM.CNF' in files:
        t = user(files['SYSTEM.CNF'][0])[:files['SYSTEM.CNF'][1]].decode('latin1')
        mm = re.search(r'BOOT\s*=\s*(\S+)', t)
        if mm:
            boot = re.split(r'[:\\/]', mm.group(1))[-1].split(';')[0].upper()
    lba, size = files[boot]
    hdr = user(lba)
    assert hdr[:8] == b'PS-X EXE'
    taddr, tsize = struct.unpack_from('<II', hdr, 0x18)
    # does the source carry valid EDC/ECC?  (checked on the executable's first body sector)
    probe = bytes(d[(lba + 1) * 2352:(lba + 2) * 2352])
    valid = 'standard' if fix_sector(probe) == probe else ('address-included' if fix_sector(probe, False) == probe else None)
    pj = json.load(open(a.patches))
    dirty = set()
    for q in pj['patches']:
        off = 0x800 + q['addr'] - taddr
        assert 0x800 <= off < 0x800 + tsize, 'address %08x outside the executable' % q['addr']
        sec, so = lba + off // 2048, off % 2048
        pos = sec * 2352 + 24 + so
        old, = struct.unpack_from('<I', d, pos)
        assert old == q['old'], 'word at %08x is %08x, expected %08x (other build?)' % (q['addr'], old, q['old'])
        struct.pack_into('<I', d, pos, q['new'])
        dirty.add(sec)
    if valid:
        for sec in dirty:
            d[sec * 2352:(sec + 1) * 2352] = fix_sector(bytes(d[sec * 2352:(sec + 1) * 2352]), valid == 'standard')
    os.makedirs(a.out, exist_ok=True)
    name = a.name or os.path.splitext(os.path.basename(binp))[0] + '_testpatch'
    open(os.path.join(a.out, name + '.bin'), 'wb').write(d)
    open(os.path.join(a.out, name + '.cue'), 'w').write(cue.replace(m.group(1), name + '.bin'))
    print('%s: boot file %s at lba %d, t_addr %08x; %d words patched in %d sectors; EDC/ECC %s -> %s' % (
        binp, boot, lba, taddr, len(pj['patches']), len(dirty), ('valid in the source (%s ECC), regenerated the same way' % valid) if valid else 'NOT valid in the source, left alone',
        os.path.join(a.out, name + '.cue')))


if __name__ == '__main__':
    main()

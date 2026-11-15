#!/usr/bin/env python3
"""verify_disc.py disc.cue : independent check (own cue parser, own sector parser, EDC via zlib-free bitwise CRC, ECC recomputed with
a different (matrix/polynomial-free, table-less GF) implementation). Prints layout and exits non-zero on any error."""
import sys, os, re, struct
cue = open(sys.argv[1], newline='').read().splitlines(); base = os.path.dirname(os.path.abspath(sys.argv[1]))
files = []; trk = []
for l in cue:
    m = re.match(r'\s*FILE "(.+)" BINARY', l)
    if m: files.append(os.path.join(base, m.group(1))); continue
    m = re.match(r'\s*TRACK (\d+) (\S+)', l)
    if m: trk.append({'n': int(m.group(1)), 'type': m.group(2), 'file': files[-1], 'idx': {}}); continue
    m = re.match(r'\s*INDEX (\d+) (\d+):(\d+):(\d+)', l)
    if m: trk[-1]['idx'][int(m.group(1))] = (int(m.group(2))*60 + int(m.group(3)))*75 + int(m.group(4))
def gmul(a, b):
    r = 0
    while b:
        if b & 1: r ^= a
        a <<= 1
        if a & 0x100: a ^= 0x11d
        b >>= 1
    return r
def crc(d):
    c = 0
    for x in d:
        c ^= x
        for _ in range(8): c = (c >> 1) ^ (0xD8018001 if c & 1 else 0)
    return c
def check_sector(sec, lba, expect_mode2form):
    errs = []
    if sec[:12] != b'\0' + b'\xff'*10 + b'\0': errs.append('sync')
    f = lba + 150; exp = bytes([(f//4500)//10*16+(f//4500)%10, (f//75%60)//10*16+(f//75%60)%10, (f%75)//10*16+(f%75)%10, 2])
    if sec[12:16] != exp: errs.append('header msf')
    if sec[16:20] != sec[20:24]: errs.append('subheader copies differ')
    sh = sec[18]
    form = 2 if sh & 0x20 else 1
    if form == 1:
        if crc(sec[16:0x818]) != struct.unpack('<I', sec[0x818:0x81c])[0]: errs.append('edc form1')
    else:
        if crc(sec[16:0x92c]) != struct.unpack('<I', sec[0x92c:0x930])[0]: errs.append('edc form2')
    return form, errs
# independent ECC: Reed-Solomon (26,24)/(45,43) syndromes; ECMA-130 defines P/Q parity so that for each codeword
# the two syndromes  S0 = XOR c_i  and  S1 = XOR(c_i * alpha^(n-1-i))  are both zero (c includes the 2 parity bytes).
def ecc_ok(sec):
    def run(major, minor, mult, inc, par, n):
        size = major * minor
        for mj in range(major):
            idx = (mj >> 1) * mult + (mj & 1); cw = []
            for k in range(minor):
                cw.append(sec[12 + idx]); idx = (idx + inc) % size
            cw += [sec[par + mj], sec[par + major + mj]]
            s0 = 0; s1 = 0
            for c in cw: s0 ^= c; s1 = gmul(s1, 2) ^ c
            if s0 or s1: return False
        return True
    return run(86, 24, 2, 86, 0x81c, 26) and run(52, 43, 86, 88, 0x8c8, 45)
tot_err = 0
t1 = trk[0]; data = open(t1['file'], 'rb'); size = os.path.getsize(t1['file'])
if len(trk) > 1 and trk[1]['file'] == t1['file']: dsec = trk[1]['idx'][0]
else: dsec = size // 2352
print('cue tracks:', [(t['n'], t['type'], t['idx']) for t in trk])
assert t1['type'] == 'MODE2/2352' and size % 2352 == 0, 'bad data track'
forms = {1: 0, 2: 0}; bad = 0
for lba in range(dsec):
    sec = data.read(2352); form, e = check_sector(sec, lba, 0); forms[form] += 1
    if form == 1 and not ecc_ok(sec): e.append('ecc')
    if e:
        bad += 1
        if bad < 10: print('LBA', lba, e)
print('data sectors', dsec, 'form1', forms[1], 'form2', forms[2], 'bad', bad)
# ISO9660 PVD at LBA 16 and licence area
data.seek(0); allsec = [data.read(2352) for _ in range(min(dsec, 40))]
lic = b''.join(s[24:24+2324] for s in allsec[:12]); m = re.search(rb'Licensed\s+by\s+Sony Computer Entertainment ([A-Za-z. ]+?)\s{2,}', lic)
print('licence text:', m.group(0).decode() if m else 'MISSING')
pvd = allsec[16][24:24+2048]; print('PVD at 16:', pvd[0] == 1 and pvd[1:6] == b'CD001', 'volume', pvd[40:72].decode().strip())
if not m or not (pvd[0] == 1 and pvd[1:6] == b'CD001'): bad += 1
# audio
for t in trk[1:]:
    assert t['type'] == 'AUDIO' and 0 in t['idx'] and t['idx'][1] - t['idx'][0] == 150, 'pregap'
    same = t['file'] == t1['file']
    start = t['idx'][0] * 2352 if same else 0
    flen = size if same else os.path.getsize(t['file'])
    nxt = [x for x in trk if x['n'] == t['n'] + 1]
    end = (nxt[0]['idx'][0] * 2352 if same and nxt else flen)
    assert (end - start) % 2352 == 0 and end > start
    print('track %02d  start LBA %d  pregap 150  %.1f s audio' % (t['n'], t['idx'][1], (end - start - 150 * 2352) / 176400))
    if same: assert start % 2352 == 0
print('RESULT', 'FAIL' if bad else 'PASS'); sys.exit(1 if bad else 0)

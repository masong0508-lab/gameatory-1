"""Saving the campaign (stage2.md 10) on the harness emulator, with real power cycles: each step is a new emulator process booted on the
save memory the last one left (the file the emulator would write), so what is read back was read from the EEPROM and from nothing else.
  - a game with no campaign writes nothing of ours, and leaves Payback's 64 blocks as they are and everything past them blank: the boot only reads;
  - P11, the identify: a save of 4 Kbit's size (512 bytes, Payback's own) stays in 4 Kbit mode until the campaign is started, then is proved
    64 Kbit with Payback's blocks as they were; one of 64 Kbit's size (8 KiB) with our directory in it is 64 Kbit from the boot; the emulator
    is a genuine 64 Kbit chip once it is asked 14 bits (a 4 Kbit chip that takes long requests for short ones is modelled in tests/save,
    which the emulator cannot be made to be);
  - a save in the hangar's way (mailbox 20) is read back after the power cycle: chapters open, acts, credits; the next save goes to the other slot;
  - a power cut in the middle of a save (the memory as it was after k blocks, in the slot that is not the newest, and in the one that is
    the only one) leaves the last whole save, and one block of the newest slot spoilt leaves the one before; both spoilt, none.

    SP=.. ROM=x.gba ELF=x.elf python3 tests/s2/save.py      (from stuntfox/)
"""
import json
import os
import subprocess
import sys

CHILD = len(sys.argv) > 1 and sys.argv[1] == 'child'
HERE = os.path.abspath(__file__)

if CHILD:
    import ctypes
    import h
    from h import *

    def run_child(img, out, script):
        if img != '-':
            data = open(img, 'rb').read()
            ctypes.memmove(e.lib.retro_get_memory_data(0), data, min(len(data), e.lib.retro_get_memory_size(0)))
        e.run(400)
        e.run(4, ['A'])
        e.run(1500)
        boot = bytes(e.mem(0))
        res = dict(boot_len=len(boot), boot_head=boot[:512].hex())
        for op in script.split(','):
            k, _, v = op.partition('=')
            if k == 'story':
                tap('A', after=80)
                for _ in range(11):
                    tap('A', after=60)
                run(300)
            elif k == 'camp':
                mb(16, 0)
            elif k == 'acts':
                c, b = v.split(':')
                mb(18, int(c) << 8 | int(b, 0))
            elif k == 'unl':
                mb(24, int(v))
            elif k == 'give':
                mb(28, int(v))
            elif k == 'save':
                mb(20)
                for _ in range(80):
                    run(2)
                    if not mb(27) & 16:
                        break
            elif k == 'snap':                        # (the memory when k blocks of the save are in: a power cut then)
                mb(20)
                for _ in range(120):
                    run(1)
                    if (mb(17, 7) >> 8) >= int(v):
                        break
                open(out + '.snap', 'wb').write(e.mem(0))
                res['snap_k'] = mb(17, 7) >> 8
            elif k == 'dump':
                open(out, 'wb').write(e.mem(0))
            elif k == 'run':
                run(int(v))
            elif k == 'report':
                res['report'] = dict(mode=mb(17, 8), flags=mb(17, 0), loaded=mb(17, 15), unlocked=mb(17, 2), acts0=mb(17, 32), acts1=mb(17, 33),
                                     credits=mb(17, 6), pick=mb(17, 9), chap=mb(17, 1))
        res['end_len'] = len(e.mem(0))
        res['end'] = bytes(e.mem(0)).hex()[:0]
        print('RESULT ' + json.dumps(res), flush=True)

    run_child(sys.argv[2], sys.argv[3], sys.argv[4])
    sys.exit(0)

# ---- the parent ----
START = os.getcwd()
SP = os.environ['SP']
ROM, ELF = os.environ['ROM'], os.environ['ELF']
OUT = os.environ.get('OUT', '/tmp')
bad = 0


def ck(ok, what, detail=''):
    global bad
    print('%s  %s%s' % ('PASS' if ok else 'FAIL', what, '  (' + detail + ')' if detail else ''), flush=True)
    bad += not ok


def child(img, script, tag):
    out = os.path.join(OUT, 'save_%s.bin' % tag)
    env = dict(os.environ, PYTHONPATH=os.path.join(START, 'tests', 's2'))
    r = subprocess.run([sys.executable, HERE, 'child', img, out, script], capture_output=True, text=True, env=env, cwd=START, timeout=1800)
    for line in r.stdout.splitlines():
        if line.startswith('RESULT '):
            return json.loads(line[7:]), out
    print(r.stdout[-2000:], r.stderr[-2000:])
    raise SystemExit('child %s failed' % tag)


BLK = 8


def blk(img, n):
    """block n as the emulator's save file holds it: the 8 bytes of a block in reverse order"""
    return bytes(img[n * BLK:n * BLK + BLK])


# ---- no campaign: nothing of ours is saved ----
r0, f0 = child('-', 'story,run=300,report,dump', 'fresh')
img0 = open(f0, 'rb').read()
ck(all(b == 0xff for b in img0[512:]) and bytes(img0[:512]) != b'\xff' * 512, 'a fresh chip, no campaign: nothing is written past Payback\'s own 64 blocks through the boot and a minute of play', 'save memory %d bytes (the emulator\'s buffer is 8 KiB whatever the game asks)' % len(img0))
ck(r0['report']['mode'] == 0, 'and the game is in 4 Kbit mode (nothing was proved, nothing written)')
# (a campaign started and saved on a fresh chip: this is the proof)
rp, fp = child('-', 'story,camp,save,report,dump', 'proof')
img = open(fp, 'rb').read()
ck(rp['report']['mode'] == 1 and len(img) == 8192, 'START CAMPAIGN proves the chip: 64 Kbit mode, the save is 8 KiB', 'mode %s, %d bytes' % (rp['report']['mode'], len(img)))
ck(blk(img, 64)[::-1][:4] == b'SFD1', 'the directory block is the proof of the chip', blk(img, 64).hex())
ck(any(b != 0xff for b in img[72 * BLK:112 * BLK]), 'and the first save is in slot A')
payback = img[:512]

# ---- P11: a 4 Kbit save and a 64 Kbit one ----
open(os.path.join(OUT, 'save_512.bin'), 'wb').write(payback + b'\xff' * (131072 - 512))
r1, f1 = child(os.path.join(OUT, 'save_512.bin'), 'story,run=60,report,dump', 'p11_512')
img1 = open(f1, 'rb').read()
ck(r1['report']['mode'] == 0 and r1['boot_head'][:1024] == payback.hex()[:1024] and img1[:512] == payback, 'P11: a 512-byte save (Payback\'s own) stays in 4 Kbit mode through the boot and a minute of play, byte for byte', 'mode %s' % r1['report']['mode'])
r1b, f1b = child(os.path.join(OUT, 'save_512.bin'), 'story,camp,save,report,dump', 'p11_512c')
img1b = open(f1b, 'rb').read()
ck(r1b['report']['mode'] == 1 and img1b[:512] == payback, 'P11: START CAMPAIGN on it proves the chip 64 Kbit, Payback\'s 64 blocks as they were', 'mode %s' % r1b['report']['mode'])
open(os.path.join(OUT, 'save_8k.bin'), 'wb').write(img)
r2, f2 = child(os.path.join(OUT, 'save_8k.bin'), 'story,run=60,report', 'p11_8k')
ck(r2['report']['mode'] == 1 and r2['boot_head'] == img[:512].hex(), 'P11: an 8 KiB save with the directory in it is in 64 Kbit mode from the boot, the blocks as they were', 'mode %s' % r2['report']['mode'])

# ---- a save and the power cycle ----
ra, fa = child('-', 'story,camp,unl=1,acts=0:3,give=500,save,report,dump', 's1')
ck(ra['report']['credits'] == 800 and ra['report']['acts0'] == 3, 'the first save: credits 800, acts 3 of chapter 0', str(ra['report']))
s1 = open(fa, 'rb').read()
ck(any(b != 0xff for b in s1[72 * BLK:112 * BLK]) and all(b == 0xff for b in s1[112 * BLK:152 * BLK]), 'it went to slot A (blocks 72..111), slot B is blank')
rb, fb = child(fa, 'story,report,acts=0:7,give=100,save,dump', 's2')
r = rb['report']
ck(r['loaded'] == 1 and r['flags'] & 1 and r['unlocked'] == 1 and r['acts0'] == 3 and r['credits'] == 800 and r['pick'] == 1 | 0 << 16 | 1 << 17,
   'POWER CYCLE: a new emulator on the memory the last left reads the campaign back: on, chapter 1 open, acts 3, credits 800, save 1 in slot A', str(r))
s2 = open(fb, 'rb').read()
ck(any(b != 0xff for b in s2[112 * BLK:152 * BLK]), 'the next save went to slot B (blocks 112..151)')
rc, fc = child(fb, 'story,report', 's2r')
r = rc['report']
ck(r['acts0'] == 7 and r['credits'] == 900 and r['pick'] == 2 | 1 << 16 | 1 << 17, 'and after another power cycle: acts 7, credits 900, save 2 in slot B', str(r))

# ---- a power cut in the middle of a save ----
rd, fd = child(fa, 'story,report,acts=0:0xf,give=999,snap=12', 't1')
snap = os.path.join(OUT, 'save_t1.bin.snap')
ck(rd['snap_k'] >= 12, 'the memory was taken with the save at block %s of 33' % rd['snap_k'])
re_, _ = child(snap, 'story,report', 't1r')
r = re_['report']
ck(r['acts0'] == 3 and r['credits'] == 800 and r['pick'] == 1 | 0 << 16 | 1 << 17, 'cut in slot B with only slot A whole: the first save is read back (acts 3, credits 800)', str(r))
rf, _ = child(fb, 'story,report,acts=0:0x1f,give=999,snap=12', 't2')
rg, _ = child(os.path.join(OUT, 'save_t2.bin.snap'), 'story,report', 't2r')
r = rg['report']
ck(r['acts0'] == 7 and r['credits'] == 900 and r['pick'] == 2 | 1 << 16 | 1 << 17, 'cut in slot A (the older, being overwritten) with slot B whole: save 2 is read back', str(r))
rh, fh = child(fb, 'story,report,acts=0:0x1f,give=999,save,dump', 't3')    # (the whole third save, in slot A; then the header block put back as it was)
full = bytearray(open(fh, 'rb').read())
full[72 * BLK:73 * BLK] = s2[72 * BLK:73 * BLK]
open(os.path.join(OUT, 'save_t3.bin.snap'), 'wb').write(bytes(full))
ck(bytes(full) != bytes(open(fh, 'rb').read()) and full[73 * BLK:112 * BLK] == open(fh, 'rb').read()[73 * BLK:112 * BLK], 'the third save went to slot A and its header block differs from the old one')
ri, _ = child(os.path.join(OUT, 'save_t3.bin.snap'), 'story,report', 't3r')
r = ri['report']
ck(r['acts0'] == 7 and r['credits'] == 900, 'cut after the last payload block and before the header: still save 2 (the header goes last)', str(r))

# ---- spoilt blocks ----
bad_b = bytearray(s2)
bad_b[(112 + 1 + 4) * BLK + 3] ^= 0x55                   # (one byte in slot B's fifth payload block)
open(os.path.join(OUT, 'save_badb.bin'), 'wb').write(bytes(bad_b))
rj, _ = child(os.path.join(OUT, 'save_badb.bin'), 'story,report', 'badb')
r = rj['report']
ck(r['acts0'] == 3 and r['credits'] == 800 and r['pick'] == 1 | 0 << 16 | 1 << 17, 'a spoilt block in the newest slot: the one before it is read (save 1)', str(r))
bad_a = bytearray(bad_b)
bad_a[(72 + 1 + 2) * BLK + 1] ^= 0xaa
open(os.path.join(OUT, 'save_bad2.bin'), 'wb').write(bytes(bad_a))
rk, _ = child(os.path.join(OUT, 'save_bad2.bin'), 'story,report', 'bad2')
r = rk['report']
ck(r['flags'] & 1 == 0 and r['unlocked'] == 0 and r['pick'] == 0, 'a spoilt block in both: no save is read, the game starts as new', str(r))
# ---- a whole slot whose image is not ours to read (a newer version's): the campaign stays off ----
def crc16(data):
    c = 0xffff
    for x in data:
        c ^= x << 8
        for _ in range(8):
            c = (c << 1 ^ 0x1021) & 0xffff if c & 0x8000 else (c << 1) & 0xffff
    return c


def rev(img, n):
    return bytes(img[n * BLK:n * BLK + BLK])[::-1]


fut = bytearray(s2)
nb = 33
pay = bytearray(b''.join(rev(s2, 113 + k) for k in range(nb)))
ck(bytes(pay[:4]) == b'SFP2', 'slot B holds a sealed image (its magic)', pay[:8].hex())
pay[4], pay[5] = 2, 0                                    # (version 2: a game that is not this one wrote it)
for k in range(nb):
    fut[(113 + k) * BLK:(114 + k) * BLK] = bytes(pay[k * BLK:(k + 1) * BLK])[::-1]
hd = bytearray(rev(s2, 112))
cc = crc16(pay)
hd[4], hd[5] = cc & 255, cc >> 8
hd[7] = hd[0] ^ hd[1] ^ hd[2] ^ hd[3] ^ hd[4] ^ hd[5] ^ hd[6] ^ 0x5a
fut[112 * BLK:113 * BLK] = bytes(hd)[::-1]
open(os.path.join(OUT, 'save_fut.bin'), 'wb').write(bytes(fut))
rl, _ = child(os.path.join(OUT, 'save_fut.bin'), 'story,report', 'fut')
r = rl['report']
ck(r['flags'] & 1 == 0 and r['unlocked'] == 0 and r['pick'] == 0, 'a newest slot with a good checksum but a version this game does not know: nothing of it is taken, the campaign is off', str(r))
print('ALL PASS' if not bad else '%d FAILED' % bad)
sys.exit(1 if bad else 0)

"""The PP_DIRTY change detector of the OBJ tiles (stage19/ps1rt/ppu12.h pp_obj): when it says "unchanged" the 16 KiB tile upload is
skipped, so a change it misses shows stale sprite graphics.

History.  rc10 (first): rotate-by-5/xor plus a sum repeated every 32 words (tiles moved or swapped by one 16x16 sprite kept the hash).
rc10 review fix: djb2 (h*33+w) and sdbm (h*65599+w); both linear with odd multipliers, so adding 2^31 to any two words cancelled
(PR #26 review: a=[0]*4096, b[0]^=b[32]^=0x80000000 -> both 0x016a1505).  rc10.1: check A, per pair of words a=G(a+w0); a=G((a+w1)*0x9e3779b1), G(x)=x^(x>>15)
(nonlinear: the shift feeds bit 31 into the next add and multiply) plus check B = djb2 as an independent second check, compared as 64 bits,
(B is the safety net: a cheap check independent of A; a timed forced upload was measured and not taken, see ppu12.h).

The C is tied to the test in two ways: the hash loop and the upload decision are cut out of ppu12.h by text, compiled with the host
C compiler and called (every case below runs the C), and a Python model of the hash is checked against that C.  Synthetic data only."""
import ctypes
import random
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PPU = Path(__file__).resolve().parents[1] / 'stage19' / 'ps1rt' / 'ppu12.h'
M = 0xffffffff
N = 4096


def c_parts():
    s = PPU.read_text()
    fm = re.search(r'(/\* PP_OBJCK BEGIN.*?/\* PP_OBJCK END \*/)', s, re.S)
    i = s.index('#ifdef PP_DIRTY\n  /* rc10: the 16 KiB of OBJ tiles')
    seg = s[i:s.index('if(use4|use8) pp_nobjup++;', i)]
    dm = re.search(r'(u32 ck\[2\]; pp_objck\(t,ck\); u32 ha=ck\[0\], hb=ck\[1\];).*?(if\(use4&&.*?pp_obj_hb\[1\]=hb; \})', seg, re.S)
    assert fm and dm, 'ppu12.h pp_objck / pp_obj PP_DIRTY block not found'
    return fm.group(1), dm.group(1) + '\n' + dm.group(2)


HDR = 'typedef unsigned int u32;\nstatic u32 pp_obj_ha[2], pp_obj_hb[2];\n'


def build_lib():
    fn, dec = c_parts()
    src = (HDR + fn + '\n'
           'void objhash(const u32*t,u32*out){ pp_objck(t,out); }\n'
           'int decide(const u32*t,int use4,int use8){ ' + dec + ' return use4|(use8<<1); }\n'
           'void reset(void){ for(int k=0;k<2;k++){ pp_obj_ha[k]=pp_obj_hb[k]=0; } }\n')
    d = Path(tempfile.mkdtemp(prefix='objhash'))
    (d / 'h.c').write_text(src)
    cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    subprocess.run([cc, '-O2', '-shared', '-fPIC', '-o', str(d / 'h.so'), str(d / 'h.c')], check=True)
    lib = ctypes.CDLL(str(d / 'h.so'))
    lib.objhash.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
    lib.decide.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_int, ctypes.c_int]
    return lib


def build_mips():
    """pp_objck as the PS1 build compiles it (the hand-scheduled MIPS I loop), linked at 0x80010000; None without clang/lld/unicorn"""
    clang, lld = shutil.which('clang'), shutil.which('ld.lld')
    try:
        import unicorn  # noqa
    except ImportError:
        return None
    if not clang or not lld:
        return None
    fn, _ = c_parts()
    d = Path(tempfile.mkdtemp(prefix='objhash_mips'))
    (d / 'm.c').write_text(HDR + fn + '\nvoid entry(const u32*t,u32*o){ pp_objck(t,o); }\n')
    f = ('--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -O2 -ffreestanding -G0 -mno-gpopt '
         '-mllvm -disable-mips-delay-filler -DPP_DIRTY').split()
    subprocess.run([clang] + f + ['-c', '-o', str(d / 'm.o'), str(d / 'm.c')], check=True)
    subprocess.run([lld, '-Ttext=0x80010000', '-e', 'entry', '-o', str(d / 'm.elf'), str(d / 'm.o')], check=True)
    nm = subprocess.run(['llvm-nm', str(d / 'm.elf')], capture_output=True, text=True, check=True).stdout
    entry = int(next(l.split()[0] for l in nm.splitlines() if l.endswith(' entry')), 16)
    subprocess.run(['llvm-objcopy', '-O', 'binary', '--only-section=.text', str(d / 'm.elf'), str(d / 'm.bin')], check=True)
    return (d / 'm.bin').read_bytes(), entry


LIB = build_lib()
MIPS = build_mips()
ARR = ctypes.c_uint32 * N


def ch(t):
    """the C checks (A, B) of 4096 words"""
    o = (ctypes.c_uint32 * 2)()
    LIB.objhash(ARR(*t), o)
    return o[0], o[1]


def G(x):
    return x ^ (x >> 15)


def model(t, upto=None):
    """Python model of pp_objck; with upto (even) the state of A before word upto"""
    a, b = 0x811c9dc5, 5381
    for i in range(0, N if upto is None else upto, 2):
        w0, w1 = t[i], t[i + 1]
        a = G((a + w0) & M)
        a = G(((a + w1) * 0x9e3779b1) & M)
        b = (b * 33 + w0) & M
        b = (b * 33 + w1) & M
    return a if upto is not None else (a | 1, b)


def old_rc10(t):
    a, b = 5381, 0
    for w in t:
        a = ((a << 5) + a + w) & M
        b = (w + (b << 6) + (b << 16) - b) & M
    return (a ^ (((b << 16) | (b >> 16)) & M)) | 1


def sparse_base(r):
    base = [0] * N
    for _ in range(r.randint(0, 40)):
        p = r.randrange(512) * 8
        base[p:p + 8] = [r.getrandbits(32) for _ in range(8)]
    return base


class ObjHash(unittest.TestCase):
    def differ(self, x, y, what):
        self.assertNotEqual(ch(x), ch(y), what)

    def test_c_matches(self):
        r = random.Random(3)
        for k in range(40):
            t = [0] * N if k == 0 else ([r.getrandbits(32) for _ in range(N)] if k & 1 else sparse_base(r))
            self.assertEqual(ch(t), model(t))

    @unittest.skipIf(MIPS is None, 'needs clang, ld.lld and unicorn')
    def test_mips_matches(self):
        import struct
        from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
        from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_RA, UC_MIPS_REG_SP
        code, entry = MIPS
        u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        u.mem_map(0, 0x200000)                      # KSEG0 0x80000000.. is physical 0.. (Unicorn translates it like the PS1)
        u.mem_write(0x10000, code)
        tile, out, stop = 0x80100000, 0x80180000, 0x80001000
        r = random.Random(5)
        cases = [[0] * N, [0x80000000] + [0] * 31 + [0x80000000] + [0] * (N - 33)]
        cases += [[r.getrandbits(32) for _ in range(N)] for _ in range(6)] + [sparse_base(r) for _ in range(6)]
        for t in cases:
            u.mem_write(tile & 0x1fffffff, struct.pack('<%dI' % N, *t) + b'\xa5' * 4)     # + the word past the end the loop reads
            u.reg_write(UC_MIPS_REG_A0, tile); u.reg_write(UC_MIPS_REG_A1, out)
            u.reg_write(UC_MIPS_REG_RA, stop); u.reg_write(UC_MIPS_REG_SP, 0x80070000)
            u.emu_start(entry, stop, count=200000)
            self.assertEqual(struct.unpack('<2I', u.mem_read(out & 0x1fffffff, 8)), ch(t))

    def test_changes_built_to_cancel_a(self):
        """A is a 32-bit chain: a second change can undo the state difference of a first one.  Build such pairs (one word of a pair
        changed, the other word of the pair set to cancel it in A) and check that A really is equal and B tells them apart."""
        r = random.Random(23)
        for k in range(1500):
            base = sparse_base(r) if k & 1 else [r.getrandbits(32) for _ in range(N)]
            p = r.randrange(0, N, 2)
            d0 = (1 << 31) if k % 3 == 0 else ((1 << r.randrange(32)) if k % 3 == 1 else r.getrandbits(32) or 1)
            y = (model(base, p) + base[p]) & M
            x = list(base); x[p] = (base[p] + d0) & M
            x[p + 1] = (base[p + 1] + G(y) - G((y + d0) & M)) & M
            hx, hb = ch(x), ch(base)
            self.assertEqual(hx[0], hb[0])                 # A cancelled, as built
            self.assertNotEqual(hx[1], hb[1], 'B must see the change built to cancel A (case %d)' % k)
        for k in range(1500):                              # across pairs: word p+1 changed, word p+2 undoes the state difference
            base = sparse_base(r) if k & 1 else [r.getrandbits(32) for _ in range(N)]
            p = r.randrange(0, N - 2, 2)
            d1 = (1 << 31) if k % 3 == 0 else ((1 << r.randrange(32)) if k % 3 == 1 else r.getrandbits(32) or 1)
            x = list(base); x[p + 1] = (base[p + 1] + d1) & M
            x[p + 2] = (base[p + 2] + model(base, p + 2) - model(x, p + 2)) & M
            hx, hb = ch(x), ch(base)
            self.assertEqual(hx[0], hb[0])
            self.assertNotEqual(hx[1], hb[1], 'B must see the cross-pair change built to cancel A (case %d)' % k)

    def test_review_fixture(self):
        a = [0] * N
        b = list(a); b[0] ^= 0x80000000; b[32] ^= 0x80000000
        self.assertEqual(old_rc10(a), old_rc10(b))          # the defect: the rc10 hash cancels
        self.assertEqual(old_rc10(a), 0x016a1505)
        self.differ(a, b, 'review fixture')
        self.assertNotEqual(ch(a)[0], ch(b)[0])            # check A alone sees it (B, linear, does not)

    def test_bit31_pairs_every_distance(self):
        a = [0] * N; ha = ch(a)[0]
        for j in range(1, N):
            b = list(a); b[0] ^= 0x80000000; b[j] ^= 0x80000000
            self.assertNotEqual(ch(b)[0], ha, 'bit-31 pair 0,%d' % j)

    def test_bit31_pairs_triples_random(self):
        r = random.Random(11)
        for k in range(3000):
            base = sparse_base(r) if k & 1 else [r.getrandbits(32) for _ in range(N)]
            x = list(base)
            for p in r.sample(range(N), 2 if k % 3 else 3):
                x[p] ^= 0x80000000
            self.assertNotEqual(ch(x)[0], ch(base)[0], 'bit-31 flips case %d' % k)

    def test_single_bit_flips(self):
        r = random.Random(13)
        for k in range(3000):
            base = sparse_base(r) if k & 1 else [r.getrandbits(32) for _ in range(N)]
            x = list(base); x[r.randrange(N)] ^= 1 << r.randrange(32)
            hx, hb = ch(x), ch(base)
            self.assertNotEqual(hx[0], hb[0]); self.assertNotEqual(hx[1], hb[1])   # one word changed: both checks always differ

    def test_multi_word_changes(self):
        r = random.Random(17)
        for k in range(3000):
            base = sparse_base(r)
            x = list(base)
            for p in r.sample(range(N), r.randint(2, 64)):
                x[p] = r.getrandbits(32) if k % 4 else x[p] ^ (1 << r.randrange(32))
            if x != base:
                self.differ(x, base, 'multi-word case %d' % k)

    def test_tile_moves_swaps(self):
        r = random.Random(1)
        spr = [r.getrandbits(32) for _ in range(32)]
        a = [0] * N; a[0:32] = spr
        b = [0] * N; b[32:64] = spr
        self.differ(a, b, 'sprite moved by 4 tiles')
        d = [0] * N; d[0:32] = spr; d[32:64] = spr[::-1]
        e = [0] * N; e[0:32] = spr[::-1]; e[32:64] = spr
        self.differ(d, e, 'sprites swapped')
        r = random.Random(7)
        for _ in range(2000):
            base = sparse_base(r)
            n = r.randint(1, 16) * 8
            s, t = r.randrange(0, N - n, 8), r.randrange(0, N - n, 8)
            if abs(s - t) < n:
                continue
            x = list(base)
            x[t:t + n], x[s:s + n] = base[s:s + n], base[t:t + n]
            if x != base:
                self.differ(x, base, 'tile move/swap')

    def test_upload_decision(self):
        LIB.reset()
        t = ARR(*[7] * N)
        self.assertEqual(LIB.decide(t, 1, 1), 3)                           # first use: both textures uploaded
        for i in range(50):
            self.assertEqual(LIB.decide(t, 1, 1), 0, 'present %d' % i)    # unchanged: skipped
        u = ARR(*([7] * (N - 1) + [8]))
        self.assertEqual(LIB.decide(u, 1, 0), 1)                           # changed: the texture in use
        self.assertEqual(LIB.decide(u, 1, 1), 2)                           # the 8 bpp one still holds the old tiles
        self.assertEqual(LIB.decide(u, 1, 1), 0)
        v = list(u); v[0] ^= 0x80000000; v[32] ^= 0x80000000                # the review's change
        self.assertEqual(LIB.decide(ARR(*v), 1, 1), 3)

if __name__ == '__main__':
    unittest.main()

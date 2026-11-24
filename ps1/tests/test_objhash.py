"""The PP_DIRTY change detector of the OBJ tiles (stage19/ps1rt/ppu12.h pp_obj): when it says "unchanged" a block of the tile upload is
skipped, so a change it misses shows stale sprite graphics (since rc10.2 for less than 2 s: every used block is uploaded again by then).

History.  rc10 (first): rotate-by-5/xor plus a sum repeated every 32 words (tiles moved or swapped by one 16x16 sprite kept the hash).
rc10 review fix: djb2 (h*33+w) and sdbm (h*65599+w); both linear with odd multipliers, so adding 2^31 to any two words cancelled
(PR #26 review: a=[0]*4096, b[0]^=b[32]^=0x80000000 -> both 0x016a1505).  rc10.1: A per pair a=G(a+w0); a=G((a+w1)*0x9e3779b1),
G(x)=x^(x>>15), and B = djb2, no time bound.  An independent attack found edits confined to the top nibble of tile words that fooled both
(a 4 bpp pixel of column 7 moved by an even number of rows: about 1 in 744; 33 = 1 mod 32, 0x9e3779b1 = 1 mod 16, G(G(x)) = x^(x>>30)),
w0+=d, w1-=33d pairs (1 in 3000) and a built 4-word change, and a missed change stayed on the screen for good.
rc10.2: per block of 512 words two per-word mixers, A: a=(a+w)*0x85ebca6b; a^=a>>15 and B: b=(b^w)*0x27d4eb2f; b^=b>>13 (multipliers
3 mod 4, a right xorshift after every multiply, different constants, shifts and input operations), only the blocks the drawn sprites use
are checked, and every used block is uploaded again within 2 s (pp_objdec).

The C is tied to the test: the PP_OBJCK / PP_OBJDEC / PP_OBJMASK / PP_OBJZERO blocks are cut out of ppu12.h by text, compiled with the
host C compiler and called; the MIPS I loop is compiled for the PS1 and run under Unicorn against the C on samples of every class of the
miss search (objck_search.c, run here briefly; the long run is objck_search.py).  Synthetic data only."""
import ctypes
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import objck_search  # noqa: E402

PPU = HERE.parent / 'stage19' / 'ps1rt' / 'ppu12.h'
M = 0xffffffff
N = 4096
BW = 512
SOFT, HARD = 23437, 31250


def cut(name):
    s = PPU.read_text()
    m = re.search(r'(/\* %s BEGIN.*?/\* %s END \*/)' % (name, name), s, re.S)
    assert m, 'ppu12.h %s block not found' % name
    return m.group(1)


def consts():
    s = cut('PP_OBJCK')
    g = lambda n: int(re.search(r'#define %s (0x[0-9a-fA-F]+|\d+)u?' % n, s).group(1), 0)
    return {n: g(n) for n in ('PP_OBJCK_KA', 'PP_OBJCK_SA', 'PP_OBJCK_KB', 'PP_OBJCK_SB', 'PP_OBJCK_A0', 'PP_OBJCK_B0')}


C = consts()
HDR = ('typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8; typedef int s32;\n'
       '#define RTC64 1\n#define PP_OBJ_NB 8\n'
       'static const u8 PP_SZ[3][4][2]={{{8,8},{16,16},{32,32},{64,64}},{{16,8},{32,8},{32,16},{64,32}},{{8,16},{8,32},{16,32},{32,64}}};\n')


def build_lib():
    src = (HDR + cut('PP_OBJCK') + '\n' + cut('PP_OBJDEC') + '\n' + cut('PP_OBJMASK') + '\nstatic u32 pp_obj_z[2][16];\n' + cut('PP_OBJZERO') + '\n'
           'void objck(const u32*t,u32*o){ pp_objck(t,o); }\n'
           'void objdec(const u32*t,u32 m4,u32 m8,u32 now,u32*up){ pp_objdec(t,m4,m8,now,up); }\n'
           'void objmask(const u16*oam,int map1d,u32 bg2pri,u32*m){ pp_objmask(oam,map1d,bg2pri,m); }\n'
           'void objzero(const u32*s,int b8,u32 k,u32*z){ pp_objzero(s,b8,k); for(int i=0;i<32;i++) z[i]=pp_obj_z[i>>4][i&15]; }\n'
           'void reset(void){ for(int x=0;x<2;x++){ pp_obj_vm[x]=0; for(int k=0;k<PP_OBJ_NB;k++){ pp_obj_tl[x][k]=0; pp_obj_h[x][k][0]=pp_obj_h[x][k][1]=0; } } pp_nobjrf=pp_nobjblk=0; }\n'
           'u32 nrf(void){ return pp_nobjrf; }\n')
    d = Path(tempfile.mkdtemp(prefix='objhash'))
    (d / 'h.c').write_text(src)
    cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    subprocess.run([cc, '-O2', '-shared', '-fPIC', '-o', str(d / 'h.so'), str(d / 'h.c')], check=True)
    return ctypes.CDLL(str(d / 'h.so'))


def build_mips():
    """pp_objck as the PS1 build compiles it (the hand-scheduled MIPS I loop), linked at 0x80010000; None without clang/lld/unicorn"""
    clang, lld = shutil.which('clang'), shutil.which('ld.lld')
    try:
        import unicorn  # noqa
    except ImportError:
        return None
    if not clang or not lld or not shutil.which('llvm-nm') or not shutil.which('llvm-objcopy'):
        return None
    d = Path(tempfile.mkdtemp(prefix='objhash_mips'))
    (d / 'm.c').write_text('typedef unsigned int u32;\n' + cut('PP_OBJCK') + '\nvoid entry(const u32*t,u32*o){ pp_objck(t,o); }\n')
    f = ('--target=mipsel-none-elf -march=mips1 -mno-abicalls -mfp32 -msoft-float -fno-pic -O2 -ffreestanding -G0 -mno-gpopt '
         '-mllvm -disable-mips-delay-filler -DPP_DIRTY').split()
    subprocess.run([clang] + f + ['-c', '-o', str(d / 'm.o'), str(d / 'm.c')], check=True, capture_output=True)
    subprocess.run([lld, '-Ttext=0x80010000', '-e', 'entry', '-o', str(d / 'm.elf'), str(d / 'm.o')], check=True)
    nm = subprocess.run(['llvm-nm', str(d / 'm.elf')], capture_output=True, text=True, check=True).stdout
    sym = {l.split()[2]: int(l.split()[0], 16) for l in nm.splitlines() if len(l.split()) == 3}
    subprocess.run(['llvm-objcopy', '-O', 'binary', '--only-section=.text', str(d / 'm.elf'), str(d / 'm.bin')], check=True)
    dis = subprocess.run(['llvm-objdump', '-d', '--no-show-raw-insn', str(d / 'm.elf')], capture_output=True, text=True).stdout
    return (d / 'm.bin').read_bytes(), sym['entry'], sym['pp_objck'], dis


LIB = build_lib()
LIB.objck.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
LIB.objdec.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
LIB.objmask.argtypes = [ctypes.POINTER(ctypes.c_uint16), ctypes.c_int, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
LIB.objzero.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_int, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
LIB.nrf.restype = ctypes.c_uint32
MIPS = build_mips()


def ck(block):
    """the C check (A, B) of one block of 512 words"""
    o = (ctypes.c_uint32 * 2)()
    LIB.objck((ctypes.c_uint32 * BW)(*block), o)
    return o[0], o[1]


def blocks(t):
    return [ck(t[k * BW:(k + 1) * BW]) for k in range(N // BW)]


def model(block):
    a, b = C['PP_OBJCK_A0'], C['PP_OBJCK_B0']
    for w in block:
        a = ((a + w) * C['PP_OBJCK_KA']) & M; a ^= a >> C['PP_OBJCK_SA']
        b = ((b ^ w) * C['PP_OBJCK_KB']) & M; b ^= b >> C['PP_OBJCK_SB']
    return a, b


def rc101(t):
    """the rc10.1 check over 4096 words (A|1, B), for the attack fixtures"""
    G = lambda x: x ^ (x >> 15)
    a, b = 0x811c9dc5, 5381
    for i in range(0, N, 2):
        w0, w1 = t[i], t[i + 1]
        a = G((a + w0) & M); a = G(((a + w1) * 0x9e3779b1) & M)
        b = (b * 33 + w0) & M; b = (b * 33 + w1) & M
    return a | 1, b


class Mips:
    def __init__(self):
        from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
        self.code, self.entry, self.fn, self.dis = MIPS
        self.u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.u.mem_map(0, 0x200000)                      # KSEG0 0x80000000.. is physical 0.. (Unicorn translates it like the PS1)
        self.u.mem_write(0x10000, self.code)

    def ck(self, block):
        from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_RA, UC_MIPS_REG_SP
        tile, out, stop = 0x80100000, 0x80180000, 0x80001000
        self.u.mem_write(tile & 0x1fffffff, struct.pack('<%dI' % BW, *block) + b'\xa5\x5a\x3c\xc3' * 2)   # + the two words past the end the loop reads
        self.u.reg_write(UC_MIPS_REG_A0, tile); self.u.reg_write(UC_MIPS_REG_A1, out)
        self.u.reg_write(UC_MIPS_REG_RA, stop); self.u.reg_write(UC_MIPS_REG_SP, 0x80070000)
        self.u.emu_start(self.entry, stop, count=40000)
        return struct.unpack('<2I', self.u.mem_read(out & 0x1fffffff, 8))


def search_dump(tries, k, seed=7):
    """run objck_search briefly; returns (exit code, stdout, [(class, base, changed)])"""
    exe = objck_search.build()
    d = Path(tempfile.mkdtemp(prefix='objck_dump')) / 'dump.bin'
    p = subprocess.run([str(exe), str(tries), str(seed), '-1', str(d), str(k)], capture_output=True, text=True)
    raw = d.read_bytes(); rec = 4 + 8 * N; out = []
    for i in range(0, len(raw) - rec + 1, rec):
        c = struct.unpack_from('<I', raw, i)[0]
        out.append((c, list(struct.unpack_from('<%dI' % N, raw, i + 4)), list(struct.unpack_from('<%dI' % N, raw, i + 4 + 4 * N))))
    return p.returncode, p.stdout, out


class Check(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rc, cls.out, cls.samples = search_dump(20000, 6)

    def test_constants(self):
        """requirement of rc10.2: multipliers not 1 modulo 4 (so not 1 modulo any power of two above 2), different constants and shifts"""
        for k in ('PP_OBJCK_KA', 'PP_OBJCK_KB'):
            self.assertEqual(C[k] & 3, 3, k)
        self.assertNotEqual(C['PP_OBJCK_KA'], C['PP_OBJCK_KB']); self.assertNotEqual(C['PP_OBJCK_SA'], C['PP_OBJCK_SB'])

    def test_c_matches_model(self):
        r = random.Random(3)
        for k in range(60):
            b = [0] * BW if k == 0 else ([r.getrandbits(32) for _ in range(BW)] if k & 1 else [r.getrandbits(32) if r.random() < .1 else 0 for _ in range(BW)])
            self.assertEqual(ck(b), model(b))
        self.assertNotEqual(ck([0] * BW), (0, 0))         # an all-zero block never looks like "never checked"

    def test_search_short(self):
        """every class of objck_search.c, 20,000 tries each: no miss; the built classes really cancel the check they were built for"""
        self.assertEqual(self.rc, 0, self.out)
        rows = {int(m.group(1)): (int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))
                for m in re.finditer(r'class +(\d+) .*?tries +(\d+) misses (\d+)  A-equal (\d+)  B-equal (\d+)', self.out)}
        self.assertGreaterEqual(len(rows), 15)
        for c, (t, miss, ae, be) in rows.items():
            self.assertGreaterEqual(t, 20000, 'class %d' % c); self.assertEqual(miss, 0, 'class %d' % c)
        self.assertGreater(rows[7][2], rows[7][0] * 0.95); self.assertGreater(rows[9][3], rows[9][0] * 0.95)

    @unittest.skipIf(MIPS is None, 'needs clang, ld.lld, llvm tools and unicorn')
    def test_mips_matches_c_on_search_classes(self):
        """the MIPS I loop under Unicorn = the C, on the changed blocks of samples of every search class, on the bases, and edge blocks"""
        mp = Mips(); r = random.Random(5); seen = set(); n = 0
        edge = [[0] * BW, [M] * BW, [0x80000000] * BW, [r.getrandbits(32) for _ in range(BW)]]
        for b in edge:
            self.assertEqual(mp.ck(b), ck(b))
        for c, base, x in self.samples:
            seen.add(c)
            ch = [k for k in range(N // BW) if base[k * BW:(k + 1) * BW] != x[k * BW:(k + 1) * BW]]
            self.assertTrue(ch)
            for k in ch[:2]:
                bx, bb = x[k * BW:(k + 1) * BW], base[k * BW:(k + 1) * BW]
                hx = mp.ck(bx); self.assertEqual(hx, ck(bx), 'class %d' % c); n += 1
                if n % 4 == 0:
                    self.assertEqual(mp.ck(bb), ck(bb))
            self.assertTrue(any(blocks(x)[k] != blocks(base)[k] for k in ch), 'class %d sample missed' % c)
        self.assertGreaterEqual(len(seen), 15)

    @unittest.skipIf(MIPS is None, 'needs clang, ld.lld, llvm tools and unicorn')
    def test_mips_schedule(self):
        """MIPS I rules in the hand-scheduled loop: no MULT/DIV within two instructions after MFLO/MFHI; a loaded register not used by the next instruction"""
        lines = [l.split('\t') for l in MIPS[3].splitlines() if re.match(r'\s*[0-9a-f]+:\s', l)]
        ins = [(p[1].strip() if len(p) > 1 else '', p[2] if len(p) > 2 else '') for p in lines]
        body = [i for i in ins]
        for j, (op, args) in enumerate(body):
            if op in ('mflo', 'mfhi'):
                for q in body[j + 1:j + 3]:
                    self.assertNotIn(q[0], ('mult', 'multu', 'div', 'divu'), 'MULT within two after %s' % op)
            if op in ('lw', 'lh', 'lhu', 'lb', 'lbu') and j + 1 < len(body):
                reg = args.split(',')[0].strip()
                nxt = body[j + 1][1]
                self.assertNotIn(reg, [a.strip().split('(')[-1].rstrip(')') for a in nxt.split(',')[1:]] + ([nxt.split(',')[0].strip()] if body[j + 1][0] in ('sw', 'sh', 'sb', 'bne', 'beq') else []),
                                 'load delay: %s %s then %s %s' % (op, args, body[j + 1][0], nxt))
        self.assertEqual(sum(1 for o, _ in body if o == 'multu'), 4)

    def test_rc101_attacks_fixed(self):
        """the attacks on rc10.1: its check equal, rc10.2 tells them apart"""
        r = random.Random(9)
        # F1: tile 521 (slot 9), a pixel of column 7 moved two rows: words 73 and 75 (example of the report)
        t = [0] * N; t[73] = 0x00213103; t[75] = 0x22330022
        u = list(t); u[73] = 0x20213103; u[75] = 0x02330022
        self.assertEqual(rc101(t), rc101(u))
        self.assertNotEqual(blocks(t), blocks(u))
        # F1 generalised: +c<<28 / -c<<28 at distance 2 on sprite-like tiles; F2: w0+d, w1-33d
        n1 = n2 = 0
        for k in range(400):
            base = [sum(r.choice([0, 0, 1, 2, 3]) << (4 * q) for q in range(8)) if r.random() < .5 else 0 for _ in range(N)]
            i = r.randrange(0, N - 2); c = r.randrange(1, 16)
            x = list(base); x[i] = (x[i] + (c << 28)) & M; x[i + 2] = (x[i + 2] - (c << 28)) & M
            n1 += rc101(x) == rc101(base)
            self.assertNotEqual(blocks(x), blocks(base))
            p = r.randrange(0, N, 2); d = r.randrange(1, 1 << 16)
            y = list(base); y[p] = (y[p] + d) & M; y[p + 1] = (y[p + 1] - 33 * d) & M
            n2 += rc101(y) == rc101(base)
            self.assertNotEqual(blocks(y), blocks(base))
        self.assertGreater(n1, 0)                             # the rc10.1 check really missed some of them

    def test_review_fixture(self):
        a = [0] * N
        b = list(a); b[0] ^= 0x80000000; b[32] ^= 0x80000000
        self.assertNotEqual(blocks(a), blocks(b))
        self.assertNotEqual(blocks(a)[0][0], blocks(b)[0][0]); self.assertNotEqual(blocks(a)[0][1], blocks(b)[0][1])

    def test_single_word_always(self):
        """each step is a bijection: one changed word always changes A and B of its block"""
        r = random.Random(13)
        for k in range(2000):
            b = [r.getrandbits(32) if k & 1 else 0 for _ in range(BW)]
            x = list(b); i = r.randrange(BW); x[i] ^= (1 << r.randrange(32)) if k % 3 else (r.getrandbits(32) or 1)
            hx, hb = ck(x), ck(b)
            self.assertNotEqual(hx[0], hb[0]); self.assertNotEqual(hx[1], hb[1])


class Decision(unittest.TestCase):
    def dec(self, t, m4, m8, now):
        up = (ctypes.c_uint32 * 2)()
        LIB.objdec((ctypes.c_uint32 * N)(*t), m4, m8, now & M, up)
        return up[0], up[1]

    def test_upload_decision(self):
        LIB.reset(); t = [7] * N; now = 1000
        self.assertEqual(self.dec(t, 0x0f, 0x30, now), (0x0f, 0x30))      # first use: the used blocks of each texture
        for i in range(30):
            self.assertEqual(self.dec(t, 0x0f, 0x30, now + i * 100), (0, 0), 'present %d' % i)
        self.assertEqual(self.dec(t, 0xff, 0x30, now + 3000), (0xf0, 0))   # blocks used for the first time
        u = list(t); u[2 * BW + 5] ^= 1 << 30                               # block 2 changed
        self.assertEqual(self.dec(u, 0xff, 0x34, now + 3100), (0x04, 0x04))
        self.assertEqual(self.dec(u, 0xff, 0x34, now + 3200), (0, 0))
        v = list(u); v[6 * BW] ^= 0x80000000; v[6 * BW + 32] ^= 0x80000000  # the review's change, in block 6 (used by neither texture)
        self.assertEqual(self.dec(v, 0x3f, 0x34, now + 3300), (0, 0))      # not used: not checked
        self.assertEqual(self.dec(v, 0x40, 0x00, now + 3400), (0x40, 0))   # used again: uploaded

    def test_refresh_bound(self):
        """a block whose upload is 1.5 s old is uploaded again, one per present (oldest first); none is ever used 2 s after its upload"""
        LIB.reset(); t = [5] * N; now = 50000
        self.assertEqual(self.dec(t, 0xff, 0, now), (0xff, 0))
        self.assertEqual(self.dec(t, 0xff, 0, now + SOFT - 1), (0, 0))
        got = []
        for i in range(8):
            u4, u8 = self.dec(t, 0xff, 0, now + SOFT + i)
            self.assertEqual(bin(u4).count('1'), 1); self.assertEqual(u8, 0); got.append(u4)
        self.assertEqual(sorted(got), [1 << k for k in range(8)])
        # presents far apart: everything past the hard bound at once
        LIB.reset(); self.dec(t, 0x0f, 0x0f, 0)
        self.assertEqual(self.dec(t, 0x0f, 0x0f, HARD), (0x0f, 0x0f))
        # wrap of the line clock
        LIB.reset(); self.dec(t, 0x01, 0, M - 100)
        self.assertEqual(self.dec(t, 0x01, 0, 200), (0, 0)); self.assertEqual(self.dec(t, 0x01, 0, HARD), (0x01, 0))

    def test_refresh_simulated(self):
        """presents at 1..60 per second with random used blocks: the age of every used block at a present never reaches 2 s"""
        r = random.Random(4); t = [1] * N
        for rate in (1, 3, 12, 22, 60):
            LIB.reset(); now = 7; dt = 15734 // rate; last = {}
            for p in range(600):
                m4, m8 = r.getrandbits(8) | 1, r.getrandbits(8) & r.getrandbits(8)
                u4, u8 = self.dec(t, m4, m8, now)
                for x, (m, u) in enumerate(((m4, u4), (m8, u8))):
                    for k in range(8):
                        if (u >> k) & 1: last[(x, k)] = now
                        if (m >> k) & 1: self.assertLess(now - last[(x, k)], HARD + 1, 'rate %d present %d' % (rate, p))
                now += dt + r.randrange(-dt // 4, dt // 4 + 1)


SZ = [[(8, 8), (16, 16), (32, 32), (64, 64)], [(16, 8), (32, 8), (32, 16), (64, 32)], [(8, 16), (8, 32), (16, 32), (32, 64)]]


def drawn_slots(oam, map1d, bg2pri):
    """the tile slots pp_obj's drawing loop draws (its own tests, copied), per texture"""
    s = [set(), set()]
    for i in range(128):
        a0, a1, a2 = oam[i * 4], oam[i * 4 + 1], oam[i * 4 + 2]
        aff, dbl = (a0 >> 8) & 1, (a0 >> 9) & 1
        if not aff and dbl: continue
        if ((a2 >> 10) & 3) > bg2pri: continue
        if ((a0 >> 10) & 3) == 2: continue
        sh, sz = a0 >> 14, a1 >> 14
        if sh > 2: continue
        w, h = SZ[sh][sz]; bw, bh = (2 * w, 2 * h) if dbl else (w, h)
        y = a0 & 255; y = y - 256 if y >= 160 else y; x = a1 & 511; x = x - 512 if x >= 256 else x
        if x <= -bw or y <= -bh or x >= 240: continue
        tile = a2 & 1023
        if tile < 512: continue
        b8 = (a0 >> 13) & 1; tw, th = w // 8, h // 8
        for ty in range(th):
            for tx in range(tw):
                slot = tile + (ty * tw + tx) * (2 if b8 else 1) if map1d else tile + ty * 32 + tx * (2 if b8 else 1)
                slot -= 512
                if slot >= 512: continue
                s[b8].add(slot)
                if b8: s[b8].add(slot ^ 1)        # the 8 bpp texture tile n = slot>>1 holds slots 2n, 2n+1
    return s


class Masks(unittest.TestCase):
    def test_mask_covers_drawn_tiles(self):
        r = random.Random(21)
        for k in range(400):
            oam = [0] * 512
            for i in range(128):
                if r.random() < .3:
                    oam[i * 4] = r.getrandbits(16); oam[i * 4 + 1] = r.getrandbits(16); oam[i * 4 + 2] = r.getrandbits(16) | (512 if r.random() < .8 else 0)
                else:
                    oam[i * 4] = 0x200          # disabled
            map1d, bg2pri = r.getrandbits(1), r.choice((0, 1, 2, 3, 4))
            m = (ctypes.c_uint32 * 2)()
            LIB.objmask((ctypes.c_uint16 * 512)(*oam), map1d, bg2pri, m)
            s = drawn_slots(oam, map1d, bg2pri)
            for x in range(2):
                need = 0
                for sl in s[x]: need |= 1 << (sl >> 6)
                self.assertEqual(need & ~m[x], 0, 'case %d texture %d: drawn blocks %s mask %s' % (k, x, bin(need), bin(m[x])))

    def test_mask_none(self):
        m = (ctypes.c_uint32 * 2)()
        LIB.objmask((ctypes.c_uint16 * 512)(*([0x200, 0, 600, 0] * 128)), 1, 4, m)
        self.assertEqual((m[0], m[1]), (0, 0))

    def test_zero_tiles(self):
        r = random.Random(8)
        t = [0] * N
        for i in range(N):
            if r.random() < .02: t[i] = 1 << r.randrange(32)
        z = (ctypes.c_uint32 * 32)()
        for b8 in (0, 1):
            for k in range(8):
                LIB.objzero((ctypes.c_uint32 * N)(*t), b8, k, z)
            tw = 16 if b8 else 8
            for n in range(N // tw):
                self.assertEqual((z[b8 * 16 + (n >> 5)] >> (n & 31)) & 1, int(not any(t[n * tw:(n + 1) * tw])))


if __name__ == '__main__':
    unittest.main()

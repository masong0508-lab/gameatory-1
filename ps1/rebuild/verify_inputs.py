#!/usr/bin/env python3
"""verify_inputs.py: can the surviving private PS1 inputs be used unchanged with the PR's RAM/VRAM layout?

Reads only.  usage: verify_inputs.py PRIVATE_OUT_DIR PREPARED_TREE [STAGE7_OUT_DIR]
  PRIVATE_OUT_DIR  directory with boot.bin, SF3M.BIN, pr_l/, pr_lb/, s2/prog_pr.pkl, touched_f1_boot.pkl.rompages
  PREPARED_TREE    output of ps1/tools/prepare.py --output (its linker script, rt.c, headers and t2m.py are the reference)
  STAGE7_OUT_DIR   optional: the full stage 7 pipeline output (pr_f1, pr_f2, pr_f2b ...) to show what the OLD gap put where
Every check prints PASS/FAIL with the numbers it used; exit status 1 if any check failed."""
import sys, os, re, struct, pickle, hashlib, collections

PRIV, TREE = sys.argv[1], sys.argv[2]
S7 = sys.argv[3] if len(sys.argv) > 3 else None
fails = []


def check(ok, what):
    print(('PASS  ' if ok else 'FAIL  ') + what)
    if not ok:
        fails.append(what)
    return ok


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def rd(p):
    return open(p, 'rb').read()


# ------------------------------------------------------------------ reference layout from the prepared tree
ld = open(TREE + '/ps1rt/ps1.ld').read()
rt = open(TREE + '/ps1rt/rt.c').read()
sfmem = open(TREE + '/sf/sfmem.h').read()
vram = dict((k, int(v)) for k, v in re.findall(r'^#define PS1_VRAM_(\w+) (\d+)$', open(TREE + '/include/ps1_vram.h').read(), re.M))
PPU = int(re.search(r'\.\s*=\s*(0x[0-9a-fA-F]+);\s*\.ppuscratch', ld)[1], 16)
BLOB = int(re.search(r'\.\s*=\s*(0x[0-9a-fA-F]+);\s*\.blob', ld)[1], 16)
COLDTAB = int(re.search(r'\.\s*=\s*(0x[0-9a-fA-F]+);\s*\.coldtab', ld)[1], 16)
SF = int(re.search(r'\.\s*=\s*(0x[0-9a-fA-F]+);\s*\.sf ', ld)[1], 16)
RTLIM = int(re.search(r'ASSERT\(\. < (0x[0-9a-fA-F]+), "C runtime', ld)[1], 16)
rtdef = lambda n: int(re.search(r'#define %s \(\([^)]*\)(0x[0-9a-fA-F]+)\)' % n, rt)[1], 16)
RT = {n: rtdef(n) for n in ('HELP', 'EW', 'IW', 'PAL', 'OAM', 'VRAM', 'DL')}
SFM = {n: int(v, 16) for n, v in re.findall(r'#define (SF_\w+)\s+(0x[0-9a-fA-F]+)u', sfmem)}
print('reference layout (prepared tree): blob 0x%08x, coldtab 0x%08x, PPU scratch 0x%08x, veneer scratch 0x%08x, draw ring 0x%08x, renderer 0x%08x, runtime limit 0x%08x' % (BLOB, COLDTAB, PPU, PPU + 0x1000, RT['DL'], SF, RTLIM))
print('  rt.c windows:', {k: hex(v) for k, v in RT.items()}, ' sfmem:', {k: hex(v) for k, v in SFM.items()})
sys.path.insert(0, TREE)
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
sys.dont_write_bytecode = True
# t2m imports prune, which reads t/swi5.bin at import time; only the Cfg class is needed here, so read it textually
src = open(TREE + '/t2m.py').read()
m = re.search(r"if mode=='P':.*?s\.BASE=(0x[0-9a-f]+); s\.DL=(0x[0-9a-f]+)\s+s\.reg=\[(.*?)\]\s+elif", src, re.S)
CFG_BASE, CFG_DL = int(m[1], 16), int(m[2], 16)
CFG_REG = [tuple(int(x, 16) for x in t) for t in re.findall(r'\((0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+)\)', m[3])]
CFG_HELP = int(re.search(r'HELP=(0x[0-9a-f]+)', src)[1], 16)
check(CFG_BASE == BLOB, 'translator blob base 0x%08x == linker .blob 0x%08x' % (CFG_BASE, BLOB))
check(CFG_DL == RT['DL'], 'translator draw ring 0x%08x == rt.c DL 0x%08x' % (CFG_DL, RT['DL']))
check(CFG_HELP == RT['HELP'], 'translator helper table 0x%08x == rt.c HELP 0x%08x' % (CFG_HELP, RT['HELP']))
want = {0x02000000: RT['EW'], 0x03000000: RT['IW'], 0x05000000: RT['PAL'], 0x06000000: RT['VRAM'], 0x07000000: RT['OAM'], 0x04000000: 0x8017f000}
check(all(want[g] == h for g, n, h in CFG_REG), 'translator guest windows == rt.c windows: ' + ', '.join('%08x->%08x' % (g, h) for g, n, h in CFG_REG))
check('ea-0x8017f000u<0x400' in rt, 'rt.c still serves the guest I/O window at 0x8017f000')
check(RT['DL'] == PPU + 0x2000, 'scratch 0x%08x..0x%08x ends exactly at the draw ring' % (PPU, PPU + 0x2000))

# ------------------------------------------------------------------ translations
def coldtab(p):
    d = rd(p)
    n = struct.unpack_from('<I', d, 0)[0]
    assert len(d) == 4 + 16 * n, (len(d), n)
    return [struct.unpack_from('<4I', d, 4 + 16 * i) for i in range(n)]


def hostmap(p):
    return [int(l.split()[1], 16) for l in open(p)]


def translation(d, name, physical=True):
    print('--- translation %s (%s)' % (name, d))
    meta = pickle.load(open(d + '/meta_P.pkl', 'rb'))
    cs, ce = meta['cold']['start'], meta['cold']['end']
    hot = os.path.getsize(d + '/payback_P.bin')
    cold = os.path.getsize(d + '/cold_P.bin')
    rows = coldtab(d + '/coldtab_P.bin')
    hm = hostmap(d + '/payback_P.map')
    lo = min(r[2] for r in rows)
    hi = max(r[3] for r in rows)
    print('  hot blob %d bytes 0x%08x..0x%08x, cold code %d bytes, home 0x%08x..0x%08x (meta end 0x%08x), %d table rows, spans 0x%08x..0x%08x, map hosts 0x%08x..0x%08x' % (
        hot, CFG_BASE, CFG_BASE + hot, cold, cs, cs + cold, ce, len(rows), lo, hi, min(hm), max(hm)))
    check(cs == CFG_BASE + hot, '%s: cold home starts where the hot blob ends (0x%08x)' % (name, cs))
    gapped = (ce - cs) != cold
    inres = [r for r in rows if r[3] > PPU and r[2] < 0x80200000]
    inres_map = [h for h in hm if PPU <= h < 0x80200000]
    if physical:
        check(not gapped and cs + cold == ce, '%s: contiguous cold prefix, file size == meta range' % name)
        check(hi <= cs + cold, '%s: every table span ends inside the cold file (max 0x%08x <= 0x%08x)' % (name, hi, cs + cold))
        check(max(hm) < PPU, '%s: highest translated host address 0x%08x is below the PPU scratch 0x%08x (margin %d bytes)' % (name, max(hm), PPU, PPU - max(hm)))
        check(not inres and not inres_map, '%s: no table span and no map entry inside 0x%08x..0x80200000' % (name, PPU))
        ng = (cold + 16383) // 16384
        coldgroups = int(re.search(r'#define COLDGROUPS (\d+)', rt)[1])
        check(ng <= coldgroups, '%s: %d overlay groups of 16 KiB <= COLDGROUPS %d' % (name, ng, coldgroups))
        check(cs + ng * 16384 <= COLDTAB, '%s: last overlay group ends 0x%08x <= coldtab 0x%08x' % (name, cs + ng * 16384, COLDTAB))
        tabend = COLDTAB + os.path.getsize(d + '/coldtab_P.bin')
        print('  coldtab occupies 0x%08x..0x%08x' % (COLDTAB, tabend))
    else:
        print('  full-cold (simulator) translation: %d spans and %d map entries lie in 0x%08x..0x80200000' % (len(inres), len(inres_map), PPU))
        if inres:
            a = sorted(inres, key=lambda r: r[2])
            print('    first: guest 0x%08x host span 0x%08x..0x%08x; last: guest 0x%08x host span 0x%08x..0x%08x' % (a[0][0], a[0][2], a[0][3], a[-1][0], a[-1][2], a[-1][3]))
            scr = [r for r in rows if r[3] > PPU and r[2] < PPU + 0x2000]
            print('    of these %d overlap the PPU/veneer scratch 0x%08x..0x%08x itself' % (len(scr), PPU, PPU + 0x2000))
    return dict(meta=meta, cs=cs, cold=cold, rows=rows, hot=hot)


L = translation(PRIV + '/pr_l', 'pr_l')
LB = translation(PRIV + '/pr_lb', 'pr_lb')
check(sha(PRIV + '/pr_l/payback_P.bin') == sha(PRIV + '/pr_lb/payback_P.bin'), 'pr_l and pr_lb share one hot blob (sha256 %s)' % sha(PRIV + '/pr_l/payback_P.bin')[:16])
# world window (t/worldaddr.py with WORLDPRD=pr_l)
w = (L['cs'] + ((L['cold'] + 2047) & ~2047) + 2047) & ~2047
check(SFM['SF_PBUF'] - w >= 239616, 'world window 0x%08x..0x%08x holds %d bytes (need 239616); pr_l prefix may grow by at most %d bytes before it no longer does' % (
    w, SFM['SF_PBUF'], SFM['SF_PBUF'] - w, (SFM['SF_PBUF'] - 239616) - (L['cs'] + L['cold'])))
# resident hash / helper symbols used by mkps1.py
for k in ('HASH', 'HEND', 'RT_BX', 'RT_STUB', 'RT_MISS', 'RT_MEMRD_SLOW', 'RT_MEMWR', 'RT_VBL'):
    if k not in LB['meta']['rt']:
        check(False, 'pr_lb meta lacks runtime label ' + k)
print('  pr_lb runtime labels: HASH 0x%08x HEND 0x%08x RT_BX 0x%08x RT_STUB 0x%08x' % tuple(LB['meta']['rt'][k] for k in ('HASH', 'HEND', 'RT_BX', 'RT_STUB')))

# absolute addresses the hot blob itself materialises with lui/ori|addiu pairs (helper table, draw ring, private stack, guest windows)
def lui_consts(code, base):
    out = collections.Counter()
    ws = struct.unpack('<%dI' % (len(code) // 4), code[:len(code) // 4 * 4])
    for i, wd in enumerate(ws[:-1]):
        if wd >> 26 == 0x0f:
            rt_ = (wd >> 16) & 31
            nx = ws[i + 1]
            hi = (wd & 0xffff) << 16
            if nx >> 26 == 0x0d and ((nx >> 21) & 31) == rt_:
                out[hi | (nx & 0xffff)] += 1
            elif nx >> 26 == 0x09 and ((nx >> 21) & 31) == rt_:
                out[(hi + ((nx & 0xffff) ^ 0x8000) - 0x8000) & 0xffffffff] += 1
            else:
                out[hi] += 1
    return out


for nm, T in (('pr_lb hot blob', rd(PRIV + '/pr_lb/payback_P.bin')), ('pr_lb cold code', rd(PRIV + '/pr_lb/cold_P.bin'))):
    c = lui_consts(T, 0)
    host = {v: n for v, n in c.items() if 0x80000000 <= v < 0x80200000}
    reg = collections.Counter()
    for v, n in host.items():
        if v < 0x80010000: r = 'below EXE'
        elif v < 0x80028000: r = 'C runtime 0x80010000..0x80028000'
        elif v < 0x80030000: r = 'helper table / interp stacks 0x80028000..0x80030000'
        elif v < LB['cs']: r = 'hot blob'
        elif v < LB['cs'] + LB['cold']: r = 'cold prefix'
        elif v < PPU: r = 'ABOVE COLD PREFIX, BELOW SCRATCH'
        elif v < PPU + 0x2000: r = 'PPU/VENEER SCRATCH'
        elif v < 0x8017f000: r = 'draw ring 0x8017c000..'
        elif v < 0x80180000: r = 'guest I/O window 0x8017f000'
        elif v < 0x80199000: r = 'PAL/OAM/VRAM shadow'
        elif v < 0x801b0000: r = 'RENDERER 0x80199000..0x801b0000'
        elif v < 0x801f8000: r = 'guest EWRAM/IWRAM'
        else: r = 'stack area 0x801f8000..'
        reg[r] += n
    print('  %s: lui-built host constants by region: %s' % (nm, dict(reg)))
    bad = [(hex(v), n) for v, n in host.items() if PPU <= v < PPU + 0x2000 or (LB['cs'] + LB['cold'] <= v < PPU and v >= 0x80030000)]
    check(not bad, '%s: no constant points into the scratch or into unowned RAM between the cold prefix and the scratch %s' % (nm, bad[:6]))

# ------------------------------------------------------------------ boot image
print('--- boot.bin')
b = rd(PRIV + '/boot.bin')
exp = 160 + 0x40000 + 0x8000 + 0x400 + 0x18000 + 0x400 + 0x400
check(len(b) == exp, 'boot.bin is 160-byte header + EWRAM + IWRAM + PAL + VRAM + OAM + I/O = %d bytes (file %d)' % (exp, len(b)))
regs = struct.unpack_from('<32I', b, 0)
st = struct.unpack_from('<8I', b, 128)
print('  regs r0..r7 ($16..$23) %s sp($30) 0x%08x lr($31) 0x%08x; io state %s' % ([hex(x) for x in regs[16:24]], regs[30], regs[31], st))
check(RT['IW'] <= regs[30] <= RT['IW'] + 0x8000, 'guest sp 0x%08x lies in the IWRAM window' % regs[30])
img = b[160:]
ws = struct.unpack('<%dI' % (len(img) // 4), img)
hosts = collections.Counter()
for v in ws:
    if 0x80010000 <= v < 0x80200000:
        if v < 0x80030000: hosts['runtime/helpers'] += 1
        elif v < 0x80044c88: hosts['hot blob'] += 1
        elif v < PPU: hosts['cold/world/tables/cache/ragdoll area'] += 1
        elif v < PPU + 0x2000: hosts['PPU/veneer scratch'] += 1
        elif v < 0x80180000: hosts['draw ring / IO window'] += 1
        elif v < 0x80199000: hosts['PAL/OAM/VRAM shadow'] += 1
        elif v < 0x801b0000: hosts['renderer region'] += 1
        else: hosts['EWRAM/IWRAM windows'] += 1
print('  words of the memory image that look like host addresses, by region:', dict(hosts))
check(hosts['PPU/veneer scratch'] == 0 and hosts['renderer region'] == 0 and hosts['cold/world/tables/cache/ragdoll area'] == 0,
      'boot image holds no pointer into the scratch, the renderer or the relocatable middle of RAM')

# ------------------------------------------------------------------ world pack
print('--- SF3M.BIN')
d = rd(PRIV + '/SF3M.BIN')
magic, n = struct.unpack_from('<4sI', d, 0)
check(magic == b'SF3M' and n == 11, 'SF3M header: magic %r, %d maps, %d bytes, %d sectors' % (magic, n, len(d), len(d) // 2048))
regions = [('display buffers', 0, 0, 320, 480), ('MODEL', vram['MODEL_X'], vram['MODEL_Y'], vram['MODEL_W'], vram['MODEL_H']),
           ('MODEL_CLUT', vram['MODEL_CLUT_X'], vram['MODEL_CLUT_Y'], vram['MODEL_CLUT_W'], vram['MODEL_CLUT_H']),
           ('PPU_L1', vram['PPU_L1_X'], vram['PPU_L1_Y'], vram['PPU_L1_W'], vram['PPU_L1_H']),
           ('PPU_CLUT', vram['PPU_CLUT_X'], vram['PPU_CLUT_Y'], vram['PPU_CLUT_W'], vram['PPU_CLUT_H']),
           ('PPU_OBJ4', vram['PPU_OBJ_X'], vram['PPU_OBJ4_Y'], vram['PPU_OBJ_W'], vram['PPU_OBJ_H']),
           ('PPU_OBJ8', vram['PPU_OBJ_X'], vram['PPU_OBJ8_Y'], vram['PPU_OBJ_W'], vram['PPU_OBJ_H'])]
for pg in range(vram['PPU_ATLAS_PAGES']):
    regions.append(('PPU cache %d' % pg, vram['PPU_ATLAS_X'] + pg * vram['PPU_ATLAS_PAGE_W'], vram['PPU_ATLAS_Y'], vram['PPU_ATLAS_PAGE_W'], vram['PPU_ATLAS_PAGE_H']))


def clash(x, y, w_, h_):
    return [nm for nm, ox, oy, ow, oh in regions if x < ox + ow and ox < x + w_ and y < oy + oh and oy < y + h_]


maxw = 0; allrects = set(); fontrects = set(); bad = []; sides = []; total = 1
for i in range(n):
    first, wsec, asec, sbytes, sx, sy, sz, z = struct.unpack_from('<8I', d, 8 + 32 * i)
    wb = d[first * 2048:(first + wsec) * 2048]
    if wb[:4] != b'SF3W': bad.append('map %d world magic' % i)
    maxw = max(maxw, wsec * 2048)
    a = d[(first + wsec) * 2048:(first + wsec + asec) * 2048]
    npg, nclut, nfont, _ = struct.unpack_from('<4I', a, 0)
    rc = struct.unpack_from('<%dH' % (4 * npg), a, 16)
    for k in range(npg):
        x, y = rc[4 * k], rc[4 * k + 1]
        allrects.add((x, y)); c = clash(x, y, 128, 256)
        if c or not (0 <= x and x + 128 <= 1024 and 0 <= y and y + 256 <= 512): bad.append('map %d atlas page %d at (%d,%d) clashes with %s' % (i, k, x, y, c))
    fo = 2048 + npg * 65536 + ((nclut + 2047) & ~2047)
    fx, fy, fw, fh = struct.unpack_from('<4H', a, fo)
    fontrects.add((fx, fy, fw, fh)); c = clash(fx, fy, fw, fh)
    if c: bad.append('map %d font rect %s clashes with %s' % (i, (fx, fy, fw, fh), c))
    if nclut > 256 * 8 * 2: bad.append('map %d clut %d bytes' % (i, nclut))
    sides.append(sbytes - 8192)
    total = max(total, first + wsec + asec + (sbytes + 2047) // 2048)
    print('  map %2d: first sector %4d, world %6d bytes, atlas %d pages at %s, clut %d, font %s, side fields %d bytes, start (%d,%d,%d)' % (
        i, first, wsec * 2048, npg, [(rc[4 * k], rc[4 * k + 1]) for k in range(npg)], nclut, (fx, fy, fw, fh), sbytes - 8192, sx, sy, sz))
check(not bad, 'every map: SF3W magic, atlas pages and font outside the model, PPU and display regions of include/ps1_vram.h %s' % bad[:4])
slots = {(320 + 128 * (p % 5), 256 * (p // 5)) for p in range(7)}
check(allrects <= slots, 'atlas pages only use the 7 world page slots %s' % sorted(allrects))
for nm, x, y, w_, h_ in (('world CLUTs (0,480,256,8)', 0, 480, 256, 8), ('font CLUT (0,488,16,1)', 0, 488, 16, 1)):
    check(not clash(x, y, w_, h_), nm + ' written by sf3.c do not touch a model/PPU region')
check(total * 2048 == len(d), 'file length matches its directory (%d sectors)' % total)
check(maxw <= SFM['SF_PBUF'] - w, 'largest world %d bytes fits the world window of %d bytes' % (maxw, SFM['SF_PBUF'] - w))
check(max(sides) <= 0x8011b200 - SFM['SF_SIDE'], 'largest per-map side table %d bytes fits 0x%08x..0x8011b200' % (max(sides), SFM['SF_SIDE']))

# ------------------------------------------------------------------ ROM pages / cache geometry (t/mkrompages.py + t/disc7.sh arithmetic)
print('--- ROM pages and page cache')
pg = pickle.load(open(PRIV + '/touched_f1_boot.pkl.rompages', 'rb'))
N = 56
top = sorted(pg, key=lambda p: -pg[p])[:N]
ctab = os.path.getsize(PRIV + '/pr_lb/coldtab_P.bin')
start = (COLDTAB + ctab + 15) & ~15
end = start + 4 + 4 * len(top) + 4096 * len(top)
pc = (end + 0xfff) & ~0xfff
NS = 8
doll = pc + NS * 4096
print('  %d ROM pages read by the boot+level scenario; %d preloaded (rompack 0x%08x..0x%08x); PCACHE_ADDR 0x%08x, %d slots -> cache ends 0x%08x = ragdoll base' % (len(pg), len(top), start, end, pc, NS, doll))
check(max(pg) < 2048, 'all touched ROM pages are inside the 8 MiB / 2048-page window (max page %d)' % max(pg))
check(end <= pc, 'rompack ends at or below the page cache (linker assert "resident ROM pages overlap the page cache")')
check(PPU - doll >= 0, 'ragdoll may use 0x%08x..0x%08x = %d bytes (linker assert "ragdoll code overlaps PPU scratch")' % (doll, PPU, PPU - doll))

# ------------------------------------------------------------------ program metadata
print('--- s2/prog_pr.pkl')
try:
    import disc  # noqa: F401  (classes for the pickle)
    P = pickle.load(open(PRIV + '/s2/prog_pr.pkl', 'rb'))
    ra = sorted(a for a, i in P.ins.items() if i.mode == 'A' and a >> 24 == 8)
    runs = []
    for a in ra:
        if runs and a <= runs[-1][1]: runs[-1][1] = a + 4
        else: runs.append([a, a + 4])
    print('  %d instructions, %d in ARM state inside the ROM in %d runs (ARMTAB = %d bytes of runtime rodata)' % (len(P.ins), len(ra), len(runs), 8 * len(runs)))
    check(len(P.ins) == 220981, 'discovery holds 220,981 instructions (the number STATUS.md and the stage 7 logs report)')
    check(all(0x08000000 <= a < 0x08800000 or a < 0x04000000 for a in P.ins), 'every discovered address is in the 8 MiB ROM window or guest RAM')
except Exception as e:
    check(False, 'prog_pr.pkl could not be loaded: %r' % (e,))

# ------------------------------------------------------------------ the old full-cold translations, for contrast
if S7:
    for nm in ('pr_f1', 'pr_f2', 'pr_f2b'):
        if os.path.isdir(S7 + '/' + nm):
            translation(S7 + '/' + nm, nm + ' (stage 7, COLD_GAP=0x8017c000)', physical=False)

print()
print('RESULT: %d failed checks' % len(fails))
for f in fails:
    print('  FAILED: ' + f)
sys.exit(1 if fails else 0)

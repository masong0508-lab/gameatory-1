#!/usr/bin/env python3
"""mkps1world.py: world0/ (+ the built ELF/ROM for pb_* tables) -> build/w0/ PS1 data. Derived from the player's ROM: scratchpad only.
usage: python3 -I mkps1world.py WORLD0_DIR ELF ROM OUTDIR"""
import sys, struct, json, subprocess, hashlib
import numpy as np
w0, elf, rom, out = sys.argv[1:5]
blob = bytearray(open(w0 + '/world.bin', 'rb').read())
t = np.load(w0 + '/tiles.npz')
ids = [int(i) for i in t['ids']]; nt = len(ids)
slot = {i: s for s, i in enumerate(ids)}
assert nt <= 384 and ids == sorted(ids)
# header
assert blob[:4] == b'SFW4'
nbox, nlot, nramp, nloop, nitem, nline, ntree = struct.unpack_from('<7I', blob, 4)
offs = struct.unpack_from('<17I', blob, 36)
SEC = dict(zip('box lot ramp loop sector item cell far line tree ctex btex deck wall deck2 dtex swim'.split(), offs))
def remap(off, count):
    a = np.frombuffer(bytes(blob[off:off + 2 * count]), '<u2').copy()
    bad = 0
    for k in range(count):
        v = int(a[k])
        if v == 0xffff: continue
        if v not in slot: bad += 1; a[k] = 0xffff; continue
        a[k] = slot[v]
    blob[off:off + 2 * count] = a.astype('<u2').tobytes(); return bad
bad = remap(SEC['ctex'], 16384) + remap(SEC['btex'], nbox * 16) + remap(SEC['dtex'], 16384)
print('tile ids not in the atlas (set to none):', bad)
# palette / CLUT
pal555 = t['pal555'].astype(np.uint16)          # ROM order: red at bit 10 ?  (tiles.npz says PS1/GBA order)
pal = t['pal'].astype(np.int32)                  # RGB8
def rgb15(r, g, b): return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
clut = np.array([rgb15(*pal[i]) for i in range(256)], np.uint16)
clut_stp = clut.copy()
clut_stp[clut_stp == 0] = 0x8000
fog = (22 << 3, 26 << 3, 30 << 3)
rows = [clut_stp]
for f in range(1, 8):
    k = f / 8.0
    r = [rgb15(int(pal[i][0] * (1 - k) + fog[0] * k), int(pal[i][1] * (1 - k) + fog[1] * k), int(pal[i][2] * (1 - k) + fog[2] * k)) for i in range(256)]
    r = np.array(r, np.uint16); r[r == 0] = 0x8000; rows.append(r)
open(out + '/CLUT.BIN', 'wb').write(b''.join(r.astype('<u2').tobytes() for r in rows))
# atlas: 6+ pages of 256x256, 8 bit; VRAM upload rects
npg = (nt + 63) // 64
pages = np.zeros((npg, 256, 256), np.uint8)
for s in range(nt):
    pg, k = divmod(s, 64); u, v = (k % 8) * 32, (k // 8) * 32
    pages[pg, v:v + 32, u:u + 32] = t['idx'][s]
rects = b''; data = b''
for pg in range(npg):
    x = 320 + 128 * (pg % 5); y = 256 * (pg // 5)
    rects += struct.pack('<4H', x, y, 128, 256)
    data += pages[pg].tobytes()           # little endian bytes = 2 texels a word, low byte left
open(out + '/ATLAS.VRM', 'wb').write(struct.pack('<4I', npg, 0, 0, 0) + rects + data)
# ELF tables
def sym(name):
    for l in subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout.splitlines():
        p = l.split()
        if len(p) == 3 and p[2] == name: return int(p[0], 16)
rd = open(rom, 'rb').read()
def tab(name, n): a = sym(name) - 0x08000000; return rd[a:a + n]
pmap = tab('pb_pmap', 256); pavg = tab('pb_avg', 0x318); pmesh = struct.unpack('<25I', tab('pb_mesh', 100)); psky = tab('pb_sky', 16)
sinT = tab('sin_table', 8192)
def gp0col(idx): r, g, b = pal[idx]; return int(r) | (int(g) << 8) | (int(b) << 16)
mesh = bytes(1 if (i < 0x318 and (pmesh[i >> 5] >> (i & 31)) & 1) else 0 for i in ids)
# per slot: flat colour of the tile's average (palette index through pb_avg) as 0xBBGGRR, and a 555
avgcol = [gp0col(pavg[i]) if i < 0x318 else gp0col(0) for i in ids]
if 0x317 in slot:   # water: the flat colour is the true texel average of the water tile (the ROM table entry is olive, which showed as an olive flat polygon beyond the textured range)
    m = pal[t['idx'][slot[0x317]].reshape(-1)].mean(0).astype(int); avgcol[slot[0x317]] = int(m[0]) | (int(m[1]) << 8) | (int(m[2]) << 16)
# ground mask
gm = np.zeros((128, 128), bool)
ctex = np.frombuffer(bytes(blob[SEC['ctex']:SEC['ctex'] + 32768]), '<u2').reshape(128, 128)
gm[:] = ctex != 0xffff
for k in range(nbox):
    x0, z0, x1, z1, h, mb, base = struct.unpack_from('<4BhBb', blob, SEC['box'] + 8 * k)
    if base == 0: gm[x0:x1, z0:z1] = False
for k in range(nramp):
    x0, z0, x1, z1, h0, h1, d, m = struct.unpack_from('<4B2hBB', blob, SEC['ramp'] + 10 * k)
    if not d & 0x80: gm[x0:x1, z0:z1] = False
gbits = bytearray(2048)
for x in range(128):
    for z in range(128):
        if gm[x, z]: i = x * 128 + z; gbits[i >> 3] |= 1 << (i & 7)
# flat colours [16][4][4] and sky
flat = [gp0col(pmap[m * 16 + l * 4 + f] if False else pmap[(m * 4 + l) * 4 + f]) for m in range(16) for l in range(4) for f in range(4)]
skyc = [gp0col(psky[i]) for i in range(16)]
sky9 = [gp0col(c) for c in (199, 198, 197, 195, 194)] + [gp0col(pmap[6 * 16 + 1 * 4 + f]) for f in (3, 2, 1, 0)]
side = bytes(gbits) + struct.pack('<384H', *([slot_id for slot_id in ids] + [0] * (384 - nt)))
side += struct.pack('<384H', *([rgb15(avgcol[s] & 255, (avgcol[s] >> 8) & 255, avgcol[s] >> 16) for s in range(nt)] + [0] * (384 - nt)))
side += mesh + bytes(384 - nt)
side += struct.pack('<384I', *(avgcol + [0] * (384 - nt)))
side += struct.pack('<256I', *flat) + struct.pack('<9I', *sky9) + struct.pack('<I', fog[0] | fog[1] << 8 | fog[2] << 16)
side += struct.pack('<%dh' % 4096, *struct.unpack('<4096h', sinT))
open(out + '/SIDE.BIN', 'wb').write(side)
open(out + '/WORLD.SFW', 'wb').write(blob)
# check images
from PIL import Image
im = Image.new('L', (128, 128))
im.putdata([255 if gm[x, z] else 0 for z in range(128) for x in range(128)]); im.resize((512, 512), Image.NEAREST).save(out + '/gmask.png')
json.dump(dict(ntiles=nt, pages=npg, ids=ids, ground_cells=int(gm.sum()), sizes={n: len(open(out + '/' + n, 'rb').read()) for n in ('WORLD.SFW', 'ATLAS.VRM', 'CLUT.BIN', 'SIDE.BIN')},
               sha=hashlib.sha1(bytes(blob)).hexdigest()), open(out + '/manifest.json', 'w'), indent=1)
print('ok', nt, npg, 'ground cells', int(gm.sum()))

# ---- HUD font: 5x7 glyphs drawn by this tool, 4 bit, 16 glyphs a row, 8x8 cells (96 glyphs: ascii 32..127), CLUT of 16
G = {'0':'0E11131519110E','1':'040C0404040E0E'[:12]+'0E','2':'0E110102040 81F'.replace(' ',''),'3':'1F0204020111 0E'.replace(' ',''),'4':'02060A121F0202','5':'1F101E0101110E','6':'0608101E11110E','7':'1F010204080808','8':'0E11110E11110E','9':'0E11110F01020C',
 'A':'0E11111F111111','B':'1E11111E11111E','C':'0E11101010110E','D':'1E111111111 11E'.replace(' ',''),'E':'1F10101E10101F','F':'1F10101E101010','G':'0E1110171111 0F'.replace(' ',''),'H':'11111111F1111'[:0]+'11111F111111'[:0]+'1111111F111111'[:14],
 'I':'0E04040404040E','J':'07020202021 20C'.replace(' ',''),'K':'11121418141211','L':'1010101010101F','M':'111B15151111 11'.replace(' ',''),'N':'11191513111 111'.replace(' ',''),'O':'0E11111111110E','P':'1E11111E101010','Q':'0E11111115120D','R':'1E11111E141211',
 'S':'0F10100E01011E','T':'1F040404040404','U':'1111111111110E','V':'1111111111 0A04'.replace(' ',''),'W':'1111111515 1B11'.replace(' ',''),'X':'11110A040A1111','Y':'11110A04040404','Z':'1F010204081 01F'.replace(' ',''),
 ':':'00040000000400','.':'0000000000 0C0C'.replace(' ',''),'-':'0000001F000000','/':'01010204081010','%':'191A02040 80B13'.replace(' ',''),'+':'00 04041F040400'.replace(' ',''),',':'00000000 0C0408'.replace(' ',''),'=':'00001F001F0000','(':'02040808080402',')':'08040202020408','#':'0A0A1F0A1F0A0A','_':'0000000000001F','>':'08040201020408','<':'02040810080402','!':'04040404040004','?':'0E11010204 0004'.replace(' ','')}
G['1'] = '040C0404040404'[:12] + '0E0E'[:0]; G['1'] = bytes([0x04,0x0C,0x04,0x04,0x04,0x04,0x0E]).hex()
G['H'] = bytes([0x11,0x11,0x11,0x1F,0x11,0x11,0x11]).hex()
G['2'] = bytes([0x0E,0x11,0x01,0x02,0x04,0x08,0x1F]).hex(); G['3'] = bytes([0x1F,0x02,0x04,0x02,0x01,0x11,0x0E]).hex()
G['D'] = bytes([0x1E,0x11,0x11,0x11,0x11,0x11,0x1E]).hex(); G['G'] = bytes([0x0E,0x11,0x10,0x17,0x11,0x11,0x0F]).hex()
G['J'] = bytes([0x07,0x02,0x02,0x02,0x02,0x12,0x0C]).hex(); G['M'] = bytes([0x11,0x1B,0x15,0x15,0x11,0x11,0x11]).hex()
G['N'] = bytes([0x11,0x19,0x15,0x13,0x11,0x11,0x11]).hex(); G['V'] = bytes([0x11,0x11,0x11,0x11,0x11,0x0A,0x04]).hex()
G['W'] = bytes([0x11,0x11,0x11,0x15,0x15,0x1B,0x11]).hex(); G['Z'] = bytes([0x1F,0x01,0x02,0x04,0x08,0x10,0x1F]).hex()
G['.'] = bytes([0,0,0,0,0,0x0C,0x0C]).hex(); G['%'] = bytes([0x19,0x1A,0x02,0x04,0x08,0x0B,0x13]).hex()
G['+'] = bytes([0,0x04,0x04,0x1F,0x04,0x04,0]).hex(); G[','] = bytes([0,0,0,0,0x0C,0x04,0x08]).hex(); G['?'] = bytes([0x0E,0x11,0x01,0x02,0x04,0,0x04]).hex()
fimg = np.zeros((48, 128), np.uint8)
for ch, hx in G.items():
    rows = bytes.fromhex(hx); assert len(rows) == 7, ch
    gi = ord(ch) - 32; cx, cy = (gi % 16) * 8, (gi // 16) * 8
    for r, b in enumerate(rows):
        for c in range(5):
            if b & (0x10 >> c): fimg[cy + r, cx + c] = 1
fw = bytearray()
for y in range(48):
    for x in range(0, 128, 4):
        v = 0
        for k in range(4): v |= int(fimg[y, x + k]) << (4 * k)
        fw += struct.pack('<H', v)
fclut = struct.pack('<16H', 0, 0x7FFF, *([0x7FFF] * 14))
open(out + '/FONT.VRM', 'wb').write(struct.pack('<4H', 960, 0, 32, 48) + bytes(fw) + fclut)
print('font ok', len(fw))

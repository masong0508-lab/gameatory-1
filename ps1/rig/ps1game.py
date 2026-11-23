#!/usr/bin/env python3
"""ps1game.py: test helpers for the Payback PS1 port on top of retro_ps1.Emu (headless libretro frontend).  See RIG.md.

    from ps1game import Game
    g = Game(disc, outdir, core='pcsx_rearmed', card='blank', syms='payback.elf')   # card: 'blank' | 'none' | path | bytes
    g.run(60, ['CROSS']); g.tap('START', until=lambda: g.on('PAUSED'))               # every input change is logged (g.script)
    g.g8(a); g.g16(a); g.g32(a)                    # guest memory by GBA address
    g.level_clock(); g.map_id(); g.player(); g.pos(); g.entities(); g.title_cursor()
    g.wait_until(lambda: g.level_clock() > 0, 3000)
    g.text(); g.screen(); g.on('PAUSED')           # what the game drew (from the runtime's draw ring, no pixels)
    g.snap('title'); g.sheet(outdir + '/sheet.png')
    g.card_now().files()                           # [{'name': 'BESLES-99902PAYBACK', 'blocks': 2, ...}]
    g.save_card(path); g.save_state_file('x.state'); g.load_state_file('x.state')
    g.counters(); g.speed(600); g.cpu_where(8); g.tty()

Build independence: the GBA memory windows are fixed addresses of the runtime (rt.c: EW/IW/PAL/OAM/VRAM; PS1GAME_LAYOUT in the
environment overrides them); everything that is a C static of the runtime (frame counters, pad words, interpreter and
overlay counters) is looked up by NAME in a symbol file (ELF, `nm` output or an lld/GNU ld map) passed as syms=...; without
one those helpers return None and the sessions skip the checks that need them.  One Game per process.

The game's own text: single UI words a check needs (PAUSED, Cancel, the language names) are plain strings; anything longer
is a Mark (its length and a sha256 of it, see class Mark), so that the rig never quotes the game.  on(), menu() and
wait_text() take either.
"""
import ctypes as C
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
try:
    import numpy as _np
except ImportError:          # the picture measures then run in plain Python (slower, same result)
    _np = None
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from retro_ps1 import Emu, BTN, LogCb, Variable, RigSetupError, build_so, core_path, system_dir   # noqa: E402,F401

# ------------------------------------------------------------------------------------------------ GBA windows in PS1 RAM
# rt.c: #define EW 0x801b0000 (EWRAM 256 KiB), IW 0x801f0000 (IWRAM 32 KiB), PAL 0x80180000, OAM 0x80180400,
# VRAM 0x80181000 (96 KiB), guest IO window 0x8017f000 (not memory: the translated code's IO accesses trap into io_read /
# io_write, the register file itself is the static io[0x400], symbol "io").  Draw ring 0x8017c000, helper table 0x80028000.
EW, IW, PAL, OAM, VRAM, IOWIN, DL, HELP = 0x801b0000, 0x801f0000, 0x80180000, 0x80180400, 0x80181000, 0x8017f000, 0x8017c000, 0x80028000
# A build that moves a window: PS1GAME_LAYOUT="EW=0x801b0000,IW=0x801f0000,DL=0x8017c000" in the environment overrides them.
for _kv in os.environ.get('PS1GAME_LAYOUT', '').split(','):
    if '=' in _kv:
        _k, _v = _kv.split('=', 1)
        if _k.strip() in ('EW', 'IW', 'PAL', 'OAM', 'VRAM', 'IOWIN', 'DL', 'HELP'):
            globals()[_k.strip()] = int(_v, 0)

# Payback (Europe) RAM, from stuntfox/src/pbapi.h and the task notes
PB_CLOCK, PB_LEVEL_END, PB_RESPAWN, PB_LIVES, PB_MULT = 0x02001e00, 0x02001e08, 0x02001e0c, 0x02001e4e, 0x02001df0
PB_MAP, PB_DIFF, PB_RAMPAGE, PB_WAS_RAMPAGE, PB_GRID_ID = 0x02001d40, 0x02001d3c, 0x02001d39, 0x02001d3a, 0x02001e66
PB_CONTROLLED, PB_ENTITY, PB_NENTITY, PB_DESC0 = 0x02001db8, 0x03000c60, 0x0300000c, 0x08354af4
PB_BTN, PB_TITLE_CURSOR, PB_CITY, PB_SUB = 0x0200c3e4, 0x03007e68, 0x02003ef2, 0x02003ef4
GBA_KEYS = {'A': 1, 'B': 2, 'SELECT': 4, 'START': 8, 'RIGHT': 0x10, 'LEFT': 0x20, 'UP': 0x40, 'DOWN': 0x80, 'R': 0x100, 'L': 0x200}
# pad mapping of the port (hw_pad.h pad_to_gba)
PS1_TO_GBA = {'CROSS': 'A', 'CIRCLE': 'B', 'SQUARE': 'B', 'SELECT': 'SELECT', 'START': 'START', 'RIGHT': 'RIGHT', 'LEFT': 'LEFT',
              'UP': 'UP', 'DOWN': 'DOWN', 'R1': 'R', 'L1': 'L'}


def g2h(a):
    """GBA address -> PS1 address (kseg0), None when the region has no window."""
    r = a >> 24
    if r == 2:
        return EW + (a & 0x3ffff)
    if r == 3:
        return IW + (a & 0x7fff)
    if r == 5:
        return PAL + (a & 0x3ff)
    if r == 6:
        o = a & 0x1ffff
        return VRAM + (o - 0x8000 if o >= 0x18000 else o)
    if r == 7:
        return OAM + (a & 0x3ff)
    return None


def h2g(h):
    """PS1 address inside a guest window -> GBA address (else None)."""
    h = 0x80000000 | (h & 0x1fffff)
    for base, size, g in ((EW, 0x40000, 0x02000000), (IW, 0x8000, 0x03000000), (PAL, 0x400, 0x05000000), (OAM, 0x400, 0x07000000), (VRAM, 0x18000, 0x06000000)):
        if base <= h < base + size:
            return g + (h - base)
    return None


# ------------------------------------------------------------------------------------------------ the game's own text
class Mark:
    """A piece of the game's own text that a check looks for, kept as its length in characters and the sha256 (hex) of its
    lower-cased UTF-8 form, so that the rig does not quote the game.  `label` is our own name for it: logs and reports
    print the label.  found_in(text) is what `piece.lower() in text.lower()` would say: it hashes every window of that
    length of the lower-cased text (cached per text, the drawn text changes rarely)."""
    __slots__ = ('label', 'n', 'sha256')

    def __init__(self, label, n, sha256):
        self.label, self.n, self.sha256 = label, n, sha256

    def __repr__(self):
        return '<%s>' % self.label

    def __str__(self):
        return self.label

    def __eq__(self, other):
        return isinstance(other, Mark) and (other.n, other.sha256) == (self.n, self.sha256)

    def __hash__(self):
        return hash((self.n, self.sha256))

    def found_in(self, text):
        """True when the piece is part of `text` (case-insensitive)."""
        return self.sha256 in _windows(text.lower(), self.n)

    def equals(self, text):
        """True when `text` is the piece itself (case-insensitive)."""
        return len(text) == self.n and hashlib.sha256(text.lower().encode('utf-8')).hexdigest() == self.sha256

    def find(self, data):
        """Offset of the piece in `data` (bytes, ASCII letters case-insensitive), -1 when it is not there.  Only for a piece
        that is plain ASCII (one byte per character)."""
        d = bytes(data).lower()
        for i in range(len(d) - self.n + 1):
            if hashlib.sha256(d[i:i + self.n]).hexdigest() == self.sha256:
                return i
        return -1


_WINDOWS = {}


def _windows(t, n):
    """The sha256 of every n-character window of t."""
    k = (t, n)
    s = _WINDOWS.get(k)
    if s is None:
        if len(_WINDOWS) > 4096:
            _WINDOWS.clear()
        s = _WINDOWS[k] = frozenset(hashlib.sha256(t[i:i + n].encode('utf-8')).hexdigest() for i in range(len(t) - n + 1))
    return s


def contains(text, x):
    """True when x (a plain word or a Mark) is part of text, case-insensitive."""
    if isinstance(x, Mark):
        return x.found_in(text)
    return x.lower() in text.lower()


def same_text(text, x):
    """True when text is x (a plain word, compared as it is, or a Mark)."""
    return x.equals(text) if isinstance(x, Mark) else text == x


# ------------------------------------------------------------------------------------------------ packed PSX.EXE
EXEPACK_MAGIC = 0x31584b50          # 'PKX1': the run table of a packed PSX.EXE (ps1/stage19/ps1rt/exepack.py, speed item M11)


def exe_image(exe, syms=None):
    """(load address, bytes) of the program image a PS-X EXE puts in RAM.  A packed EXE (-DEXEPACK: the ELF defines __exepack_v1)
    is rebuilt by its crt0 before main(): the runtime verbatim below __bss_start, then a run table 'PKX1', n, zero_end, n x (dest,
    len) and the runs' bytes back to back; the image is the runs at their destinations and zeros elsewhere up to zero_end (the same
    model as exepack.unpack).  Without the two symbols, or without a run table at __bss_start, the image is the EXE's text as it is."""
    t_addr, t_size = struct.unpack_from('<II', exe, 0x18)
    body = exe[0x800:0x800 + t_size]
    syms = syms or {}
    bss = syms.get('__bss_start')
    if '__exepack_v1' not in syms or bss is None:
        return t_addr, body
    off = bss - t_addr
    if off < 0 or off + 12 > len(body):
        return t_addr, body
    magic, n, zero_end = struct.unpack_from('<III', body, off)
    if magic != EXEPACK_MAGIC or off + 12 + 8 * n > len(body) or zero_end < bss:
        return t_addr, body
    ents = [struct.unpack_from('<II', body, off + 12 + 8 * i) for i in range(n)]
    img = bytearray(zero_end - t_addr)
    img[:off] = body[:off]
    src = off + 12 + 8 * n
    for dest, ln in ents:
        d = dest - t_addr
        if d < off or d + ln > len(img) or src + ln > len(body):
            raise ValueError('packed PSX.EXE: run 0x%08x+%d lies outside the image' % (dest, ln))
        img[d:d + ln] = body[src:src + ln]
        src += ln
    return t_addr, bytes(img)


# ------------------------------------------------------------------------------------------------ symbols
def load_symbols(path, sizes=None):
    """name -> address from an ELF (32-bit LE symtab), `nm` text or a linker map (lld: 'VMA LMA Size Align Out In Symbol').
    When `sizes` is a dict it receives name -> size for the formats that carry one (ELF, lld map)."""
    if not path or not os.path.exists(path):
        return {}
    d = open(path, 'rb').read()
    out = {}
    if d[:4] == b'\x7fELF':
        shoff, = struct.unpack_from('<I', d, 0x20)
        shentsize, shnum = struct.unpack_from('<HH', d, 0x2e)
        secs = [struct.unpack_from('<10I', d, shoff + i * shentsize) for i in range(shnum)]
        for s in secs:
            if s[1] != 2:      # SHT_SYMTAB
                continue
            stroff = secs[s[6]][4]
            for o in range(s[4], s[4] + s[5], 16):
                nm, val, size, info, other, shndx = struct.unpack_from('<IIIBBH', d, o)
                if not nm or shndx == 0:
                    continue
                e = d.index(b'\0', stroff + nm)
                name = d[stroff + nm:e].decode('latin1')
                if not name.startswith('$'):
                    if sizes is not None and name not in out:
                        sizes[name] = size
                    out.setdefault(name, val)
        return out
    for line in d.decode('latin1').splitlines():
        p = line.split()
        try:
            if len(p) == 3 and len(p[1]) == 1:                 # nm: addr type name
                out.setdefault(p[2], int(p[0], 16))
            elif len(p) == 5 and p[3].isdigit():               # lld map symbol line: vma lma size align name
                if sizes is not None and p[4] not in out:
                    sizes[p[4]] = int(p[2], 16)
                out.setdefault(p[4], int(p[0], 16))
            elif len(p) == 2 and p[0].startswith('0x'):        # GNU ld map: 0xaddr name
                out.setdefault(p[1], int(p[0], 16))
        except ValueError:
            pass
    return out


# ------------------------------------------------------------------------------------------------ disc image (ISO9660 in MODE2/2352 or 2048)
class Disc:
    def __init__(self, path):
        self.path = path
        b = path
        if path.lower().endswith('.cue'):
            for line in open(path, errors='replace'):
                if line.strip().upper().startswith('FILE'):
                    b = os.path.join(os.path.dirname(os.path.abspath(path)), line.split('"')[1])
                    break
        self.bin = b
        self.f = open(b, 'rb')
        head = self.f.read(16)
        self.raw = 2352 if head[:12] == b'\x00' + b'\xff' * 10 + b'\x00' else 2048
        pvd = self.sectors(16, 1)
        if pvd[1:6] != b'CD001':
            raise RuntimeError('no ISO9660 volume in ' + b)
        self.volume = pvd[40:72].decode('latin1').strip()
        lba, size = struct.unpack_from('<I', pvd, 158)[0], struct.unpack_from('<I', pvd, 166)[0]
        d = self.sectors(lba, (size + 2047) // 2048)
        self.files = {}
        o = 0
        while o < size:
            n = d[o]
            if n == 0:
                o = (o // 2048 + 1) * 2048
                continue
            nl = d[o + 32]
            name = d[o + 33:o + 33 + nl].decode('latin1').split(';')[0]
            if nl > 1:
                self.files[name] = (struct.unpack_from('<I', d, o + 2)[0], struct.unpack_from('<I', d, o + 10)[0])
            o += n

    def sectors(self, lba, n):
        out = bytearray()
        for i in range(n):
            self.f.seek((lba + i) * self.raw + (24 if self.raw == 2352 else 0))
            out += self.f.read(2048)
        return bytes(out)

    def read(self, name, off=0, size=None):
        lba, total = self.files[name]
        if size is None:
            size = total - off
        s0 = off // 2048
        d = self.sectors(lba + s0, (off % 2048 + size + 2047) // 2048)
        return d[off % 2048:off % 2048 + size]

    def sha1(self, name):
        return hashlib.sha1(self.read(name)).hexdigest()


# ------------------------------------------------------------------------------------------------ memory card image (128 KiB)
class MemCard:
    """PS1 memory card image: 16 blocks of 64 frames of 128 bytes.  Block 0: frame 0 'MC' header, frames 1..15 directory."""
    SIZE = 0x20000

    def __init__(self, data=None):
        self.data = bytearray(data) if data is not None else self.blank()
        if len(self.data) != self.SIZE:
            raise ValueError('memory card image must be %d bytes, got %d' % (self.SIZE, len(self.data)))

    @staticmethod
    def _ck(fr):
        c = 0
        for b in fr[:127]:
            c ^= b
        return c

    @classmethod
    def blank(cls):
        """A freshly formatted card (the layout the hardware documentation describes; written by this file, no image copied)."""
        d = bytearray(cls.SIZE)
        fr = bytearray(128); fr[0:2] = b'MC'; fr[127] = cls._ck(fr)
        d[0:128] = fr
        for k in range(1, 16):                       # directory: free, no next block
            fr = bytearray(128); fr[0] = 0xa0; fr[8] = fr[9] = 0xff; fr[127] = cls._ck(fr)
            d[k * 128:(k + 1) * 128] = fr
        for k in range(16, 36):                      # broken sector list: none
            fr = bytearray(128); fr[0:4] = b'\xff\xff\xff\xff'; fr[8] = fr[9] = 0xff; fr[127] = cls._ck(fr)
            d[k * 128:(k + 1) * 128] = fr
        for k in range(36, 63):                      # replacement data + unused
            d[k * 128:(k + 1) * 128] = b'\xff' * 128
        d[63 * 128:64 * 128] = d[0:128]              # write test frame
        return d

    @classmethod
    def load(cls, path):
        d = open(path, 'rb').read()
        if len(d) > cls.SIZE and d[:11] == b'123-456-STD':      # .gme (DexDrive): 3904-byte header
            d = d[3904:3904 + cls.SIZE]
        return cls(d)

    def save(self, path):
        open(path, 'wb').write(bytes(self.data))

    def frame(self, n):
        return bytes(self.data[n * 128:(n + 1) * 128])

    def formatted(self):
        f0 = self.frame(0)
        return f0[:2] == b'MC' and self._ck(f0) == f0[127]

    def directory(self):
        """Raw directory: 15 entries {index, state, size, next, name, cksum_ok}."""
        out = []
        for k in range(1, 16):
            fr = self.frame(k)
            name = fr[10:31].split(b'\0')[0].decode('latin1')
            out.append({'block': k, 'state': fr[0], 'size': struct.unpack_from('<I', fr, 4)[0], 'next': struct.unpack_from('<H', fr, 8)[0],
                        'name': name, 'cksum_ok': self._ck(fr) == fr[127]})
        return out

    def files(self):
        """Files on the card: name, block list, block count, size from the directory, title of the first block (Shift-JIS)."""
        d = self.directory()
        out = []
        for e in d:
            if e['state'] != 0x51:
                continue
            blocks = [e['block']]
            nx = e['next']
            while nx != 0xffff and nx < 15 and len(blocks) < 15:
                blocks.append(nx + 1)
                nx = d[nx]['next']
            t = self.frame(blocks[0] * 64)
            title = ''
            if t[:2] == b'SC':
                try:
                    title = t[4:68].split(b'\0\0')[0].decode('shift_jis', 'replace')
                    title = ''.join(chr(ord(c) - 0xfee0) if 0xff01 <= ord(c) <= 0xff5e else (' ' if c == '　' else c) for c in title).strip()
                except Exception:
                    title = ''
            out.append({'name': e['name'], 'blocks': len(blocks), 'block_list': blocks, 'size': e['size'], 'title': title,
                        'icon_flag': t[2] if t[:2] == b'SC' else None, 'cksum_ok': e['cksum_ok']})
        return out

    def free_blocks(self):
        return sum(1 for e in self.directory() if (e['state'] & 0xf0) == 0xa0)

    def file_data(self, name):
        for f in self.files():
            if f['name'] == name:
                return b''.join(bytes(self.data[b * 0x2000:(b + 1) * 0x2000]) for b in f['block_list'])
        return None

    def payback_save(self, name='BESLES-99902PAYBACK'):
        """The port's save file (hw_card.h): image frame 3 = meta (magic 'FSFB', version, seq, n, crc32), payload at 0x200."""
        img = self.file_data(name)
        if img is None:
            return None
        magic, ver, seq, n, crc = struct.unpack_from('<5I', img, 3 * 128)
        ee = img[0x200:0x200 + n] if n <= len(img) - 0x200 else b''
        return {'magic_ok': magic == 0x42465346, 'version': ver, 'seq': seq, 'n': n, 'crc': crc, 'crc_ok': (zlib.crc32(ee) & 0xffffffff) == crc,
                'eeprom': ee, 'eeprom_sha1': hashlib.sha1(ee).hexdigest()}

    def summary(self):
        s = {'formatted': self.formatted(), 'free_blocks': self.free_blocks(), 'files': self.files(), 'sha1': hashlib.sha1(bytes(self.data)).hexdigest()}
        ps = self.payback_save()
        if ps:
            s['payback_save'] = {k: v for k, v in ps.items() if k != 'eeprom'}
            s['payback_save']['eeprom_ff_bytes'] = ps['eeprom'].count(0xff)
        return s


# ------------------------------------------------------------------------------------------------ images
def lum(im):
    """Mean luminance 0..255 of a PIL image (subsampled)."""
    g = im.convert('L').resize((80, 60))
    d = g.tobytes()
    return sum(d) / len(d)


def lit(im, thr=40):
    """Fraction of pixels brighter than thr (0..255) in the full-size picture."""
    if im is None:
        return 0.0
    d = im.convert('L').tobytes()
    return sum(1 for v in d if v > thr) / max(1, len(d))


def measures(im):
    """(lit, white, chroma): fractions of the pixels of the full-size picture that are brighter than dark grey (luminance
    over 24), nearly white (every channel over 200) and coloured (channels more than 40 apart)."""
    if im is None:
        return 0.0, 0.0, 0.0
    if _np is not None:
        a = _np.asarray(im.convert('RGB')).astype(_np.int32)
        mx, mn = a.max(2), a.min(2)
        return (float((a[:, :, 0] * 299 + a[:, :, 1] * 587 + a[:, :, 2] * 114 > 24000).mean()), float((mn > 200).mean()),
                float((mx - mn > 40).mean()))
    d = im.convert('RGB').tobytes()
    n = len(d) // 3
    nl = nw = nc = 0
    for i in range(0, n * 3, 3):
        r, g, b = d[i], d[i + 1], d[i + 2]
        mx = r if r > g else g
        if b > mx: mx = b
        mn = r if r < g else g
        if b < mn: mn = b
        if r * 299 + g * 587 + b * 114 > 24000: nl += 1
        if mn > 200: nw += 1
        if mx - mn > 40: nc += 1
    n = max(1, n)
    return nl / n, nw / n, nc / n


def is_black(im, frac=0.002):
    """True when the picture shows nothing: fewer than 0.2 % of its pixels are brighter than dark grey."""
    return im is None or lit(im) < frac


def ncolors(im, box=None):
    """Number of distinct colours in a (cropped) 80x60 thumbnail: a flat or empty picture has very few."""
    if box:
        im = im.crop(box)
    return len(set(im.convert('RGB').resize((80, 60)).getdata()))


def diff(a, b):
    """Mean absolute difference per channel 0..255 between two frames (thumbnails)."""
    if a is None or b is None:
        return 255.0
    x = a.convert('RGB').resize((80, 60)).tobytes()
    y = b.convert('RGB').resize((80, 60)).tobytes()
    return sum(abs(p - q) for p, q in zip(x, y)) / len(x)


def shape_diff(a, b):
    """Fraction of the cells of an 80x60 grid where two pictures differ in SHAPE: each picture is cut at a quarter of its
    own brightest value first, so a faded copy of the same picture gives 0.  1.0 when one of them is missing or black."""
    if a is None or b is None:
        return 1.0
    x = a.convert('L').resize((80, 60)).tobytes()
    y = b.convert('L').resize((80, 60)).tobytes()
    mx, my = max(x), max(y)
    if mx < 16 or my < 16:
        return 1.0
    return sum(1 for p, q in zip(x, y) if (p * 4 > mx) != (q * 4 > my)) / float(len(x))


def contact_sheet(items, path, cols=4, cell=(320, 240), title=None):
    """items: list of (PIL image or None, caption).  Saves a labelled sheet and returns it."""
    from PIL import Image, ImageDraw
    if not items:
        return None
    cw, ch = cell
    bar = 14
    rows = (len(items) + cols - 1) // cols
    top = 16 if title else 0
    sheet = Image.new('RGB', (cols * cw, top + rows * (ch + bar)), (24, 24, 24))
    dr = ImageDraw.Draw(sheet)
    if title:
        dr.text((4, 2), title, fill=(255, 255, 255))
    for i, (im, cap) in enumerate(items):
        x, y = (i % cols) * cw, top + (i // cols) * (ch + bar)
        if im is not None:
            sheet.paste(im.convert('RGB').resize((cw, ch)), (x, y + bar))
        dr.text((x + 3, y + 1), cap[:52], fill=(255, 255, 0))
    sheet.save(path)
    return sheet


# ------------------------------------------------------------------------------------------------ core specifics
CORE_OPTS = {
    # option values checked on the buildbot binary the rig was made with (pcsx_rearmed r26l-137): memcard1 = libretro | serial | shared | none
    'pcsx_rearmed': {'base': {'pcsx_rearmed_bios': 'HLE', 'pcsx_rearmed_memcard2': 'none'},
                     'card_on': {'pcsx_rearmed_memcard1': 'libretro'}, 'card_off': {'pcsx_rearmed_memcard1': 'none'}},
    # option names from the cores' strings; these cores need a firmware file: the rig gives them openboot (tools/ob_session.py,
    # tools/obrun.py and BOOTROM.md), never a Sony BIOS
    'swanstation': {'base': {'swanstation_MemoryCards_Card2Type': 'None'},
                    'card_on': {'swanstation_MemoryCards_Card1Type': 'Libretro'}, 'card_off': {'swanstation_MemoryCards_Card1Type': 'None'}},
    'beetle': {'base': {}, 'card_on': {'beetle_psx_use_mednafen_memcard0_method': 'libretro'}, 'card_off': {}},
}
# pcsx_rearmed prints BIOS putchar (the runtime's dbg() text) only when Config.PsxOut is set; the libretro build has no option
# for it.  For the exact binary below the flag is the byte at this offset from the load address (found by disassembly: the
# A0:3C handler tests it before SysPrintf("%c")).  Any other binary: no TTY (the helpers then return '').
PCSX_PSXOUT = {'0dd73cf4d8acfbd79e75cf304f72ee8ccbd665ca': (0x84f047, 'retro_run', 0x199f10)}


class Fail(Exception):
    pass


class Game(Emu):
    _real_frames = 0        # video callbacks that carried a picture (the core hands over nothing when the display did not change)
    _stale_from = None      # set by load_state(): the core's picture is the old machine's until a new one arrives
    _gpu_off = None

    def _vid(self, data, w, h, pitch):
        if data and w and h:
            self._real_frames += 1
        Emu._vid(self, data, w, h, pitch)

    def __init__(self, disc, out, core='pcsx_rearmed', card='blank', syms=None, opts=None, tty=True, sysdir=None, audio=False, quiet=False):
        """card: 'blank' (formatted, empty), 'none' (no card in slot 1), a path to a 128 KiB image (carried over from an
        earlier run; the file itself is never modified), or bytes.  The card of this run is written to OUT/card1.mcd by
        save_card() / close()."""
        self.core_name = core
        self.disc_path = os.path.abspath(disc)
        self.out = os.path.abspath(out)
        os.makedirs(self.out, exist_ok=True)
        self.quiet = quiet
        self.cleaned = self._clean_out()
        self.symsize = {}
        self.sym = load_symbols(syms, self.symsize) if syms else {}
        self.syms_path = syms
        self.script = []            # (emulator frame, sorted button list) at every change of the held buttons
        self._held = ()
        self.nrun = 0               # retro_run calls = emulator frames
        self.snaps = []             # (image, caption)
        self.results = []           # (ok, text)
        self.events = []
        self._tty = bytearray()
        self._tty_seen = 0
        self._tty_lpos = 0          # offset in _tty up to which complete lines were stamped into tty_timeline
        self._tty_polled = 0        # emulator frame of the last timeline poll
        self.tty_timeline = []      # (emulator frame at which the line was read, line) for every TTY line but the noisy ones
        self._psxout_off = None
        self._ring_reset()
        co = CORE_OPTS.get(core, {'base': {}, 'card_on': {}, 'card_off': {}})
        o = dict(co['base'])
        self.card_mode = 'none' if (isinstance(card, str) and card == 'none') else 'libretro'
        o.update(co['card_off'] if self.card_mode == 'none' else co['card_on'])
        o.update(opts or {})
        # our own log sink (core log + guest TTY); the base class asks for GET_LOG_INTERFACE through _env, overridden below
        self._rs = C.CDLL(self._build_shim())
        self._rs.rs_open(C.c_char_p((self.out + '/core.log').encode()), C.c_char_p((self.out + '/tty.log').encode()))
        self._rs.rs_tty_read.argtypes = [C.c_char_p, C.c_uint]
        self._rs.rs_tty_read.restype = C.c_uint
        self._want_tty = tty
        if core == 'pcsx_rearmed' and tty:
            try:
                h = hashlib.sha1(open(core_path(core), 'rb').read()).hexdigest()
                self._psxout = PCSX_PSXOUT.get(h)
            except (OSError, RigSetupError):     # a missing core is reported by Emu.__init__ below
                self._psxout = None
        else:
            self._psxout = None
        self.tty_available = False
        Emu.__init__(self, core, disc, self.out, o, sysdir, audio)
        self._rs.rs_flush()
        # ---- memory card
        self.card = None
        if self.card_mode != 'none':
            n = self.lib.retro_get_memory_size(0)
            p = self.lib.retro_get_memory_data(0)
            if not p or n != MemCard.SIZE:
                raise RuntimeError('core %s exposes no 128 KiB save RAM (size %d): cannot attach a memory card' % (core, n))
            self._card_buf = (C.c_ubyte * n).from_address(p)
            if isinstance(card, (bytes, bytearray)):
                img = MemCard(card)
            elif card == 'blank':
                img = MemCard()
            elif card == 'core':
                img = MemCard(bytes(self._card_buf))      # whatever the core formatted itself
            else:
                img = MemCard.load(card)
            C.memmove(p, bytes(img.data), n)
            self.card_in = img
        self.disc = Disc(self.bin_path())
        self._rom = None
        # Preserve resolved libretro settings in private result.json. Without
        # this, a stock run and a 400%-CPU/10x-CD run look identical to QA.
        self.meta = {'disc': self.disc_path, 'core': core, 'card': card if isinstance(card, str) else 'bytes', 'syms': syms, 'fps': self.fps,
                     'exe_sha1': self.disc.sha1('PSX.EXE') if 'PSX.EXE' in self.disc.files else None, 'tty': self.tty_available,
                     'core_options': {k: v.decode('utf-8', 'replace') for k, v in sorted(self.opts.items())}}
        if self.sym and 'PSX.EXE' in self.disc.files:
            self.meta['syms_match_disc'] = self._syms_match()

    # ---- plumbing
    OUT_PATTERNS = ('sheet.png', 'result.json', 'script.txt', 'inputs.txt', 'tty_timeline.txt', 'speed.json')

    def _clean_out(self):
        """Remove the outputs of an earlier run in the same directory (numbered pictures, sheet, result, script, timeline), so
        that a directory never mixes two runs.  States, card images and subdirectories are left alone.  Returns the count."""
        import re
        n = 0
        for f in os.listdir(self.out):
            if re.match(r'^\d{3}_.*\.png$', f) or f in self.OUT_PATTERNS:
                try:
                    os.remove(os.path.join(self.out, f))
                    n += 1
                except OSError:
                    pass
        return n

    @staticmethod
    def _build_shim():
        return build_so(os.path.join(HERE, 'rigshim.c'), 'librigshim.so')

    def bin_path(self):
        return self.disc_path

    def _env(self, cmd, data):
        c = cmd & 0xffff
        if self._psxout and getattr(self, 'lib', None) is not None:
            # every environment call between retro_init (which clears the core's config) and the BIOS set-up in
            # retro_load_game: switch the BIOS text output on
            off, name, symoff = self._psxout
            base = C.cast(getattr(self.lib, name), C.c_void_p).value - symoff
            C.c_ubyte.from_address(base + off).value = 1
            self.tty_available = True
        if c == 27:     # GET_LOG_INTERFACE -> our sink
            C.cast(data, C.POINTER(LogCb))[0].log = C.cast(self._rs.rs_log, C.c_void_p)
            return True
        return Emu._env(self, cmd, data)

    def _syms_match(self):
        """True when the symbol file is an ELF whose loadable image equals the PSX.EXE on the disc (else None: cannot tell).
        A packed PSX.EXE (exe_image) is compared after rebuilding the image its crt0 makes: every PT_LOAD segment with file bytes,
        also those that lie beyond the packed file's end (the renderer and ragdoll overlays), must equal the image there."""
        try:
            d = open(self.syms_path, 'rb').read()
            if d[:4] != b'\x7fELF':
                return None
            exe = self.disc.read('PSX.EXE')
            t_addr, img = exe_image(exe, load_symbols(self.syms_path))
            phoff, = struct.unpack_from('<I', d, 0x1c)
            phentsize, phnum = struct.unpack_from('<HH', d, 0x2a)
            for i in range(phnum):
                p_type, p_off, p_va, p_pa, p_fsz, p_msz = struct.unpack_from('<6I', d, phoff + i * phentsize)
                if p_type == 1 and p_fsz:
                    o = p_va - t_addr
                    if o < 0 or o + p_fsz > len(img) or img[o:o + p_fsz] != d[p_off:p_off + p_fsz]:
                        return False
            return True
        except Exception:
            return None

    def log(self, *a):
        s = ' '.join(str(x) for x in a)
        self.events.append((self.nrun, s))
        if not self.quiet:
            print(s, flush=True)

    # ---- running and input (every change of the held buttons goes to self.script)
    def run(self, frames=1, buttons=()):
        b = tuple(sorted(buttons))
        if b != self._held:
            self.script.append((self.nrun, list(b)))
            self._held = b
        self.buttons = set(b)
        for _ in range(frames):
            self.lib.retro_run()
            self.nrun += 1
            self._ring_poll()
        if self.nrun - self._tty_polled >= 30:          # stamp new TTY lines with the frame (30 frames resolution)
            self._tty_polled = self.nrun
            self.tty()

    # ---- draw-ring tracking: run() looks at the ring after every emulator frame, so that complete guest frames (from one
    # gfx_fade_flip to the next) are kept even when one frame has more entries than fit beside the next one in the ring
    def _ring_reset(self):
        self._rseen = None          # ring count already consumed
        self._rcur = []             # entries of the guest frame being drawn
        self._rcur_ok = False       # its start was seen
        self._rframes = []          # the last complete frames: (emulator frame, entries)
        self._rflip_n = None        # ring count at the last flip
        self.frames_drawn = 0       # complete 2D frames seen since the reset
        self._rlast_at = None       # (emulator frame, guest frame) of the last complete frame

    def _ring_poll(self):
        n = self.r32(DL)
        if self._rseen is None:
            self._rseen = n
            return
        if n == self._rseen:
            return
        if n < self._rseen or n - self._rseen > 256:      # ring restarted, or entries were lost between two polls
            self._rcur, self._rcur_ok = [], False
            self._rseen = max(0, n - 256)
        d = self.read(DL + 32, 256 * 32)
        for k in range(self._rseen, n):
            e = struct.unpack_from('<5I', d, (k & 255) * 32)
            if e[0] == 1 or e[0] == 6:      # gfx_fade_flip ends a menu frame; the level starts each HUD frame with a page clear
                if self._rcur_ok:
                    self._rframes.append((self.nrun, self._rcur))
                    del self._rframes[:-12]
                    self.frames_drawn += 1
                    self._rlast_at = (self.nrun, self.gframes())
                self._rcur, self._rcur_ok = [], True
                self._rflip_n = k
            else:
                self._rcur.append((k,) + e)
                if len(self._rcur) > 4096:                # a screen that never flips (the level): keep the tail
                    del self._rcur[:2048]
                    self._rcur_ok = False
        self._rseen = n

    def release(self):
        if self._held:
            self.script.append((self.nrun, []))
            self._held = ()
        self.buttons = set()

    def hold(self, buttons, frames):
        self.run(frames, buttons)

    def press(self, *buttons, hold=6, after=30):
        """Press for `hold` frames, release for `after` frames."""
        self.run(hold, buttons)
        self.run(after)

    def wait_until(self, pred, max_frames, buttons=(), step=1, what=None):
        """Run until pred() is true.  Returns the number of frames waited, or None on timeout (logged)."""
        n = 0
        while n < max_frames:
            if pred():
                return n
            self.run(step, buttons)
            n += step
        if pred():
            return n
        if what:
            self.log('  timeout after %d frames waiting for %s (frame %d)' % (max_frames, what, self.nrun))
        return None

    def script_text(self):
        """The button script so far, one line per change: 'f<frame>: BTN+BTN' / 'f<frame>: (release)'."""
        return '\n'.join('f%d: %s' % (f, '+'.join(b) if b else '(release)') for f, b in self.script)

    # ---- pressing like a patient player (the port polls the pad rarely: once per presented frame)
    def polls(self):
        """Pad transfers the runtime did so far (symbol pad_polls); None without symbols."""
        return self.v('pad_polls')

    def tap(self, buttons, until=None, hold_polls=2, release_polls=1, wait=4000, max_hold=6000, what=None):
        """Click like a patient player: hold `buttons` until the runtime polled the pad hold_polls times with them down
        (without symbols: 600 frames; the hold ends early when until() turns true, but never before the runtime polled the
        pad once with them down), release for release_polls polls, then
        run until until() is true, at most `wait` frames.  Several screens of the game act on the release, so holding a
        button until something happens does not work.  Returns the frames from the press to the first moment until() was
        seen true (also kept as self.tap_true_at, an emulator frame; the call itself returns after the release was
        polled), or the frames held when until is None; None on timeout.
        An until() that is already true when the press starts (a condition read from the draw ring, such as "not on
        PAUSED" while the pause menu draws its text only in its first frames) used to end the hold after 2 frames: in
        the pause loop the runtime polls the pad about every 6 frames, so the click was lost and the game stayed paused."""
        if isinstance(buttons, str):
            buttons = [buttons]
        if self._held:
            self.run(2)
        t0, p0, n = self.nrun, self.polls(), 0
        self.tap_true_at = None             # emulator frame at which until() was first seen true (the click may end later)
        while n < max_hold:
            if until is not None and n and (p0 is None or self.polls() > p0) and until():
                self.tap_true_at = self.nrun
                break
            if (p0 is not None and self.polls() >= p0 + hold_polls) or (p0 is None and n >= 600):
                break
            self.run(2, buttons)
            n += 2
        p1, m = self.polls(), 0
        while m < max_hold:
            if (p1 is not None and self.polls() >= p1 + release_polls) or (p1 is None and m >= 600):
                break
            self.run(2)
            m += 2
            if until is not None and self.tap_true_at is None and until():
                self.tap_true_at = self.nrun
        if until is None:
            return n
        if self.wait_until(until, wait, step=2) is None:
            if what:
                self.log('  timeout: %s clicked at frame %d (held %d), %d frames later still no %s' % ('+'.join(buttons), t0, n, self.nrun - t0, what))
            return None
        if self.tap_true_at is None:
            self.tap_true_at = self.nrun
        return self.tap_true_at - t0

    def settle(self, n=2, max_frames=4000):
        """Wait until n complete 2D frames in a row were drawn with the same text (a screen that is built and idle).
        Returns the emulator frames waited, or None."""
        same, last, seen, m = 0, None, self.frames_drawn, 0
        while m < max_frames:
            self.run(2)
            m += 2
            if self.frames_drawn != seen:
                seen = self.frames_drawn
                t = self.screen()
                same = same + 1 if t == last else 1
                last = t
                if same >= n:
                    return m
        return None

    def wait_fade(self, max_frames=9000):
        """Menus fade in from white over many guest frames: wait until that is over (runtime symbol pp_fade_w back at 0;
        without symbols until two pictures 300 frames apart differ by less than 2).  Returns frames waited or None."""
        if 'pp_fade_w' in self.sym:
            return self.wait_until(lambda: self.v('pp_fade_w') == 0, max_frames, step=4)
        n, prev = 0, self.image()
        while n < max_frames:
            self.run(300)
            n += 300
            im = self.image()
            if diff(im, prev) < 2.0:
                return n
            prev = im
        return None

    def wait_presented(self, n=2, max_frames=6000):
        """Run until the runtime presented n more frames, so that the picture shows what the game drew last (symbol g_pres;
        without symbols 1200 frames).  The text read-back is ahead of the picture by up to two guest frames."""
        p0 = self.v('g_pres')
        if p0 is None:
            self.run(1200)
            return 1200
        return self.wait_until(lambda: self.v('g_pres') >= p0 + n, max_frames, step=2)

    def card_idle(self, quiet=1500, max_frames=12000):
        """Run until the runtime stopped writing the memory card for `quiet` frames (symbol mc_writes; without symbols just
        `quiet` frames).  Returns the frames waited."""
        if 'mc_writes' not in self.sym:
            self.run(quiet)
            return quiet
        n, last, since = 0, self.v('mc_writes'), 0
        while n < max_frames and since < quiet:
            self.run(50)
            n += 50
            w = self.v('mc_writes')
            since = since + 50 if w == last else 0
            last = w
        return n

    def screen(self):
        """The drawn text lines of the last complete 2D frame, as a tuple of strings."""
        return tuple(l['text'] for l in self.text_lines())

    def on(self, *subs):
        """True when every given word or Mark is part of the drawn text (case-insensitive)."""
        t = self.text()
        return all(contains(t, x) for x in subs)

    def wait_text(self, sub, max_frames, buttons=()):
        subs = [sub] if isinstance(sub, (str, Mark)) else list(sub)
        return self.wait_until(lambda: self.on(*subs), max_frames, buttons, step=2, what='text %r' % (subs,))

    def dispcnt(self):
        """The guest's DISPCNT (runtime register shadow); None without symbols."""
        return self.io16(0)

    def assist_tables(self):
        """Menu-assist key plans in the runtime: symbols KPL* with a size, as (name, address, size)."""
        return sorted((n, a, self.symsize.get(n, 0)) for n, a in self.sym.items() if n.startswith('KPL') and self.symsize.get(n, 0) >= 12)

    def assist_off(self):
        """Blank the menu-assist key plan(s) in RAM so that only the pad drives the menus (a rig intervention: say so in
        the report).  Returns the names blanked; [] when the symbol file names no plan (the assist then stays on)."""
        done = []
        for n, a, size in self.assist_tables():
            self.write(a, bytes(size))
            done.append(n)
        if done:
            self.log('  rig: menu assist plan blanked in RAM (%s) at frame %d' % (', '.join(done), self.nrun))
        return done

    # ---- PS1 memory by symbol
    def has(self, *names):
        return all(n in self.sym for n in names)

    def v(self, name, size=4, signed=False):
        a = self.sym.get(name)
        if a is None:
            return None
        d = self.read(a, size)
        return int.from_bytes(d, 'little', signed=signed)

    # ---- guest (GBA) memory
    def gread(self, a, n):
        h = g2h(a)
        if h is None:
            if (a >> 24) in (8, 9):
                return self.rom(a & 0x1ffffff, n)
            raise ValueError('GBA address %08x has no window' % a)
        return self.read(h, n)

    def g8(self, a): return self.gread(a, 1)[0]
    def g16(self, a): return int.from_bytes(self.gread(a, 2), 'little')
    def g32(self, a): return int.from_bytes(self.gread(a, 4), 'little')
    def gs8(self, a): return int.from_bytes(self.gread(a, 1), 'little', signed=True)
    def gs16(self, a): return int.from_bytes(self.gread(a, 2), 'little', signed=True)
    def gs32(self, a): return int.from_bytes(self.gread(a, 4), 'little', signed=True)

    def rom(self, off, n):
        """Bytes of the GBA ROM, read from ROM.BIN on the disc (the runtime pages it in from there)."""
        if self._rom is None:
            self._rom = self.disc.read('ROM.BIN')
        return self._rom[off:off + n]

    def io16(self, off):
        """Guest IO register (the runtime's io[] shadow), None without symbols."""
        a = self.sym.get('io')
        return None if a is None else self.r16(a + off)

    # ---- Payback state
    def level_clock(self): return self.g32(PB_CLOCK)
    def map_id(self): return self.gs16(PB_MAP)
    def grid_id(self): return self.gs16(PB_GRID_ID)
    def controlled(self): return self.gs16(PB_CONTROLLED)
    def nentity(self): return self.gs16(PB_NENTITY)
    def title_cursor(self): return self.gs32(PB_TITLE_CURSOR)
    def lives(self): return self.gs16(PB_LIVES)
    def level_end(self): return self.gs16(PB_LEVEL_END)
    def respawn(self): return self.gs16(PB_RESPAWN)
    def in_level(self): return self.level_clock() > 0 and 0 <= self.nentity() <= 100

    def _entp(self, p):
        """Entity pointer as stored by the guest: GBA 0x02xxxxxx or a host address inside the EWRAM window."""
        if (p >> 24) == 2:
            return EW + (p & 0x3ffff)
        if EW <= p < EW + 0x40000:
            return p
        return None

    def entity(self, i):
        """Entity record i: x, y (2048 a cell), z (19904 street level), heading (5760 a turn), descriptor, class (0 vehicle, 1 person)."""
        p = self.g32(PB_ENTITY + 4 * i)
        h = self._entp(p)
        if h is None:
            return None
        rec = self.read(h, 0x150)
        x, y = struct.unpack_from('<ii', rec, 4)
        z, = struct.unpack_from('<H', rec, 0xc)
        head, = struct.unpack_from('<h', rec, 0x12)
        desc, = struct.unpack_from('<I', rec, 0x1c)
        k = (desc - PB_DESC0) // 0x3c if 0 <= desc - PB_DESC0 < 128 * 0x3c else None
        cls = self.rom((desc + 0x26) & 0x1ffffff, 1)[0] if k is not None else None
        return {'i': i, 'ptr': p, 'x': x, 'y': y, 'z': z, 'heading': head, 'desc': desc, 'k': k, 'cls': cls,
                'kind': {0: 'vehicle', 1: 'person'}.get(cls, 'other'), 'health': struct.unpack_from('<h', rec, 0x68)[0],
                'score': struct.unpack_from('<i', rec, 0x90)[0], 'wanted': struct.unpack_from('<b', rec, 0x5a)[0], 'state': rec[0x10f]}

    def entities(self):
        n = self.nentity()
        if n < 0 or n > 100:
            return []
        return [e for e in (self.entity(i) for i in range(n + 1)) if e]

    def player(self):
        ci, n = self.controlled(), self.nentity()
        if not (0 <= ci <= n <= 100):
            return None
        return self.entity(ci)

    def pos(self):
        p = self.player()
        return None if p is None else (p['x'], p['y'], p['z'], p['heading'])

    # ---- the runtime's draw ring (rt.c DL, 0x8017c000): the last 256 calls of the game's 2D routines, in order
    # entry = (index, id, r0, r1, r2, r3): id 1 gfx_fade_flip (once per drawn guest frame), 2 gfx_blit_image (transparent: text
    # glyphs; r0 = image header in ROM, r1/r2 = x/y, r3 = the character code the text routine holds), 3 gfx_effect,
    # 4 gfx_blit_image_m4 (opaque backdrops), 6 clear page, 0x20 DISPCNT write (synthetic).
    def ring(self, last=256):
        d = self.read(DL, 32 + 256 * 32)
        n = struct.unpack_from('<I', d, 0)[0]
        out = []
        for k in range(max(0, n - last), n):
            e = struct.unpack_from('<5I', d, 32 + (k & 255) * 32)
            out.append((k,) + e)
        return n, out

    def ring_frame(self):
        """Draw calls of the last complete guest frame (between two gfx_fade_flip entries).  Uses the frames run() collected;
        before the first complete frame is seen (right after a state load) or on screens that draw without flipping
        (more than 512 entries since the last flip) it falls back to what the ring itself still holds.  A frame older
        than 8 guest frames (3000 emulator frames) counts as gone: the result is then empty."""
        n = self.r32(DL)
        if self._rframes and self._rflip_n is not None and n - self._rflip_n <= 512:
            f, gf = self._rlast_at
            now = self.gframes()
            if (gf is not None and now is not None and now - gf > 8) or self.nrun - f > 3000:
                return []           # nothing 2D was drawn for 8 guest frames: that screen is gone (logos, loading)
            return self._rframes[-1][1]
        n, r = self.ring()
        flips = [i for i, e in enumerate(r) if e[1] == 1]
        if len(flips) >= 2:
            return r[flips[-2] + 1:flips[-1]]
        if len(flips) == 1:
            a, b = r[:flips[0]], r[flips[0] + 1:]
            return a if len(a) >= len(b) else b
        return r

    def blink_lines(self):
        """Texts of the lines whose font changed between the complete frames kept by run() (menus blink the selected line)."""
        seen = {}
        for f, ent in self._rframes:
            for l in self.text_lines(ent):
                seen.setdefault((l['text'], l['y']), set()).add(l['font'])
        return [t for (t, y), fs in seen.items() if len(fs) > 1]

    def text_lines(self, entries=None):
        """Text the game drew in the last complete guest frame, read from the draw ring (no pixels involved):
        list of {'text', 'x', 'y', 'font'} in draw order.  font = glyph table base (r0 - 8 * character): menus draw the
        selected line with another font than the rest."""
        ent = self.ring_frame() if entries is None else entries
        gl = []
        for e in ent:
            k, id_, r0, r1, r2, r3 = e
            if id_ == 2 and 0x20 <= r3 < 0x100 and (r0 >> 24) == 8 and (r0 & 3) == 0:
                gl.append((r0 - 8 * r3, struct.unpack('<i', struct.pack('<I', r1))[0], struct.unpack('<i', struct.pack('<I', r2))[0], r3))
        cnt = {}
        for b, x, y, c in gl:
            cnt[b] = cnt.get(b, 0) + 1
        fonts = getattr(self, '_fonts', set())
        fonts |= {b for b, n in cnt.items() if n >= 3}
        self._fonts = fonts
        lines = []
        cur = None
        for b, x, y, c in gl:
            if b not in fonts:
                continue
            if cur and cur['font'] == b and abs(y - cur['ys'][-1]) <= 4 and x > cur['xs'][-1]:
                cur['xs'].append(x); cur['ys'].append(y); cur['cs'].append(c)
            else:
                cur = {'font': b, 'xs': [x], 'ys': [y], 'cs': [c]}
                lines.append(cur)
        out = []
        for l in lines:
            dx = sorted(b - a for a, b in zip(l['xs'], l['xs'][1:]))
            adv = dx[len(dx) // 4] if dx else 8          # lower quartile = the plain advance
            t = chr(l['cs'][0])
            for i in range(1, len(l['cs'])):
                if l['xs'][i] - l['xs'][i - 1] >= adv * 1.6:
                    t += ' '
                t += chr(l['cs'][i])
            out.append({'text': t, 'x': l['xs'][0], 'y': l['ys'][0], 'font': l['font']})
        return out

    def text(self):
        """The drawn text as one string, lines joined by ' | '."""
        return ' | '.join(l['text'] for l in self.text_lines())

    def menu(self, items):
        """Among the given menu items (words or Marks; case-insensitive, substring match), which are on screen and which one
        is drawn in the odd (highlight) font.  Returns (found: list of (item, line), selected item or None)."""
        ls = self.text_lines()
        found = []
        for it in items:
            for l in ls:
                if contains(l['text'], it):
                    found.append((it, l))
                    break
        sel = None
        if len(found) >= 2:
            fc = {}
            for it, l in found:
                fc[l['font']] = fc.get(l['font'], 0) + 1
            odd = [it for it, l in found if fc[l['font']] == 1]
            if len(odd) == 1 and len(fc) == 2:
                sel = odd[0]
        return found, sel

    # ---- runtime counters (need symbols)
    COUNTERS = ('g_gframes', 'g_pres', 'io_nd', 'g_nvbl', 'cold_loads', 'cold_calls', 'rom_miss_count', 'cd_sectors', 'sf3_ok', 'st3_render',
                'ip_enters', 'ip_stat_steps', 'ip_stat_undef', 'ip_stat_calls', 'ip_undef', 'ip_swis', 'ip_depth_max',
                'pad_polls', 'pad_fails', 'mc_reads', 'mc_writes', 'mc_err', 'sv_ok_writes', 'sv_have', 'sv_ready', 'sv_seq',
                'pp_lost', 'pp_nreset', 'max_lines', 'cd_dbg', 'cdda_playing', 'sf3_retry')

    def counters(self):
        return {n: self.v(n) for n in self.COUNTERS if n in self.sym}

    def gframes(self):
        """Guest (GBA) frames since power-on: the runtime's g_gframes, else io_cyc / 280896, else None."""
        x = self.v('g_gframes')
        if x is None and 'io_cyc' in self.sym:
            x = self.v('io_cyc') // 280896
        return x

    def gba_frame(self):
        """GBA frames of the runtime's time base (io_cyc / 280896): what the menu assist plan is keyed on."""
        x = self.v('io_cyc')
        return None if x is None else x // 280896

    def keys_seen(self):
        """GBA KEYINPUT word the guest last read (active low), None without symbols."""
        return self.v('io_keys')

    def assist_pressed(self):
        """GBA keys that are down in the guest's KEYINPUT without coming from the pad (the menu assist's presses), as a name
        list.  With the symbol pad_gba (the pad word of the runtime's last poll) this is exact; without it, keys not held
        on the pad right now, which also names the rig's own presses for as long as the runtime has not polled again."""
        k = self.keys_seen()
        if k is None:
            return None
        pg = self.v('pad_gba')
        if pg is not None:
            down = (~k) & pg & 0x3ff
            return [n for n, m in GBA_KEYS.items() if down & m]
        mine = 0
        for b in self._held:
            if b in PS1_TO_GBA:
                mine |= GBA_KEYS[PS1_TO_GBA[b]]
        down = (~k) & 0x3ff & ~mine
        return [n for n, m in GBA_KEYS.items() if down & m]

    def rom_cache(self):
        """ROM offsets of the 4 KiB pages now in the runtime's page cache (symbol slot_owner: page number + 1 per slot, 0 =
        empty), in slot order; None without the symbol.  The slot count is the symbol's size / 4."""
        if not self.has('slot_owner'):
            return None
        n = (self.symsize.get('slot_owner') or 0) // 4
        if not n:
            return None
        ow = struct.unpack('<%dI' % n, self.read(self.sym['slot_owner'], 4 * n))
        return [None if o == 0 else (o - 1) << 12 for o in ow]

    def rom_cluster_last(self):
        """ROM offset of the 16 KiB cluster fetched from the disc last (from rom_miss_last, else from the cache slots the
        runtime filled last: the 4 before slot_next)."""
        if self.has('rom_miss_last'):
            return self.v('rom_miss_last') & ~0x3fff
        c = self.rom_cache()
        if not c or not self.has('slot_next'):
            return None
        n = len(c)
        s = (self.v('slot_next') - 4) % n
        if all(c[(s + k) % n] is None for k in range(4)):     # these four are being filled right now (the CPU sits in
            s = (s - 4) % n                                    # the next cd_read): the last finished fetch is the one before
        for k in range(4):
            if c[(s + k) % n] is not None:
                return c[(s + k) % n] & ~0x3fff
        return None

    def speed(self, frames=60):
        """Run `frames` emulator frames; returns guest frames, level clock ticks, presents, CD sectors, ROM cluster loads ...
        per 60 emulator frames, plus (with symbols) which 16 KiB ROM clusters were fetched from the disc most often:
        'top_clusters' = ['<ROM offset>:<times sampled>', ...] and 'clusters_seen' = how many different ones."""
        g0, c0, p0, s0 = self.gframes(), self.level_clock(), self.v('g_pres'), self.v('cd_sectors')
        m0 = {n: self.v(n) for n in ('rom_miss_count', 'cold_loads', 'st3_render', 'ip_enters') if n in self.sym}
        hist = {}
        if self.has('rom_miss_count') and (self.has('rom_miss_last') or self.has('slot_owner', 'slot_next')):
            last = self.v('rom_miss_count')
            for _ in range(frames):
                self.run(1, self._held)
                c = self.v('rom_miss_count')
                if c != last:             # at most one cluster comes in per emulator frame with this core's CD timing
                    last = c
                    k = self.rom_cluster_last()
                    if k is not None:
                        hist[k] = hist.get(k, 0) + 1
        else:
            self.run(frames, self._held)
        sc = 60.0 / frames
        r = {'clock_per_60': (self.level_clock() - c0) * sc}
        if g0 is not None:
            r['gframes_per_60'] = (self.gframes() - g0) * sc
        if p0 is not None:
            r['presents_per_60'] = (self.v('g_pres') - p0) * sc
        if s0 is not None:
            r['cd_sectors_per_60'] = (self.v('cd_sectors') - s0) * sc
        for name, key in (('rom_miss_count', 'rom_cluster_loads_per_60'), ('cold_loads', 'cold_loads_per_60'), ('st3_render', 'frames3d_per_60'), ('ip_enters', 'interp_enters_per_60')):
            if name in m0:
                r[key] = (self.v(name) - m0[name]) * sc
        if hist:
            r['clusters_seen'] = len(hist)
            r['top_clusters'] = ['%07x:%d' % (k, n) for k, n in sorted(hist.items(), key=lambda kv: -kv[1])[:8]]
        return r

    # ---- TTY (the runtime's dbg() text through BIOS putchar)
    TTY_NOISE = ('present ', 'cd_read lba')

    def tty(self):
        """All guest TTY text so far.  Every complete new line (but the periodic 'present' lines, the first cd_read traces and
        their 'ssss...pause' marks) also goes to self.tty_timeline as (emulator frame, line): the frame is when the rig read it,
        at most 30 frames after the guest printed it (run() reads the TTY every 30 frames)."""
        buf = C.create_string_buffer(65536)
        while True:
            n = self._rs.rs_tty_read(buf, 65536)
            if not n:
                break
            self._tty += buf.raw[:n]
        if self.core_name != 'pcsx_rearmed':
            ob = self._ob_tty_read()
            if ob:
                self._tty += ob
                try:                    # tty.log as on the fast core (there the core's log sink writes it)
                    with open(os.path.join(self.out, 'tty.log'), 'ab') as f:
                        f.write(ob)
                except OSError:
                    pass
        e = self._tty.rfind(b'\n')
        if e >= self._tty_lpos:
            for raw in bytes(self._tty[self._tty_lpos:e]).split(b'\n'):
                l = raw.decode('latin1').strip()
                if not l or l.startswith(self.TTY_NOISE) or (set(l) <= set('s') or (l.endswith('pause') and set(l[:-5]) <= set('s'))):
                    continue
                if len(self.tty_timeline) < 50000:
                    self.tty_timeline.append((self.nrun, l))
            self._tty_lpos = e + 1
        return self._tty.decode('latin1')

    _ob_rd = 0

    def _ob_tty_read(self):
        """The accurate cores run openboot (rig/openboot) as firmware: it keeps the game's putchar text in a RAM ring (u32 write
        count at 0x5000, 16 KiB of text from 0x5008; trace table with magic 'OBT1' at 0x1000, see BOOTROM.md).  Returns the
        bytes written since the last call, b'' when no openboot trace table is in RAM."""
        try:
            if self.r32(0x1000) != 0x3154424f:
                return b''
            wr = self.r32(0x5000)
        except Exception:
            return b''
        rd = self._ob_rd
        if rd is None or wr < rd:     # a state was loaded: skip the text of the time before it
            self._ob_rd = wr
            return b''
        if wr - rd > 0x4000:
            rd = wr - 0x4000
        out = bytearray()
        while rd < wr:
            o = rd % 0x4000
            n = min(wr - rd, 0x4000 - o)
            out += self.read(0x5008 + o, n)
            rd += n
        self._ob_rd = rd
        if out and not self.tty_available:
            self.tty_available = True
            self.meta['tty'] = 'openboot ring'
        return bytes(out)

    def tty_when(self, *words, since=0):
        """(frame, line) of the TTY lines read at or after emulator frame `since` that hold one of the words."""
        self.tty()
        return [(f, l) for f, l in self.tty_timeline if f >= since and any(w in l for w in words)]

    RENDERER_WORDS = ('CONFLICT', 're-init', 'sf3_ok', 'deferred sf3_init', 'COLD load')

    def renderer_events(self, since=0, limit=6):
        """Short text of the renderer / overlay lines of the TTY since a frame: 'f<frame> <line>' (who switched the 3D view
        off and when it came back: 'SF3 CONFLICT ... renderer off', 'sf3 re-init after overlay load', 'sf3_ok 1')."""
        ev = self.tty_when(*self.RENDERER_WORDS, since=since)
        return ['f%d %s' % (f, l[:70]) for f, l in ev[:limit]] + (['... %d more' % (len(ev) - limit)] if len(ev) > limit else [])

    def tty_new(self):
        """TTY text since the previous tty_new() call."""
        t = self.tty()
        s = t[self._tty_seen:]
        self._tty_seen = len(t)
        return s

    FAULT_WORDS = ('BADRD', 'BADWR', 'RT_MISS', 'PANIC', 'panic', 'UNDEF', 'overflow', 'CD timeout', 'CD error', 'CD busy', 'MC write fail', 'MC dir error', 'MC crc', 'MC bad meta', 'gather failed', 'SPIN')

    def tty_lines(self, *words):
        """Lines of the TTY that hold one of the words."""
        return [l for l in self.tty().splitlines() if any(w in l for w in words)]

    def tty_faults(self, text=None):
        """Lines of the TTY that report a fault of the runtime."""
        t = self.tty() if text is None else text
        return [l for l in t.splitlines() if any(w in l for w in self.FAULT_WORDS)]

    # ---- pictures
    def snap(self, tag, save=True, im=None, frame=None):
        """Screenshot for the contact sheet (and OUT/NNN_tag.png).  im/frame: a picture taken earlier (e.g. by a Scan)."""
        im = im if im is not None else self.image()
        cap = 'f%d %s' % (self.nrun if frame is None else frame, tag)
        self.snaps.append((im, cap))
        if save and im is not None:
            safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in tag)[:60]
            im.save('%s/%03d_%s.png' % (self.out, len(self.snaps), safe))
        return im

    def sheet(self, path=None, cols=4, title=None):
        path = path or (self.out + '/sheet.png')
        return contact_sheet(self.snaps, path, cols=cols, title=title)

    def view3d(self):
        """Colours in the middle band of the picture (a drawn 3D view has many, a blank page next to none)."""
        im = self.image()
        if im is None:
            return 0
        w, h = im.size
        return ncolors(im, (0, h // 4, w, 3 * h // 4))

    # ---- the GPU out of the core's save state: registers and the whole VRAM, independent of the core's video output
    def gpu(self, state=None):
        """{'status', 'regs' (GP1 0..8 as last written), 'ex' (GP0 E0..E7), 'display': (x, y, w, h), 'vram': bytes (1024 x 512
        words of 15 bit colour), 'bpp24'} parsed from a save state of pcsx_rearmed (this machine now, or the given state).
        The block is found by its shape (version word 1, then the control registers with their own number in the top byte),
        so a changed layout gives None rather than nonsense.  None for other cores."""
        if self.core_name != 'pcsx_rearmed':
            return None
        st = state if state is not None else self.save_state()
        need = 8 + 1024 + 1024 * 512 * 2
        def good(p):
            if p is None or p < 0 or p + need > len(st) or st[p:p + 4] != b'\x01\x00\x00\x00':
                return False
            c = struct.unpack_from('<9I', st, p + 8)
            return all((c[i] >> 24) == i for i in (5, 6, 7, 8))
        p = self._gpu_off
        if not good(p):
            p, base = None, 37 + 128 * 96 * 3 + 0x200000 + 0x80000 + 0x10000
            i = st.find(b'\x01\x00\x00\x00', base)
            while i >= 0 and i + need <= len(st):
                if good(i):
                    p = i
                    break
                i = st.find(b'\x01\x00\x00\x00', i + 1)
            if p is None:
                return None
            self._gpu_off = p
        status = struct.unpack_from('<I', st, p + 4)[0]
        ctl = struct.unpack_from('<256I', st, p + 8)
        r5, r6, r7, r8 = ctl[5], ctl[6], ctl[7], ctl[8]
        hres = 368 if r8 & 0x40 else (256, 320, 512, 640)[r8 & 3]
        div = {256: 10, 320: 8, 512: 5, 640: 4, 368: 7}[hres]
        x1, x2 = r6 & 0xfff, (r6 >> 12) & 0xfff
        y1, y2 = r7 & 0x3ff, (r7 >> 10) & 0x3ff
        w = min(hres, max(0, (x2 - x1) // div)) or hres
        h = max(0, y2 - y1) * (2 if (r8 & 0x24) == 0x24 else 1) or 240
        return {'status': status, 'regs': list(ctl[:9]), 'ex': list(ctl[0xe0:0xe8]), 'bpp24': bool(r8 & 0x10),
                'display': (r5 & 0x3ff, (r5 >> 10) & 0x1ff, w, h), 'vram': st[p + 8 + 1024:p + need]}

    def vram_image(self, state=None, gpu=None):
        """The whole VRAM as a 1024 x 512 picture (every word read as 15 bit colour: frame buffers look right, 4/8 bit
        textures and CLUTs look like noise).  None when the core's state cannot be read."""
        gp = gpu or self.gpu(state)
        if gp is None:
            return None
        from PIL import Image
        # PS1 15 bit colour: red in bits 0-4, green 5-9, blue 10-14 = Pillow's 'RGB;15' ('BGR;15' swaps red and blue)
        return Image.frombuffer('RGB', (1024, 512), gp['vram'], 'raw', 'RGB;15', 0, 1)

    def display_image(self, state=None, gpu=None):
        """The picture the GPU is set to show (display start and size from GP1 05h..08h), cut from VRAM.  This is the machine's
        own frame buffer: use it when the core's video output cannot be trusted (right after loading a state)."""
        gp = gpu or self.gpu(state)
        if gp is None or gp['bpp24']:
            return None
        x, y, w, h = gp['display']
        im = self.vram_image(gpu=gp)
        if x + w <= 1024 and y + h <= 512:
            return im.crop((x, y, x + w, y + h))
        from PIL import Image
        out = Image.new('RGB', (w, h))
        for oy in (0, 512):
            for ox in (0, 1024):
                out.paste(im, (ox - x, oy - y))
        return out

    def fb_sha1(self, state=None):
        """sha1 over the displayed part of VRAM (raw 15 bit words), or None."""
        gp = self.gpu(state)
        if gp is None:
            return None
        x, y, w, h = gp['display']
        v, hh = gp['vram'], hashlib.sha1()
        for yy in range(y, y + h):
            o = ((yy & 511) * 1024 + x) * 2
            hh.update(v[o:o + w * 2] if x + w <= 1024 else v[o:(yy & 511) * 2048 + 2048] + v[(yy & 511) * 2048:(yy & 511) * 2048 + (x + w - 1024) * 2])
        return hh.hexdigest()

    def picture_stale(self):
        """True while the core's video output still shows the machine from before the last load_state (pcsx_rearmed hands
        over a new picture only when the guest touches the GPU again, which in the level can take a thousand frames)."""
        if self._stale_from is not None and self._real_frames > self._stale_from:
            self._stale_from = None
        return self._stale_from is not None

    def image(self):
        """The core's picture; while that is stale after a state load, the displayed frame buffer cut from VRAM instead
        (scaled to the core's picture size), so screenshots and picture checks never show the old machine."""
        if self.picture_stale():
            im = self.display_image()
            if im is not None:
                if self.size[0] and self.size[1] and im.size != tuple(self.size):
                    im = im.resize(tuple(self.size))
                return im
        return Emu.image(self)

    def load_state(self, s):
        Emu.load_state(self, s)
        self._stale_from = self._real_frames
        self._ob_rd = None          # openboot TTY ring: what it holds now was printed before the state was saved

    # ---- where the CPU is (for hangs): registers out of the core's save state
    def cpu(self):
        """{'pc', 'ra', 'sp', 'gpr'} read from a save state of pcsx_rearmed (header 37 bytes + 128x96x3 thumbnail, RAM, ROM,
        hardware page, then the register block: 34 GPR, 32 CP0, 2 x 32 GTE, pc).  None for other cores / layouts."""
        if self.core_name != 'pcsx_rearmed':
            return None
        st = self.save_state()
        off = 32 + 4 + 1 + 128 * 96 * 3 + 0x200000 + 0x80000 + 0x10000
        if st[:9] != b'STv4 PCSX' or len(st) < off + 600:
            return None
        g = struct.unpack_from('<34I', st, off)
        if g[0] != 0:
            return None
        return {'pc': struct.unpack_from('<I', st, off + 34 * 4 + 3 * 32 * 4)[0], 'ra': g[31], 'sp': g[29], 'gpr': g}

    def addr_name(self, a):
        """symbol+offset of a PS1 address (nearest symbol below), or hex."""
        if not self.sym:
            return '%08x' % a
        if getattr(self, '_symtab', None) is None:
            self._symtab = sorted((v, n) for n, v in self.sym.items() if 0x80010000 <= v < 0x80200000)
        import bisect
        i = bisect.bisect_right(self._symtab, (a, '~')) - 1
        if i < 0 or a - self._symtab[i][0] > 0x8000:
            return '%08x' % a
        return '%s+0x%x' % (self._symtab[i][1], a - self._symtab[i][0])

    def backtrace(self, depth=10, span=0x600):
        """Rough call chain of the PS1 CPU now: pc, ra, then every word on the stack (sp .. sp+span) that points behind a
        jal/jalr in RAM.  Names with symbols.  Stale return addresses left on the stack can appear: read it as a hint."""
        c = self.cpu()
        if c is None:
            return None
        out = [self.addr_name(c['pc']), self.addr_name(c['ra'])]
        sp = c['sp']
        if not (0x80000000 <= sp < 0x80200000):
            return out
        n = min(span, 0x80200000 - sp) & ~3
        words = struct.unpack('<%dI' % (n // 4), self.read(sp, n))
        for w in words:
            if len(out) >= depth + 2:
                break
            if 0x80010008 <= w < 0x80200000 and w % 4 == 0:
                ins = struct.unpack('<I', self.read(w - 8, 4))[0]
                if (ins >> 26) == 3 or ((ins >> 26) == 0 and (ins & 0x3f) == 9):
                    nm = self.addr_name(w)
                    if nm != out[-1]:
                        out.append(nm)
        return out

    def cpu_where(self, samples=1, gap=7):
        """'pc (ra)' as symbol names; with samples > 1 the distinct places seen while running on (gap frames apart)."""
        seen = {}
        for i in range(samples):
            c = self.cpu()
            if c is None:
                return None
            k = '%s (ra %s)' % (self.addr_name(c['pc']), self.addr_name(c['ra']))
            seen[k] = seen.get(k, 0) + 1
            if i + 1 < samples:
                self.run(gap, self._held)
        return seen

    def stalled(self, frames=3000):
        """True when the runtime presented no frame and counted no guest frame for `frames` emulator frames (runs them).
        Needs symbols; None without."""
        if not self.has('g_pres', 'g_gframes'):
            return None
        a = (self.v('g_pres'), self.v('g_gframes'))
        self.run(frames, self._held)
        return a == (self.v('g_pres'), self.v('g_gframes'))

    # ---- checks
    def check(self, ok, text, detail=''):
        self.results.append((bool(ok), text, detail))
        self.log('%s %s%s' % ('PASS' if ok else 'FAIL', text, (' [' + str(detail) + ']') if detail != '' else ''))
        return bool(ok)

    def note(self, text):
        self.log('NOTE ' + text)

    # ---- memory card of this run
    def card_now(self):
        """The card as the core holds it right now (None when no card is attached)."""
        if self.card_mode == 'none':
            return None
        return MemCard(bytes(self._card_buf))

    def save_card(self, path=None):
        c = self.card_now()
        if c is None:
            return None
        path = path or (self.out + '/card1.mcd')
        c.save(path)
        return path

    # ---- save states
    # A state of this core is only good when it is taken while the runtime is NOT inside present(): the GPU plugin does not
    # save a half-sent GP0 command or a running VRAM upload, the words that follow after the reload are then taken for new
    # commands (garbage, and a segfault of the core was seen that way).  present() counts g_pres at its start and toggles buf
    # at its end, so "no present running" is (g_pres & 1) == buf.  Needs the symbols g_pres and buf.
    def in_present(self):
        p, b = self.v('g_pres'), self.v('buf')
        if p is None or b is None:
            return None
        return (p & 1) != (b & 1)

    def _leave_present(self, max_frames=3000):
        """Step until the runtime is not inside present() (the core's GPU keeps a transfer in flight outside the state:
        neither save nor load a state at such a moment).  No-op without symbols."""
        n = 0
        while self.in_present() and n < max_frames:
            self.lib.retro_run()
            n += 1
        return n

    def fingerprint(self):
        """RAM and picture of this moment.  'fb' is the displayed part of VRAM read from the core's state (pcsx_rearmed);
        'img' is the core's video output and only present when that is not stale (see picture_stale)."""
        fp = {'ram': self.ram_sha1(), 'fb': self.fb_sha1()}
        if not self.picture_stale():
            im = Emu.image(self)
            fp['img'] = hashlib.sha1(im.tobytes()).hexdigest() if im is not None else None
        return fp

    @staticmethod
    def same_fingerprint(a, b):
        """Compare two fingerprints on what both carry: RAM always, the frame buffer when both have it, else the core picture."""
        if not a or not b or a.get('ram') != b.get('ram'):
            return False
        if a.get('fb') and b.get('fb'):
            return a['fb'] == b['fb']
        if a.get('img') and b.get('img'):
            return a['img'] == b['img']
        return True

    def save_state_file(self, path, note='', wait=1800, verify=20):
        """Step (no input) to a frame boundary where no present() runs, save the state, then prove it in this process: run
        `verify` frames, reload, run them again and compare RAM and picture.  The fingerprint after `verify` frames goes to
        PATH.json, so that a fresh process can repeat the proof (sessions/state_check.py).  Returns the metadata, or None
        when no good state could be made (nothing is written then).  The session continues from the saved point."""
        self.release()
        tried = 0
        while True:
            n = 0
            ip = self.in_present()
            while ip and n < wait:
                self.run(1)
                n += 1
                ip = self.in_present()
            if ip:
                self.log('  save_state_file: present() never idle at a frame boundary within %d frames, no state written' % wait)
                return None
            s = self.save_state()
            card = bytes(self._card_buf) if self.card_mode != 'none' else None
            f0 = self.nrun
            if verify:
                self.run(verify)
                a = self.fingerprint()
                self._leave_present()
                self.load_state(s)
                self._ring_reset()
                if card is not None:
                    C.memmove(C.addressof(self._card_buf), card, len(card))
                self.nrun = f0
                self.run(verify)
                b = self.fingerprint()
                self._leave_present()
                self.load_state(s)
                self._ring_reset()
                if card is not None:
                    C.memmove(C.addressof(self._card_buf), card, len(card))
                self.nrun = f0
                self.run(1)          # the session goes on one frame after the saved point (the video callback needs a frame)
                if not self.same_fingerprint(a, b):
                    tried += 1
                    self.log('  save_state_file: reload does not reproduce (attempt %d, frame %d)%s' % (tried, f0, '' if ip is not None else ' [no symbols: cannot tell whether present() was running]'))
                    if tried >= 5:
                        return None
                    self.run(7)
                    continue
            else:
                a = None
            meta = {'core': self.core_name, 'exe_sha1': self.meta.get('exe_sha1'), 'frame': f0, 'note': note, 'size': len(s),
                    'state_sha1': hashlib.sha1(s).hexdigest(), 'card_sha1': hashlib.sha1(card).hexdigest() if card is not None else None,
                    'verify_frames': verify, 'fingerprint': a, 'safe_point': ip is not None, 'opts': {k: v.decode() for k, v in self.opts.items()}}
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            open(path, 'wb').write(s)
            json.dump(meta, open(path + '.json', 'w'), indent=1)
            if card is not None:
                open(path + '.mcd', 'wb').write(card)
            return meta

    def state_fits(self, path):
        """(True, meta) when the state file was made by this core from this disc's PSX.EXE, else (False, reason)."""
        if not os.path.exists(path):
            return False, 'no such file'
        meta = json.load(open(path + '.json')) if os.path.exists(path + '.json') else {}
        if meta.get('core') and meta['core'] != self.core_name:
            return False, 'made with core %s, this run uses %s' % (meta['core'], self.core_name)
        if meta.get('exe_sha1') and self.meta.get('exe_sha1') and meta['exe_sha1'] != self.meta['exe_sha1']:
            return False, 'made from another PSX.EXE (sha1 %s, this disc %s)' % (meta['exe_sha1'][:12], self.meta['exe_sha1'][:12])
        return True, meta

    def load_state_file(self, path, with_card=True):
        """Load a state written by save_state_file (same core, same disc).  The memory card image saved next to it is put back
        first (the core's state does not carry the card).  One frame is run afterwards so the picture is there."""
        meta = json.load(open(path + '.json')) if os.path.exists(path + '.json') else {}
        if meta.get('exe_sha1') and self.meta.get('exe_sha1') and meta['exe_sha1'] != self.meta['exe_sha1']:
            raise RuntimeError('state %s was made with another PSX.EXE (%s, this disc %s)' % (path, meta['exe_sha1'], self.meta['exe_sha1']))
        if meta.get('core') and meta['core'] != self.core_name:
            raise RuntimeError('state %s was made with core %s' % (path, meta['core']))
        if with_card and self.card_mode != 'none' and os.path.exists(path + '.mcd'):
            d = open(path + '.mcd', 'rb').read()
            C.memmove(C.addressof(self._card_buf), d, len(d))
        # the core's GPU keeps a transfer in flight outside the state: leave present() in THIS machine before replacing it
        self._leave_present()
        self.load_state(open(path, 'rb').read())
        self._ring_reset()
        self.run(1)
        return meta

    def ram_sha1(self):
        return hashlib.sha1(bytes(self.ram)).hexdigest()

    # ---- end of a session
    def finish(self, name, extra=None, sheet_cols=4):
        """Contact sheet, card image, button script, TTY, results JSON.  Returns the process exit code (0 = no FAIL)."""
        self.release()
        self.sheet(self.out + '/sheet.png', cols=sheet_cols, title='%s  |  %s  |  %s' % (name, os.path.basename(self.disc_path), self.core_name))
        cardsum = None
        if self.card_mode != 'none':
            self.save_card()
            cardsum = self.card_now().summary()
        open(self.out + '/script.txt', 'w').write(self.script_text() + '\n')
        self.tty()
        self._rs.rs_flush()
        open(self.out + '/tty_timeline.txt', 'w').write(''.join('f%d %s\n' % fl for fl in self.tty_timeline))
        nfail = sum(1 for r in self.results if not r[0])
        res = {'session': name, 'meta': self.meta, 'frames': self.nrun, 'pass': sum(1 for r in self.results if r[0]), 'fail': nfail,
               'results': [{'ok': r[0], 'text': r[1], 'detail': str(r[2])} for r in self.results], 'counters': self.counters(),
               'tty_faults': self.tty_faults(), 'card': cardsum, 'events': self.events, 'extra': extra or {},
               'tty_timeline': [{'frame': f, 'line': l} for f, l in self.tty_timeline if not l.startswith('INTERP')][:600]}
        json.dump(res, open(self.out + '/result.json', 'w'), indent=1, default=str)
        print('%s: %d PASS, %d FAIL, %d frames, out %s' % (name, res['pass'], nfail, self.nrun, self.out), flush=True)
        return 1 if nfail else 0


def std_args(desc, extra=None):
    """Common command line of the sessions: disc, core, outdir, symbols, card."""
    import argparse
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument('--disc', required=True, help='.cue (or .bin/.iso) of the build under test')
    ap.add_argument('--core', default='pcsx_rearmed')
    ap.add_argument('--out', required=True, help='output directory of this run')
    ap.add_argument('--syms', default=None, help='ELF / nm output / linker map of THIS build (optional: counters and assist detection)')
    ap.add_argument('--card', default='blank', help="blank | none | path of a 128 KiB card image")
    ap.add_argument('--state-dir', default=os.environ.get('RIG_STATES') or os.path.join(HERE, 'states'),
                    help='where reusable save states are written / looked up (default: $RIG_STATES, else states/ next to this file)')
    ap.add_argument('--opt', action='append', default=[], help='core option KEY=VALUE (repeatable), e.g. pcsx_rearmed_cd_turbo=enabled')
    if extra:
        extra(ap)
    a = ap.parse_args()
    a.core_opts = dict(kv.split('=', 1) for kv in a.opt if '=' in kv)
    return a

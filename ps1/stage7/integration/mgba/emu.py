"""Headless GBA emulator wrapper over libmgba (a tiny C shim, gbashim.c, loaded with ctypes) for the Star-FlyBack tests.

    from emu import Emu, load_symbols
    e = Emu('game.gba', elf='stuntfox-merge.elf')   # elf optional: e.S['s2_dbg'], e.S['frame_count']
    e.run(60, ['A', 'UP'])                           # 60 frames with A and UP held
    e.r32(0x02001e00); e.w8(0x02001e4e, 3)           # EWRAM 0x02000000, IWRAM 0x03000000, ROM 0x08000000, IO 0x04000000
    e.frame                                          # numpy uint8 (160, 240, 3) RGB
    e.screenshot('x.png'); e.pc; e.wedged(); e.vblanks

Keys: A B SELECT START RIGHT LEFT UP DOWN R L (the GBA KEYINPUT bit order). Builds libgbashim.so on first use (gcc, -lmgba).
No save file is written anywhere: the cartridge save lives in memory.
"""
import ctypes
import os
import subprocess
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = {k: 1 << i for i, k in enumerate(['A', 'B', 'SELECT', 'START', 'RIGHT', 'LEFT', 'UP', 'DOWN', 'R', 'L'])}
W, H = 240, 160

# address ranges the PC may be in on a healthy GBA (BIOS, EWRAM, IWRAM, ROM and its mirrors)
OK_PC = [(0x00000000, 0x00004000), (0x02000000, 0x02040000), (0x03000000, 0x03008000), (0x08000000, 0x0E000000)]


def _lib():
    so, src = os.path.join(HERE, 'libgbashim3.so'), os.path.join(HERE, 'gbashim.c')
    if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
        subprocess.check_call(['gcc', '-O2', '-shared', '-fPIC', src, '-o', so, '-lmgba'])
    L = ctypes.CDLL(so)
    u32, vp = ctypes.c_uint32, ctypes.c_void_p
    L.gba_open.restype = vp
    L.gba_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    for n in ('r8', 'r16', 'r32', 'pc', 'frames'):
        getattr(L, 'gba_' + n).restype = u32
    L.gba_reg.restype = u32
    L.gba_statesize.restype = ctypes.c_size_t
    for n in ('r8', 'r16', 'r32'):
        getattr(L, 'gba_' + n).argtypes = [vp, u32]
    for n in ('w8', 'w16', 'w32'):
        getattr(L, 'gba_' + n).argtypes = [vp, u32, u32]
    L.gba_read.argtypes = [vp, u32, vp, u32]
    L.gba_write.argtypes = [vp, u32, vp, u32]
    L.gba_run.argtypes = [vp, ctypes.c_int]
    L.gba_cover.argtypes = [vp, ctypes.c_int, vp]
    L.gba_prof.argtypes = [vp, ctypes.c_int, u32, vp, vp]
    L.gba_keys.argtypes = [vp, u32]
    L.gba_fb.argtypes = [vp, vp]
    L.gba_reg.argtypes = [vp, ctypes.c_int]
    L.gba_savestate.argtypes = L.gba_loadstate.argtypes = [vp, vp]
    return L


_L = None


class Symbols(dict):
    """name -> address from an ELF (llvm-nm, else readelf). Static (local) symbols are included; a name used by
    several translation units keeps its global one, else the first."""
    def __init__(self, elf=None):
        super().__init__()
        self.elf = elf
        if elf:
            self._load(elf)

    def _load(self, elf):
        try:
            out = subprocess.check_output(['llvm-nm', elf], text=True, stderr=subprocess.DEVNULL)
            rows = [l.split() for l in out.splitlines()]
            rows = [(r[2], int(r[0], 16), r[1]) for r in rows if len(r) == 3]
        except (OSError, subprocess.CalledProcessError):
            out = subprocess.check_output(['readelf', '-sW', elf], text=True)
            rows = []
            for l in out.splitlines():
                f = l.split()
                if len(f) == 8 and f[3] in ('OBJECT', 'FUNC', 'NOTYPE') and f[1] != '00000000':
                    rows.append((f[7], int(f[1], 16), 'T' if f[4] == 'GLOBAL' else 't'))
        for name, addr, kind in rows:
            if name not in self or kind.isupper():
                self[name] = addr

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def load_symbols(elf):
    return Symbols(elf)


class Emu:
    def __init__(self, rom, elf=None, vblank_symbol='frame_count'):
        global _L
        if _L is None:
            _L = _lib()
        self.L = _L
        self.rom = rom
        err = ctypes.c_int(0)
        self.h = _L.gba_open(os.fsencode(rom), ctypes.byref(err))
        if not self.h:
            raise RuntimeError('cannot load %s (error %d)' % (rom, err.value))
        self.S = Symbols(elf)
        self.vsym = self.S.get(vblank_symbol)
        self.keys = 0
        self.frames = 0                      # frames run through this object (not rolled back by load_state)
        self.hist = []                       # (pc, framebuffer crc, vblanks) of the last frames, for wedged()
        self._fb = None
        self._fbbuf = ctypes.create_string_buffer(W * H * 4)
        self._st = None
        self.on_frame = None                 # callable(emu) after each frame, if set

    # ---- running ----
    @staticmethod
    def keymask(keys):
        if isinstance(keys, int):
            return keys
        m = 0
        for k in keys or ():
            m |= KEYS[k.upper()]
        return m

    def set_keys(self, keys=()):
        """hold exactly these keys (names, or a bitmask) from now on"""
        self.keys = self.keymask(keys)
        self.L.gba_keys(self.h, self.keys)

    def run(self, n=1, keys=None):
        """step n frames; keys (names) are held for them (None: keep what set_keys left held)"""
        if keys is not None:
            self.set_keys(keys)
        for _ in range(n):
            self.L.gba_run(self.h, 1)
            self.frames += 1
            self._fb = None
            if len(self.hist) > 1200:
                del self.hist[:600]
            self.hist.append((self.pc, self.vblanks, None if self.vsym else zlib.crc32(self._fbraw())))
            if self.on_frame:
                self.on_frame(self)
        return self

    def tap(self, key, hold=6, after=24):
        """press for hold frames, release, wait after frames (menus poll about every 5 frames: hold > 5)"""
        self.run(hold, [key] if key else [])
        self.run(after, [])

    def reset(self):
        self.L.gba_reset(self.h)
        self.hist.clear()

    def save_state(self):
        if self._st is None:
            self._st = self.L.gba_statesize(self.h)
        buf = ctypes.create_string_buffer(self._st)
        self.L.gba_savestate(self.h, buf)
        return buf

    def load_state(self, st):
        if not self.L.gba_loadstate(self.h, st):
            raise RuntimeError('load_state failed')
        self._fb = None
        self.hist.clear()
        self.L.gba_keys(self.h, self.keys)

    # ---- memory ----
    def r8(self, a):
        return self.L.gba_r8(self.h, a)

    def r16(self, a):
        return self.L.gba_r16(self.h, a)

    def r32(self, a):
        return self.L.gba_r32(self.h, a)

    def w8(self, a, v):
        self.L.gba_w8(self.h, a, v & 0xff)

    def w16(self, a, v):
        self.L.gba_w16(self.h, a, v & 0xffff)

    def w32(self, a, v):
        self.L.gba_w32(self.h, a, v & 0xffffffff)

    read8, read16, read32, write8, write16, write32 = r8, r16, r32, w8, w16, w32

    def s32(self, a):
        v = self.r32(a)
        return v - (1 << 32) if v & 0x80000000 else v

    def read(self, a, n):
        """n bytes from a, as bytes"""
        buf = ctypes.create_string_buffer(n)
        self.L.gba_read(self.h, a, buf, n)
        return buf.raw

    def write(self, a, data):
        data = bytes(data)
        self.L.gba_write(self.h, a, data, len(data))

    # ---- picture ----
    def _fbraw(self):
        self.L.gba_fb(self.h, self._fbbuf)
        return self._fbbuf.raw

    @property
    def frame(self):
        """the 240x160 screen, numpy uint8 (160, 240, 3) RGB"""
        if self._fb is None:
            self.L.gba_fb(self.h, self._fbbuf)
            self._fb = np.frombuffer(self._fbbuf, np.uint8).reshape(H, W, 4)[:, :, :3].copy()
        return self._fb

    def screenshot(self, path, scale=1):
        from PIL import Image
        im = Image.fromarray(self.frame)
        if scale != 1:
            im = im.resize((W * scale, H * scale), Image.NEAREST)
        im.save(path)
        return path

    # ---- CPU / health ----
    @property
    def pc(self):
        return self.L.gba_pc(self.h)

    def reg(self, i):
        """r0..r15, 16 = CPSR"""
        return self.L.gba_reg(self.h, i)

    @property
    def vblanks(self):
        """the game's own vblank count when the ELF has frame_count (the IRQ handler's), else frames emulated"""
        return self.r32(self.vsym) if self.vsym else self.frames

    @staticmethod
    def pc_ok(pc):
        return any(lo <= pc < hi for lo, hi in OK_PC)

    def wedged(self, window=120):
        """None while the core looks alive, else the reason: the PC is outside BIOS/EWRAM/IWRAM/ROM, or it has not moved
        for `window` frames and (with the ELF's frame_count) the vblank interrupt has not counted either; with no ELF
        the test is at most 4 different frame-end PCs and the same picture over `window` frames, which a static screen (a pause) can also give:
        pass a larger window there."""
        pc = self.pc
        if not self.pc_ok(pc):
            return 'pc %08x outside BIOS/EWRAM/IWRAM/ROM' % pc
        h = self.hist[-window:]
        if len(h) < window:
            return None
        if self.vsym:
            if h[0][1] == h[-1][1]:
                return 'stuck at pc %08x: the vblank count has not moved in %d frames' % (pc, window)
            return None
        if len({x[0] for x in h}) <= 4 and len({x[2] for x in h}) == 1:
            return 'stuck at pc %08x, picture unchanged for %d frames (no ELF: a static screen looks the same)' % (pc, window)
        return None

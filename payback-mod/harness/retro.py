"""Minimal headless libretro frontend for scripted testing (ctypes)."""
import ctypes as C, os, sys
from PIL import Image

S = os.path.dirname(os.path.abspath(__file__))
CORES = {'gba': os.environ.get('MGBA_CORE', S + '/mgba/build/mgba_libretro.so'),
         'snes': os.environ.get('SNES9X_CORE', S + '/snes9x/libretro/snes9x_libretro.so')}

BTN = {'B': 0, 'Y': 1, 'SELECT': 2, 'START': 3, 'UP': 4, 'DOWN': 5, 'LEFT': 6,
       'RIGHT': 7, 'A': 8, 'X': 9, 'L': 10, 'R': 11}

class GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]

ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUD = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL = C.CFUNCTYPE(None)
STATE = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

class Emu:
    def __init__(self, system, rom):
        self.lib = C.CDLL(CORES[system])
        self.fmt = 0  # 0RGB1555
        self.frame = None
        self.buttons = set()
        self._sysdir = C.c_char_p(S.encode())
        self._cbs = [ENV(self._env), VID(self._vid), AUD(lambda l, r: None),
                     AUDB(lambda d, n: n), POLL(lambda: None), STATE(self._state)]
        L = self.lib
        L.retro_set_environment(self._cbs[0])
        L.retro_init()
        L.retro_set_video_refresh(self._cbs[1]); L.retro_set_audio_sample(self._cbs[2])
        L.retro_set_audio_sample_batch(self._cbs[3]); L.retro_set_input_poll(self._cbs[4])
        L.retro_set_input_state(self._cbs[5])
        self.romdata = open(rom, 'rb').read()
        self._buf = C.create_string_buffer(self.romdata, len(self.romdata))
        gi = GameInfo(rom.encode(), C.cast(self._buf, C.c_void_p), len(self.romdata), None)
        assert L.retro_load_game(C.byref(gi)), 'load failed'
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.restype = C.c_size_t
        L.retro_serialize_size.restype = C.c_size_t

    def _env(self, cmd, data):
        cmd &= 0xffff
        if cmd == 10:  # SET_PIXEL_FORMAT
            self.fmt = C.cast(data, C.POINTER(C.c_int))[0]; return True
        if cmd in (9, 31):  # system / save dir
            C.cast(data, C.POINTER(C.c_char_p))[0] = self._sysdir; return True
        if cmd == 15:  # GET_VARIABLE
            C.cast(data, C.POINTER(C.c_char_p * 2))[0][1] = None; return False
        if cmd == 27: return False
        return False

    def _vid(self, data, w, h, pitch):
        if not data: return
        raw = C.string_at(data, pitch * h)
        if self.fmt == 1:
            img = Image.frombuffer('RGB', (w, h), raw, 'raw', 'BGRX', pitch, 1)
        else:
            img = Image.frombuffer('RGB', (w, h), raw, 'raw', 'BGR;16' if self.fmt == 2 else 'BGR;15', pitch, 1)
        self.frame = img.convert('RGB')

    def _state(self, port, dev, idx, id_):
        if port != 0 or dev != 1: return 0
        return 1 if id_ in self.buttons else 0

    def run(self, frames=1, buttons=()):
        self.buttons = {BTN[b] for b in buttons}
        for _ in range(frames): self.lib.retro_run()
        self.buttons = set()

    def press(self, *buttons, hold=4, after=20):
        self.run(hold, buttons); self.run(after)

    def shot(self, path):
        self.frame.save(path)

    def mem(self, kind=2):
        p = self.lib.retro_get_memory_data(kind); n = self.lib.retro_get_memory_size(kind)
        return C.string_at(p, n) if p else b''

    def save_state(self):
        n = self.lib.retro_serialize_size(); b = C.create_string_buffer(n)
        assert self.lib.retro_serialize(b, n); return b.raw

    def load_state(self, s):
        b = C.create_string_buffer(s, len(s)); assert self.lib.retro_unserialize(b, len(s))

    def read(self, addr, n):
        b = C.create_string_buffer(n); self.lib.harness_readblock(addr, b, n); return b.raw

    def write8(self, addr, v): self.lib.harness_write8(addr, v)

    def write32(self, addr, v):
        for i in range(4): self.lib.harness_write8(addr + i, (v >> (8 * i)) & 0xff)

    def r32(self, addr):
        import struct; return struct.unpack('<i', self.read(addr, 4))[0]

    class Hit(C.Structure):
        _fields_ = [('pc', C.c_uint32), ('addr', C.c_uint32), ('val', C.c_uint32), ('lr', C.c_uint32),
                    ('size', C.c_uint8), ('write', C.c_uint8), ('thumb', C.c_uint8), ('pad', C.c_uint8)]

    def watch(self, lo, hi, mode):
        C.c_uint32.in_dll(self.lib, 'harness_wlo').value = lo
        C.c_uint32.in_dll(self.lib, 'harness_whi').value = hi
        C.c_int.in_dll(self.lib, 'harness_wmode').value = mode
        C.c_uint32.in_dll(self.lib, 'harness_nhits').value = 0

    def hits(self):
        n = C.c_uint32.in_dll(self.lib, 'harness_nhits').value
        arr = (Emu.Hit * 65536).in_dll(self.lib, 'harness_hits')
        return [(h.pc, h.addr, h.val, h.lr, h.size, h.write, h.thumb) for h in arr[:n]]

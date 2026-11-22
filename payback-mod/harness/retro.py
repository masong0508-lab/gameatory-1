"""Headless libretro frontend with stock-core memory-map access.

Only one Emu may be active per process: libretro cores have global state.
The optional mGBA harness patch adds watchpoints; normal gameplay, screenshots,
savestates, and canonical GBA RAM reads/writes work with a stock mGBA core.
"""
import ctypes as C
import os
import struct
from PIL import Image

S = os.path.dirname(os.path.abspath(__file__))
CORES = {'gba': os.environ.get('MGBA_CORE', S + '/mgba/build/mgba_libretro.so'),
         'snes': os.environ.get('SNES9X_CORE', S + '/snes9x/libretro/snes9x_libretro.so')}

BTN = {'B': 0, 'Y': 1, 'SELECT': 2, 'START': 3, 'UP': 4, 'DOWN': 5, 'LEFT': 6,
       'RIGHT': 7, 'A': 8, 'X': 9, 'L': 10, 'R': 11}

class GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]

class MemoryDescriptor(C.Structure):
    _fields_ = [('flags', C.c_uint64), ('ptr', C.c_void_p), ('offset', C.c_size_t),
                ('start', C.c_size_t), ('select', C.c_size_t), ('disconnect', C.c_size_t),
                ('length', C.c_size_t), ('addrspace', C.c_char_p)]

class MemoryMap(C.Structure):
    _fields_ = [('descriptors', C.POINTER(MemoryDescriptor)), ('num_descriptors', C.c_uint)]

ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUD = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL = C.CFUNCTYPE(None)
STATE = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

class Emu:
    def __init__(self, system, rom, *, capture_video=True):
        rom = os.fspath(rom)
        self.system = system
        self.lib = C.CDLL(CORES[system])
        self.fmt = 0  # 0RGB1555
        self.frame = None
        self.frames = 0
        self.capture_video = capture_video
        self.maps = []
        self.closed = False
        self.buttons = set()
        self._sysdir = C.c_char_p(S.encode())
        self._cbs = [ENV(self._env), VID(self._vid), AUD(lambda l, r: None),
                     AUDB(lambda d, n: n), POLL(lambda: None), STATE(self._state)]
        L = self.lib
        L.retro_load_game.argtypes = [C.POINTER(GameInfo)]
        L.retro_load_game.restype = C.c_bool
        L.retro_get_memory_data.argtypes = [C.c_uint]
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.argtypes = [C.c_uint]
        L.retro_get_memory_size.restype = C.c_size_t
        L.retro_serialize_size.restype = C.c_size_t
        L.retro_serialize.argtypes = [C.c_void_p, C.c_size_t]
        L.retro_serialize.restype = C.c_bool
        L.retro_unserialize.argtypes = [C.c_void_p, C.c_size_t]
        L.retro_unserialize.restype = C.c_bool
        self._patched_read = hasattr(L, 'harness_readblock')
        self._patched_write = hasattr(L, 'harness_write8')
        if self._patched_read:
            L.harness_readblock.argtypes = [C.c_uint32, C.c_void_p, C.c_uint32]
            L.harness_readblock.restype = None
        if self._patched_write:
            L.harness_write8.argtypes = [C.c_uint32, C.c_uint32]
            L.harness_write8.restype = None
        L.retro_set_environment(self._cbs[0])
        L.retro_init()
        L.retro_set_video_refresh(self._cbs[1]); L.retro_set_audio_sample(self._cbs[2])
        L.retro_set_audio_sample_batch(self._cbs[3]); L.retro_set_input_poll(self._cbs[4])
        L.retro_set_input_state(self._cbs[5])
        self.romdata = open(rom, 'rb').read()
        self._buf = C.create_string_buffer(self.romdata, len(self.romdata))
        gi = GameInfo(rom.encode(), C.cast(self._buf, C.c_void_p), len(self.romdata), None)
        if not L.retro_load_game(C.byref(gi)):
            L.retro_deinit()
            self.closed = True
            raise RuntimeError('libretro core could not load ROM')

    def _env(self, cmd, data):
        cmd &= 0xffff
        if cmd == 10:  # SET_PIXEL_FORMAT
            self.fmt = C.cast(data, C.POINTER(C.c_int))[0]; return True
        if cmd in (9, 31):  # system / save dir
            C.cast(data, C.POINTER(C.c_char_p))[0] = self._sysdir; return True
        if cmd == 15:  # GET_VARIABLE
            C.cast(data, C.POINTER(C.c_char_p * 2))[0][1] = None; return False
        if cmd == 36:  # SET_MEMORY_MAPS (also supplied with the experimental flag)
            memory_map = C.cast(data, C.POINTER(MemoryMap))[0]
            self.maps = [MemoryDescriptor.from_buffer_copy(memory_map.descriptors[i])
                         for i in range(memory_map.num_descriptors)]
            return True
        if cmd == 27: return False
        return False

    def _vid(self, data, w, h, pitch):
        if not data or not self.capture_video: return
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
        if self.closed:
            raise RuntimeError('emulator is closed')
        self.buttons = {BTN[b] for b in buttons}
        for _ in range(frames):
            self.lib.retro_run()
            self.frames += 1
        self.buttons = set()

    def press(self, *buttons, hold=4, after=20):
        self.run(hold, buttons); self.run(after)

    def shot(self, path):
        if self.frame is None:
            raise RuntimeError('no captured video frame; run with capture_video enabled')
        self.frame.save(path)

    def mem(self, kind=2):
        p = self.lib.retro_get_memory_data(kind); n = self.lib.retro_get_memory_size(kind)
        if not p and self.system == 'gba' and kind in (2, 3):
            # Some mGBA builds expose RAM only through SET_MEMORY_MAPS.
            address, size = (0x02000000, 0x40000) if kind == 2 else (0x06000000, 0x18000)
            return self.read(address, size)
        return C.string_at(p, n) if p else b''

    def save_state(self):
        n = self.lib.retro_serialize_size(); b = C.create_string_buffer(n)
        if not n or not self.lib.retro_serialize(b, n):
            raise RuntimeError('libretro state serialization failed')
        return b.raw

    def load_state(self, s):
        b = C.create_string_buffer(s, len(s))
        if not self.lib.retro_unserialize(b, len(s)):
            raise RuntimeError('libretro state restore failed')

    def _mapped_address(self, addr, n, *, write=False):
        """Resolve a canonical region; mirrors and MMIO writes are not emulated.

        Stock libretro gives direct backing pointers, not CPU bus operations.
        Reject writes outside GBA RAM so a successful test cannot accidentally
        depend on side effects that a plain memory write does not implement.
        """
        if n < 0:
            raise ValueError('negative memory length')
        if write and self.system == 'gba' and addr >> 24 not in (2, 3, 5, 6, 7, 14):
            raise ValueError('stock-core writes are limited to canonical GBA RAM')
        for region in self.maps:
            if not region.ptr or region.disconnect or (write and region.flags & 1):
                continue
            offset = addr - region.start
            if 0 <= offset and offset + n <= region.length:
                return region.ptr + region.offset + offset
        raise ValueError(f'unmapped {"write" if write else "read"}: 0x{addr:08x}+{n}')

    def read(self, addr, n):
        if n < 0:
            raise ValueError('negative memory length')
        if self._patched_read:
            b = C.create_string_buffer(n)
            self.lib.harness_readblock(addr, b, n)
            return b.raw
        return C.string_at(self._mapped_address(addr, n), n)

    def write8(self, addr, v):
        if self._patched_write:
            self.lib.harness_write8(addr, v & 0xff)
        else:
            C.c_uint8.from_address(self._mapped_address(addr, 1, write=True)).value = v & 0xff

    def write16(self, addr, v):
        for i in range(2): self.write8(addr + i, (v >> (8 * i)) & 0xff)

    def write32(self, addr, v):
        for i in range(4): self.write8(addr + i, (v >> (8 * i)) & 0xff)

    def r32(self, addr):
        return struct.unpack('<i', self.read(addr, 4))[0]

    def u32(self, addr): return struct.unpack('<I', self.read(addr, 4))[0]
    def s16(self, addr): return struct.unpack('<h', self.read(addr, 2))[0]
    def u16(self, addr): return struct.unpack('<H', self.read(addr, 2))[0]

    def close(self):
        if not self.closed:
            self.lib.retro_unload_game()
            self.lib.retro_deinit()
            self.closed = True

    def __enter__(self): return self

    def __exit__(self, *_): self.close()

    class Hit(C.Structure):
        _fields_ = [('pc', C.c_uint32), ('addr', C.c_uint32), ('val', C.c_uint32), ('lr', C.c_uint32),
                    ('size', C.c_uint8), ('write', C.c_uint8), ('thumb', C.c_uint8), ('pad', C.c_uint8)]

    def watch(self, lo, hi, mode):
        if not hasattr(self.lib, 'harness_wlo'):
            raise NotImplementedError('watchpoints require the optional mgba-harness.patch core')
        C.c_uint32.in_dll(self.lib, 'harness_wlo').value = lo
        C.c_uint32.in_dll(self.lib, 'harness_whi').value = hi
        C.c_int.in_dll(self.lib, 'harness_wmode').value = mode
        C.c_uint32.in_dll(self.lib, 'harness_nhits').value = 0

    def hits(self):
        if not hasattr(self.lib, 'harness_nhits'):
            raise NotImplementedError('watchpoints require the optional mgba-harness.patch core')
        n = C.c_uint32.in_dll(self.lib, 'harness_nhits').value
        arr = (Emu.Hit * 65536).in_dll(self.lib, 'harness_hits')
        return [(h.pc, h.addr, h.val, h.lr, h.size, h.write, h.thumb) for h in arr[:n]]

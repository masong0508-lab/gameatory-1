#!/usr/bin/env python3
"""retro_ps1.py: headless libretro frontend for PlayStation cores (PCSX-ReARMed, SwanStation, Beetle PSX).

    from retro_ps1 import Emu
    e = Emu('pcsx_rearmed', 'path/to/disc.cue', work='runs/try1', opts={'pcsx_rearmed_bios': 'HLE'})
    e.run(600); e.run(4, ['CROSS']); e.shot('a.png'); e.r32(0x80010000); e.ram  (2 MiB bytes view)
    s = e.save_state(); e.load_state(s)

One Emu per process (cores keep global state). Frames are exact: retro_run is one video frame, input is sampled per frame.
Buttons: SELECT L3 R3 START UP RIGHT DOWN LEFT L2 R2 L1 R1 TRIANGLE CIRCLE CROSS SQUARE.
CLI:  retro_ps1.py CORE DISC OUTDIR FRAMES [--shots 300,600,...] [--keys "f0-f1:BTN+BTN;..."] [--opt k=v ...] [--sys DIR]
The log callback of the core goes to OUTDIR/core.log (through a small C shim, liblog.so, built on first use).

Where things are (environment, each with a default inside this directory; see README.md):
  RIG_CORES   the libretro cores: pcsx_rearmed_libretro.so, swanstation_libretro.so, mednafen_psx_libretro.so (default ./cores)
  RIG_SYSTEM  openboot under the names scph5500.bin, scph5501.bin, scph5502.bin, for SwanStation and Beetle (default ./system)
  RIG_BUILD   where the small C shims are compiled to (default ./build)
CORE is a name of CORE_FILES or a path to a libretro .so.
"""
import ctypes as C
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE_FILES = {'pcsx_rearmed': 'pcsx_rearmed_libretro.so',
              'swanstation': 'swanstation_libretro.so',
              'beetle': 'mednafen_psx_libretro.so'}
# the Debian/Ubuntu package libretro-beetle-psx, when it is installed (another build of Beetle PSX than the buildbot's)
SYSTEM_CORES = {'beetle_apt': '/usr/lib/x86_64-linux-gnu/libretro/mednafen_psx_libretro.so'}
BIOS_NAMES = ('scph5500.bin', 'scph5501.bin', 'scph5502.bin')
BUILDBOT = 'https://buildbot.libretro.com/nightly/linux/x86_64/latest/'


class RigSetupError(RuntimeError):
    """Something the rig needs from outside the repository (a core, the openboot directory) is not where it was looked for."""


def cores_dir():
    return os.path.abspath(os.environ.get('RIG_CORES') or os.path.join(HERE, 'cores'))


def core_path(core):
    """The shared object of a core: a name of CORE_FILES (looked up in RIG_CORES), 'beetle_apt', or a path to a .so."""
    if core in CORE_FILES:
        p = os.path.join(cores_dir(), CORE_FILES[core])
        if not os.path.isfile(p):
            raise RigSetupError('core %r not found: %s does not exist.  Download %s.zip from the libretro buildbot (%s), unpack '
                                'it into %s, or set RIG_CORES to the directory that holds it (README.md, "Cores").'
                                % (core, p, CORE_FILES[core], BUILDBOT, cores_dir()))
        return p
    if core in SYSTEM_CORES:
        if not os.path.isfile(SYSTEM_CORES[core]):
            raise RigSetupError('core %r is the distribution package of Beetle PSX (%s), which is not installed; use core '
                                "'beetle' (from RIG_CORES) instead" % (core, SYSTEM_CORES[core]))
        return SYSTEM_CORES[core]
    if os.path.isfile(core):
        return os.path.abspath(core)
    raise RigSetupError('unknown core %r: give one of %s or the path of a libretro .so' % (core, ', '.join(sorted(CORE_FILES))))


def system_dir(path=None):
    """The firmware directory for SwanStation and Beetle.  An explicit `path` (a --sys option) is used as given: a directory
    with an openboot variant, or an empty one on purpose (the cores then run the open-source BIOS they carry inside).
    Otherwise RIG_SYSTEM, else ./system, which must hold openboot (built by openboot/build.sh, never a Sony BIOS) under the
    three names of BIOS_NAMES: anything else is an error, because the cores would quietly run something else."""
    if path:
        return os.path.abspath(path)
    d = os.path.abspath(os.environ.get('RIG_SYSTEM') or os.path.join(HERE, 'system'))
    missing = [n for n in BIOS_NAMES if not os.path.isfile(os.path.join(d, n))]
    if missing:
        raise RigSetupError('the openboot system directory %s lacks %s.  Build openboot (sh openboot/build.sh) and copy '
                            'openboot/build/openboot.bin there under each of the names %s, or set RIG_SYSTEM to a directory '
                            'that has them (README.md, "openboot").' % (d, ', '.join(missing), ', '.join(BIOS_NAMES)))
    return d


def build_so(src, name):
    """Compile a small C shim of the rig into RIG_BUILD (default ./build) unless an up-to-date copy is there.  Returns its path."""
    d = os.path.abspath(os.environ.get('RIG_BUILD') or os.path.join(HERE, 'build'))
    os.makedirs(d, exist_ok=True)
    so = os.path.join(d, name)
    if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
        subprocess.check_call(['gcc', '-O1', '-shared', '-fPIC', src, '-o', so])
    return so
# libretro joypad ids -> PlayStation names
BTN = {'CROSS': 0, 'SQUARE': 1, 'SELECT': 2, 'START': 3, 'UP': 4, 'DOWN': 5, 'LEFT': 6, 'RIGHT': 7,
       'CIRCLE': 8, 'TRIANGLE': 9, 'L1': 10, 'R1': 11, 'L2': 12, 'R2': 13, 'L3': 14, 'R3': 15}


class GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


class Variable(C.Structure):
    _fields_ = [('key', C.c_char_p), ('value', C.c_char_p)]


class LogCb(C.Structure):
    _fields_ = [('log', C.c_void_p)]


class AvInfo(C.Structure):
    _fields_ = [('base_w', C.c_uint), ('base_h', C.c_uint), ('max_w', C.c_uint), ('max_h', C.c_uint),
                ('aspect', C.c_float), ('fps', C.c_double), ('rate', C.c_double)]


ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUD = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL = C.CFUNCTYPE(None)
STATE = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

SHIM = r'''
#include <stdarg.h>
#include <stdio.h>
static FILE *f;
void shim_open(const char *p) { f = fopen(p, "w"); if (f) setvbuf(f, 0, _IOLBF, 0); }
void shim_log(int level, const char *fmt, ...) { va_list a; if (!f) return; fprintf(f, "[%d] ", level); va_start(a, fmt); vfprintf(f, fmt, a); va_end(a); }
'''


def _shim():
    src = os.path.join(HERE, 'liblog.c')
    if not os.path.exists(src):           # liblog.c is SHIM; write it only when the file is missing
        open(src, 'w').write(SHIM)
    return C.CDLL(build_so(src, 'liblog.so'))


class Emu:
    def __init__(self, core, disc, work, opts=None, sysdir=None, audio=False):
        self.work = os.path.abspath(work)
        os.makedirs(self.work, exist_ok=True)
        self.sysdir = os.path.abspath(sysdir or (self.work + '/system'))
        os.makedirs(self.sysdir, exist_ok=True)
        self.savedir = self.work + '/saves'
        os.makedirs(self.savedir, exist_ok=True)
        self.opts = {k: v.encode() for k, v in (opts or {}).items()}
        self.asked = {}
        self.fmt = 0
        self.frame = None
        self.size = (0, 0)
        self.frames = 0
        self.buttons = set()
        self.audio = bytearray() if audio else None
        self.unknown_env = set()
        self.shim = _shim()
        self.shim.shim_open(C.c_char_p((self.work + '/core.log').encode()))
        self._keep = [C.c_char_p(self.sysdir.encode()), C.c_char_p(self.savedir.encode())]
        self.lib = L = C.CDLL(core_path(core))
        self._cbs = [ENV(self._env), VID(self._vid), AUD(self._aud), AUDB(self._audb), POLL(lambda: None), STATE(self._state)]
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
        L.retro_set_controller_port_device.argtypes = [C.c_uint, C.c_uint]
        L.retro_get_system_av_info.argtypes = [C.POINTER(AvInfo)]
        L.retro_set_environment(self._cbs[0])
        L.retro_set_video_refresh(self._cbs[1])
        L.retro_set_audio_sample(self._cbs[2])
        L.retro_set_audio_sample_batch(self._cbs[3])
        L.retro_set_input_poll(self._cbs[4])
        L.retro_set_input_state(self._cbs[5])
        L.retro_init()
        self._path = C.c_char_p(os.path.abspath(disc).encode())
        gi = GameInfo(self._path, None, 0, None)
        if not L.retro_load_game(C.byref(gi)):
            raise RuntimeError('retro_load_game failed (see %s/core.log)' % self.work)
        L.retro_set_controller_port_device(0, 1)
        av = AvInfo()
        L.retro_get_system_av_info(C.byref(av))
        self.fps = av.fps

    # --- callbacks
    def _env(self, cmd, data):
        cmd &= 0xffff
        if cmd == 9:      # GET_SYSTEM_DIRECTORY
            C.cast(data, C.POINTER(C.c_char_p))[0] = self._keep[0]
            return True
        if cmd == 31:     # GET_SAVE_DIRECTORY
            C.cast(data, C.POINTER(C.c_char_p))[0] = self._keep[1]
            return True
        if cmd == 10:     # SET_PIXEL_FORMAT
            self.fmt = C.cast(data, C.POINTER(C.c_int))[0]
            return True
        if cmd == 15:     # GET_VARIABLE
            v = C.cast(data, C.POINTER(Variable))
            key = v[0].key.decode() if v[0].key else ''
            self.asked[key] = self.opts.get(key)
            if key in self.opts:
                v[0].value = self.opts[key]
                return True
            v[0].value = None
            return False
        if cmd == 17:     # GET_VARIABLE_UPDATE
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        if cmd == 27:     # GET_LOG_INTERFACE
            C.cast(data, C.POINTER(LogCb))[0].log = C.cast(self.shim.shim_log, C.c_void_p)
            return True
        if cmd == 3:      # GET_CAN_DUPE
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd in (8, 11, 16, 34, 35, 36, 44, 53, 54, 55, 59, 67, 68, 69, 70):   # levels, descriptors, variables, infos, maps
            return cmd not in (53, 54, 67, 68)   # say no to the newer core-option forms so the core falls back to SET_VARIABLES
        if cmd == 52:     # GET_CORE_OPTIONS_VERSION
            C.cast(data, C.POINTER(C.c_uint))[0] = 0
            return True
        self.unknown_env.add(cmd)
        return False

    def _vid(self, data, w, h, pitch):
        self.frames += 1
        if not data or not w or not h:
            return
        self.size = (w, h)
        self.frame = (C.string_at(data, pitch * h), pitch)

    def _aud(self, l, r):
        if self.audio is not None:
            self.audio += int(l & 0xffff).to_bytes(2, 'little') + int(r & 0xffff).to_bytes(2, 'little')

    def _audb(self, d, n):
        if self.audio is not None:
            self.audio += C.string_at(d, n * 4)
        return n

    def _state(self, port, dev, idx, id_):
        if port != 0 or dev != 1:
            return 0
        if id_ == 256:    # RETRO_DEVICE_ID_JOYPAD_MASK
            return sum(1 << BTN[b] for b in self.buttons)
        return 1 if any(BTN[b] == id_ for b in self.buttons) else 0

    # --- driving
    def run(self, frames=1, buttons=()):
        self.buttons = set(buttons)
        for _ in range(frames):
            self.lib.retro_run()
        self.buttons = set()

    def press(self, *buttons, hold=4, after=20):
        self.run(hold, buttons)
        self.run(after)

    def image(self):
        from PIL import Image
        if not self.frame:
            return None
        raw, pitch = self.frame
        w, h = self.size
        if self.fmt == 1:      # XRGB8888
            return Image.frombuffer('RGBA', (w, h), raw, 'raw', 'BGRA', pitch, 1).convert('RGB')
        mode = 'BGR;16' if self.fmt == 2 else 'BGR;15'
        return Image.frombuffer('RGB', (w, h), raw, 'raw', mode, pitch, 1)

    def shot(self, path):
        im = self.image()
        if im:
            im.save(path)
        return im

    # --- memory (PS1 main RAM, 2 MiB; kuseg/kseg0/kseg1 addresses all accepted)
    @property
    def ram(self):
        p = self.lib.retro_get_memory_data(2)
        n = self.lib.retro_get_memory_size(2)
        if not p:
            raise RuntimeError('core exposes no system RAM')
        return (C.c_ubyte * n).from_address(p)

    def read(self, addr, n):
        a = addr & 0x1fffff
        return bytes(self.ram[a:a + n])

    def r8(self, addr): return self.read(addr, 1)[0]
    def r16(self, addr): return int.from_bytes(self.read(addr, 2), 'little')
    def r32(self, addr): return int.from_bytes(self.read(addr, 4), 'little')

    def write(self, addr, data):
        a = addr & 0x1fffff
        r = self.ram
        for i, b in enumerate(data):
            r[a + i] = b

    def save_state(self):
        n = self.lib.retro_serialize_size()
        b = C.create_string_buffer(n)
        if not self.lib.retro_serialize(b, n):
            raise RuntimeError('serialize failed')
        return b.raw

    def load_state(self, s):
        b = C.create_string_buffer(s, len(s))
        if not self.lib.retro_unserialize(b, len(s)):
            raise RuntimeError('unserialize failed')

    def close(self):
        self.lib.retro_unload_game()
        self.lib.retro_deinit()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('core'); ap.add_argument('disc'); ap.add_argument('out'); ap.add_argument('frames', type=int)
    ap.add_argument('--shots', default=''); ap.add_argument('--keys', default=''); ap.add_argument('--opt', action='append', default=[])
    ap.add_argument('--sys', help='system directory (default OUTDIR/system, empty: PCSX-ReARMed then uses its HLE BIOS); '
                                  'for openboot on SwanStation or Beetle give the RIG_SYSTEM directory')
    a = ap.parse_args()
    opts = dict(o.split('=', 1) for o in a.opt)
    try:
        e = Emu(a.core, a.disc, a.out, opts, a.sys)
    except RigSetupError as ex:
        sys.exit(str(ex))
    shots = sorted(int(x) for x in a.shots.split(',') if x)
    keys = []
    for part in a.keys.split(';'):
        if part:
            rng, b = part.split(':'); f0, f1 = rng.split('-'); keys.append((int(f0), int(f1), b.split('+')))
    for f in range(a.frames):
        e.run(1, [b for f0, f1, bs in keys if f0 <= f < f1 for b in bs])
        if f + 1 in shots:
            e.shot('%s/f%06d.png' % (a.out, f + 1))
    e.shot('%s/final.png' % a.out)
    print('frames', e.frames, 'video', e.size, 'fmt', e.fmt, 'fps %.3f' % e.fps)
    print('options the core asked for:', {k: (v.decode() if v else None) for k, v in sorted(e.asked.items())})
    print('unhandled env:', sorted(e.unknown_env))


if __name__ == '__main__':
    main()

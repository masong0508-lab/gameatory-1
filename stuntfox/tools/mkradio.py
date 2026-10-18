"""The car radio's remixes (build.py --merge): our remixes of Payback's songs 1, 2 and 4 as
streams at the top of a 32 MiB cartridge, played by src/radio.c next to Payback's own songs.

Everything is made from the player's own ROM at build time: tools/music/remix_song*.py render
the remixes (minutes each, all three at once, so the renders are kept under build/radio/, keyed
by a hash of the ROM and of every script in tools/music), and the streams are encoded from those
renders. None of it is ever in this repository. The renders need numpy and scipy (tools/music);
without them, or with --no-remixes, the build goes on without remixes (Unavailable) and the
radio plays Payback's own songs.

Each remix is mixed to mono, resampled to Payback's mixing rate (16777216 / 699 = 24001.7 Hz;
24002 Hz here, 11 ppm off), set to the loudness of its own original as Payback plays it (both
at music volume 256; the remixes are mastered louder) and encoded by tools/radenc.c, all three
at once into the space they have, at 2 or 4 bits per 480 samples wherever that costs the least
error per byte. At BASE: u32 MAGIC, u32 count, then {u32 address, u32 segments, u32 Payback
song} per remix, then the streams.
"""
import ctypes
import glob
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MUSIC = os.path.join(HERE, 'music')
RATE = 24002
SONGS = ((1, 'remix_song1.py'), (2, 'remix_song2.py'), (4, 'remix_song4.py'))   # Payback's numbers
BASE = 0x09A00000                  # 0x09000000-0x099FFFFF stays free (the big map's)
TOP = 0x09FFFF00                   # the last 256 bytes answer as the EEPROM on a 32 MiB cart
MAGIC = 0x31444152                 # "RAD1"
HEAD = 0x40
SEG = 480
# segments kept at 2 bits: at 4 their codes happen to spell, in ASCII, a word that text scanners
# flag (found by scanning the built ROM; inaudible at 2 bits there)
PLAIN = {4: (5735,)}


def _hash(*parts):
    h = hashlib.sha1()
    for p in parts:
        h.update(p if isinstance(p, bytes) else p.encode())
    return h.hexdigest()[:16]


def _music_sources():
    return b''.join(open(os.path.join(MUSIC, f), 'rb').read() for f in sorted(os.listdir(MUSIC)) if f.endswith('.py'))


class Unavailable(Exception):
    """the remixes cannot be made here (no numpy/scipy, no C compiler, a render failed)"""


def renders(rom_path, build):
    """({song: mono float at RATE, full scale 1.0}, key), rendering (in parallel) whatever the
    cache does not hold yet"""
    try:
        import numpy as np
        from scipy import signal
        from scipy.io import wavfile
    except ImportError as e:
        raise Unavailable('%s (the remixes need numpy and scipy)' % e)
    key = _hash(open(rom_path, 'rb').read(), _music_sources())
    d = os.path.join(os.path.abspath(build), 'radio', 'render-' + key)
    os.makedirs(d, exist_ok=True)
    env = dict(os.environ, PAYBACK_ROM=os.path.abspath(rom_path), MIX_WAV_ONLY='1')   # (no MP3: no ffmpeg)
    todo = [(n, os.path.join(d, 'remix%d' % n), script) for n, script in SONGS
            if not os.path.exists(os.path.join(d, 'remix%d.npy' % n))]
    if todo:
        print('radio: rendering the remixes of songs %s from the ROM (a few minutes, once)'
              % ', '.join(str(n) for n, _, _ in todo), flush=True)
    jobs = []
    for n, base, script in todo:
        log = open(base + '.log', 'w')
        jobs.append((n, base, log, subprocess.Popen([sys.executable, os.path.join(MUSIC, script), base], env=env,
                                                    stdout=log, stderr=subprocess.STDOUT, cwd=d)))
    failed = []
    for n, base, log, p in jobs:
        if p.wait():
            failed.append('song %d (%s.log)' % (n, base))
        log.close()
    if failed:
        raise Unavailable('the remix of %s did not render' % ', '.join(failed))
    out = {}
    for n, base, _ in todo:
        rate, x = wavfile.read(base + '.wav')
        assert rate == 44100 and x.dtype == np.int16
        m = x.astype(np.float64).mean(axis=1) / 32768
        np.save(base + '.npy', signal.resample_poly(m, 12001, 22050).astype(np.float32))
        os.remove(base + '.wav')
    for n, _ in SONGS:
        out[n] = np.load(os.path.join(d, 'remix%d.npy' % n)).astype(np.float64)
    for old in glob.glob(os.path.join(os.path.abspath(build), 'radio', 'render-*')):
        if old != d:
            shutil.rmtree(old)
    return out, key


def originals(rom_path):
    """{song: LUFS} of Payback's songs as its player makes them at music volume 256 (8-bit full
    scale = 1.0): its mixer adds the four channels, each sample * volume (0-64) >> 8. That is
    the plain sum of render.py's stems / 4, not its mono mix, which is panned (-3 dB)."""
    sys.path.insert(0, MUSIC)
    import dsp
    import pbsong
    import render
    lufs = {}
    for n, _ in SONGS:
        r = render.render(pbsong.load(rom_path, n), flavour='payback', rate=RATE, interp='nearest', stereo=0,
                          gain=1.0, game_pitch=True, stems=True)
        lufs[n] = round(float(dsp.loudness_lufs(sum(r.stems.values()) / 4, rate=RATE)), 3)
    return lufs


def _lib(build):
    src = os.path.join(HERE, 'radenc.c')
    so = os.path.join(build, 'radio', 'radenc-%s.so' % _hash(open(src, 'rb').read()))
    if not os.path.exists(so):
        os.makedirs(os.path.dirname(so), exist_ok=True)
        _drop(os.path.join(build, 'radio', 'radenc-*.so'))
        try:
            subprocess.run(['cc', '-O2', '-shared', '-fPIC', '-o', so, src, '-lm'], check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            raise Unavailable('no host C compiler for tools/radenc.c (%s)' % e)
    lib = ctypes.CDLL(so)
    lib.radenc_encode.restype = ctypes.c_long
    return lib


def _drop(pattern):
    """older builds' leftovers in the cache"""
    for f in glob.glob(pattern):
        os.remove(f)


def _p(a, t):
    return a.ctypes.data_as(ctypes.POINTER(t))


def prepare(y, lufs_to):
    """the remix at its original's loudness, as 16-bit (8-bit full scale = 32768), with a short
    fade in, its tail cut where it falls below half the GBA's step at full volume (no one hears
    the rest, and the radio's next song comes that much sooner)"""
    import numpy as np
    sys.path.insert(0, MUSIC)
    import dsp
    g = 10 ** ((lufs_to - dsp.loudness_lufs(y, rate=RATE)) / 20)
    x = y * g * 32768
    nz = np.nonzero(np.abs(x) >= 128)[0]
    x = x[:nz[-1] + RATE // 50] if len(nz) else x
    ramp = int(0.01 * RATE)
    x[:ramp] *= np.linspace(0, 1, ramp)
    x[-ramp:] *= np.linspace(1, 0, ramp)
    clip = int(np.sum(np.abs(x) > 32767))
    return np.clip(np.round(x), -32768, 32767).astype(np.int16), g, clip


def seg_bytes(b):
    return 16 + 15 * 32 * b // 8


def blob(rom_path, build):
    """(bytes for BASE, report); Unavailable when the remixes cannot be made here"""
    src, key0 = renders(rom_path, build)
    import numpy as np
    key = _hash(key0, open(__file__, 'rb').read(), open(os.path.join(HERE, 'radenc.c'), 'rb').read())
    cache = os.path.join(build, 'radio', 'streams-%s' % key)
    if os.path.exists(cache + '.bin'):
        return open(cache + '.bin', 'rb').read(), json.load(open(cache + '.json'))
    lib = _lib(build)
    lufs = originals(rom_path)
    xs, D, rep = [], [], {'songs': {}}
    for n, _ in SONGS:
        x, g, clip = prepare(src[n], lufs[n])
        e = np.zeros(2 * ((len(x) + SEG - 1) // SEG), np.int64)
        lib.radenc_errors(_p(x, ctypes.c_int16), len(x), _p(e, ctypes.c_int64))
        xs.append(x)
        D.append(e.reshape(-1, 2).astype(np.float64))
        rep['songs'][n] = dict(seconds=round(len(x) / RATE, 2), gain_db=round(20 * np.log10(g), 2),
                               lufs_original=lufs[n], peak_dbfs=round(20 * np.log10(max(1, np.abs(x).max()) / 32768), 2),
                               clipped=clip)
    # 2 or 4 bits per segment: the least total error that fits, one slope for all three songs
    room = TOP - BASE - HEAD
    Dall = np.concatenate(D)
    R = np.array([seg_bytes(2), seg_bytes(4)], np.float64)

    def pick(lam):
        return np.argmin(Dall + lam * R, axis=1)
    lo, hi = 0.0, 1.0
    while R[pick(hi)].sum() > room:
        hi *= 4
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if R[pick(mid)].sum() > room else (lo, mid)
    choice = pick(hi)
    head = struct.pack('<II', MAGIC, len(SONGS))
    body, at, k = b'', BASE + HEAD, 0
    for (n, _), x in zip(SONGS, xs):
        nseg = (len(x) + SEG - 1) // SEG
        bits = np.where(choice[k:k + nseg] == 1, 4, 2).astype(np.uint8)
        bits[[g for g in PLAIN.get(n, ()) if g < nseg]] = 2
        k += nseg
        out = np.zeros(nseg * seg_bytes(4), np.uint8)
        rec = np.zeros(len(x), np.int16)
        nb = lib.radenc_encode(_p(x, ctypes.c_int16), len(x), _p(bits, ctypes.c_uint8), _p(out, ctypes.c_uint8),
                               _p(rec, ctypes.c_int16))
        r, e = x.astype(np.float64), (rec.astype(np.float64) - x)
        rep['songs'][n].update(address='0x%08x' % (at + len(body)), bytes=int(nb), segments=nseg,
                               bits_per_sample=round(nb * 8 / len(x), 3), four_bit=int((bits == 4).sum()),
                               snr_db=round(10 * np.log10(np.sum(r * r) / max(np.sum(e * e), 1)), 2))
        head += struct.pack('<III', at + len(body), nseg, n)
        body += out[:nb].tobytes()
    data = head.ljust(HEAD, b'\0') + body
    assert BASE + len(data) <= TOP
    rep['bytes'] = len(data)
    rep['end'] = '0x%08x' % (BASE + len(data))
    _drop(os.path.join(build, 'radio', 'streams-*'))
    open(cache + '.bin', 'wb').write(data)
    json.dump(rep, open(cache + '.json', 'w'), indent=1)
    return data, rep


if __name__ == '__main__':
    d, r = blob(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, '..', 'build'))
    print(json.dumps(r, indent=1))

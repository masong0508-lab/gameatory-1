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

# The title songs (Payback's song 0 remade): the nu metal theme, which plays wherever Payback plays song 0, and the
# djent that plays over the credits. Each is a loop of whole segments with its ring-out folded into its head, so the
# stream wraps with no seam. They are streams of their own below the radio's (5 MiB, up to the radio's; the radio keeps all it had).
TITLE_BASE = 0x09500000
TITLE_CEIL = 10 ** (-1 / 20)       # the songs peak at -1 dBFS at most (the decoder adds the coding error to the music)
TITLE_MAGIC = 0x31544954           # "TIT1"
TITLE_HEAD = 0x40
# Each loop is a whole number of the songs' own 20 ms ticks, 128 to a bar (the nu metal's 115 bars, the djent's 86), cut on
# a bar line, and each tick becomes exactly one 480-sample segment, which is one call of Payback's sequencer: no rounding
# of the length, no stretch (the bars keep their place), and the song runs at the tempo Payback's own song 0 does.
TITLES = (('title_numetal.py', 115 * 128), ('title_djent.py', 86 * 128))   # script, the loop's length in ticks
TITLE_TICK = 882                 # samples of a render's tick at RATE (44100 / 50)
TITLE_LUFS_SONG = 0                # loudness of Payback's own song 0, as the radio's remixes are set to their originals'


# Street Jungle (build.py --street-jungle FILE.mp3): a seventh song, a remix of a tracker module made outside the
# game, so it cannot be rendered from the player's ROM and comes in as an MP3 the player supplies (never in the
# repository). It sits below the title songs, in the cartridge's free space (it ends where they begin), and its
# five words follow the three remixes' entries in the table at BASE. The file's music loops: at the end of its
# last bar it goes back to SJ_LOOP[0]. Everything after the loop's end in the file (the 4.4 s ring-out) is not in
# the stream.
SJ_TOP = TITLE_BASE
SJ_LOOP = (32.24, 313.84)          # seconds in the file: the loop's start, and its end, 176 bars of 1.6 s later (150 BPM,
                                   # measured on the audio: the last drum fill ends on that bar line)
SJ_KIB = 3072                      # its room: 3 MiB, 2 bits a sample would be 2.04 MiB and 4 bits 3.83
SJ_WORDS = 5                       # {address, segments, loop address, loop segments, the decoder's state at the loop}
SJ_AT = 2 + 3 * len(SONGS)         # its first word in the table at BASE


def sj_load(path):
    """the MP3 as mono floats at 44100 Hz, full scale 1.0 (ffmpeg decodes it, the two channels are averaged here)"""
    import numpy as np
    try:
        r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-f', 'f32le', '-ac', '2', '-ar', '44100', '-'],
                           capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise Unavailable('Street Jungle: ffmpeg did not decode %s (%s)' % (path, getattr(e, 'stderr', b'').decode()[-200:] or e))
    x = np.frombuffer(r.stdout, np.float32).astype(np.float64).reshape(-1, 2).mean(axis=1)
    if len(x) < int((SJ_LOOP[1] + 1) * 44100):
        raise Unavailable('Street Jungle: %s is shorter than the loop (%.2f s)' % (path, SJ_LOOP[1]))
    return x


def sj_prepare(x44, lufs_to):
    """(samples at Payback's rate as int16, loop segment, loop segments, report): the file resampled so that its loop
    is a whole number of 480-sample segments (a change of at most 4 ppm in speed: the loop then ends on a segment
    and the decoder goes back with no seam), silence in front so that the loop starts on one, cut where the loop
    ends; at the loudness of the radio's other songs, with a peak ceiling (the ARM decoder has no clamp)."""
    import numpy as np
    from fractions import Fraction
    from scipy import signal
    sys.path.insert(0, MUSIC)
    import dsp
    a, n = int(round(SJ_LOOP[0] * 44100)), int(round((SJ_LOOP[1] - SJ_LOOP[0]) * 44100))
    m = int(round(n * RATE / 44100 / SEG))                     # segments in the loop
    f = Fraction(m * SEG, n)
    y = signal.resample_poly(x44[:a + n], f.numerator, f.denominator)
    start = int(round(a * float(f)))                           # (the loop's first sample, to a sample)
    pad = -start % SEG
    y = np.concatenate([np.zeros(pad), y[:start + m * SEG]])
    assert len(y) % SEG == 0
    g = 10 ** ((lufs_to - dsp.loudness_lufs(y, rate=RATE)) / 20)
    g = min(g, TITLE_CEIL / max(1e-9, np.abs(y).max()))
    x = np.clip(np.round(y * g * 32768), -32768, 32767).astype(np.int16)
    rep = dict(seconds=round(len(x) / RATE, 2), loop_seconds=round(m * SEG / RATE, 2), gain_db=round(20 * np.log10(g), 2),
               lufs_to=round(lufs_to, 2), rate=round(44100 * float(f), 2),
               peak_dbfs=round(20 * np.log10(max(1, np.abs(x).max()) / 32768), 2), front_silence_ms=round(1000 * pad / RATE, 1))
    return x, (pad + start) // SEG, m, rep


def sj_sources():
    return open(__file__, 'rb').read() + open(os.path.join(HERE, 'radenc.c'), 'rb').read()


def sj_blob(path, build, lufs_to, kib=SJ_KIB):
    """(bytes, report) for the stream of Street Jungle, whose room is kib KiB: it ends where the title songs begin, so its
    address (report['address'], the first byte of the bytes) is what the table at BASE needs. 2 or 4 bits a segment,
    the least error that fits. Unavailable when it cannot be made here."""
    try:
        import numpy as np
        import scipy.signal    # noqa: F401
    except ImportError as e:
        raise Unavailable('%s (Street Jungle needs numpy and scipy)' % e)
    key = _hash(open(path, 'rb').read(), sj_sources(), repr((SJ_LOOP, kib, round(lufs_to, 3), RATE)))
    cache = os.path.join(build, 'radio', 'sj-%s' % key)
    if os.path.exists(cache + '.bin'):
        return open(cache + '.bin', 'rb').read(), json.load(open(cache + '.json'))
    lib = _lib(build)
    x, ls, m, rep = sj_prepare(sj_load(path), lufs_to)
    nseg = len(x) // SEG
    assert nseg == ls + m
    e = np.zeros(2 * nseg, np.int64)
    lib.radenc_errors(_p(x, ctypes.c_int16), len(x), _p(e, ctypes.c_int64))
    D = e.reshape(-1, 2).astype(np.float64)
    R = np.array([seg_bytes(2), seg_bytes(4)], np.float64)
    room = kib * 1024 - 16 - 3                                 # (the address is aligned down to 16)

    def pick(lam):
        return np.argmin(D + lam * R, axis=1)
    if R[0] * nseg > room:
        raise Unavailable('Street Jungle: %d KiB is less than its %d KiB at 2 bits a sample' % (kib, R[0] * nseg // 1024))
    if R[1] * nseg <= room:
        choice = np.ones(nseg, int)
    else:
        lo, hi = 0.0, 1.0
        while R[pick(hi)].sum() > room:
            hi *= 4
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if R[pick(mid)].sum() > room else (lo, mid)
        choice = pick(hi)
    bits = np.where(choice == 1, 4, 2).astype(np.uint8)
    bits[[g for g in PLAIN.get('sj', ()) if g < nseg]] = 2
    out = np.zeros(nseg * seg_bytes(4), np.uint8)
    rec = np.zeros(len(x), np.int16)
    nb = lib.radenc_encode(_p(x, ctypes.c_int16), len(x), _p(bits, ctypes.c_uint8), _p(out, ctypes.c_uint8), _p(rec, ctypes.c_int16))
    data = out[:nb].tobytes()
    sizes = np.where(bits == 4, seg_bytes(4), seg_bytes(2))
    loop_off = int(sizes[:ls].sum())                           # (the loop's first segment, in bytes)
    base = (SJ_TOP - len(data)) & ~15
    a0, b0 = int(rec[ls * SEG - 1]), int(rec[ls * SEG - 2])    # the decoder's state going into the loop: the same on every pass
    r, d = x.astype(np.float64), rec.astype(np.float64) - x
    rep.update(address='0x%08x' % base, end='0x%08x' % (base + len(data)), bytes=len(data), segments=int(nseg),
               loop_segment=int(ls), loop_address='0x%08x' % (base + loop_off), loop_segments=int(m), loop_state=[a0, b0],
               bits_per_sample=round(nb * 8 / len(x), 3), four_bit=int((bits == 4).sum()),
               snr_db=round(10 * np.log10(np.sum(r * r) / max(np.sum(d * d), 1)), 2),
               seam_error=int(abs(int(rec[-1]) - int(rec[ls * SEG - 1]))), seam_step=int(abs(int(rec[ls * SEG]) - int(rec[-1]))),
               source_seam_step=int(abs(int(x[ls * SEG]) - int(x[-1]))))
    rep['words'] = [base, int(nseg), base + loop_off, int(m), (a0 & 0xffff) | (b0 & 0xffff) << 16]
    _drop(os.path.join(build, 'radio', 'sj-*'))
    open(cache + '.bin', 'wb').write(data)
    json.dump(rep, open(cache + '.json', 'w'), indent=1)
    return data, rep


def sj_table(streams, words):
    """the table at BASE with Street Jungle in it: count 4, its five words after the three remixes' entries"""
    head = bytearray(streams[:HEAD])
    assert struct.unpack_from('<II', head) == (MAGIC, len(SONGS)) and not any(head[4 * SJ_AT:]), 'the table has no room'
    struct.pack_into('<I', head, 4, len(SONGS) + 1)
    struct.pack_into('<%dI' % SJ_WORDS, head, 4 * SJ_AT, *words)
    return bytes(head) + streams[HEAD:]


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


def originals(rom_path, songs=None):
    """{song: LUFS} of Payback's songs as its player makes them at music volume 256 (8-bit full
    scale = 1.0): its mixer adds the four channels, each sample * volume (0-64) >> 8. That is
    the plain sum of render.py's stems / 4, not its mono mix, which is panned (-3 dB)."""
    sys.path.insert(0, MUSIC)
    import dsp
    import pbsong
    import render
    lufs = {}
    for n in songs if songs is not None else [n for n, _ in SONGS]:
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



def _title_sources():
    d = os.path.join(MUSIC, 'title')
    return _music_sources() + b''.join(open(os.path.join(d, f), 'rb').read() for f in sorted(os.listdir(d))
                                       if f.endswith('.py'))


def title_renders(rom_path, build):
    """[mono float at RATE, one whole loop, full scale 1.0] for each of TITLES, rendered (one at a time: each wants
    about 3 GB) when the cache does not hold it"""
    try:
        import numpy as np
        from scipy import signal
        from scipy.io import wavfile
    except ImportError as e:
        raise Unavailable('%s (the title songs need numpy and scipy)' % e)
    key = _hash(open(rom_path, 'rb').read(), _title_sources(), repr(TITLES), str(RATE), str(TITLE_TICK))
    d = os.path.join(os.path.abspath(build), 'radio', 'title-' + key)
    os.makedirs(d, exist_ok=True)
    env = dict(os.environ, PAYBACK_ROM=os.path.abspath(rom_path), MIX_WAV_ONLY='1')
    out = []
    for i, (script, ticks) in enumerate(TITLES):
        npy = os.path.join(d, 'title%d.npy' % i)
        if not os.path.exists(npy):
            base = os.path.join(d, 'title%d' % i)
            if not os.path.exists(base + '.wav'):
                print('radio: rendering the title song %s from the ROM (some minutes, once)' % script, flush=True)
                with open(base + '.log', 'w') as log:
                    r = subprocess.run([sys.executable, os.path.join(MUSIC, 'title', script), base], env=env, stdout=log,
                                       stderr=subprocess.STDOUT, cwd=d)
                if r.returncode:
                    raise Unavailable('the title song %s did not render (%s.log)' % (script, base))
            rate, x = wavfile.read(base + '.wav')
            assert rate == 44100 and x.dtype == np.int16
            m = x.astype(np.float64).mean(axis=1) / 32768
            n0 = ticks * TITLE_TICK
            body, tail = m[:n0].copy(), m[n0:]
            assert 0 < len(tail) < n0, 'the title song %s is shorter than its loop' % script
            body[:len(tail)] += tail                 # the ring-out rings into the head: the loop has no seam
            # 882 samples -> 480 per tick: exactly the ratio 80/147 (the stream's 24000 Hz per render's 44100), so the loop
            # is ticks whole segments by itself (circular resample: the loop is periodic)
            np.save(npy, signal.resample(body, ticks * SEG).astype(np.float32))
            os.remove(base + '.wav')
        out.append(np.load(npy).astype(np.float64))
    for old in glob.glob(os.path.join(os.path.abspath(build), 'radio', 'title-*')):
        if old != d:
            shutil.rmtree(old)
    return out, key


def title_blob(rom_path, build):
    """(bytes for TITLE_BASE, report): u32 MAGIC, u32 count, then {u32 address, u32 segments, u32 the decoder's two
    samples at the loop (low 16 bits the newer, high the one before), u32 0} per song, then the streams"""
    src, key0 = title_renders(rom_path, build)
    import numpy as np
    key = _hash(key0, open(__file__, 'rb').read(), open(os.path.join(HERE, 'radenc.c'), 'rb').read())
    cache = os.path.join(build, 'radio', 'tstreams-%s' % key)
    if os.path.exists(cache + '.bin'):
        return open(cache + '.bin', 'rb').read(), json.load(open(cache + '.json'))
    lib = _lib(build)
    lufs = originals(rom_path, [TITLE_LUFS_SONG])[TITLE_LUFS_SONG]
    sys.path.insert(0, MUSIC)
    import dsp
    xs, D, rep, pre = [], [], {'songs': {}}, []
    for i, y in enumerate(src):
        g = 10 ** ((lufs - dsp.loudness_lufs(y, rate=RATE)) / 20)
        g = min(g, TITLE_CEIL * 32768 / max(1e-9, np.abs(y).max() * 32768))     # (a ceiling: the ARM decoder has no clamp)
        x = np.clip(np.round(y * g * 32768), -32768, 32767).astype(np.int16)
        assert np.abs(x).max() <= TITLE_CEIL * 32768 + 1
        n = len(x) // SEG
        # the loop's own last segment goes in front, so the first one is coded from the state the loop ends in
        full = np.concatenate([x[-SEG:], x])
        e = np.zeros(2 * (n + 1), np.int64)
        lib.radenc_errors(_p(full, ctypes.c_int16), len(full), _p(e, ctypes.c_int64))
        xs.append(full)
        D.append(e.reshape(-1, 2)[1:].astype(np.float64))
        rep['songs'][i] = dict(seconds=round(len(x) / RATE, 2), gain_db=round(20 * np.log10(g), 2), lufs_original=lufs,
                               peak_dbfs=round(20 * np.log10(max(1, np.abs(x).max()) / 32768), 2),
                               clipped=int(np.sum(np.abs(y * g * 32768) > 32767)))
    room = BASE - TITLE_BASE - TITLE_HEAD
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
    head = struct.pack('<II', TITLE_MAGIC, len(xs))
    body, at, k = b'', TITLE_BASE + TITLE_HEAD, 0
    for i, full in enumerate(xs):
        n = len(full) // SEG - 1
        bits = np.concatenate([[4], np.where(choice[k:k + n] == 1, 4, 2)]).astype(np.uint8)
        k += n
        out = np.zeros((n + 1) * seg_bytes(4), np.uint8)
        rec = np.zeros(len(full), np.int16)
        nb = lib.radenc_encode(_p(full, ctypes.c_int16), len(full), _p(bits, ctypes.c_uint8), _p(out, ctypes.c_uint8),
                               _p(rec, ctypes.c_int16))
        skip = seg_bytes(4)
        a0, b0 = int(rec[SEG - 1]), int(rec[SEG - 2])
        x = full[SEG:].astype(np.float64)
        r, e = x, rec[SEG:].astype(np.float64) - x
        rep['songs'][i].update(address='0x%08x' % (at + len(body)), bytes=int(nb - skip), segments=n,
                               bits_per_sample=round((nb - skip) * 8 / len(x), 3), four_bit=int((bits[1:] == 4).sum()),
                               snr_db=round(10 * np.log10(np.sum(r * r) / max(np.sum(e * e), 1)), 2),
                               seam_error=int(abs(int(rec[-1]) - a0)))
        head += struct.pack('<IIII', at + len(body), n, (a0 & 0xffff) | (b0 & 0xffff) << 16, 0)
        body += out[skip:nb].tobytes()
    data = head.ljust(TITLE_HEAD, b'\0') + body
    assert TITLE_BASE + len(data) <= BASE, 'title songs end at 0x%08x, past the radio at 0x%08x' % (TITLE_BASE + len(data), BASE)
    rep['bytes'] = len(data)
    rep['end'] = '0x%08x' % (TITLE_BASE + len(data))
    _drop(os.path.join(build, 'radio', 'tstreams-*'))
    open(cache + '.bin', 'wb').write(data)
    json.dump(rep, open(cache + '.json', 'w'), indent=1)
    return data, rep


if __name__ == '__main__':
    d, r = blob(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, '..', 'build'))
    print(json.dumps(r, indent=1))

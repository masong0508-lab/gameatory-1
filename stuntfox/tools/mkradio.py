"""The car radio's remixes (build.py --merge): our remixes of Payback's songs 1, 2 and 4 as
streams at the top of a 32 MiB cartridge, played by src/radio.c next to Payback's own songs.

Everything is made from the player's own ROM at build time: tools/music/remix_song*.py render
the remixes (minutes each, all three at once, so the renders are kept under build/radio/, keyed
by a hash of the ROM and of every script in tools/music), and the streams are encoded from those
renders. None of it is ever in this repository. The renders need numpy and scipy (tools/music);
without SciPy, or with --no-remixes, the build goes on without remixes (Unavailable) and
the radio plays Payback's own songs. The complete game build still needs NumPy for its
world and planet tools; only this radio subsystem can fall back without NumPy.

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


# The radio edits (build.py --radio-edits DIR, tools/radedits.py): our tracker-module remixes, each cut down to a short
# radio edit that ends, as MP3 files the player supplies (never in the repository). They sit below the title songs, in the
# cartridge's free space (they end where the table of them begins), and a table of their own is the last 256 bytes
# below the title songs: u32 EDIT_MAGIC, u32 count, then {u32 address, u32 segments, u32 the banner's name (an index into
# radedits.EDITS)} per edit. Each is a plain stream from silence to silence, 20 ms to a segment; the radio ends it
# (3 segments early) as it ends Payback's own songs and goes on to the next.
EDIT_TAB = TITLE_BASE - 0x100
EDIT_MAGIC = 0x31444552            # "RED1"
EDIT_KIB = 5120                    # the room of all the edits together: 5 MiB (all at 2 bits a sample, 11 edits of about 75 s
                                   # are 4.7 MiB; the rest goes to 4 bits where it matters most)
EDIT_MAX = 16                      # (the table's, and radio.c's, limit)
TAIL = 0.16                        # seconds of silence after an edit's ending


def edit_prepare(y44, lufs_to):
    """(samples at Payback's rate as int16, report): an edit (mono floats at 44100 Hz) resampled, set to the loudness of the
    radio's other songs under a peak ceiling (the ARM decoder has no clamp), and padded with silence to whole segments"""
    import numpy as np
    from scipy import signal
    sys.path.insert(0, MUSIC)
    import dsp
    y = signal.resample_poly(y44, 12001, 22050)                # 44100 -> 24002 Hz
    y = np.concatenate([y, np.zeros(int(TAIL * RATE))])
    y = np.concatenate([y, np.zeros(-len(y) % SEG)])
    g = 10 ** ((lufs_to - dsp.loudness_lufs(y, rate=RATE)) / 20)
    g = min(g, TITLE_CEIL / max(1e-9, np.abs(y).max()))
    x = np.clip(np.round(y * g * 32768), -32768, 32767).astype(np.int16)
    rep = dict(seconds=round(len(x) / RATE, 2), gain_db=round(20 * np.log10(g), 2), lufs_to=round(lufs_to, 2),
               peak_dbfs=round(20 * np.log10(max(1, np.abs(x).max()) / 32768), 2))
    return x, rep


def edits_sources():
    return b''.join(open(os.path.join(HERE, f), 'rb').read() for f in ('mkradio.py', 'radenc.c', 'radedits.py'))


def edits_blob(files, build, lufs_to, kib=EDIT_KIB):
    """(bytes, report) for the edits of files ({key: path of the MP3}, keys of radedits.EDITS), whose room is kib KiB in all:
    the bytes end at EDIT_TAB (report['address'] is where the first byte goes) and report['table'] is the 256 bytes of
    their table for EDIT_TAB. 2 or 4 bits a segment, the least error that fits, one slope for all of them. An edit whose
    file is not the one the cuts were made for is left out (report['skipped']). Unavailable when none can be made."""
    try:
        import numpy as np
        import scipy.signal    # noqa: F401
    except ImportError as e:
        raise Unavailable('%s (the radio edits need numpy and scipy)' % e)
    sys.path.insert(0, HERE)
    import radedits
    keys = [k for k in radedits.KEYS if k in files]
    if not keys:
        raise Unavailable('no edit files')
    key = _hash(b''.join(open(files[k], 'rb').read() for k in keys), edits_sources(), repr((keys, kib, round(lufs_to, 3), RATE)))
    cache = os.path.join(build, 'radio', 'edits-%s' % key)
    if os.path.exists(cache + '.bin'):
        return open(cache + '.bin', 'rb').read(), json.load(open(cache + '.json'))
    lib = _lib(build)
    xs, D, skipped, made = [], [], {}, []
    for k in keys:
        try:
            y, info = radedits.make(k, files[k])
        except radedits.Missing as e:
            skipped[k] = str(e)
            print('radio: edit %s left out: %s' % (k, e), flush=True)
            continue
        x, rep = edit_prepare(y, lufs_to)
        e = np.zeros(2 * (len(x) // SEG), np.int64)
        lib.radenc_errors(_p(x, ctypes.c_int16), len(x), _p(e, ctypes.c_int64))
        xs.append(x)
        D.append(e.reshape(-1, 2).astype(np.float64))
        rep.update(key=k, name=radedits.entry(k)[1], pieces=info['pieces'], joins=info['joins'],
                   cuts=[round(c / radedits.IN_RATE, 3) for c in info['cuts']], id=radedits.KEYS.index(k))
        made.append(rep)
    if not made:
        raise Unavailable('none of the edit files is the one its cuts were made for')
    if len(made) > EDIT_MAX:
        raise Unavailable('more edits than the table holds')
    room = kib * 1024 - len(made) * 16 - 256
    Dall = np.concatenate(D)
    R = np.array([seg_bytes(2), seg_bytes(4)], np.float64)
    if R[0] * len(Dall) > room:
        raise Unavailable('the radio edits: %d KiB is less than their %d KiB at 2 bits a sample' % (kib, R[0] * len(Dall) // 1024))

    def pick(lam):
        return np.argmin(Dall + lam * R, axis=1)
    if R[1] * len(Dall) <= room:
        choice = np.ones(len(Dall), int)
    else:
        lo, hi = 0.0, 1.0
        while R[pick(hi)].sum() > room:
            hi *= 4
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if R[pick(mid)].sum() > room else (lo, mid)
        choice = pick(hi)
    # the codes are plain bytes in the cartridge: a segment that spells a name the repository keeps out (tools/lint_text.py) is
    # coded the other way (2 bits for 4 or the reverse: the next 20 ms differ, nobody hears it) until none does
    import lint_text
    flip = set()
    for _ in range(40):
        blobs, k0, bad = [], 0, []
        for i, x in enumerate(xs):
            n = len(x) // SEG
            bits = np.where(choice[k0:k0 + n] == 1, 4, 2).astype(np.uint8)
            for g in flip:
                if k0 <= g < k0 + n:
                    bits[g - k0] = 6 - bits[g - k0]
            out = np.zeros(n * seg_bytes(4), np.uint8)
            rec = np.zeros(len(x), np.int16)
            nb = lib.radenc_encode(_p(x, ctypes.c_int16), len(x), _p(bits, ctypes.c_uint8), _p(out, ctypes.c_uint8), _p(rec, ctypes.c_int16))
            blobs.append((out[:nb].tobytes(), bits, rec))
            ends = np.cumsum(np.where(bits == 4, seg_bytes(4), seg_bytes(2)))
            for m in lint_text.NAMES.finditer(blobs[-1][0].decode('latin-1')):
                bad.append(k0 + int(np.searchsorted(ends, m.start(), side='right')))
            k0 += n
        if not bad:
            break
        flip.symmetric_difference_update(bad)
    else:
        raise Unavailable('the radio edits spell a banned word in their codes')
    data = b''.join(b for b, _, _ in blobs)
    base = (EDIT_TAB - len(data)) & ~15
    tab = struct.pack('<II', EDIT_MAGIC, len(made))
    at = base
    for rep, x, (b, bits, rec) in zip(made, xs, blobs):
        r, d = x.astype(np.float64), rec.astype(np.float64) - x
        rep.update(address='0x%08x' % at, bytes=len(b), segments=len(x) // SEG, bits_per_sample=round(len(b) * 8 / len(x), 3),
                   four_bit=int((bits == 4).sum()), snr_db=round(10 * np.log10(np.sum(r * r) / max(np.sum(d * d), 1)), 2),
                   end_silence_segments=int(len(x) // SEG - 1 - np.nonzero(np.abs(x.reshape(-1, SEG)).max(axis=1) > 64)[0][-1]))
        tab += struct.pack('<III', at, len(x) // SEG, rep['id'])
        at += len(b)
    assert at == base + len(data) and base + len(data) <= EDIT_TAB
    rep = dict(edits=made, skipped=skipped, address='0x%08x' % base, end='0x%08x' % (base + len(data)), bytes=len(data),
               seconds=round(sum(m['seconds'] for m in made), 1), table=tab.ljust(256, b'\0').hex())
    _drop(os.path.join(build, 'radio', 'edits-*'))
    open(cache + '.bin', 'wb').write(data)
    json.dump(rep, open(cache + '.json', 'w'), indent=1)
    return data, rep


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

"""The car radio's edits (tools/mkradio.py, build.py --radio-edits DIR): eleven tracker-module remixes, each cut down
to a short radio edit: a real beginning (the intro), the main section, for some a bridge or breakdown from the
middle, the main section again and the file's own ending, so that the song finishes and Payback's radio goes on to
the next one.

The edits are made from the player's own MP3 files (never in the repository). What is here is only where to cut: for
each file, its bar length and the pieces to keep, in bars counted from the start of the file (bar b starts at
b * bar seconds; the files are renders at a fixed tempo, so the grid holds to a few ms over the whole song). A piece
(a, b) is bars a up to b; a b of None runs to the end of the file's sound, ring-out included. Each join is cut on a
bar line, a few ms before it (the downbeats of these renders fall 0-8 ms after the line; both pieces are cut at the same
distance from their bar lines), and crossfaded over XFADE seconds that end there, so the downbeat of the piece that comes in is whole and the
piece that goes out is faded where nothing sharp is in the way. A file that is not the one the cuts were made for
(another length) is left out of the build with a message, and the radio plays the others.

    python3 tools/radedits.py DIR            # report the cuts of the files found in DIR (joins, lengths)
    python3 tools/radedits.py DIR OUT_DIR    # ... and write each edit as a WAV for listening (not in the repo)
"""
import os
import subprocess
import sys

IN_RATE = 44100
XFADE = 0.020                  # seconds of crossfade at a join
GUARD = 0.003                  # the crossfade ends this long before the bar line it joins to
END_LEVEL = 10 ** (-54 / 20)   # the ending is cut where the file's sound falls below this (-54 dBFS)
END_FADE = 0.060               # ... faded out over this long
TAIL_SEGMENTS = 8              # silence after the ending, in 20 ms segments (the radio ends a song 3 segments early)
HEAD_FADE = 0.004

# key, the radio banner's name (letters of the font), the file, a bar in seconds, the file's length in seconds (+-0.1: a
# different file is not the one the cuts were made for), the pieces in bars
EDITS = (
    ('harley', 'HARLEY MUSIC', 'Kevin Collier - Harley Music (GBA remix v2).mp3', 1.92, 173.95,
     ((0, 12), (24, 32), (48, 56), (60, 64), (80, None))),
    ('spilt', 'SPILT MILK', 'Hollywood - Spilt Milk (GBA radical remix v2).mp3', 1.92, 219.53,
     ((0, 8), (24, 32), (40, 48), (104, None))),
    ('groovything', 'GROOVY THING', 'Moby - Groovy Thing (GBA remix).mp3', 1.92, 257.93,
     ((0, 16), (16, 24), (76, 86), (126, None))),
    ('knulla', 'KNULLA KUK', 'Moby - Knulla Kuk (GBA remix).mp3', 1.92, 273.07,
     ((0, 24), (64, 72), (133, None))),
    ('pelforth', 'PELFORTH BLUES', 'Moby - Pelforth Blues (GBA remix).mp3', 1.92, 273.79,
     ((0, 8), (16, 24), (104, 112), (120, 126), (136, None))),
    ('guitar', 'GUITAR SLINGER', 'Jogeir Liljedahl - Guitar Slinger (GBA remix).mp3', 2.24, 257.85,
     ((0, 8), (16, 24), (78, 88), (108, None))),
    ('reverie', 'REVERIE OF TRUTH', 'Misty & Daeron - Reverie of Truth (GBA remix).mp3', 1.92, 193.42,
     ((0, 8), (24, 32), (48, 56), (64, 68), (92, None))),
    ('genlove', 'GENERATION LOVE', 'Marc - Generation Love (GBA remix v3).mp3', 1.6327, 257.56,
     ((0, 8), (16, 24), (32, 40), (64, 72), (144, None))),
    ('element', 'GROOVY ELEMENT', 'Vinnie - The Groovy Element (GBA remix v2).mp3', 2.1374, 183.50,
     ((0, 8), (16, 24), (26, 36), (36, 44), (76, None))),
    ('opsept', 'OPERATION SEPTEMBER', 'Bassbomb - Operation September (GBA radical remix v2).mp3', 1.92, 234.89,
     ((0, 8), (16, 24), (32, 44), (80, 86), (112, None))),
    ('street', 'STREET JUNGLE', 'Heatbeat - Street Jungle (Remix v6).mp3', 1.6, 312.07,
     ((0, 8), (16, 24), (32, 48), (184, None))),
)
KEYS = tuple(e[0] for e in EDITS)


class Missing(Exception):
    """this edit cannot be made (no file, a different file, no ffmpeg)"""


def load(path):
    """the MP3 as mono floats at 44100 Hz, full scale 1.0 (ffmpeg decodes it; the two channels are averaged)"""
    import numpy as np
    try:
        r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-f', 'f32le', '-ac', '2', '-ar', str(IN_RATE), '-'],
                           capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise Missing('ffmpeg did not decode %s (%s)' % (path, getattr(e, 'stderr', b'').decode()[-200:] or e))
    return np.frombuffer(r.stdout, np.float32).astype(np.float64).reshape(-1, 2).mean(axis=1)


def find(dirpath):
    """{key: path} of the edits' files found in dirpath (by their exact names)"""
    return {e[0]: os.path.join(dirpath, e[2]) for e in EDITS if os.path.isfile(os.path.join(dirpath, e[2]))}


def sound_end(x):
    """the sample after the last one of the file's sound (smoothed over 20 ms, above END_LEVEL)"""
    import numpy as np
    k = IN_RATE // 50
    env = np.convolve(np.abs(x), np.ones(k) / k, 'same')
    loud = np.nonzero(env > END_LEVEL)[0]
    return int(loud[-1]) + 1 if len(loud) else len(x)


def assemble(x, bar, pieces):
    """(mono at 44100 Hz, info): the pieces of x joined as described above. info['joins'] has one dict per join (the bars,
    the shift of the cut from the bar line in ms), info['pieces'] each piece's length in seconds and info['cuts'] the
    joins' places in the output (samples)"""
    import numpy as np
    nx = int(XFADE * IN_RATE)
    end = sound_end(x)
    # every join is cut GUARD before the bar line (the downbeats of these renders fall 0-8 ms after it: measured by folding
    # the envelope's rise over all the bars), so that the crossfade ends before the first attack of the bar it joins to;
    # pieces that follow each other are one piece
    off = -GUARD
    merged = []
    for a, b in pieces:
        if merged and merged[-1][1] == a:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    pieces = merged
    starts, ends, joins = [0], [], []
    for k in range(1, len(pieces)):
        joins.append(dict(bar_out=pieces[k - 1][1], bar_in=pieces[k][0], shift_ms=round(1000 * off, 1)))
        starts.append(int(round((pieces[k][0] * bar + off) * IN_RATE)))
        ends.append(int(round((pieces[k - 1][1] * bar + off) * IN_RATE)))
    ends.append(end)
    out = None
    cuts = []
    for k, (s, e) in enumerate(zip(starts, ends)):
        if not 0 <= s - (nx if k else 0) < e <= len(x):
            raise Missing('the cut %d runs outside the file' % k)
        if k == 0:
            out = x[s:e].copy()
            continue
        b = x[s - nx:e].copy()
        t = (np.arange(nx) + 0.5) / nx * np.pi / 2
        out[-nx:] *= np.cos(t)
        b[:nx] *= np.sin(t)
        cuts.append(len(out) - nx)
        out = np.concatenate([out[:-nx], out[-nx:] + b[:nx], b[nx:]])
    fade = int(END_FADE * IN_RATE)
    out[-fade:] *= np.linspace(1, 0, fade)
    h = int(HEAD_FADE * IN_RATE)
    out[:h] *= np.linspace(0, 1, h)
    info = dict(joins=joins, cuts=cuts, pieces=[round((e - s) / IN_RATE, 2) for s, e in zip(starts, ends)],
                seconds=round(len(out) / IN_RATE, 2))
    return out, info


def entry(key):
    for e in EDITS:
        if e[0] == key:
            return e
    raise KeyError(key)


def make(key, path):
    """(mono at 44100 Hz, info) of one edit from its file; Missing when the file is not the one the cuts were made for"""
    _, name, fname, bar, secs, pieces = entry(key)
    x = load(path)
    if abs(len(x) / IN_RATE - secs) > 0.1:
        raise Missing('%s is %.2f s long, the cuts were made for %.2f s (%s)' % (os.path.basename(path), len(x) / IN_RATE, secs, fname))
    return assemble(x, bar, pieces)


if __name__ == '__main__':
    import json
    found = find(sys.argv[1])
    for key in KEYS:
        if key not in found:
            print('%-12s no file' % key)
            continue
        try:
            y, info = make(key, found[key])
        except Missing as e:
            print('%-12s %s' % (key, e))
            continue
        print('%-12s %6.1f s  pieces %s' % (key, info['seconds'], info['pieces']))
        for j in info['joins']:
            print('             join bar %s -> %s  shift %s ms' % (j['bar_out'], j['bar_in'], j['shift_ms']))
        if len(sys.argv) > 2:
            import numpy as np
            from scipy.io import wavfile
            os.makedirs(sys.argv[2], exist_ok=True)
            wavfile.write(os.path.join(sys.argv[2], key + '.wav'), IN_RATE, np.clip(y * 32767, -32768, 32767).astype(np.int16))

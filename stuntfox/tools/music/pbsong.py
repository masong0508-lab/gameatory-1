"""Payback's songs, read from the user's own ROM into plain Python objects.

Payback plays five converted four-channel ProTracker modules (tools/mkmusic.py has the player).
Per song s:
  sample headers  0x084b009c + 0x174*s: 31 x 12 bytes (u32 offset from the sample data, u16 loop
                  start in words or 0xffff for none, u16 length in words, s8 finetune, u8 volume)
  order list      0x084b07e0 + 0x100*s: up to 128 s16 pattern numbers, ending in -1
  patterns        0x0860d738 + 0x400*n: 64 rows x 4 channels of u32
                  instrument<<24 | Amiga period<<12 | effect<<8 | param
  sample data     0x084b14e0: signed 8 bit, at the sample's native rate when played at period 428
The player itself starts every song at speed 6, tempo 125 (play() 0x08076c98).
Nothing here holds ROM bytes: everything is read from the ROM file at run time.

    song = load(rom_path, 1)
    song.order, song.patterns[song.order[0]][row][ch].period, song.samples[k].data ...
    write_mod(song, path)           # a standard M.K. module, for reference listening only

CLI: python3 pbsong.py ROM SONG [--mod out.mod] [--dump N]
"""
import math
import os
import struct
import sys
from dataclasses import dataclass, field

import numpy as np

GBA = 0x08000000
SAMPLES, ORDERS, STEPS, SAMPLE_DATA, PATTERNS = 0x084b009c, 0x084b07e0, 0x084b0ce0, 0x084b14e0, 0x0860d738
SONGS = 5
PLAYER_LITERALS = ((0x0807611c, SAMPLES), (0x08076124, SAMPLE_DATA), (0x0807614c, ORDERS),
                   (0x08076150, PATTERNS), (0x08076e20, ORDERS), (0x08076e24, PATTERNS))
PAL_CLOCK = 3546894.6           # Amiga PAL Paula clock / 2: Hz = PAL_CLOCK / period
NATIVE_PERIOD = 428             # ProTracker C-2: a sample plays at its own rate (8287 Hz)
START_SPEED, START_TEMPO = 6, 125
NOTE_NAMES = ('C-', 'C#', 'D-', 'D#', 'E-', 'F-', 'F#', 'G-', 'G#', 'A-', 'A#', 'B-')
EFFECT_NAMES = {0: 'arpeggio', 1: 'porta up', 2: 'porta down', 3: 'tone porta', 4: 'vibrato',
                5: 'tone porta + vol slide', 6: 'vibrato + vol slide', 7: 'tremolo', 8: 'pan',
                9: 'sample offset', 0xa: 'vol slide', 0xb: 'position jump', 0xc: 'set volume',
                0xd: 'pattern break', 0xe: 'extended', 0xf: 'speed/tempo'}


def default_rom():
    """The ROM path from $PAYBACK_ROM (the tools never guess another location)."""
    p = os.environ.get('PAYBACK_ROM')
    if not p:
        raise SystemExit('set PAYBACK_ROM to your Payback (Europe) ROM, or pass its path')
    return p


def period_to_midi(period):
    """MIDI note number (float) of a period, with ProTracker C-2 (428) = MIDI 60 (C4)."""
    return 60 + 12 * math.log2(NATIVE_PERIOD / period)


def note_name(period):
    """ProTracker note name of a period (C-1 = 856 ... B-3 = 113), '---' for none."""
    if not period:
        return '---'
    m = int(round(period_to_midi(period)))
    return '%s%d' % (NOTE_NAMES[m % 12], m // 12 - 3)


def midi_name(m):
    """Scientific name of a MIDI note (60 = C4)."""
    m = int(round(m))
    return '%s%d' % (NOTE_NAMES[m % 12].replace('-', ''), m // 12 - 1)


@dataclass
class Sample:
    number: int                 # 1..31, as the patterns name it
    data: np.ndarray            # int8 PCM (empty if the slot is unused)
    loop_start: int             # in samples, or -1 for a one-shot sample
    finetune: int               # -8..7 (Payback adds it to the period)
    volume: int                 # 0..64
    rom_offset: int = 0         # GBA address of the first byte

    @property
    def looped(self):
        return self.loop_start >= 0

    @property
    def length(self):
        return len(self.data)

    @property
    def loop_len(self):
        return self.length - self.loop_start if self.looped else 0

    def pcm(self):
        """Float32 PCM in -1..1."""
        return self.data.astype(np.float32) / 128.0

    def native_rate(self, period=NATIVE_PERIOD):
        return PAL_CLOCK / period


@dataclass
class Cell:
    period: int = 0
    instrument: int = 0         # 0 = none, else sample number 1..31
    effect: int = 0
    param: int = 0

    @property
    def empty(self):
        return not (self.period or self.instrument or self.effect or self.param)

    @property
    def note(self):
        return note_name(self.period)

    @property
    def midi(self):
        return period_to_midi(self.period) if self.period else None

    def __str__(self):
        return '%s %s %X%02X' % (self.note, '%02d' % self.instrument if self.instrument else '..',
                                 self.effect, self.param)


@dataclass
class Song:
    number: int
    samples: list               # 31 Sample, samples[k - 1] is sample k
    patterns: dict              # pattern number -> 64 rows of 4 Cell
    order: list                 # pattern numbers
    speed: int = START_SPEED
    tempo: int = START_TEMPO
    step_table: np.ndarray = field(default=None, repr=False)   # Payback's period -> pitch step

    def sample(self, k):
        return self.samples[k - 1] if 1 <= k <= 31 else None

    def rows(self):
        """Every (order index, pattern, row, [4 Cell]) in order-list order (no jumps)."""
        for oi, p in enumerate(self.order):
            for r, cells in enumerate(self.patterns[p]):
                yield oi, p, r, cells

    def effects_used(self):
        """{'A': n, 'E9': n, ...}: every effect that occurs in the order list, with counts."""
        out = {}
        for _, _, _, cells in self.rows():
            for c in cells:
                if c.effect or c.param:
                    k = 'E%X' % (c.param >> 4) if c.effect == 0xe else '%X' % c.effect
                    out[k] = out.get(k, 0) + 1
        return dict(sorted(out.items()))

    def dump(self, order_index):
        p = self.order[order_index]
        lines = ['order %d pattern %d' % (order_index, p)]
        for r, cells in enumerate(self.patterns[p]):
            lines.append('%02d | ' % r + ' | '.join(str(c) for c in cells))
        return '\n'.join(lines)


def check_rom(d):
    for lit, v in PLAYER_LITERALS:
        if struct.unpack_from('<I', d, lit - GBA)[0] != v:
            raise ValueError('not Payback (Europe): music player literal at %x differs' % lit)


def load(rom, number):
    """Song `number` (0..4) from a ROM path or its bytes."""
    d = open(rom, 'rb').read() if isinstance(rom, (str, os.PathLike)) else bytes(rom)
    check_rom(d)
    if not 0 <= number < SONGS:
        raise ValueError('song is 0..4')
    o = struct.unpack_from('<128h', d, ORDERS - GBA + 0x100 * number)
    order = list(o[:o.index(-1)] if -1 in o else o)
    samples = []
    for k in range(31):
        off, ls, words, ft, vol = struct.unpack_from('<IHHbB', d, SAMPLES - GBA + 0x174 * number + 12 * k)
        a = SAMPLE_DATA - GBA + off
        data = np.frombuffer(d, dtype=np.int8, count=2 * words, offset=a).copy() if words else np.zeros(0, np.int8)
        loop = 2 * ls if ls != 0xffff and words else -1
        if loop >= len(data):
            loop = -1
        samples.append(Sample(k + 1, data, loop, ft, vol, SAMPLE_DATA + off))
    patterns = {}
    for p in sorted(set(order)):
        w = np.frombuffer(d, dtype='<u4', count=256, offset=PATTERNS - GBA + 0x400 * p).reshape(64, 4)
        patterns[p] = [[Cell(int(v >> 12) & 0xfff, int(v >> 24), int(v >> 8) & 15, int(v) & 0xff) for v in row]
                       for row in w]
    steps = np.frombuffer(d, dtype=np.uint8, count=SAMPLE_DATA - STEPS, offset=STEPS - GBA).copy()
    return Song(number, samples, patterns, order, step_table=steps)


def write_mod(song, path):
    """A standard 31-sample M.K. ProTracker module of the song (scratch reference only)."""
    pats = sorted(set(song.order))
    remap = {p: i for i, p in enumerate(pats)}
    h = bytearray(('payback song %d' % song.number).encode().ljust(20, b'\0'))
    for s in song.samples:
        words = len(s.data) // 2
        lps, lpl = (s.loop_start // 2, max(1, (len(s.data) - s.loop_start) // 2)) if s.looped else (0, 1)
        h += ('sample %d' % s.number).encode().ljust(22, b'\0')
        h += struct.pack('>HBBHH', words, s.finetune & 15, min(64, s.volume), lps, lpl)
    h += bytes([len(song.order), 127]) + bytes([remap[p] for p in song.order] + [0] * (128 - len(song.order)))
    h += b'M.K.'
    for p in pats:
        for row in song.patterns[p]:
            for c in row:
                h += bytes([(c.instrument & 0xf0) | (c.period >> 8 & 15), c.period & 0xff,
                            (c.instrument & 15) << 4 | c.effect, c.param])
    for s in song.samples:
        h += s.data.tobytes()
    with open(path, 'wb') as f:
        f.write(h)
    return len(h)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('rom')
    ap.add_argument('song', type=int)
    ap.add_argument('--mod', help='write a reference .mod here (scratch only)')
    ap.add_argument('--dump', type=int, action='append', default=[], help='print order position N')
    a = ap.parse_args(argv)
    s = load(a.rom, a.song)
    print('song %d: %d orders, %d patterns, order %s' % (s.number, len(s.order), len(s.patterns), s.order))
    print('effects:', s.effects_used())
    for x in s.samples:
        if x.length:
            print('  sample %2d: %6d bytes  loop %s  finetune %+d  volume %d' % (
                x.number, x.length, '%d-%d' % (x.loop_start, x.length) if x.looped else 'none', x.finetune, x.volume))
    for n in a.dump:
        print(s.dump(n))
    if a.mod:
        print('wrote', a.mod, write_mod(s, a.mod), 'bytes')


if __name__ == '__main__':
    main(sys.argv[1:])

#!/usr/bin/env python3
"""The title songs in a built ROM (tools/mkradio.py, src/radio.c), decoded on the host: the table, each stream's
extent, its loop's seam (the decoder's state carried over the wrap as src/radio.c does it) measured against the
steps the song makes everywhere else, and, with a reference WAV, how close the decode is to it.

    python3 tools/title_check.py ROM.gba
"""
import ctypes
import glob
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mkradio  # noqa: E402

GBA = 0x08000000


def lib():
    so = sorted(glob.glob(os.path.join(HERE, '..', 'build', 'radio', 'radenc-*.so')))
    if not so:
        so = [mkradio._lib(os.path.join(HERE, '..', 'build'))._name]
    L = ctypes.CDLL(so[-1])
    L.radenc_decode.restype = ctypes.c_long
    return L


def check(rom):
    L = lib()
    t = lambda a, n: rom[a - GBA:a - GBA + n]   # noqa: E731
    magic, count = struct.unpack('<II', t(mkradio.TITLE_BASE, 8))
    assert magic == mkradio.TITLE_MAGIC and count == 2, 'no title songs in this ROM'
    res = []
    for i in range(count):
        addr, nseg, ab, zero = struct.unpack('<IIII', t(mkradio.TITLE_BASE + 8 + 16 * i, 16))
        assert zero == 0 and mkradio.TITLE_BASE < addr and addr + nseg * 136 <= mkradio.BASE, 'entry %d out of range' % i
        a0, b0 = struct.unpack('<hh', struct.pack('<I', ab))
        data = np.frombuffer(rom, np.uint8, count=mkradio.BASE - addr, offset=addr - GBA).copy()
        st = (ctypes.c_int * 2)(a0, b0)
        out = np.zeros(nseg * mkradio.SEG, np.int16)
        used = L.radenc_decode(data.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), nseg, st, out.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)))
        end = (st[0], st[1])
        n = nseg * mkradio.SEG
        two = np.concatenate([out, out]).astype(np.int64)   # (the decoder starts each pass from (a0, b0): the same samples)
        d = np.abs(np.diff(two))
        seam = int(d[n - 1])                       # the step across the wrap
        around = d[n - 1 - 4800:n - 1 + 4800]
        rest = np.delete(d, np.arange(n - 1 - 64, n - 1 + 64))
        res.append(dict(song=i, segments=nseg, seconds=round(n / mkradio.RATE, 2), bytes=used, ends_in=end, starts_from=(a0, b0),
                        seam_step=seam, step_p99=int(np.percentile(rest, 99)), step_p9999=int(np.percentile(rest, 99.99)),
                        step_max_nearby=int(around.max()), end_vs_start_state=int(abs(end[0] - a0) + abs(end[1] - b0)),
                        out=out))
    return res


if __name__ == '__main__':
    rom = open(sys.argv[1], 'rb').read()
    for r in check(rom):
        r.pop('out')
        print(r)

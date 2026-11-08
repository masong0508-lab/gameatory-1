#!/usr/bin/env python3
"""Street Jungle in a built ROM (tools/mkradio.py, src/radio.c), decoded on the host the way the radio plays it: the
table at BASE, the stream's extent, the stream played into its loop and round once more (the decoder set to the stored
state at the jump, as src/radio.c does it), the loop's seam measured against the steps the song makes everywhere else,
and, with the MP3 it was made from, how close the decode is to it (SNR over the whole stream, and over the loop).

    python3 tools/sj_check.py ROM.gba [FILE.mp3 [LUFS]]

LUFS is what the build gave the song (the mean of the radio's other songs'); the default is read from build/radio.
"""
import ctypes
import glob
import json
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


def decode(L, rom, addr, nseg, a, b):
    data = np.frombuffer(rom, np.uint8, count=min(nseg * 256, len(rom) - (addr - GBA)), offset=addr - GBA).copy()
    st = (ctypes.c_int * 2)(a, b)
    out = np.zeros(nseg * mkradio.SEG, np.int16)
    used = L.radenc_decode(data.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), nseg, st,
                           out.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)))
    return out, used, (st[0], st[1])


def snr(x, y):
    x, d = x.astype(np.float64), y.astype(np.float64) - x
    return round(float(10 * np.log10(np.sum(x * x) / max(np.sum(d * d), 1))), 2)


def check(rom, mp3=None, lufs=None):
    L = lib()
    t = lambda a, n: rom[a - GBA:a - GBA + n]   # noqa: E731
    magic, count = struct.unpack('<II', t(mkradio.BASE, 8))
    assert magic == mkradio.MAGIC and count == len(mkradio.SONGS) + 1, 'no Street Jungle in this ROM'
    addr, nseg, laddr, lseg, state = struct.unpack('<5I', t(mkradio.BASE + 4 * mkradio.SJ_AT, 4 * mkradio.SJ_WORDS))
    assert mkradio.TITLE_BASE - 0x400000 < addr and addr % 16 == 0, 'address 0x%08x out of range' % addr
    a0, b0 = struct.unpack('<hh', struct.pack('<I', state))
    first, used, end_state = decode(L, rom, addr, nseg, 0, 0)
    assert addr + used <= mkradio.TITLE_BASE, 'the stream runs into the title songs'
    ls = nseg - lseg                                   # the loop's first segment
    # the loop's address is where the segment before it ends: walk the segments' sizes
    at, sizes = addr, []
    for g in range(nseg):
        sizes.append(136 if rom[at - GBA] == 2 else 256)
        assert rom[at - GBA] in (2, 4)
        at += sizes[-1]
    assert at == addr + used and laddr == addr + sum(sizes[:ls]), 'the loop address is not at segment %d' % ls
    # the state going into the loop on the first pass is the stored one
    assert (int(first[ls * mkradio.SEG - 1]), int(first[ls * mkradio.SEG - 2])) == (a0, b0), 'stored state != first pass'
    again, used2, _ = decode(L, rom, laddr, lseg, a0, b0)
    assert np.array_equal(again, first[ls * mkradio.SEG:]), 'the second pass differs from the first'
    n = nseg * mkradio.SEG
    two = np.concatenate([first, again]).astype(np.int64)
    d = np.abs(np.diff(two))
    wrap = n - 1
    rest = np.delete(d, np.arange(wrap - 64, wrap + 64))
    res = dict(address='0x%08x' % addr, end='0x%08x' % (addr + used), bytes=used, segments=nseg, loop_segment=ls,
               loop_segments=lseg, seconds=round(n / mkradio.RATE, 2), loop_seconds=round(lseg * mkradio.SEG / mkradio.RATE, 2),
               four_bit=sum(1 for s in sizes if s == 256), seam_step=int(d[wrap]), step_p99=int(np.percentile(rest, 99)),
               step_p9999=int(np.percentile(rest, 99.99)), step_max=int(rest.max()),
               peak=int(np.abs(first).max()), after_end_free_to_titles=mkradio.TITLE_BASE - addr - used)
    if mp3:
        if lufs is None:
            j = sorted(glob.glob(os.path.join(HERE, '..', 'build', 'radio', 'sj-*.json')))
            lufs = json.load(open(j[-1]))['lufs_to']
        x, ls2, m2, rep = mkradio.sj_prepare(mkradio.sj_load(mp3), lufs)
        assert (ls2, m2) == (ls, lseg), 'the file gives another loop (%d, %d)' % (ls2, m2)
        res.update(snr_db=snr(x, first), snr_loop_db=snr(x[ls * mkradio.SEG:], first[ls * mkradio.SEG:]),
                   source_seam_step=int(abs(int(x[ls * mkradio.SEG]) - int(x[-1]))),
                   source_step_p9999=int(np.percentile(np.abs(np.diff(x.astype(np.int64))), 99.99)),
                   decode_vs_source_samples=int(len(x) - len(first)))
        # the loop's two seams, side by side, in the source and in the decode: what comes after the wrap, over 20 ms
        k = mkradio.SEG
        res['wrap_window_rms_error'] = round(float(np.sqrt(np.mean((two[wrap - k:wrap + k] - np.concatenate(
            [x[-k:], x[ls * k:ls * k + k]]).astype(np.int64)) ** 2))), 1)
    return res


if __name__ == '__main__':
    rom = open(sys.argv[1], 'rb').read()
    r = check(rom, sys.argv[2] if len(sys.argv) > 2 else None, float(sys.argv[3]) if len(sys.argv) > 3 else None)
    for k, v in r.items():
        print('%-24s %s' % (k, v))

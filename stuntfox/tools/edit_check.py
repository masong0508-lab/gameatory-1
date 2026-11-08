#!/usr/bin/env python3
"""The radio edits in a built ROM (tools/mkradio.py, tools/radedits.py, src/radio.c), decoded on the host the way the radio plays
them: the table below the title songs, each stream's extent (the segments walked one by one, the streams back to back and
ending in the table), its beginning and end (they start and finish in silence, with the segments the radio drops at the end
silent too) and, with the folder of the MP3s the edits were made from, how close each decode is to them (SNR over the
whole edit) and how its joins sound: the biggest step between two samples within 4 ms of a join, against the 99.99th
percentile of the steps in the rest of the edit, in the edit as cut (the source) and in the decode.

    python3 tools/edit_check.py ROM.gba [DIR [LUFS]]

LUFS is what the build gave the songs (the mean of the radio's other songs'); the default is read from build/radio.
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
import radedits  # noqa: E402

GBA = 0x08000000


def lib():
    so = sorted(glob.glob(os.path.join(HERE, '..', 'build', 'radio', 'radenc-*.so')))
    if not so:
        so = [mkradio._lib(os.path.join(HERE, '..', 'build'))._name]
    L = ctypes.CDLL(so[-1])
    L.radenc_decode.restype = ctypes.c_long
    return L


def decode(L, rom, addr, nseg):
    data = np.frombuffer(rom, np.uint8, count=min(nseg * 256, len(rom) - (addr - GBA)), offset=addr - GBA).copy()
    st = (ctypes.c_int * 2)(0, 0)
    out = np.zeros(nseg * mkradio.SEG, np.int16)
    used = L.radenc_decode(data.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), nseg, st,
                           out.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)))
    return out, used


def snr(x, y):
    x, d = x.astype(np.float64), y.astype(np.float64) - x
    return round(float(10 * np.log10(np.sum(x * x) / max(np.sum(d * d), 1))), 2)


def join_steps(x, cuts, w=int(0.004 * mkradio.RATE)):
    """(the biggest step within w samples of each cut, the 99.99th percentile of the steps elsewhere)"""
    d = np.abs(np.diff(x.astype(np.int64)))
    keep = np.ones(len(d), bool)
    big = []
    for c in cuts:
        a, b = max(c - w, 0), min(c + w, len(d))
        big.append(int(d[a:b].max()))
        keep[max(c - 8 * w, 0):c + 8 * w] = False
    return big, int(np.percentile(d[keep], 99.99))


def check(rom, folder=None, lufs=None):
    L = lib()
    t = lambda a, n: rom[a - GBA:a - GBA + n]   # noqa: E731
    magic, count = struct.unpack('<II', t(mkradio.EDIT_TAB, 8))
    assert magic == mkradio.EDIT_MAGIC and 0 < count <= mkradio.EDIT_MAX, 'no radio edits in this ROM'
    ents = [struct.unpack('<III', t(mkradio.EDIT_TAB + 8 + 12 * i, 12)) for i in range(count)]
    assert not any(t(mkradio.EDIT_TAB + 8 + 12 * count, 256 - 8 - 12 * count)), 'the table has more than it says'
    res, at = [], ents[0][0]
    assert at % 16 == 0 and at > mkradio.TITLE_BASE - 0x800000, 'first address 0x%08x out of range' % at
    files = radedits.find(folder) if folder else {}
    if folder and lufs is None:
        j = sorted(glob.glob(os.path.join(HERE, '..', 'build', 'radio', 'streams-*.json')))
        lufs = float(np.mean([v['lufs_original'] for v in json.load(open(j[-1]))['songs'].values()])) if j else -14.06
    for addr, nseg, ident in ents:
        assert addr == at, 'the streams are not back to back at 0x%08x' % addr
        assert ident < len(radedits.EDITS), 'name %d out of range' % ident
        out, used = decode(L, rom, addr, nseg)
        p, sizes = addr, []
        for g in range(nseg):                      # (the segments' own sizes: 2 bits 136 bytes, 4 bits 256)
            b = rom[p - GBA]
            assert b in (2, 4), 'segment %d of %s has bits %d' % (g, radedits.EDITS[ident][0], b)
            sizes.append(136 if b == 2 else 256)
            p += sizes[-1]
        assert p == addr + used
        at = p
        assert at <= mkradio.EDIT_TAB, 'the streams run into the table'
        loud = np.nonzero(np.abs(out.reshape(-1, mkradio.SEG)).max(axis=1) > 64)[0]
        r = dict(key=radedits.EDITS[ident][0], name=radedits.EDITS[ident][1], address='0x%08x' % addr, bytes=used,
                 segments=nseg, seconds=round(nseg * mkradio.SEG / mkradio.RATE, 2),
                 four_bit=sum(1 for s in sizes if s == 256), bits=round(used * 8 / (nseg * mkradio.SEG), 3),
                 peak=int(np.abs(out).max()), start_peak=int(np.abs(out[:mkradio.SEG // 4]).max()),
                 end_silent_segments=int(nseg - 1 - loud[-1]), last_sample=int(out[-1]))
        assert r['end_silent_segments'] >= 4, '%s: the radio drops its last 3 segments, so the sound must end before them' % r['key']
        assert r['last_sample'] == 0 or abs(r['last_sample']) < 4
        if radedits.EDITS[ident][0] in files:
            try:
                y, info = radedits.make(r['key'], files[r['key']])
            except radedits.Missing as e:
                r['source'] = str(e)
            else:
                x, _ = mkradio.edit_prepare(y, lufs)
                assert len(x) == len(out), '%s: %d samples in the ROM, %d from the file' % (r['key'], len(out), len(x))
                cuts = [int(round(c * mkradio.RATE / radedits.IN_RATE)) for c in info['cuts']]
                big_src, p_src = join_steps(x, cuts)
                big_dec, p_dec = join_steps(out, cuts)
                r.update(snr_db=snr(x, out), joins=len(cuts), join_step_source=big_src, step_p9999_source=p_src,
                         join_step_decoded=big_dec, step_p9999_decoded=p_dec,
                         worst_join_over_p9999=round(max(big_dec) / max(p_dec, 1), 2) if cuts else 0)
        res.append(r)
    return res


if __name__ == '__main__':
    rom = open(sys.argv[1], 'rb').read()
    for r in check(rom, sys.argv[2] if len(sys.argv) > 2 else None, float(sys.argv[3]) if len(sys.argv) > 3 else None):
        print('--- %s' % r['name'])
        for k, v in r.items():
            if k not in ('name',):
                print('%-24s %s' % (k, v))

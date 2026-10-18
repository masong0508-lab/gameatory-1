"""Payback's soundtrack, one song short (build.py --merge).

Payback plays four-channel ProTracker modules converted to its own player's data (sequencer
0x08075dd0 on the timer interrupt, play 0x08076c98(song), stop 0x08076b10, song number s16 at
0x020001c8). Five songs, each with 31 sample headers of 12 bytes (offset from the sample data,
loop start and length in words, finetune, volume) at 0x084b009c + 0x174 * song, an order list
of s16 pattern numbers ending in -1 at 0x084b07e0 + 0x100 * song, 1 KiB patterns from
0x0860d738 and signed 8-bit samples from 0x084b14e0. No names or text survive the conversion.
Song 0 plays at the title, in the menus and on a few vehicles' radios; every other radio plays
1 + random(4) (0x08077464 on getting in, 0x08077498 when a song ends), so songs 1-4 rotate.

Song 3 (H&B's "Jammin' In The Wind", 1993) goes: the sample names of its original module greet
someone by a racist nickname. Its slot gets song 4's headers and order list (so nothing can
reach its own data), the radios draw 1 + random(3) (songs 1 and 2, and song 4 in slot 3, evenly)
and its patterns and samples, which no other song shares, are zeroed.
"""
import struct
import zlib

GBA = 0x08000000
SAMPLES, ORDERS, PATTERNS, SAMPLE_DATA = 0x084b009c, 0x084b07e0, 0x0860d738, 0x084b14e0
PLAYER_LITERALS = ((0x0807611c, SAMPLES), (0x08076124, SAMPLE_DATA), (0x0807614c, ORDERS),
                   (0x08076150, PATTERNS), (0x08076e20, ORDERS), (0x08076e24, PATTERNS))
SONGS = 5
DROP, INSTEAD = 3, 4
DROP_TABLES_CRC = 0xd0707a81      # its headers and order list, as Payback has them
DROP_DATA_CRC = 0xae927bb8        # its samples (by offset), then its patterns (by number)
RADIO = (0x08077472, 0x080774c6)  # movs r0, #4; bl random; adds r0, #1; bl play
RANDOM, PLAY = 0x08077eb0, 0x08076c98


def song(d, s):
    """A song's distinct patterns and its samples as (ROM offset, bytes)."""
    o = struct.unpack_from('<128h', d, ORDERS - GBA + 0x100 * s)
    pats = sorted(set(o[:o.index(-1)]))
    smp = []
    for k in range(31):
        off, _, words = struct.unpack_from('<IHH', d, SAMPLES - GBA + 0x174 * s + 12 * k)
        if words:
            smp.append((SAMPLE_DATA - GBA + off, 2 * words))
    return pats, sorted(smp)


def drop_song(d, bl_target):
    for lit, v in PLAYER_LITERALS:
        assert struct.unpack_from('<I', d, lit - GBA)[0] == v, 'music player not as expected at %x' % lit
    assert (ORDERS - SAMPLES) // 0x174 == SONGS
    hdr = lambda s: slice(SAMPLES - GBA + 0x174 * s, SAMPLES - GBA + 0x174 * (s + 1))
    ords = lambda s: slice(ORDERS - GBA + 0x100 * s, ORDERS - GBA + 0x100 * (s + 1))
    assert zlib.crc32(d[hdr(DROP)] + d[ords(DROP)]) == DROP_TABLES_CRC, 'song %d not as expected' % DROP
    pats, smp = song(d, DROP)
    for s in range(SONGS):
        if s != DROP:
            p, sm = song(d, s)
            assert not set(p) & set(pats), 'song %d shares patterns with song %d' % (s, DROP)
            assert all(a + n <= b or b + m <= a for a, n in sm for b, m in smp), 'shared samples'
    pat = lambda p: slice(PATTERNS - GBA + 0x400 * p, PATTERNS - GBA + 0x400 * (p + 1))
    crc = 0
    for a, n in smp:
        crc = zlib.crc32(d[a:a + n], crc)
    for p in pats:
        crc = zlib.crc32(d[pat(p)], crc)
    assert crc == DROP_DATA_CRC, 'song %d data not as expected' % DROP
    for site in RADIO:
        a = site - GBA
        assert (struct.unpack_from('<H', d, a)[0] == 0x2000 | (SONGS - 1) and bl_target(d, site + 2) == RANDOM
                and struct.unpack_from('<H', d, a + 6)[0] == 0x3001 and bl_target(d, site + 8) == PLAY), \
            'radio song pick not as expected at %x' % site
        struct.pack_into('<H', d, a, 0x2000 | (SONGS - 2))
    d[hdr(DROP)] = d[hdr(INSTEAD)]
    d[ords(DROP)] = d[ords(INSTEAD)]
    for a, n in smp:
        d[a:a + n] = bytes(n)
    for p in pats:
        d[pat(p)] = bytes(0x400)
    return sum(n for _, n in smp) + 0x400 * len(pats)

"""The mission data blob's layout, as src/misdata.h has it (tests/content/test_misfmt.py compiles the header and
checks every size, offset and number here against it). Little-endian, every record aligned to its own size, no
pointers: offsets from the blob's start. pack() writes a blob, parse() reads one back (round-trip and the validators).
"""
import struct
import zlib

MAGIC, VER = 0x31433253, 1                       # 'S2C1'
NOPLACE = 0xffff

# (name, struct code); the records are laid out with the C rules (natural alignment), checked by layout()
FIELDS = {
    'S2Head': [('magic', 'I'), ('ver', 'H'), ('nchap', 'H'), ('nmis', 'H'), ('nobj', 'H'), ('nplace', 'H'), ('ntext', 'H'),
               ('off_chap', 'I'), ('off_mis', 'I'), ('off_obj', 'I'), ('off_place', 'I'), ('off_text', 'I'),
               ('off_name', 'I'), ('off_spare', 'I'), ('size', 'I'), ('crc', 'I'), ('flags', 'I')],
    'Chapter': [('map', 'B'), ('flags', 'B'), ('nact', 'B'), ('split', 'B'), ('mis0', 'H'), ('nmis', 'H'), ('title', 'H'),
                ('brief', 'H'), ('hx2', 'B'), ('hy2', 'B'), ('next', 'H')],
    'MisDef': [('id', 'H'), ('map', 'B'), ('kind', 'B'), ('act', 'B'), ('tier', 'B'), ('flags', 'H'), ('title', 'H'),
               ('brief', 'H'), ('obj0', 'H'), ('nobj', 'B'), ('giver', 'B'), ('start', 'H'), ('par', 'H'), ('pay', 'H'),
               ('score', 'H')],
    'MisObj': [('op', 'B'), ('flags', 'B'), ('mode', 'B'), ('n', 'B'), ('place', 'H'), ('a', 'h'), ('b', 'h'), ('text', 'H')],
    'MsPlace': [('x8', 'H'), ('y8', 'H'), ('h', 'H'), ('r8', 'B'), ('kind', 'B')],
}
# (a place's height is a u16: mission.c takes it as it is, so no place sits below the street level 0)

OPS = ['NOP', 'GOTO', 'CHECK', 'RINGS', 'LAND', 'ENTER', 'DELIVER', 'RACE', 'CHASE', 'DESTROY', 'BLAST', 'FOES', 'BOSS',
       'ESCORT', 'DEFEND', 'COLLECT', 'CRATES', 'STUNT', 'JUMP', 'SCORE', 'WANTED', 'PHONE', 'SURVIVE', 'SPACE', 'DOCK',
       'TALK', 'BRIEF', 'TIMER', 'ENDTIMER', 'GROUP', 'ENDGROUP', 'SPAWNVEH', 'CARD', 'WAIT', 'CEIL', 'ZONE', 'GIVE',
       'UNLOCK', 'SET', 'GATEWAY', 'FINISH']
ENUMS = {
    'OP': {n: i for i, n in enumerate(OPS)},
    'MO': {'STRICT': 1, 'ORDER': 2, 'HIDDEN': 4, 'CKPT': 8},
    'PK': {n: i for i, n in enumerate(['POINT', 'PAD', 'RING_X', 'RING_Y', 'RING_H', 'BOX0', 'BOX1', 'PICK', 'SPAWN'])},
    'MK': {'ACT': 0, 'CONTRACT': 1, 'CHAL': 2, 'MEDAL': 3},
    'CH': {'STORY': 1, 'DROP': 2, 'FINAL': 4, 'RESERVED': 8},
    'FF': {'TIME': 1, 'DEATH': 2, 'VEHLOST': 4, 'ZONE': 8, 'CEIL': 0x10, 'ESCORT': 0x20},
    'MF': {'PHONE': 0x40},
    'MS': {'FOOT': 0x100, 'DRIVE': 0x200, 'FLY': 0x400, 'SPACE': 0x800, 'AFTER': 0x1000, 'REPEAT': 0x2000},
}
for _k, _v in ENUMS.items():
    for _n, _i in _v.items():
        globals()['%s_%s' % (_k, _n)] = _i
for _n, _i in ENUMS['OP'].items():
    globals()['OP_' + _n] = _i
OP_N = len(OPS)

# the modes a MisObj.mode names (0 any, 1 foot, 2 drive, 3 fly) and the player's (merge.c: FOOT 0, DRIVE 1, FLY 2)
MODE_ANY, MODE_FOOT, MODE_DRIVE, MODE_FLY = 0, 1, 2, 3

# C layout rules: natural alignment, the struct padded to its widest member
_SIZE = {'B': 1, 'b': 1, 'H': 2, 'h': 2, 'I': 4, 'i': 4}


def layout(name):
    """[(field, offset, code)], size of the C struct."""
    off, wide, out = 0, 1, []
    for f, c in FIELDS[name]:
        s = _SIZE[c]
        off = (off + s - 1) // s * s
        out.append((f, off, c))
        off += s
        wide = max(wide, s)
    return out, (off + wide - 1) // wide * wide


def fmt(name):
    """A struct format (explicit padding) for the record."""
    lay, size = layout(name)
    parts, at = ['<'], 0
    for f, o, c in lay:
        parts.append('x' * (o - at) + c)
        at = o + _SIZE[c]
    parts.append('x' * (size - at))
    return ''.join(parts)


SIZES = {n: layout(n)[1] for n in FIELDS}
assert SIZES == {'S2Head': 56, 'Chapter': 16, 'MisDef': 24, 'MisObj': 12, 'MsPlace': 8}, SIZES


def h_to(h):
    """A place's height in units; the field is unsigned (a place under the street level is not expressible)."""
    h = int(round(h))
    assert 0 <= h <= 65535, 'a place height of %d is outside 0..65535' % h
    return h


def pad4(b):
    return b + bytes(-len(b) % 4)


def pack_text(texts):
    """texts[0] is ''. A table of u16 offsets from its own start, then NUL-terminated ASCII."""
    strs = [t.encode('ascii') + b'\0' for t in texts]
    at = 2 * len(strs)
    offs = []
    for s in strs:
        offs.append(at)
        at += len(s)
    assert at < 0x10000, 'the text table is over 64 KiB'
    return pad4(struct.pack('<%dH' % len(offs), *offs) + b''.join(strs))


def pack_rec(name, d, extra=0):
    """One record from a dict of its fields (a missing field is 0; an unknown one is an error)."""
    lay, size = layout(name)
    names = [f for f, _, _ in lay]
    bad = set(d) - set(names)
    assert not bad, '%s has no field %s' % (name, sorted(bad))
    vals = []
    for f, _, c in lay:
        v = int(d.get(f, 0))
        if c in 'BHI':
            assert 0 <= v < (1 << (8 * _SIZE[c])), '%s.%s = %d does not fit' % (name, f, v)
        else:
            assert -(1 << (8 * _SIZE[c] - 1)) <= v < (1 << (8 * _SIZE[c] - 1)), '%s.%s = %d does not fit' % (name, f, v)
        vals.append(v)
    return struct.pack(fmt(name), *vals)


def unpack_rec(name, blob, off=0):
    lay, size = layout(name)
    vals = struct.unpack_from(fmt(name), blob, off)
    return {f: v for (f, _, _), v in zip(lay, vals)}


def pack(chapters, missions, objs, places, texts, names=()):
    """Lists of dicts (the fields above). names: the debug strings (missions then places), after the text."""
    chap = b''.join(pack_rec('Chapter', c) for c in chapters)
    mis = b''.join(pack_rec('MisDef', m) for m in missions)
    obj = b''.join(pack_rec('MisObj', o) for o in objs)
    pl = b''.join(pack_rec('MsPlace', p) for p in places)
    text = pack_text(texts)
    nm = pad4(b''.join(n.encode('ascii') + b'\0' for n in names))
    head_size = SIZES['S2Head']
    off_chap = head_size
    off_mis = off_chap + len(chap)
    off_obj = off_mis + len(mis)
    off_place = off_obj + len(obj)
    off_text = off_place + len(pl)
    off_name = off_text + len(text)
    size = off_name + len(nm)
    body = chap + mis + obj + pl + text + nm
    head = pack_rec('S2Head', dict(magic=MAGIC, ver=VER, nchap=len(chapters), nmis=len(missions), nobj=len(objs),
                                   nplace=len(places), ntext=len(texts), off_chap=off_chap, off_mis=off_mis,
                                   off_obj=off_obj, off_place=off_place, off_text=off_text, off_name=off_name,
                                   off_spare=size, size=size, crc=zlib.crc32(body) & 0xffffffff, flags=0))
    assert len(head) == head_size
    return head + body


def parse(blob):
    """The blob back into lists of dicts: head, chapters, missions, objs, places, texts, names."""
    head = unpack_rec('S2Head', blob)
    assert head['magic'] == MAGIC and head['ver'] == VER, 'not a content blob'
    assert head['size'] == len(blob), 'size %d, blob %d' % (head['size'], len(blob))
    assert head['crc'] == zlib.crc32(blob[SIZES['S2Head']:]) & 0xffffffff, 'crc'

    def recs(name, off, n):
        s = SIZES[name]
        return [unpack_rec(name, blob, off + i * s) for i in range(n)]
    out = dict(head=head,
               chapters=recs('Chapter', head['off_chap'], head['nchap']),
               missions=recs('MisDef', head['off_mis'], head['nmis']),
               objs=recs('MisObj', head['off_obj'], head['nobj']),
               places=recs('MsPlace', head['off_place'], head['nplace']))
    t0 = head['off_text']
    offs = struct.unpack_from('<%dH' % head['ntext'], blob, t0)
    texts = []
    for o in offs:
        e = blob.index(b'\0', t0 + o)
        texts.append(blob[t0 + o:e].decode('ascii'))
    out['texts'] = texts
    nm = blob[head['off_name']:head['size']].rstrip(b'\0')
    out['names'] = nm.decode('ascii').split('\0') if nm else []
    return out

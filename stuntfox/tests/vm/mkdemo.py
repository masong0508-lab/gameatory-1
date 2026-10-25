"""Demo chapters for maps 0 and 3: the mission engine's blob (src/misdata.h) with no content package in the build.

s2build.py picks tools/content/sfc.py when it is there and this file when it is not. build(rom, orig, gen) -> bytes.
Map 0 (the city): an on-foot act, a stunt challenge, a jump medal and a street sprint. Map 3 (the arena): a ring run for
the Arwing and a lap race. Every place is checked against the map's own cells (road, kerb or open ground, none of them a
building, a ramp or water); a cell that is not free fails the build. The act's beacon stands off the street the man walks down
(a lone engine shows an act within 4 cells), so the standard speed scenes do not arm it.

    python3 tests/vm/mkdemo.py out.bin [payback.gba]     (without the ROM: no cell check)
"""
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

(OP_NOP, OP_GOTO, OP_CHECK, OP_RINGS, OP_LAND, OP_ENTER, OP_DELIVER, OP_RACE, OP_CHASE, OP_DESTROY, OP_BLAST, OP_FOES,
 OP_BOSS, OP_ESCORT, OP_DEFEND, OP_COLLECT, OP_CRATES, OP_STUNT, OP_JUMP, OP_SCORE, OP_WANTED, OP_PHONE, OP_SURVIVE,
 OP_SPACE, OP_DOCK, OP_TALK, OP_BRIEF, OP_TIMER, OP_ENDTIMER, OP_GROUP, OP_ENDGROUP, OP_SPAWNVEH, OP_CARD, OP_WAIT,
 OP_CEIL, OP_ZONE, OP_GIVE, OP_UNLOCK, OP_SET, OP_GATEWAY, OP_FINISH) = range(41)
MO_STRICT, MO_ORDER, MO_HIDDEN, MO_CKPT = 1, 2, 4, 8
PK_POINT, PK_PAD, PK_RING_X, PK_RING_Y, PK_RING_H, PK_BOX0, PK_BOX1, PK_PICK, PK_SPAWN = range(9)
MK_ACT, MK_CONTRACT, MK_CHAL, MK_MEDAL = range(4)
FF_TIME, FF_DEATH = 1, 2
MS_FOOT, MS_DRIVE, MS_FLY, MS_REPEAT = 0x100, 0x200, 0x400, 0x2000
CH_STORY, CH_DROP = 1, 2
NOPLACE = 0xffff
MAGIC, VER = 0x31433253, 1


class Blob:
    def __init__(self):
        self.places, self.objs, self.mis, self.chap, self.text = [], [], [], [], ['']
        self.cells = []                            # (map, x, y) to check

    def t(self, s, hud=False):
        assert s == s.upper() and s.count('\n') <= 1, s
        for line in s.split('\n'):
            assert len(line) <= (18 if hud else 38), s
        if s not in self.text:
            self.text.append(s)
        return self.text.index(s)

    def place(self, m, x, y, h=0, r=1.5, kind=PK_POINT):
        """x, y in cells; the height in units; the radius in cells."""
        self.places.append((int(x * 8), int(y * 8), h, int(r * 8), kind))
        self.cells.append((m, x, y, kind))
        return len(self.places) - 1

    def obj(self, op, place=0, mode=0, n=0, a=0, b=0, text='', flags=0):
        self.objs.append((op, flags, mode, n, place, a, b, self.t(text, op not in (OP_BRIEF, OP_CARD, OP_TALK)) if text else 0))
        return len(self.objs) - 1

    def mission(self, m, kind, title, brief, start, flags, objs, act=0, par=0, pay=0, score=0, giver=0, tier=0):
        assert len(title) <= 19, title
        first = len(self.objs)
        for o in objs:
            self.obj(*o[:1], **o[1])
        self.mis.append(dict(id=len(self.mis) + 1, map=m, kind=kind, act=act, tier=tier, flags=flags, title=self.t(title),
                             brief=self.t(brief) if brief else 0, obj0=first, nobj=len(objs), giver=giver, start=start,
                             par=par, pay=pay, score=score))
        return len(self.mis) - 1

    def pack(self):
        pad4 = lambda b: b + bytes(-len(b) % 4)
        chap = b''.join(struct.pack('<BBBBHHHHBBH', c['map'], c['flags'], c['nact'], c['split'], c['mis0'], c['nmis'],
                                    c['title'], c['brief'], 0, 0, NOPLACE) for c in self.chap)
        mis = b''.join(struct.pack('<HBBBBHHHHBBHHHH', d['id'], d['map'], d['kind'], d['act'], d['tier'], d['flags'],
                                   d['title'], d['brief'], d['obj0'], d['nobj'], d['giver'], d['start'], d['par'], d['pay'],
                                   d['score']) for d in self.mis)
        obj = b''.join(struct.pack('<BBBBHhhH', *o) for o in self.objs)
        pl = b''.join(struct.pack('<HHHBB', *p) for p in self.places)
        strs = [s.encode('ascii') + b'\0' for s in self.text]
        base = 2 * len(strs)
        offs, at = [], base
        for s in strs:
            offs.append(at)
            at += len(s)
        text = pad4(struct.pack('<%dH' % len(offs), *offs) + b''.join(strs))
        off_chap = 56
        off_mis = off_chap + len(chap)
        off_obj = off_mis + len(mis)
        off_place = off_obj + len(obj)
        off_text = off_place + len(pl)
        size = off_text + len(text)
        body = chap + mis + obj + pl + text
        head = struct.pack('<I6H10I', MAGIC, VER, len(self.chap), len(self.mis), len(self.objs), len(self.places),
                           len(self.text), off_chap, off_mis, off_obj, off_place, off_text, off_text, off_text, size,
                           zlib.crc32(body), 0)
        assert len(head) == 56
        return head, body


def content():
    b = Blob()
    # ---- map 0: the city. The man starts at (9.5, 48) and the street south of him runs along x 9.7; the open square beside it is
    # x 8..15, y 53..63, and the act's beacon stands at its east side, 5 cells off that street: a walk or a flight down the
    # street does not arm it (a lone engine shows an act within 4 cells) ----
    sq = b.place(0, 14.5, 58.5, r=1.5, kind=PK_PAD)
    chk = [b.place(0, 11.5, 60.5), b.place(0, 14.5, 55.0), b.place(0, 9.5, 54.0)]
    coins = [b.place(0, 9.0, 58.5, 140, 1.0, PK_PICK), b.place(0, 13.0, 62.0, 140, 1.0, PK_PICK),
             b.place(0, 12.5, 58.0, 140, 1.0, PK_PICK)]
    goal = b.place(0, 20.0, 66.0, r=1.5)
    act1 = b.mission(0, MK_ACT, 'FIRST STEPS', 'GET YOUR LEGS UNDER YOU', sq, MS_FOOT | FF_DEATH | MS_REPEAT, [
        (OP_BRIEF, dict(text='WALK THE MARKERS, GRAB THE COINS.\nTHEN HEAD FOR THE BEACON.')),
        (OP_CHECK, dict(place=chk[0], mode=1, n=3, text='WALK THE MARKERS')),
        (OP_COLLECT, dict(place=coins[0], n=3, text='GRAB THE COINS', flags=MO_CKPT)),
        (OP_GOTO, dict(place=goal, mode=0, text='REACH THE BEACON')),
        (OP_FINISH, dict()),
    ], act=1, par=90, pay=50, score=10)
    # the avenue at y 33..34 runs x 6..26 and the road at y 40..41 x 5..24, with a ramp at x 16..17 below it: a stunt challenge,
    # a sprint and a jump medal, each more than 10 cells (a beacon shows within 10) from the man's start and from the act's beacon
    st = b.place(0, 14.0, 34.5, r=1.5)
    stunt = b.mission(0, MK_CHAL, 'STUNT 300', 'LAND 300 POINTS OF STUNTS', st, MS_DRIVE | FF_TIME, [
        (OP_TIMER, dict(b=60)),
        (OP_STUNT, dict(a=300, b=-1, text='STUNTS 300')),
        (OP_FINISH, dict()),
    ], par=60, pay=20, score=5)
    cs = [b.place(0, x, 33.5, r=1.5) for x in (9, 14, 19, 24)]
    sp = b.place(0, 7.0, 33.5, r=1.5)
    sprint = b.mission(0, MK_CHAL, 'CITY SPRINT', 'BEAT THE PAR TIME', sp, MS_DRIVE, [
        (OP_RACE, dict(place=cs[0], mode=2, n=4, b=1, text='CITY SPRINT')),
        (OP_FINISH, dict()),
    ], par=40, pay=20, score=5)
    jm = b.place(0, 16.5, 41.5, r=1.5)
    medal = b.mission(0, MK_MEDAL, 'SKY HIGH', 'JUMP FIVE CELLS', jm, MS_DRIVE, [
        (OP_JUMP, dict(a=40, text='JUMP 5 CELLS')),
        (OP_FINISH, dict()),
    ], pay=10, score=5)
    b.chap.append(dict(map=0, flags=CH_STORY, nact=1, split=1, mis0=act1, nmis=4, title=b.t('THE CITY'), brief=b.t('DEMO CITY')))
    # ---- map 3: the arena (x 53..86, y 58..91); the Arwing flies it at 1500..2600 units ----
    rs = b.place(3, 58.0, 66.0, 1800, 2.0, PK_RING_Y)
    rings = [b.place(3, 64.0, 70.0, 1700, 2.0, PK_RING_X), b.place(3, 72.0, 64.0, 2000, 2.0, PK_RING_X),
             b.place(3, 80.0, 70.0, 2400, 2.0, PK_RING_Y), b.place(3, 76.0, 84.0, 2000, 2.0, PK_RING_X),
             b.place(3, 66.0, 82.0, 1700, 2.0, PK_RING_Y)]
    pad = b.place(3, 70.5, 75.5, 0, 1.5, PK_PAD)
    ring = b.mission(3, MK_ACT, 'RING RUN', 'FLY THE RINGS', rs, MS_FLY | FF_DEATH | MS_REPEAT, [
        (OP_BRIEF, dict(text='FLY THROUGH EACH RING IN ORDER.\nTHEN SET DOWN ON THE PAD.')),
        (OP_RINGS, dict(place=rings[0], n=5, text='FLY THE RINGS', flags=MO_CKPT)),
        (OP_LAND, dict(place=pad, text='SET DOWN ON PAD')),
        (OP_FINISH, dict()),
    ], act=1, par=90, pay=50, score=10)
    ls = b.place(3, 60.0, 62.0, 1500, 2.0, PK_RING_X)
    lc = [b.place(3, x, y, 1700, 2.0) for x, y in ((80, 64), (80, 86), (60, 86), (60, 70))]
    lap = b.mission(3, MK_CHAL, 'ARENA LAPS', 'TWO LAPS AGAINST PAR', ls, MS_FLY | FF_DEATH, [
        (OP_RACE, dict(place=lc[0], mode=3, n=4, b=2, text='ARENA LAPS')),
        (OP_FINISH, dict()),
    ], par=60, pay=20, score=5)
    b.chap.append(dict(map=3, flags=CH_DROP, nact=1, split=1, mis0=ring, nmis=2, title=b.t('THE ARENA'), brief=b.t('DEMO ARENA')))
    return b


def check_cells(b, rom):
    """Every ground place sits on a free cell of its map: road, kerb or open ground (the arena's are in the air)."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    sys.path.insert(0, os.path.join(ROOT, '..', 'payback-mod'))
    import mkworld
    kinds = {}
    for m in {c[0] for c in b.cells}:
        g = rom.painted.get(m) or rom.grid(m)
        kinds[m] = mkworld.classify(rom, g)
    bad = []
    for m, x, y, pk in b.cells:
        if m == 3 and pk in (0, 2, 3, 4) and b.places[b.cells.index((m, x, y, pk))][2] >= 1000:
            continue
        k = kinds[m][(int(x) << 7) + int(y)][0]
        if k in ('building', 'ramp'):
            bad.append((m, x, y, k))
    assert not bad, 'demo places on blocked cells: %s' % bad


def build(rom, orig, gen):
    b = content()
    head, body = b.pack()
    try:
        check_cells(b, rom)
    except ImportError:
        pass
    return head + body


if __name__ == '__main__':
    b = content()
    head, body = b.pack()
    if len(sys.argv) > 2:
        sys.path.insert(0, os.path.join(ROOT, '..', 'payback-mod'))
        from paybackmod.rom import PaybackRom
        check_cells(b, PaybackRom(open(sys.argv[2], 'rb').read()))
    open(sys.argv[1] if len(sys.argv) > 1 else 'demo.bin', 'wb').write(head + body)
    print('%d bytes, %d missions, %d objectives, %d places, %d texts' % (len(head + body), len(b.mis), len(b.objs), len(b.places), len(b.text)))

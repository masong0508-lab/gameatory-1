"""Every act of the campaign blob, through the debug mailbox, on its own map: started (cmd 1), its title the banner, run to
its end by the autopilot (cmd 4: each objective is forced a second after it began), ACT COMPLETE, paid, Payback's goal list
back to its own, no line on the ticker (the same frames without the act give the same count), no Prog bit unless a Prog
exists (the progress words are the ones the control run has), and the flash monitor (flashcheck's rules) over all of it. An act whose objectives need the foe/boss code (OP_FOES, OP_BOSS,
OP_DEFEND) is run the same way but is listed apart: the autopilot forces what the foes would have decided, so for those the
check is the structure (the engine takes the objectives, nothing hangs, nothing leaks), not the fight.

ALL=1 runs every mission of the blob the same way (contracts, challenges and medals too: their banner is CHALLENGE DONE or
MEDAL FOUND where an act's is ACT COMPLETE), so a mission that cannot start or finish is found whoever wrote it.

    SP=.. ROM=x.gba ELF=x.elf [MAPS=0,1] [ALL=1] [OUT=dir] python3 tests/s2/acts.py      (from stuntfox/)
"""
import json
import h
from h import *

sys.path.insert(0, os.path.join(START, 'tools', 'content'))
import misfmt as F                                   # noqa: E402

maps = [int(a) for a in os.environ.get('MAPS', '').split(',') if a] or list(range(11))
OUT = os.environ.get('OUT')
ALL = bool(os.environ.get('ALL'))
ck = Check()
DONE = {F.MK_ACT: 'ACT COMPLETE', F.MK_CONTRACT: 'ACT COMPLETE', F.MK_CHAL: 'CHALLENGE DONE', F.MK_MEDAL: 'MEDAL FOUND'}
BAN = 0x020026e4                                     # Payback's banner slot 0
FOES = (F.OP_FOES, F.OP_BOSS, F.OP_DEFEND)


def ban():
    return bytes(e.read(BAN, 20)).split(b'\0')[0].decode('latin1')


def ticker_n():
    return r16(0x02019424)


def st():
    v = mb(7)
    return v & 255, (v >> 8) & 255, (v >> 16) & 0xffff


def own():
    return [(g[0], g[1]) for g in goals() if not 0x5000 <= g[0] < 0x5100]


def ours():
    return [g for g in goals() if 0x5000 <= g[0] < 0x5100]


def blob():
    head = bytes(e.read(S['s2_blob'], 56))
    size = F.unpack_rec('S2Head', head)['size']
    return bytes(e.read(S['s2_blob'], size))


d = F.parse(blob())
NAMES = mission_names(d)                            # (the ROM's blob has no mission keys: the build writes them beside it)
merged_state(e)
run(30)
fm_start('acts')                                     # (the flash monitor on every frame of every act: no more than 3 flashes in a second, whole screen or red)
ck(mb(8, 0) == len(d['missions']), 'the blob in the ROM is the one the engine holds: %d missions' % len(d['missions']), str(mb(8, 0)))
acts = [(i, m) for i, m in enumerate(d['missions']) if ALL or m['kind'] == F.MK_ACT]
ck(len(acts) == (len(d['missions']) if ALL else 66), '%d %s' % (len(acts), 'missions' if ALL else 'acts (11 chapters of 6)'), str(len(acts)))
rows = []
for g in maps:
    gstate(g)
    run(40)
    mb(10, 1)                                        # (roaming off: no beacon starts anything by itself)
    base = e.save_state()
    base_goals, base_words = own(), words()
    for i, m in [a for a in acts if a[1]['map'] == g]:
        ops = [o['op'] for o in d['objs'][m['obj0']:m['obj0'] + m['nobj']]]
        title = d['texts'][m['title']]
        foes = any(o in FOES for o in ops)
        sp = d['places'][m['start']] if m['start'] < len(d['places']) else None

        def put():                                   # (the player at the act's beacon, as one who walked up to it: a zone act starts inside its zone)
            e.load_state(base)
            fm_break()
            run(1)
            if sp:
                tele_man(sp['x8'] / 8.0, sp['y8'] / 8.0)
            run(1)
        put()
        t0, s0 = ticker_n(), score()
        r = mb(1, i)
        banners = []
        for _ in range(8):
            run(3)
            b = ban()
            if not banners or banners[-1] != b:
                banners.append(b)
        started = r == 1 and st()[0] in (2, 5) and st()[2] == i
        mb(4, 1)
        n = 0
        limit = 140 * len(ops) + 400
        while mb(8, 2) < 1 and st()[0] in (2, 5) and n < limit:
            run(3)
            n += 3
            b = ban()
            if not banners or banners[-1] != b:
                banners.append(b)
        done = mb(8, 2) == 1
        for _ in range(3):
            run(2)
            b = ban()
            if not banners or banners[-1] != b:
                banners.append(b)
        frames = n + 24
        paid = score() > s0 or m['score'] == 0
        goals_ok = own() == base_goals and not ours()
        tk = ticker_n() - t0
        mb(4, 0)
        mb(9)
        put()                                        # (the control: the same frames, no act)
        c0 = ticker_n()
        run(frames + 7)
        quiet = tk == ticker_n() - c0
        shown = any(title.upper().startswith(b[:8]) or b.startswith(title.upper()[:8]) for b in banners if b) if title else True
        ok = started and done and DONE[m['kind']] in banners and goals_ok and quiet and shown and paid
        rows.append(dict(map=g, mis=i, name=NAMES[i], kind=m['kind'], title=title, ops=ops, foes=foes, frames=frames, ok=bool(ok)))
        ck(ok, 'map %2d %-8s %-19s %s%d objs, %d frames' % (g, NAMES[i], title, 'foe code, ' if foes else '', len(ops), frames),
           'started %s done %s banners %s goals %s ticker %d vs control %s paid %s' % (started, done, banners[:4], goals_ok, tk, quiet, paid))
    e.load_state(base)
    run(2)
    ck(words() == base_words, 'map %2d: the progress words are untouched by the acts' % g, '%s vs %s' % (words(), base_words))
worst, worst_red = fm_report()
ck(worst <= 3 and worst_red <= 3, 'flashcheck over every frame of the %d acts: most flashes in a second %d, red %d' % (len(rows), worst, worst_red))
if OUT:
    with open(os.path.join(OUT, 'acts.json'), 'w') as f:
        json.dump(rows, f, indent=1)
print('acts that need the foe code (structure only): %d of %d' % (sum(r['foes'] for r in rows), len(rows)))
ck.done()

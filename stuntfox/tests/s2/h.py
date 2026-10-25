"""The small harness the stage-2 tests share: the emulator on the ROM and ELF named by $ROM and $ELF, the earlier
playtest helpers (gstate, jack_car, board_now, ents, fm_start ...) pointed at them, and the debug mailbox (stage2.h).

    SP=<harness folder> ROM=x.gba ELF=x.elf python3 tests/s2/<test>.py       (run from the repo's stuntfox/ folder)
"""
import os
import re
import struct
import sys
import types

START = os.getcwd()
SP = os.environ['SP']
ROM, ELF = (os.path.join(START, os.environ[k]) for k in ('ROM', 'ELF'))
PLAY = SP + '/v12/s1play5'
sys.path[:0] = [SP + '/work', PLAY]
os.chdir(SP + '/work')
_src = open(PLAY + '/pp.py').read()
for _old, _new in (("ROM=SP+'/v12/s1fin/m.gba'", 'ROM=%r' % ROM), ("ELF=SP+'/v12/s1fin/m.elf'", 'ELF=%r' % ELF)):
    assert _old in _src
    _src = _src.replace(_old, _new)
pp = types.ModuleType('pp')                      # (the helpers import it by name)
sys.modules['pp'] = pp
exec(compile(_src, 'pp.py', 'exec'), pp.__dict__)
from pp5 import *                                # noqa: E402,F401,F403  (ppx, pp: e, S, run, status, ents, epos, jack_car ...)

HK = ['TICK', 'DRAW3D', 'HUD', 'LEVEL', 'MENU', 'KEYS', 'ROOM', 'BANNER']
EV = ['NONE', 'STUNT', 'KILL', 'LAND', 'MODE', 'DEATH', 'SPACE', 'DOCK', 'LAUNCH', 'FOE_DOWN', 'ARWING_DOWN', 'PICKUP', 'TALK',
      'MENU', 'MIS_DONE', 'MIS_FAIL']
D_EVENTS, D_HOOK, D_RAISE, D_PUT, D_RESET = range(64, 69)     # stage2.h DBG_F_*
MAGIC = 0x42443253


def mb(cmd, arg=0, frames=40):
    """One mailbox command, run by the next frame of ours: its answer (None if no frame took it)."""
    a = S['s2_dbg']
    seq = u32(a + 12)
    e.write8(a + 4, cmd & 255), e.write8(a + 5, cmd >> 8), e.write8(a + 6, arg & 255), e.write8(a + 7, arg >> 8)
    e.write32(a, MAGIC)
    for _ in range(frames):
        e.run(1)
        if u32(a + 12) != seq:
            return r32(a + 8)
    return None


def hooks():
    return dict(zip(HK, struct.unpack('<8H', e.read(S['hook_count'], 16))))


def events():
    return dict(zip(EV, e.read(S['ev_count'], 16)))


def s2f():
    x, y, z, speed = struct.unpack_from('<4i', e.read(S['s2f'], 16))
    heading, mode, docked, paused, mp, sub, story, air, sgs = struct.unpack_from('<H8B', e.read(S['s2f'] + 16, 10))
    veh, ticks, clock, me = struct.unpack_from('<HxxIII', e.read(S['s2f'] + 28, 16))
    return dict(pos=(x, y, z), speed=speed, heading=heading, mode=mode, docked=docked, paused=paused, map=mp, sub=sub,
                story=story, air=air, sgstate=sgs, veh=veh, ticks=ticks, clock=clock, me=me)


def mission_names(d):
    """The mission keys (m3.gr1 ...) of a parsed blob: the blob's own, else the sidecar the build writes (the ROM's copy has none)."""
    import json
    names = d.get('names', [])[:len(d['missions'])]
    if len(names) != len(d['missions']):
        try:
            with open(os.path.join(START, 'build', 'content', 'names.json')) as f:
                names = json.load(f)
        except OSError:
            names = []
    return names if len(names) == len(d['missions']) else ['#%d' % i for i in range(len(d['missions']))]


class Check:
    """pass/fail lines; exit status 1 if any failed"""
    def __init__(self):
        self.bad = 0

    def __call__(self, ok, what, detail=''):
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', what, '  (' + detail + ')' if detail else ''), flush=True)
        self.bad += not ok
        return ok

    def done(self):
        print('%s' % ('ALL PASS' if not self.bad else '%d FAILED' % self.bad))
        sys.exit(1 if self.bad else 0)


def title_state(tag=''):
    """The title menu, cold boot to it (language English), cached per ROM next to the tests' outputs."""
    import hashlib
    path = '%s/v12/s2/st/title_%s.st' % (SP, hashlib.sha1(e.romdata).hexdigest()[:10])
    if os.path.exists(path):
        e.load_state(open(path, 'rb').read())
        e.run(2)
        return
    e.run(400)
    e.run(4, ['A'])
    e.run(1500)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'wb').write(e.save_state())
    title_state()                                # (always from the file: a run that made it must not differ from one that found it)


def tap(k, hold=4, after=24):
    e.run(hold, [k] if k else [])
    e.run(after)


def words():
    """What persists: STATE (magic + one), the progress copy (4 words + its check) and the extras (2 words)."""
    return dict(state=[u32(0x0203ffd0 + 4 * i) for i in range(2)], mirror=[u32(0x0203ffd8 + 4 * i) for i in range(5)],
                extras=[u32(0x0203ff90), u32(0x0203ff94)])


def pba(name):
    """A Payback address from src/pbapi.h by name (PBA_RESPAWN ...)."""
    m = re.search(r'#define\s+%s\s+(0x[0-9a-fA-F]+)' % name, open(os.path.join(START, 'src/pbapi.h')).read())
    return int(m.group(1), 16)


def get_car(tries=8, maxd=20):
    """Into a car on foot, as a player: the nearest parked or passing car within maxd cells (traffic differs from
    build to build, so wait a little, walking, for one that suits). The car stuck in the corner of map 0 is no use."""
    for _ in range(tries):
        c = jack_car(maxd=maxd)
        if c and modename() == 'DRIVE' and c[2] != 0:
            return c
        run(90, ['UP'])
    return None

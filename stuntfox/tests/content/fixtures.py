"""Synthetic content for the validator tests: a small map made by hand (flat ground, a road along y 60-61, a building, a
pond), the smallest content that passes every validator (the control), and the knobs the failing fixtures turn."""
import copy

import atlas as A
import sfc

CAMPAIGN = '''crew rook=1 pip=2 nova=3 dusty=4 quill=5 juno=6 kestrel=7
const UNLOCK_QUARTERS = 1
chapter map=0 flags=final split=6 hover=0,0 title="TEST CITY" brief="LINE ONE\\nLINE TWO"
'''

PLACES = '''map 0
place gate x=20.5 y=60.5 h=ground+400 r=1.6 ring_x car
place r.1 x=30.5 y=60.5 h=ground r=2.5 car
place r.2 x=40.5 y=60.5 h=ground r=2.5 car
place r.3 x=50.5 y=60.5 h=ground r=2.5 car
place r.4 x=60.5 y=60.5 h=ground r=2.5 car
'''

SFM = '''act t1 "TEST ACT" map=0 act=1 giver=rook par=60 pay=100 score=10 fail=time start=gate mode=drive
  brief "TEST ACT" "LINE ONE\\nLINE TWO"
  race r.1..r.4 "RACE THE ROAD"
  finish
'''

LOCK = dict(ids={'m0.t1': 0}, next=1, retired=[])
QUOTA = dict(acts=1, contracts=0, chal=(0, 9), medals=0)


def atlas():
    """Flat ground with a road (lanes) along y 60-61 from x 10 to x 110, a building (20-30, 20-30; h 3072), a pond."""
    a = A.Atlas.blank(0)
    a.put_road(10, 60, 110, 61)
    a.put_building(20, 20, 30, 30, 3072)
    a.put_water(80, 20, 90, 30)
    a.finish()
    a.crates = []
    a.phones = [(70, 70)]
    a.starts = [(4, 4, 0)]
    return a


def run(places=PLACES, sfm=SFM, campaign=CAMPAIGN, a=None, lock=LOCK, cal=None, quota=QUOTA, extra=None):
    """The issues of compiling this content on the map."""
    files = {'campaign.sfc': campaign, 'maps/m00.places': places, 'missions/m00.sfm': sfm}
    files.update(extra or {})
    c = sfc.Content.from_texts(files, lock=copy.deepcopy(lock), cal=cal)
    res = sfc.compile(c, {0: a or atlas()}, quota=quota)
    return res


def codes(res, sev=None):
    return sorted({i.code for i in res.issues if sev is None or i.sev == sev})

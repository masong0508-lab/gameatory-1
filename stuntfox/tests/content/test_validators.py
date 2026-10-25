"""T0: every validator V1-V16 has a failing fixture here, and the control (the smallest content that passes them all)
passes. A fixture changes one thing of the control and expects that validator's code among the errors."""
import math
import unittest

import common
import fixtures as X
import par as PAR
import validate as V


def err(res):
    return {i.code for i in res.issues if i.sev == V.ERR}


class Control(unittest.TestCase):
    def test_control_passes_every_validator(self):
        res = X.run()
        self.assertEqual([V.fmt(i) for i in res.issues if i.sev == V.ERR], [])
        self.assertIsNotNone(res.blob)

    def test_every_validator_is_registered(self):
        self.assertEqual([f.__name__ for f in V.ALL], ['v%d' % i for i in range(1, 17)])


class Fixtures(unittest.TestCase):
    def expect(self, code, **kw):
        res = X.run(**kw)
        self.assertIn(code, err(res), [V.fmt(i) for i in res.issues])

    def test_v1_place_inside_a_building(self):
        self.expect('V1', places=X.PLACES + 'place bad x=25.5 y=25.5 h=1500 r=2\n',
                  sfm=X.SFM.replace('finish', 'goto bad "GO INSIDE"\n  finish'))

    def test_v1_ring_disc_in_a_wall(self):
        a = X.atlas()
        self.expect('V1', a=a, places='map 0\nplace s x=19 y=25.5 h=1500 r=1.6 ring_x air\nplace r.1 x=40.5 y=25.5 h=1500 r=1.6 ring_x air\n',
                  sfm='act t1 "FLY" map=0 act=1 giver=rook par=60 pay=1 score=1 fail=time start=s mode=fly\n  rings r.1 "RINGS"\n  finish\n')

    def test_v1_ring_dipping_into_water(self):
        pl = 'map 0\nplace s x=70.5 y=25.5 h=2600 r=1.6 ring_x air\nplace r.1 x=85.5 y=25.5 h=1000 r=1.6 ring_x air\n'
        self.expect('V1', places=pl, sfm='act t1 "FLY" map=0 act=1 giver=rook par=60 pay=1 score=1 fail=time start=s mode=fly\n  rings r.1 "RINGS"\n  finish\n')
        res = X.run(places=pl.replace('h=1000', 'h=2000'), sfm='act t1 "FLY" map=0 act=1 giver=rook par=60 pay=1 score=1 fail=time start=s mode=fly\n  rings r.1 "RINGS"\n  finish\n')
        self.assertNotIn('V1', err(res), [V.fmt(i) for i in res.issues])

    def test_v1_rim_between_the_old_samples(self):
        a = X.atlas()
        a.put_deck(40, 42, 40, 42, 3300, 3400)                       # (a thin slab only the 22.5 degree sample of a rim of 16 meets)
        old = [(1000 * math.cos(2 * math.pi * k / 8), 1000 * math.sin(2 * math.pi * k / 8)) for k in range(8)]
        self.assertFalse(any(a.blocked(40.5 * 1024, 42200 + u, 3000 + v, 128) for u, v in old))
        self.assertIsNotNone(a.clear_disc(40.5 * 1024, 42200, 3000, 1000, 'x', 128))

    def test_v2_land_on_water(self):
        self.expect('V2', places=X.PLACES + 'place pad x=85.5 y=25.5 h=ground r=2 pad\n',
                  sfm=X.SFM.replace('finish', 'land pad "LAND"\n  finish'))

    def test_v2_checkpoint_in_a_building_by_car(self):
        self.expect('V2', places=X.PLACES.replace('place r.4 x=60.5 y=60.5', 'place r.4 x=25.5 y=25.5'))

    def test_v3_rings_too_far_apart(self):
        pl = 'map 0\nplace s x=10.5 y=40.5 h=2500 r=1.6 ring_x air\nplace a x=20.5 y=40.5 h=2500 r=1.6 ring air\nplace b x=80.5 y=40.5 h=2500 r=1.6 ring air\n'
        self.expect('V3', places=pl, sfm='act t1 "FLY" map=0 act=1 giver=rook par=90 pay=1 score=1 fail=time start=s mode=fly\n  rings a b "RINGS"\n  finish\n')

    def test_v3_a_race_leg_past_the_draw_distance(self):
        pl = 'map 0\nplace s x=10.5 y=40.5 h=ground r=2 car\nplace a x=20.5 y=40.5 h=ground r=2.5 car\nplace b x=60.5 y=40.5 h=ground r=2.5 car\n'
        self.expect('V3', places=pl, sfm='act t1 "DRIVE" map=0 act=1 giver=rook par=90 pay=1 score=1 fail=time start=s mode=drive\n  race a b "RACE"\n  finish\n')

    def test_v3_a_sharp_turn(self):
        pl = ('map 0\nplace s x=10.5 y=40.5 h=2500 r=1.6 ring_x air\nplace a x=20.5 y=40.5 h=2500 r=1.6 ring air\n'
              'place b x=28.5 y=40.5 h=2500 r=1.6 ring air\nplace c x=20.5 y=41.5 h=2500 r=1.6 ring air\n')
        self.expect('V3', places=pl, sfm='act t1 "FLY" map=0 act=1 giver=rook par=90 pay=1 score=1 fail=time start=s mode=fly\n  rings a b c "RINGS"\n  finish\n')

    def test_v4_ceiling(self):
        pl = X.PLACES + 'zone zz x=25..65 y=55..65\nplace hi x=45.5 y=60.5 h=1900 r=2 car\n'
        self.expect('V4', places=pl, sfm=X.SFM.replace('  race', '  ceil 2000 zone=zz\n  race').replace('fail=time', 'fail=time,ceil').replace('r.1..r.4', 'r.1..r.2 hi r.3'))

    def test_v5_race_across_a_field(self):
        pl = X.PLACES.replace('y=60.5', 'y=100.5')
        self.expect('V5', places=pl.replace('place gate x=20.5 y=100.5', 'place gate x=20.5 y=60.5'))

    def test_v6_a_limit_that_cannot_be_met(self):
        self.expect('V6', sfm=X.SFM.replace('par=60', 'par=2'))

    def test_v6_a_bot_limit_is_held_to_the_same_bar(self):
        sfm = X.SFM.replace('par=60', 'par=auto')
        cal = {'speed': {'foot': 3.0, 'drive': 4.5, 'fly': 11.0}, 'par': {}, 'bots': {'m0.t1': {'time': 5.0, 'finished': True, 'kind': 'race-line'}}}
        res = X.run(sfm=sfm, cal=cal)
        self.assertNotIn('V6', err(res), [V.fmt(i) for i in res.issues])
        m = res.rm[0]
        self.assertEqual(m.par_from, 'bot')
        floor = PAR.limit_floor(PAR.top_time(m, cal['speed']))
        self.assertEqual((m.par, floor > 7), (floor, True))          # (1.3 x 5 s = 7 s, but the route takes 9 s at top speed: the floor stands)
        self.assertEqual(PAR.bot_par(20.0, 9.0), 26)                  # (and a slow bot sets it)
        cal['par'] = {'m0.t1': 9}
        self.expect('V6', sfm=sfm, cal=cal)                          # (a hand number under the floor is the same error)

    def test_v6_a_hunt_on_foot_over_300_seconds(self):
        pl = X.PLACES.replace('place gate x=20.5 y=60.5 h=ground+400 r=1.6 ring_x car', 'place gate x=20.5 y=60.5 h=ground r=1.5 pad foot') + \
            ''.join('place p.%d x=%d.5 y=%d.5 h=ground r=1.5 pick\n' % (i, 12 + 12 * i, 60 + 8 * (i % 2)) for i in range(8))
        sfm = 'act t1 "HUNT" map=0 act=1 giver=rook par=%d pay=1 score=1 fail=time start=gate mode=foot\n  collect p.0..p.7 "FIND THEM"\n  finish\n'
        self.expect('V6', places=pl, sfm=sfm.replace('p.0..p.7', 'p.0..p.7') % 400)
        res = X.run(places=pl, sfm=sfm % 250)
        self.assertNotIn('V6', err(res), [V.fmt(i) for i in res.issues])

    def test_v6_time_limit_needs_a_par(self):
        self.expect('V6', sfm=X.SFM.replace('par=60', 'par=auto'), cal={'speed': {'foot': 3.0, 'drive': 9.0, 'fly': 11.0}, 'par': {'m0.t1': 0}, 'bots': {}})

    def test_v7_a_line_too_long(self):
        self.expect('V7', sfm=X.SFM.replace('"RACE THE ROAD"', '"RACE THE ROAD AND BACK AGAIN"'))

    def test_v7_a_title_too_long_or_lowercase(self):
        self.expect('V7', sfm=X.SFM.replace('"TEST ACT" map', '"A TITLE FAR TOO LONG HERE" map'))
        self.expect('V7', sfm=X.SFM.replace('"TEST ACT" map', '"test act" map'))

    def test_v7_a_title_with_punctuation_or_over_the_hud_line(self):
        self.expect('V7', sfm=X.SFM.replace('"TEST ACT" map', '"KESTREL\'S LAP" map'))
        self.expect('V7', sfm=X.SFM.replace('"TEST ACT" map', '"NINETEEN LETTERS 19" map'))
        res = X.run(sfm=X.SFM.replace('"TEST ACT" map', '"EIGHTEEN LETTERS 8" map'))
        self.assertNotIn('V7', err(res), [V.fmt(i) for i in res.issues])

    def test_v7_a_card_of_three_lines(self):
        self.expect('V7', sfm=X.SFM.replace('LINE ONE\\nLINE TWO', 'ONE\\nTWO\\nTHREE'))

    def test_v8_mission_without_an_id(self):
        self.expect('V8', lock=dict(ids={}, next=0, retired=[]))

    def test_v8_an_id_used_twice(self):
        self.expect('V8', lock=dict(ids={'m0.t1': 0, 'm0.old': 0}, next=1, retired=[]))

    def test_v8_a_retired_id_back_in_use(self):
        self.expect('V8', lock=dict(ids={'m0.t1': 0}, next=1, retired=[0]))

    def test_v8_two_missions_of_one_name(self):
        self.expect('V8', sfm=X.SFM + '\n' + X.SFM.replace('act=1', 'act=2'), quota=dict(X.QUOTA, acts=2))

    def test_v9_quota(self):
        self.expect('V9', quota=None)

    def test_v9_acts_numbered_from_one(self):
        self.expect('V9', sfm=X.SFM.replace('act=1', 'act=3'))

    def test_v9_chapter_split(self):
        self.expect('V9', campaign=X.CAMPAIGN.replace('split=6', 'split=3'))

    def test_v10_too_many_destroy_spawns(self):
        pl = X.PLACES + ''.join('place d.%d x=%d.5 y=60.5 h=ground r=2 spawn car\n' % (i, 12 + 6 * i) for i in range(1, 8))
        self.expect('V10', places=pl, sfm=X.SFM.replace('  race r.1..r.4 "RACE THE ROAD"', '  destroy d.1..d.7 type=0 "WRECK THEM"'))

    def test_v10_a_race_of_one_checkpoint(self):
        self.expect('V10', sfm=X.SFM.replace('r.1..r.4', 'r.1..r.1'))

    def test_v10_a_boss_that_does_not_exist(self):
        self.expect('V10', places=X.PLACES + 'place b x=45.5 y=45.5 h=3000 r=3 air\n', sfm=X.SFM.replace('  race r.1..r.4 "RACE THE ROAD"', '  boss b boss=9 "BOSS"'))

    def test_v11_beacons_too_close(self):
        sfm = X.SFM + '\nchal t2 "OTHER" map=0 par=60 pay=1 score=1 fail=time start=gate2 mode=drive\n  race r.1..r.4 "RACE"\n'
        self.expect('V11', places=X.PLACES + 'place gate2 x=22.5 y=60.5 h=ground+400 r=1.6 ring_x car\n', sfm=sfm,
                  lock=dict(ids={'m0.t1': 0, 'm0.t2': 1}, next=2, retired=[]))

    def test_v11_beacon_at_a_phone(self):
        self.expect('V11', places=X.PLACES + 'place ph x=70.5 y=70.5 h=ground r=1.5 pad foot\n',
                  sfm=X.SFM.replace('start=gate mode=drive', 'start=ph mode=foot'))

    def test_v12_beacon_inside_a_building(self):
        self.expect('V12', places=X.PLACES + 'place bd x=25.5 y=25.5 h=ground r=1.5 pad car\n', sfm=X.SFM.replace('start=gate', 'start=bd'))

    def test_v12_fly_start_too_low(self):
        pl = 'map 0\nplace s x=10.5 y=40.5 h=300 r=1.6 ring_x air\nplace a x=20.5 y=40.5 h=2500 r=1.6 ring air\n'
        self.expect('V12', places=pl, sfm='act t1 "FLY" map=0 act=1 giver=rook par=90 pay=1 score=1 fail=time start=s mode=fly\n  rings a "RINGS"\n  finish\n')

    def test_v12_start_ring_faces_the_wrong_way(self):
        self.expect('V12', places=X.PLACES.replace('ring_x', 'ring_y'))

    def test_v13_rings_on_foot(self):
        pl = X.PLACES + 'place g2 x=20.5 y=40.5 h=2500 r=1.6 ring air\n'
        self.expect('V13', places=pl, sfm=X.SFM.replace('  race r.1..r.4 "RACE THE ROAD"', '  rings g2 "RINGS"').replace('mode=drive', 'mode=foot'))

    def test_v13_space_start_must_fly(self):
        self.expect('V13', sfm=X.SFM.replace('mode=drive', 'mode=space,drive'))

    def test_v14_blob_over_the_budget(self):
        old = V.BLOB_MAX
        V.BLOB_MAX = 100
        try:
            self.expect('V14')
        finally:
            V.BLOB_MAX = old

    def test_v14_a_place_off_the_map(self):
        self.expect('V14', places=X.PLACES + 'place far x=1.5 y=60.5 h=ground r=2 car\n', sfm=X.SFM.replace('r.1..r.4', 'r.1..r.3 far'))

    def test_v15_act_beacon_on_a_payback_start(self):
        a = X.atlas()
        a.starts = [(20, 60, 0)]
        self.expect('V15', a=a)

    def test_v15_challenge_beacon_near_a_start(self):
        a = X.atlas()
        a.starts = [(14, 60, 0)]
        self.expect('V15', a=a, sfm=X.SFM.replace('act t1 "TEST ACT" map=0 act=1 giver=rook', 'chal t1 "TEST ACT" map=0 giver=rook'),
                  quota=dict(X.QUOTA, acts=0))

    def test_v16_blast_zone_without_boxes(self):
        pl = X.PLACES + 'zone bz x=40..50 y=55..65\n'
        self.expect('V16', places=pl, sfm=X.SFM.replace('  race r.1..r.4 "RACE THE ROAD"', '  blast bz n=5 "BREAK BOXES"'))

    def test_v16_blast_zone_with_boxes_passes(self):
        a = X.atlas()
        a.crates = [(42, 58), (43, 58), (44, 58), (45, 58), (46, 58), (47, 58)]
        res = X.run(a=a, places=X.PLACES + 'zone bz x=40..50 y=55..65\n', sfm=X.SFM.replace('  race r.1..r.4 "RACE THE ROAD"', '  blast bz n=5 "BREAK BOXES"'))
        self.assertNotIn('V16', err(res))

    def test_v16_phone_op_on_a_map_without_phones(self):
        a = X.atlas()
        a.phones = []
        self.expect('V16', a=a, sfm=X.SFM.replace('finish', 'phone n=1 "PHONE MISSION"\n  finish'))


if __name__ == '__main__':
    unittest.main()

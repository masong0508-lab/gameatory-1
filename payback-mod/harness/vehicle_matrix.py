#!/usr/bin/env python3
"""mGBA libretro census of REAL original-Payback vehicle descriptors.

No model/descriptor swaps. Only the player's temporary coordinate/height copies
are adjusted to reach a *naturally existing* vehicle. All entry, movement and
exit actions use the game's real buttons. Never publish outputs or game data.

    MGBA_CORE=/private/mgba_libretro.so python3 payback-mod/harness/vehicle_matrix.py \
        '/private/Payback (Europe) (En,Fr,De,Es,It).gba' \
        --out /private/gba-vehicles.json --survey-frames 2400

The original game may not spawn all 18 descriptor indices in one map/route.
Unobserved types remain UNOBSERVED, never implicitly PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

OWNER_EU_SHA1 = '08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7'
DESC_BASE = 0x08354AF4
DESC_STRIDE = 0x3C
HELIDESC = 0x08354EF0
HELICOPTER = (HELIDESC - DESC_BASE) // DESC_STRIDE
FIRST, END = DESC_BASE, HELIDESC
MAX_VEHICLE_KIND = HELICOPTER
LAST_ENTITY = 0x0300000C
PTRS = 0x03000C60
CONTROLLED = 0x02001DB8
CLOCK = 0x02001E00
MAP_ID = 0x02001D40
PLAYER_POS = (0x02008DF8, 0x02009398, 0x02009478, 0x02009484)


def kind_from_descriptor(desc):
    """The original ROM's 0x3c-byte descriptor records, 0..17."""
    if type(desc) is not int or not FIRST <= desc <= HELIDESC:
        return None
    delta = desc - FIRST
    return delta // DESC_STRIDE if delta % DESC_STRIDE == 0 else None


def action_plan(kind):
    if kind == HELICOPTER:
        return ('L enter', 'L takeoff', 'A fly', 'LEFT steer', 'RIGHT steer',
                'B descend', 'L land', 'L exit')
    return ('L enter', 'A accelerate', 'A+LEFT steer', 'A+RIGHT steer',
            'B brake/reverse', 'L exit')


def actor(e):
    last, index = e.s16(LAST_ENTITY), e.s16(CONTROLLED)
    if not 0 <= index <= last < 64:
        return None
    return entity(e, index)


def entity(e, index):
    last = e.s16(LAST_ENTITY)
    if not 0 <= index <= last < 64:
        return None
    ptr = e.u32(PTRS + 4*index)
    if not (0x02000000 <= ptr < 0x0203FE98) or (ptr & 3):
        return None
    desc = e.u32(ptr + 0x1C)
    return dict(index=index, ptr=ptr, kind=kind_from_descriptor(desc),
                x=e.r32(ptr + 4), y=e.r32(ptr + 8), z=e.s16(ptr + 0x0C),
                heading=e.s16(ptr + 0x12), state=e.read(ptr+0x10F,1)[0])


def census(e):
    player = e.s16(CONTROLLED)
    found = {}
    for i in range(min(max(0, e.s16(LAST_ENTITY)+1), 64)):
        if i == player:
            continue
        ent = entity(e,i)
        if ent and ent['kind'] is not None and 0 <= ent['x'] < 128*2048 and 0 <= ent['y'] < 128*2048:
            found.setdefault(ent['kind'], []).append(ent)
    return found


def delta(a,b):
    if not (a and b):
        return None
    # Payback's z points DOWN: smaller z is higher above the street.
    raw_dz = b['z'] - a['z']
    return dict(horizontal_units=round(math.hypot((b['x']-a['x']), (b['y']-a['y'])),1),
                vertical_units=raw_dz, climb_units=-raw_dz,
                heading_units=((b['heading']-a['heading']+2880)%5760)-2880)


def helicopter_climbed(before, after, min_units=1000):
    """Payback's z decreases on ascent; a fall is NOT takeoff."""
    return bool(before and after and before['z'] - after['z'] > min_units)


LANDING_SETTLE_FRAMES = 1800


def helicopter_landed(before_descent, touchdown, after_wait,
                      min_descent_units=32, horizontal_tolerance=512,
                      vertical_tolerance=256):
    """Descending then holding position while still in k17 proves touchdown.

    Ground elevation varies across Payback's map: the height at L-entry is
    diagnostic, NOT a touchdown target. World z increases when descending.
    """
    if not (before_descent and touchdown and after_wait
            and touchdown.get('kind') == HELICOPTER
            and after_wait.get('kind') == HELICOPTER):
        return False
    if touchdown['z'] - before_descent['z'] < min_descent_units:
        return False
    still = delta(touchdown, after_wait)
    return bool(still and still['horizontal_units'] <= horizontal_tolerance
                and abs(still['vertical_units']) <= vertical_tolerance)


def press(e, keys, frames, after=20):
    e.run(frames, list(keys))
    e.run(after, [])


def enter_existing(e, snapshot, target_kind, target_index):
    """Return a real L-entered vehicle or reason; no descriptor mutation."""
    for dx,dy in ((1200,0),(-1200,0),(0,1200),(0,-1200)):
        e.load_state(snapshot)
        v = entity(e,target_index)
        p = actor(e)
        if not v or v['kind'] != target_kind or not p:
            return False, 'vehicle_vanished'
        for ptr in PLAYER_POS:
            e.write32(ptr, v['x']+dx)
            e.write32(ptr+4, v['y']+dy)
        e.write16(p['ptr']+0x0C, v['z'] & 0xffff)
        e.run(3)
        press(e, ('L',), 16, 260)
        current = actor(e)
        if current and current['kind'] == target_kind and current['index'] == target_index:
            return True, None
    return False, 'L_entry_not_observed'


def ground_vehicle(e):
    initial=e.save_state()
    scenarios=(('A accelerate', ('A',), 180),
               ('A+LEFT steer', ('A','LEFT'), 80),
               ('A+RIGHT steer', ('A','RIGHT'), 80),
               ('B brake/reverse', ('B',), 160))
    rows=[]
    for label,buttons,frames in scenarios:
        e.load_state(initial)
        a=actor(e)
        press(e,buttons,frames)
        b=actor(e)
        d = delta(a,b)
        if label == 'A accelerate':
            passed = bool(d and d['horizontal_units'] > 32)
        elif label.startswith('A+'):  # heading should respond to each direction
            passed = bool(d and abs(d['heading_units']) > 0)
        else:
            # B can brake from a standstill. Arbitrary >32 unit movement is
            # not a valid reverse-control oracle; report the measured response
            # without grading movement as a defect until the route starts with
            # a known speed and direction.
            rows.append(dict(action=label, frames=frames, change=d,
                             diagnostic_only=True, passed=None))
            continue
        rows.append(dict(action=label, frames=frames, change=d, passed=passed))
    e.load_state(initial)
    a=actor(e)
    press(e,('L',),16,240)
    b=actor(e)
    rows.append(dict(action='L exit',frames=256,
                     passed=bool(b and b['kind'] is None),
                     exited=bool(b and b['kind'] is None),
                     controlled_after=None if b is None else b['index']))
    return rows


def helicopter(e):
    """mGBA test pattern used in the existing private modded-GBA suite.

    A stationary helicopter should not be graded as a broken road car.
    Takeoff/flight/landing are checked separately from entry/exit.
    """
    rows=[]
    a=actor(e)
    ground_z = None if a is None else a['z']
    press(e,('L',),16,300)
    b=actor(e)
    airborne=helicopter_climbed(a, b)
    rows.append(dict(action='L takeoff',change=delta(a,b),
                     passed=airborne,airborne=airborne))
    before=actor(e)
    press(e,('A',),120)
    after=actor(e)
    d=delta(before,after)
    rows.append(dict(action='A fly',change=d,passed=bool(d and d['horizontal_units'] > 100)))
    for label,btn in (('LEFT steer','LEFT'),('RIGHT steer','RIGHT')):
        before=actor(e)
        press(e,(btn,'A'),90)
        after=actor(e)
        d=delta(before,after)
        rows.append(dict(action=label,change=d,passed=bool(d and abs(d['heading_units']) > 0)))
    pre_descent=actor(e)
    press(e,('B',),180)
    after_descent=actor(e)
    d=delta(pre_descent,after_descent)
    descent_ok=bool(d and d['vertical_units'] > 0)
    rows.append(dict(action='B descend',change=d,passed=descent_ok))
    before_land=actor(e)
    press(e,('L',),16,900)
    touchdown=actor(e)
    # Landings may be a whole block away and at a different ground height.
    # Observe sustained position stability with real controller input released.
    e.run(LANDING_SETTLE_FRAMES, [])
    after_wait=actor(e)
    d=delta(before_land,touchdown)
    stable_d=delta(touchdown,after_wait)
    landed=descent_ok and helicopter_landed(pre_descent,touchdown,after_wait)
    near_entry=(ground_z is not None and touchdown is not None
                and abs(touchdown['z']-ground_z) <= 2048)
    rows.append(dict(action='L land',change=d,
                     passed=landed,descended=descent_ok,
                     stable_frames=LANDING_SETTLE_FRAMES,
                     stability_change=stable_d,
                     remained_in_helicopter=bool(touchdown and after_wait
                         and touchdown['kind']==HELICOPTER
                         and after_wait['kind']==HELICOPTER),
                     near_entry_ground=near_entry,
                     entry_ground_delta_z=None if ground_z is None or touchdown is None
                                          else touchdown['z']-ground_z,
                     entry_ground_is_diagnostic_only=True))
    press(e,('L',),16,300)
    p=actor(e)
    exited=bool(p and p['kind'] is None)
    rows.append(dict(action='L exit after landing',passed=bool(landed and exited),
                     landed_before_exit=landed,exited=exited,
                     controlled_after=None if p is None else p['index']))
    return rows


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path, help='original SHA-1 verified 8 MiB European GBA ROM')
    ap.add_argument('--out', required=True, type=Path, help='PRIVATE numeric JSON report; do not commit')
    ap.add_argument('--from-state', type=Path, help='PRIVATE mGBA savestate at another original guest map; omit for normal Rampage boot')
    ap.add_argument('--survey-frames', type=int, default=2400, help='observe traffic for N emulated frames, minimum 1')
    ap.add_argument('--step', type=int, default=120, help='survey snapshot interval')
    ap.add_argument('--require-all', action='store_true', help='exit 3 if any of 18 descriptors unobserved')
    ap.add_argument('--max-tests', type=int, default=18, help='maximum types to attempt')
    a=ap.parse_args(argv)
    if a.survey_frames < 1 or a.step < 1 or not 1 <= a.max_tests <= 18:
        ap.error('survey-frames, step and max-tests must be positive')
    if a.out.resolve().is_relative_to(HERE.parent.parent):
        ap.error('private report must be outside the public Git repository')
    data=a.rom.read_bytes()
    if len(data)!=0x800000 or hashlib.sha1(data).hexdigest()!=OWNER_EU_SHA1:
        ap.error('original 8 MiB European Payback ROM SHA-1 does not match')
    if not os.environ.get('MGBA_CORE') or not Path(os.environ['MGBA_CORE']).is_file():
        ap.error('mGBA libretro core unavailable: privately set MGBA_CORE to libretro-mgba shared library')
    from retro import Emu
    from drive_lanes import BOOT
    report=dict(schema=1,source='original_gba_mgba',owner_rom_sha1=OWNER_EU_SHA1,
                setup='Existing vehicles, player position adjustment only, real controller input',
                matched={},not_entered=[],unobserved=[],failed=[],status='INCOMPLETE')
    with Emu('gba',a.rom,capture_video=False) as e:
        if a.from_state:
            if not a.from_state.is_file():
                ap.error('private mGBA state file does not exist')
            e.load_state(a.from_state.read_bytes())
            e.run(1)
        else:
            for n,b in BOOT:
                e.run(n,[b] if b else [])
        if e.r32(CLOCK)==0 or actor(e) is None:
            raise RuntimeError('boot did not reach live Rampage level; no gameplay claims can be made')
        report['guest_map_id']=e.s16(MAP_ID)
        seen={}
        # Take a *new* save state for each naturally present descriptor type,
        # then restore it before testing; no model swapping and no screens.
        for t in range(0,a.survey_frames,a.step):
            snapshot=e.save_state()
            for kind,instances in census(e).items():
                if kind not in seen:
                    seen[kind]=(snapshot,instances[0]['index'],e.frames)
            e.run(min(a.step,a.survey_frames-t),[])
        for kind in sorted(seen)[:a.max_tests]:
            snap,index,frame=seen[kind]
            ok,reason=enter_existing(e,snap,kind,index)
            if not ok:
                report['matched'][str(kind)]={'observed_at_frame':frame,'entered':False,'reason':reason}
                report['not_entered'].append(kind)
                continue
            entry=actor(e)
            actions=helicopter(e) if kind==HELICOPTER else ground_vehicle(e)
            verified=all(row['passed'] for row in actions if not row.get('diagnostic_only'))
            if not verified:
                report['failed'].append(kind)
            report['matched'][str(kind)]=dict(observed_at_frame=frame,entered=True,
                                              controls_passed=verified,
                                              controlled_index=entry['index'],
                                              plan=action_plan(kind),actions=actions)
        report['unobserved']=[i for i in range(MAX_VEHICLE_KIND+1) if str(i) not in report['matched']]
        report['status']=('OBSERVED_DEFECTS' if report['failed'] else
                          'INCOMPLETE_ENTRY' if report['not_entered'] else
                          'PASS_OBSERVED')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(f"mGBA observed {len(report['matched'])} of 18 descriptor types; "
          f"not entered {len(report['not_entered'])}, verified control failures "
          f"{len(report['failed'])}, unobserved {len(report['unobserved'])}")
    if report['failed']:
        return 1
    if a.require_all and (report['unobserved'] or report['not_entered']):
        return 3
    return 0


if __name__=='__main__':
    sys.exit(main())

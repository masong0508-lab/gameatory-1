#!/usr/bin/env python3
"""Scan all eleven PS1 renderer-map views for unintended picture changes.

The R2 view is a renderer test, NOT a natural guest level selector. Checks
picture-hash changes against rc8's actual GPU flip counter g_flips,
black flashes and strong brightness oscillation. g_pres starts present(),
not a display flip, and may cause rc7 false positives. Result files/screenshots belong only in a private output dir.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import sys

RIG = str(Path(__file__).resolve().parents[1] / 'rig')
sys.path.insert(0, RIG)
from payback import *  # noqa
from flicker_evidence import choose_counter, display_step


def sample(im):
    if im is None:
        return None
    rgb = im.convert('RGB')
    raw = rgb.tobytes()
    # No captured pixels escape the process: only the digest and totals.
    digest = hashlib.blake2b(raw, digest_size=16).digest()
    ex = rgb.getextrema()
    black = all(hi < 8 for lo, hi in ex)
    # Fixed-step sampling, intentionally not an exposure-safety certificate.
    brightness = sum(raw[::23]) / max(1,len(raw[::23]))
    return digest, black, brightness


def extra(ap):
    ap.add_argument('--from-state', default=None)
    ap.add_argument('--frames-per-map', type=int, default=1200)
    ap.add_argument('--warmup-frames', type=int, default=180)
    ap.add_argument('--change-budget', type=int, default=14000)
    ap.add_argument('--allow-legacy-present-counter', action='store_true',
                    help='for old rc7 diagnostics only: g_pres is NOT release-grade flip evidence')


def main():
    a=std_args(__doc__,extra)
    if min(a.frames_per_map,a.warmup_frames,a.change_budget) < 1:
        raise SystemExit('flicker frame counts must be positive')
    g=open_game(a,'map_flicker')
    ok = start_level(g,a)
    g.check(ok,'level starts for 11-map picture scan',g.level_report() if ok else '')
    if not ok:
        return g.finish('map_flicker')
    counter, release_grade = choose_counter(g.v,
                                            allow_legacy=a.allow_legacy_present_counter)
    if g.v('sf3_map_cur') is None or counter is None:
        g.check(False, 'matching renderer and GPU display-flip symbols are required',
                {'needed': 'sf3_map_cur and g_flips; g_pres only with explicit legacy opt-in'})
        return g.finish('map_flicker')
    if not release_grade:
        g.note('legacy g_pres is a present-start counter, not GPU flip evidence; synchronization NOT CERTIFIED')
    rows=[]
    for map_id in range(11):
        if map_id:
            pressed=g.tap('R2',until=lambda: g.v('sf3_map_cur')==map_id,
                          wait=a.change_budget,what='renderer map change')
            if not g.check(pressed is not None and g.v('sf3_map_cur')==map_id,
                           'renderer map %d selected' % map_id,
                           {'emulator_frame':g.nrun,'renderer_map':g.v('sf3_map_cur')}):
                break
        g.run(a.warmup_frames)
        last=None
        previous_mean=None
        pending_big_up=False
        changed=unannounced=blacks=brightness_flips=0
        first_active=False
        unexpected_frames=[]
        start=g.nrun
        for i in range(a.frames_per_map):
            g.run(1)
            p=sample(g.image())
            if not p:
                continue
            digest,black,bright=p
            last, was_changed, unsynced = display_step(last, digest, g.v(counter))
            if was_changed:
                changed += 1
            if unsynced:
                unannounced += 1
                if len(unexpected_frames)<12:
                    unexpected_frames.append(g.nrun)
            if black and first_active:
                blacks += 1
            else:
                first_active=first_active or not black
            if previous_mean is not None:
                jump=bright - previous_mean
                if jump > 65:
                    pending_big_up=True
                elif jump < -65 and pending_big_up:
                    brightness_flips+=1
                    pending_big_up=False
            previous_mean=bright
        row=dict(map=map_id,emulator_start_frame=start,emulator_end_frame=g.nrun,
                 flip_counter=counter,release_grade_flip_evidence=release_grade,
                 picture_changes=changed,changes_without_flip=unannounced,
                 unexpected_frames=unexpected_frames,black_frames_after_visible=blacks,
                 extreme_brightness_flips=brightness_flips)
        rows.append(row)
        g.check(changed>0, 'renderer map %d pictures advance' % map_id,
                {'frames':g.nrun-start,'picture_changes':changed})
        if release_grade:
            g.check(unannounced==0, 'renderer map %d actual display flips synchronize' % map_id,
                    {'flip_symbol':counter,'count':unannounced,'emulator_frames':unexpected_frames})
        else:
            g.note('renderer map %d legacy present-start mismatch count %d: NOT a GPU defect verdict'
                   % (map_id, unannounced))
        g.check(blacks==0, 'renderer map %d has no black flashes' % map_id,
                {'black_frames':blacks})
        g.check(brightness_flips==0, 'renderer map %d has no obvious brightness oscillation' % map_id,
                {'oscillations':brightness_flips})
    g.check(len(rows)==11,'all 11 renderer-map scans completed',len(rows))
    return g.finish('map_flicker',extra={'rows':rows,'flip_counter':counter,
                                        'release_grade_flip_evidence':release_grade,
                                        'emulator_only':True,
                                        'not_a_clinical_flash_safety_certification':True})

if __name__=='__main__':
    sys.exit(main())
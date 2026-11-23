#!/usr/bin/env python3
"""Independently quantify PS1 pause-resume picture latency on a PRIVATE disc.

Usage with SwanStation (openboot setup from ps1/rig/README.md):
    python3 ps1/rig/tools/ob_session.py ps1/qa/pause_resume_latency.py \
        --disc /private/rc8.cue --syms /private/rc8/payback_rc8.nm.txt \
        --core swanstation --out /private/pause_results \
        --opt swanstation_CPU_Overclock=400 \
        --opt swanstation_CDROM_ReadSpeedup=10 \
        --opt swanstation_CDROM_SeekSpeedup=0

Clock restart, image change, renderer refresh and physical GPU display flip
are separate events. The script reports their frame numbers, not game text.
Press-to-first-new-city-picture is the main linger. A post-return sampling
window reports later freezes; the guest-clock delta is only diagnostic.
A strict maximum visible-linger limit is OPT-IN; no performance promise is
inferred from a compiling or bootable disc. Results and images stay private.
"""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RIG = str(HERE.parent / 'rig')
sys.path.insert(0, str(HERE))
sys.path.insert(0, RIG)
from payback import *  # noqa: F403
from pause_latency_metrics import ResumeEvidence


def picture_hash(im):
    return None if im is None else hashlib.blake2b(
        im.convert('RGB').tobytes(), digest_size=16).digest()


def extra(ap):
    ap.add_argument('--from-state', default=None,
                    help='private, same-disc/core state at a running level')
    ap.add_argument('--prepause-frames', type=int, default=120)
    ap.add_argument('--pause-dwell-frames', type=int, default=120)
    ap.add_argument('--observe-frames', type=int, default=900)
    ap.add_argument('--post-new-frame-observe-frames', type=int, default=120,
                    help='keep sampling after first changed city image to catch short stalls')
    ap.add_argument('--allow-legacy-present-counter', action='store_true',
                    help='rc7 diagnostic only: g_pres is not GPU flip evidence')
    ap.add_argument('--max-visible-linger-frames', type=int, default=None,
                    help='optional owner-agreed hard limit, from resume press to new city picture')


def main():
    a = std_args(__doc__, extra)  # noqa: F405
    if min(a.prepause_frames, a.pause_dwell_frames, a.observe_frames,
           a.post_new_frame_observe_frames) < 1:
        raise SystemExit('frame sampling windows must be positive')
    if a.max_visible_linger_frames is not None and a.max_visible_linger_frames < 0:
        raise SystemExit('linger budget must be nonnegative')
    g = open_game(a, 'pause_resume_latency')  # noqa: F405
    running = start_level(g, a)  # noqa: F405
    g.check(running, 'running level reached for pause-latency probe')
    if not running:
        return g.finish('pause_resume_latency')
    g.run(a.prepause_frames)
    c_before = g.level_clock()
    entered = g.tap('START', until=lambda: g.on('PAUSED'), wait=8000,
                    what='pause menu displayed')
    g.check(entered is not None, 'Start opens the native pause menu')
    if entered is None:
        return g.finish('pause_resume_latency')
    g.settle(2, 4000)
    chosen = g.menu_goto(PAUSE_RESUME, PAUSE_MENU)  # noqa: F405
    g.check(chosen is not None, 'pause resume entry selected')
    if chosen is None:
        return g.finish('pause_resume_latency')
    g.run(a.pause_dwell_frames)
    c_pause = g.level_clock()
    g.check(c_pause == c_before, 'guest clock remains stopped during pause',
            {'clock_before': c_before, 'clock_after': c_pause})
    image = picture_hash(g.image())
    flip_symbol = 'g_flips'
    flips = g.v(flip_symbol)
    if flips is None and a.allow_legacy_present_counter:
        flip_symbol = 'g_pres'
        flips = g.v(flip_symbol)
        g.note('rc7 legacy g_pres is NOT release-grade physical flip timing')
    if flips is None:
        g.check(False, 'rc8 g_flips required for accurate display latency; use legacy opt-in for rc7')
        return g.finish('pause_resume_latency')
    renders = g.v('st3_render')
    if renders is None:
        g.check(False, '3D renderer instrumentation required for latency probe')
        return g.finish('pause_resume_latency')
    origin = g.nrun
    tracker = ResumeEvidence(origin, image, c_pause, flips, renders)
    original_run = g.run

    def one_frame_observed(n=1, buttons=()):
        for _ in range(n):
            original_run(1, buttons)
            im = g.image()
            tracker.sample(g.nrun, g.level_clock(), picture_hash(im),
                           g.v(flip_symbol), g.v('st3_render'),
                           view_state(im) == 'city')  # noqa: F405

    g.run = one_frame_observed
    try:
        # Observe every emulated frame, including inside a prolonged pad hold.
        # The timer condition avoids false 'menu closed' readings when PAUSED
        # temporarily disappears from the draw-ring between guest frames.
        accepted = g.tap('CROSS', until=lambda: g.level_clock() > c_pause,
                         wait=10000, what='resume guest level clock')
        # Do not stop at the first new image: rc8 may show another short
        # freeze a few frames later. observe_frames remains a hard safety cap.
        while (g.nrun - origin < a.observe_frames
               and (tracker.events['first_new_picture'] is None
                    or g.nrun - tracker.events['first_new_picture']
                       < a.post_new_frame_observe_frames)):
            g.run(1, ())
    finally:
        g.run = original_run
    observed = tracker.summary()
    g.check(accepted is not None and observed['clock_restarted'] is not None,
            'resume press restarts the level clock',
            {'frames_until_clock': None if observed['clock_restarted'] is None
             else observed['clock_restarted'] - origin})
    g.check(observed['first_new_picture'] is not None,
            'a newly changed city image appears after the resume press')
    post_complete = (observed['first_new_picture'] is not None
                     and observed['post_new_frame_observed_frames']
                         >= a.post_new_frame_observe_frames)
    g.check(post_complete, 'post-return observation window completed',
            {'requested_frames': a.post_new_frame_observe_frames,
             'observed_frames': observed['post_new_frame_observed_frames'],
             'max_still_frames': observed['post_new_frame_max_static_frames']})
    g.check(observed['first_gpu_flip'] is not None,
            'display counter advances after resuming', {'counter': flip_symbol})
    g.check(observed['first_3d_render'] is not None,
            'renderer presents a new frame after resume')
    g.check(observed['first_playable_picture'] is not None,
            '3D scene returns after restart, render and display flip')
    lag = observed['visible_linger_after_resume_press_frames']
    if a.max_visible_linger_frames is not None:
        g.check(lag is not None and lag <= a.max_visible_linger_frames,
                'press-to-new-city-picture within optional frame budget',
                {'budget': a.max_visible_linger_frames, 'observed': lag})
    g.check(not g.tty_faults(), 'no runtime fault lines during pause/resume',
            {'count': len(g.tty_faults())})
    return g.finish('pause_resume_latency', extra={
        'timing': observed, 'core': a.core,
        'hardware_display_flip_counter_available': flip_symbol == 'g_flips',
        'display_counter_used': flip_symbol,
        'emulator_only': True,
        'owner_approved_press_to_picture_budget': a.max_visible_linger_frames,
        'post_new_picture_observation_complete': post_complete,
        'duckstation_android_verified': False,
    })


if __name__ == '__main__':
    sys.exit(main())
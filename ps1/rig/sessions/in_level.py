#!/usr/bin/env python3
"""Session c: in the level - idle, walk, turn, weapons, fire, pause/resume, vehicle (enter, drive, leave), death/respawn.

  python3 sessions/in_level.py --disc DISC.cue --out runs/c [--syms payback.elf] [--from-state states/level_start.state]
                               [--idle-ticks 300] [--approach-frames 24000] [--no-teleport] [--no-death]
                               [--steps idle,walk,turn,weapons,fire,pause,death,vehicle]

The level clock counts 30 per second of game time.  Every step holds its buttons until the effect shows in guest RAM (RC v2
polls the pad only once per presented frame, rc4 more often), with a frame budget; the budget and the frames used are printed.
Pause/resume checks the menu text, the clock standing and running on, the 3D view and the HUD (score corner) coming back,
with the frames each took after the resume entry was chosen.
Two steps use a rig intervention when the natural way is out of reach, and say so: the player is moved next to the nearest
vehicle (RAM poke) when walking there would take too long, and death is provoked by writing health 0.
The walk to the vehicle steers in a straight line (no path finding): a wall on the way stops it (RC v2 with
--no-teleport: stuck at 115712,42700, 26700 units short)."""
import os, sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--from-state', default=None)
    ap.add_argument('--idle-ticks', type=int, default=300, help='idle time in level clock ticks (300 = 10 s of game time)')
    ap.add_argument('--idle-max-frames', type=int, default=80000)
    ap.add_argument('--approach-frames', type=int, default=24000, help='budget for turning and walking towards the nearest vehicle')
    ap.add_argument('--no-teleport', action='store_true')
    ap.add_argument('--no-death', action='store_true')
    ap.add_argument('--steps', default='idle,walk,turn,weapons,fire,pause,death,vehicle')


def dist(a, b):
    return ((a['x'] - b['x']) ** 2 + (a['y'] - b['y']) ** 2) ** 0.5


def poll_wait(g, n=1, buttons=(), cap=6000):
    """Hold the buttons until the runtime polled the pad n more times (without symbols: 1800 frames per poll)."""
    p0 = g.polls()
    if p0 is None:
        g.run(1800 * n, buttons)
        return 1800 * n
    return g.wait_until(lambda: g.polls() >= p0 + n, cap * n, buttons, step=4)


def hud_white(im):
    """Fraction of near-white pixels in the top right corner of the picture, where the level HUD has its score digits
    (with the HUD about 0.10 to 0.14, without it 0.0 on both builds)."""
    if im is None:
        return 0.0
    w, h = im.size
    d = im.convert('RGB').crop((int(w * 0.66), 0, w, int(h * 0.13))).tobytes()
    n = len(d) // 3
    return sum(1 for i in range(0, 3 * n, 3) if d[i] > 200 and d[i + 1] > 200 and d[i + 2] > 200) / float(max(1, n))


def walk_to(g, target, budget, near=1100, log=True):
    """Steer the man on foot towards a point by entity positions: turn on the spot when the bearing is off by more than 20
    degrees, else walk.  One decision per pad poll.  Returns the final distance."""
    t0 = g.nrun
    while g.nrun - t0 < budget:
        me = g.player()
        d = dist(me, target)
        if d < near:
            break
        want = heading_to(target['x'] - me['x'], target['y'] - me['y'])
        off = wrap(want - me['heading'])
        if abs(off) > 320:
            b = ['LEFT'] if off > 0 else ['RIGHT']
            poll_wait(g, 1, b)
            poll_wait(g, 1, [])            # the turn runs for one poll interval, then look again
        else:
            b = ['CROSS'] + ([] if abs(off) < 120 else (['LEFT'] if off > 0 else ['RIGHT']))
            poll_wait(g, 1, b)
        if log:
            me = g.player()
            key = (me['x'] // 256, me['y'] // 256, me['heading'] // 64, tuple(b))
            if key != getattr(g, '_steer_key', None):
                g._steer_key = key
                g.log('  f%d steer %s: pos %d,%d heading %d want %d dist %.0f' % (g.nrun, '+'.join(b), me['x'], me['y'], me['heading'], want, dist(me, target)))
    poll_wait(g, 1, [])
    return dist(g.player(), target)


def main():
    a = std_args(__doc__, extra)
    g = open_game(a, 'in_level')
    steps = [x.strip() for x in a.steps.split(',')]
    ok = start_level(g, a)
    g.check(ok, 'level is running', g.level_report() if ok else g.text()[:100])
    if not ok:
        g.snap('no level')
        return g.finish('in_level')
    if 'st3_render' in g.sym:
        g.wait_until(lambda: g.v('st3_render') >= 2, 9000, step=4)
    sc = Scan(g)
    sc.run(2400, until=lambda: view_state(g.image()) == 'city')
    g.snap('level')
    info = {}

    # ---- idle
    if 'idle' in steps:
        g.log('-- idle for %d clock ticks (%.1f s of game time), budget %d frames' % (a.idle_ticks, a.idle_ticks / 30, a.idle_max_frames))
        s = Scan(g)
        f0, c0, p0 = g.nrun, g.level_clock(), g.player()
        target = c0 + a.idle_ticks
        half = False
        still = still_max = 0
        last = c0
        while g.nrun - f0 < a.idle_max_frames and g.level_clock() < target:
            s.run(600)
            if g.level_clock() == last:
                still += 600
                still_max = max(still_max, still)
            else:
                still, last = 0, g.level_clock()
            if not half and g.level_clock() >= c0 + a.idle_ticks // 2:
                half = True
                g.snap('idle half way')
        p1 = g.player()
        g.snap('idle end')
        used, ticks = g.nrun - f0, g.level_clock() - c0
        info['idle'] = {'frames': used, 'ticks': ticks, 'ticks_per_60': 60.0 * ticks / max(1, used), 'longest_no_city': s.bad_max, 'states': s.states}
        g.check(still_max <= 3000, 'idle: the level clock never stands still', 'longest stretch without a tick %d frames (%.0f s console time)' % (still_max, still_max / g.fps))
        g.check(ticks >= a.idle_ticks, 'idle (speed): %.0f s of game time pass within %d emulator frames' % (a.idle_ticks / 30, a.idle_max_frames),
                '%d ticks (%.1f s game time) in %d emulator frames (%.0f s console time): %.3f ticks per 60 frames, nominal 30' % (ticks, ticks / 30, used, used / g.fps, 60.0 * ticks / max(1, used)))
        g.check(dist(p0, p1) < 64 and p1['health'] == p0['health'], 'idle: the man stands still and unhurt', 'moved %.0f units, health %d > %d' % (dist(p0, p1), p0['health'], p1['health']))
        g.check(s.bad_max <= 60, 'idle: 3D city stays on screen', 'longest stretch without it %d frames (ending at frame %s); picture states sampled: %s' % (s.bad_max, s.bad_at, s.states))

    # ---- walk
    if 'walk' in steps:
        g.log('-- walk: hold Cross')
        p0, f0, c0 = g.player(), g.nrun, g.level_clock()
        w = g.wait_until(lambda: dist(g.player(), p0) >= 1000, 12000, ['CROSS'], step=4)
        p1 = g.player()
        poll_wait(g, 1, [])
        g.snap('after walking')
        dx, dy = p1['x'] - p0['x'], p1['y'] - p0['y']
        info['walk'] = {'frames': g.nrun - f0, 'ticks': g.level_clock() - c0, 'dx': dx, 'dy': dy, 'heading': p0['heading']}
        g.check(w is not None, 'walk: Cross moves the man', 'moved %d,%d in %d frames / %d ticks at heading %d (direction walked: heading %d)' % (dx, dy, g.nrun - f0, g.level_clock() - c0, p0['heading'], heading_to(dx, dy) if (dx or dy) else -1))
        if w is not None:
            g.check(abs(wrap(heading_to(dx, dy) - p0['heading'])) < 480, 'walk: he walks the way he faces', 'heading %d, walked towards %d' % (p0['heading'], heading_to(dx, dy)))

    # ---- turn
    if 'turn' in steps:
        g.log('-- turn: hold Left, then Right')
        h0, f0 = g.player()['heading'], g.nrun
        w = g.wait_until(lambda: abs(wrap(g.player()['heading'] - h0)) >= 300, 9000, ['LEFT'], step=4)
        poll_wait(g, 1, [])
        h1 = g.player()['heading']
        g.snap('after Left')
        g.check(w is not None and wrap(h1 - h0) > 0, 'turn: Left turns (heading rises)', 'heading %d > %d in %d frames' % (h0, h1, g.nrun - f0))
        f1 = g.nrun
        w = g.wait_until(lambda: wrap(g.player()['heading'] - h1) <= -300, 9000, ['RIGHT'], step=4)
        poll_wait(g, 1, [])
        h2 = g.player()['heading']
        g.snap('after Right')
        g.check(w is not None and wrap(h2 - h1) < 0, 'turn: Right turns back (heading falls)', 'heading %d > %d in %d frames' % (h1, h2, g.nrun - f1))
        info['turn'] = {'h0': h0, 'h1': h1, 'h2': h2}

    # ---- weapons
    if 'weapons' in steps:
        g.log('-- weapons: Up, then Down')
        for b in ('UP', 'DOWN'):
            im0 = g.image()
            w, h = im0.size
            icon0 = im0.crop((0, 0, w // 5, h // 6))
            f0, cw = g.nrun, g.level_clock()
            g.tap(b)
            s = Scan(g)
            s.run(1200)
            s.run(12000, until=lambda: view_state(g.image()) == 'city' and s.bad == 0)
            if s.bad_max > 60:
                s.evidence('%s: 3D view gone' % b)
            im1 = g.snap('after %s' % b)
            icon1 = im1.crop((0, 0, w // 5, h // 6))
            g.note('weapon %s: icon corner difference %.1f (0 = same picture); the man carries only his fists in a fresh rampage, so a change of weapon cannot be seen here' % (b, diff(icon0, icon1)))
            g.check(s.bad_max <= 60, 'weapons: 3D city stays on screen after %s' % b, 'no city for %d frames in a row (%.0f s console time, %d level clock ticks = %.2f s game time), pictures sampled %s; renderer lines of the TTY since the press: %s' % (
                s.bad_max, s.bad_max / g.fps, g.level_clock() - cw, (g.level_clock() - cw) / 30.0, s.states, g.renderer_events(since=f0) or 'none'))
            if s.bad_max > 60:
                g.check(view_state(g.image()) == 'city', 'weapons: 3D city comes back after %s' % b, '%d frames (%.0f s console time) after the press; view now %s, sf3_ok %s' % (
                    g.nrun - f0, (g.nrun - f0) / g.fps, view_state(g.image()), g.v('sf3_ok')))
            info['weapon_' + b] = {'no_city_frames': s.bad_max, 'frames': g.nrun - f0, 'ticks': g.level_clock() - cw}

    # ---- fire
    if 'fire' in steps:
        g.log('-- fire: hold R1')
        p0, n0 = g.player(), g.nentity()
        seen = set()
        f0 = g.nrun
        def look():
            seen.add(g.player()['k'])
            return len(seen) > 1
        w = g.wait_until(look, 8000, ['R1'], step=4)
        g.snap('R1 held')
        poll_wait(g, 2, [])
        g.check(w is not None, 'fire: R1 changes the man\'s animation (he strikes)', 'animation descriptors seen %s within %d frames' % (sorted(seen), g.nrun - f0))

    # ---- pause
    if 'pause' in steps:
        g.log('-- pause: Start, wait, resume entry')
        c_before, f_start = g.level_clock(), g.nrun
        hud0 = hud_white(g.image())
        first = []                  # text of the frame in which PAUSED appeared

        def paused():
            t = g.text()
            if 'paused' in t.lower():
                first.append(t)
                return True
            return False
        w = g.tap('START', until=paused, wait=6000, what='pause menu')
        g.settle(2)
        g.snap('paused')
        t_now = g.text()
        # rc4 draws the menu text in few 2D frames (see tools/pause_probe.py): text() of a frame 8 guest frames old is '',
        # so the entries are also taken from the frame in which PAUSED appeared
        t_chk = t_now if contains(t_now, PAUSE_RESUME) or not first else first[0]
        g.check(w is not None and contains(t_chk, PAUSE_RESUME) and contains(t_chk, PAUSE_QUIT), 'pause: Start opens the pause menu',
                t_chk[:90] + ('' if t_chk is t_now else ' (text of the frame in which PAUSED appeared; text read after settling: %r)' % t_now[:40]))
        if w is not None:
            c0 = g.level_clock()
            g.run(1800)
            c1 = g.level_clock()
            g.check(c1 == c0, 'pause: level clock stands still', 'clock %d before Start, %d in the menu, %d after 1800 frames more' % (c_before, c0, c1))
            sel = g.menu_goto(PAUSE_RESUME, PAUSE_MENU)
            g.check(sel is not None, 'pause: cursor on the resume entry', 'taps needed: %s' % sel)
            f0, c_x = g.nrun, g.level_clock()
            w = g.tap('CROSS', until=lambda: not g.on('PAUSED'), wait=6000, what='pause menu to close')
            g.check(w is not None, 'pause: the resume entry closes the menu', '%s frames' % w)
            w2 = g.wait_clock(3, 9000)
            g.check(w2 is not None, 'pause: level clock continues', 'clock %d, %s frames after the menu closed' % (g.level_clock(), w2))
            s = Scan(g)
            hud_at = []             # first sample with the HUD back: RC v2 brings the HUD back before the 3D view

            def city_back():
                im = g.image()
                if hud0 >= 0.02 and not hud_at and hud_white(im) >= 0.5 * hud0:
                    hud_at.append((g.nrun, g.level_clock(), im))
                return view_state(im) == 'city'
            s.run(14000, until=city_back)
            if s.bad_max > 60:
                s.evidence('after resuming: still no 3D view')
            g.snap('resumed')
            back = g.nrun - f0
            g.check(view_state(g.image()) == 'city', 'pause: 3D city comes back', '%d frames (%.0f s console time) after Cross; before that: %s; renderer lines of the TTY since Start: %s' % (back, back / g.fps, s.states, g.renderer_events(since=f_start) or 'none'))
            info['pause'] = {'frames_until_city': back}
            # the HUD (white score digits in the top right corner) as before Start: the pause menu hides it, and rc4 leaves
            # the menu on the picture for a while after resuming (tools/pause_probe.py). Sampled every 120 frames
            # while waiting for the 3D view, then every 60 frames.
            if hud0 < 0.02:
                g.note('pause: no HUD in the score corner before Start (white pixels %.3f): HUD check skipped' % hud0)
            else:
                hw = 0 if hud_at else g.wait_until(lambda: hud_white(g.image()) >= 0.5 * hud0, 15000, step=60)
                f_hud, c_hud, im_hud = hud_at[0] if hud_at else (g.nrun, g.level_clock(), g.image())
                hb = f_hud - f0
                g.snap('HUD back' if hw is not None else 'HUD still missing', im=im_hud, frame=f_hud)
                g.check(hw is not None, 'pause: HUD back after resuming',
                        ('HUD back by %d frames (%.0f s console time) after Cross, %s the 3D view (%d frames); level clock +%d since Cross' % (
                            hb, hb / g.fps, 'before' if hb < back else 'with' if hb == back else 'after', back, c_hud - c_x)) if hw is not None else
                        ('score corner still without the HUD %d frames (%.0f s console time) after Cross: white pixels %.3f, before Start %.3f; level clock %d' % (
                            hb, hb / g.fps, hud_white(g.image()), hud0, g.level_clock())))
                info['pause']['frames_until_hud'] = hb if hw is not None else None

    # ---- death and respawn (provoked)
    if 'death' in steps and not a.no_death:
        g.log('-- death: health written to 0 (rig intervention), then hands off')
        me = g.player()
        lives0, c0, f0 = g.lives(), g.level_clock(), g.nrun
        g.write(me['ptr'] + 0x68, struct.pack('<h', 0))
        g.note('RIG INTERVENTION: health of the controlled entity written to 0 at frame %d (a natural death was not waited for: about 1 %% game speed)' % g.nrun)
        seen = {'resp': 0}
        def dying():
            seen['resp'] = max(seen['resp'], g.respawn())
            return g.lives() < lives0 or g.level_end() != 0
        w = g.wait_until(dying, 70000, step=20)
        g.snap('after health 0')
        g.check(w is not None, 'death: health 0 costs a life or ends the level', 'lives %d > %d, level_end %d, respawn counter peaked at %d, %s frames, %d ticks' % (lives0, g.lives(), g.level_end(), seen['resp'], w, g.level_clock() - c0))
        if w is not None and g.level_end() == 0:
            f1 = g.nrun
            def back():
                q = g.player()
                return g.respawn() == 0 and q is not None and q['health'] > 0 and q['state'] == 2 and q['x'] > 2048 and q['y'] > 2048
            w2 = g.wait_until(back, 60000, step=20)
            g.wait_presented(2, 6000)
            s = Scan(g)
            s.run(9000, until=lambda: view_state(g.image()) == 'city')
            g.snap('respawned')
            p = g.player()
            g.check(w2 is not None and p['health'] > 0, 'death: the man is back with health', 'health %d, state %d, at %d,%d (before: %d,%d), %s frames after losing the life, view %s, lives %d' % (
                p['health'], p['state'], p['x'], p['y'], me['x'], me['y'], w2, view_state(g.image()), g.lives()))
            c1 = g.level_clock()
            g.check(g.wait_clock(3, 6000) is not None, 'death: the level clock runs on after the respawn', 'clock %d > %d' % (c1, g.level_clock()))
            info['death'] = {'frames_to_life_lost': w, 'frames_to_respawn': g.nrun - f1}
    # ---- vehicle
    if 'vehicle' in steps:
        g.log('-- vehicle: walk to the nearest one, L1, drive, L1')
        import math
        me = g.player()
        def vehicles():
            me = g.player()
            return [e for e in g.entities() if e['kind'] == 'vehicle' and e['i'] != me['i'] and e['x'] > 2048 and e['y'] > 2048]
        v0 = {e['i']: e for e in vehicles()}
        g.run(900)                                    # a few clock ticks: parked vehicles stay where they are
        vs = []
        for e in vehicles():
            moved = dist(e, v0[e['i']]) if e['i'] in v0 else 1e9
            e['parked'] = moved < 16
            vs.append(e)
        me = g.player()
        # a ground vehicle first: the drive checks below (Cross accelerates, Left/Right steer, Square reverses) are those of a car or
        # tank; the helicopter (kind 17) flies with other controls, on the GBA as here (rc8 issue #14), and was picked on Beetle
        vs.sort(key=lambda e: (e['k'] == 17, not e['parked'], dist(e, me)))
        for e in vs[:6]:
            g.log('  vehicle #%d k%d at %d,%d heading %d state %d %s: %.0f units (%.1f cells) away' % (e['i'], e['k'], e['x'], e['y'], e['heading'], e['state'], 'parked' if e['parked'] else 'moving', dist(e, me), dist(e, me) / 2048))
        if not vs:
            g.check(False, 'vehicle: a vehicle exists in the entity table', 'none')
        else:
            v = vs[0]
            g.note('vehicle chosen: #%d (k%d, %s), %.0f units = %.1f cells away; %d vehicles in the entity table, %d of them parked' % (
                v['i'], v['k'], 'parked' if v['parked'] else 'moving', dist(v, me), dist(v, me) / 2048, len(vs), sum(1 for e in vs if e['parked'])))
            d0 = dist(me, v)
            want0 = heading_to(v['x'] - me['x'], v['y'] - me['y'])
            off0 = abs(wrap(want0 - me['heading']))
            p0, c_ap = g.polls(), g.level_clock()
            d1 = walk_to(g, v, a.approach_frames)
            me1 = g.player()
            off1 = abs(wrap(heading_to(v['x'] - me1['x'], v['y'] - me1['y']) - me1['heading']))
            np_ = None if p0 is None else g.polls() - p0
            g.snap('walking to the vehicle')
            g.check(off1 <= 320 or off1 < off0 - 200, 'vehicle: steering by entity positions turns the man towards the vehicle', 'bearing error %d > %d (5760 = a full turn) in %d frames, %s pad polls of the runtime' % (off0, off1, a.approach_frames, np_))
            if off1 > 320 and d1 >= d0 - 300:
                # the man turns on the spot until he faces the vehicle: at about 1 % game speed the frame budget can end first
                g.note('vehicle: the approach budget (%d frames = %d level clock ticks = %.1f s of game time, %s pad polls) ended while the man was '
                       'still turning towards the vehicle (bearing error %d > %d): no walking step yet, so "closer" is not checked' % (
                           a.approach_frames, g.level_clock() - c_ap, (g.level_clock() - c_ap) / 30.0, np_, off0, off1))
            else:
                g.check(d1 < d0 - 300 or d1 < 1500, 'vehicle: steering by entity positions brings the man closer', 'distance %.0f > %.0f units in %d frames (%s pad polls: one steering decision per poll)' % (d0, d1, a.approach_frames, np_))
            w = None
            tries = []
            for attempt, (side, off) in enumerate(((1440, 900), (-1440, 900), (1440, 600), (0, 1400))):
                v = g.entity(v['i'])
                me = g.player()
                d1 = dist(me, v)
                if d1 >= 1100 and not a.no_teleport:
                    ang = (v['heading'] + side) % 5760 / 5760.0 * 2 * math.pi       # beside the vehicle (or behind it)
                    nx, ny = int(v['x'] + off * math.sin(ang)), int(v['y'] + off * math.cos(ang))
                    g.write(me['ptr'] + 4, struct.pack('<ii', nx, ny))
                    g.note('RIG INTERVENTION: the man was moved by a RAM poke from %d,%d to %d,%d, %d units from vehicle #%d at %d,%d (walking the remaining %.0f units would take about %.0f s of console time at this speed)' % (
                        me['x'], me['y'], nx, ny, off, v['i'], v['x'], v['y'], d1, d1 / 50.0 / 0.3 * 1.0))
                    poll_wait(g, 2, [])
                    g.wait_presented(2, 6000)
                    s = Scan(g)
                    s.run(8000, until=lambda: view_state(g.image()) == 'city')
                    g.snap('moved next to the vehicle')
                    sp = g.speed(1800)
                    okp = sp.get('clock_per_60', 0) > 0.08 and (g.v('sf3_ok') in (None, 1))
                    g.check(okp, 'vehicle: the level runs on at the new place before L1', 'per 60 frames: clock %.3f, guest frames %.3f, 3D frames %.3f; sf3_ok %s; view %s' % (
                        sp.get('clock_per_60', 0), sp.get('gframes_per_60', 0) or 0, sp.get('frames3d_per_60', 0) or 0, g.v('sf3_ok'), view_state(g.image())))
                v = g.entity(v['i'])
                d1 = dist(g.player(), v)
                g.log('  attempt %d: %.0f units from the vehicle (at %d,%d), pressing L1' % (attempt + 1, d1, v['x'], v['y']))
                w = g.tap('L1', until=lambda: g.player() is not None and g.player()['kind'] == 'vehicle', wait=20000, what='the man to sit in the vehicle')
                tries.append('%.0f units: %s' % (d1, 'in after %d frames' % w if w is not None else 'not in'))
                if w is not None or a.no_teleport:
                    break
            g.snap('after L1')
            me = g.player()
            g.check(w is not None, 'vehicle: L1 gets the man into the vehicle', 'controlled entity %d is a %s (k%d); attempts: %s' % (g.controlled(), me['kind'], me['k'], '; '.join(tries)))
            f_in = g.nrun - (w or 0) - 200
            if w is not None:
                sv = Scan(g)
                sv.run(3000)
                if sv.bad_max > 60:
                    sv.evidence('in the vehicle: 3D view gone')
                g.snap('in the vehicle, 3000 frames on')
                g.check(sv.bad_max <= 600, 'vehicle: 3D city on screen after getting in', 'longest stretch without it %d of 3000 frames; pictures sampled %s; sf3_ok %s; renderer lines of the TTY since L1: %s' % (
                    sv.bad_max, sv.states, g.v('sf3_ok'), g.renderer_events(since=f_in) or 'none'))
                s = Scan(g)
                p0, f0, gf0, c0 = g.player(), g.nrun, g.gframes(), g.level_clock()
                w = g.wait_until(lambda: dist(g.player(), p0) >= 3000, 9000, ['CROSS'], step=4)
                p1 = g.player()
                g.snap('driving: Cross')
                g.check(w is not None, 'vehicle: Cross accelerates', 'moved %.0f units in %d frames' % (dist(p0, p1), g.nrun - f0))
                gfd = None if gf0 is None else g.gframes() - gf0
                running = g.level_clock() - c0 >= 10
                tty = g.renderer_events(since=f_in)
                g.check(running, 'vehicle: the game keeps its level speed after getting in',
                        'in %d frames with Cross held: %s guest frames, %d clock ticks, %s 3D renderer flag sf3_ok, CPU at %s; TTY: %s' % (
                            g.nrun - f0, gfd, g.level_clock() - c0, g.v('sf3_ok'), g.cpu_where(8, 11), tty))
                if w is None and not running:
                    g._held = ('CROSS',)
                    sp = g.speed(6000)
                    g._held = ()
                    g.snap('in the vehicle, Cross held, 15000 frames on')
                    g.note('in the vehicle, Cross held, per 60 frames over 6000 more frames: %s' % {k: (round(v, 3) if isinstance(v, float) else v) for k, v in sp.items()})
                    info['vehicle_speed'] = sp
                    bts = []
                    for _ in range(6):
                        g.run(37, ['CROSS'])
                        bt = g.backtrace(8)
                        if bt and bt not in bts:
                            bts.append(bt)
                    g.note('call chains sampled in the stand-still (pc, ra, return addresses found on the stack): %s' % [' < '.join(b) for b in bts[:4]])
                    g.note('ROM pages in the cache now: %s; interpreter: %s' % (['%07x' % x if x is not None else '-' for x in (g.rom_cache() or [])],
                                                                             [l.strip() for l in g.tty().splitlines() if l.startswith('INTERP')][-6:]))
                    info['vehicle_backtraces'] = bts
                    g.note('driving checks (Left/Right, Square, L1 out) not done: the game stands nearly still since the man sat down in the vehicle')
                    faults = g.tty_faults()
                    g.check(not faults, 'no fault text on the TTY', faults[:3])
                    info['vehicle'] = {'entered': True, 'stalled': True}
                    return g.finish('in_level', extra=info, sheet_cols=5)
                h0 = p1['heading']
                w = g.wait_until(lambda: abs(wrap(g.player()['heading'] - h0)) >= 200, 9000, ['CROSS', 'LEFT'], step=4)
                h1 = g.player()['heading']
                g.snap('driving: Left')
                g.check(w is not None and wrap(h1 - h0) > 0, 'vehicle: Left steers (heading rises)', 'heading %d > %d' % (h0, h1))
                w = g.wait_until(lambda: wrap(g.player()['heading'] - h1) <= -200, 9000, ['CROSS', 'RIGHT'], step=4)
                h2 = g.player()['heading']
                g.snap('driving: Right')
                g.check(w is not None and wrap(h2 - h1) < 0, 'vehicle: Right steers (heading falls)', 'heading %d > %d' % (h1, h2))
                # Square: brake, then reverse - the vehicle ends up moving against its heading
                import math
                def along():
                    q = g.player()
                    return q, math.sin(q['heading'] / 5760.0 * 2 * math.pi), math.cos(q['heading'] / 5760.0 * 2 * math.pi)
                rev = {'seen': False}
                last = {'p': g.player()}
                def reversing():
                    q, sx, cy = along()
                    d = (q['x'] - last['p']['x']) * sx + (q['y'] - last['p']['y']) * cy
                    last['p'] = q
                    if d < -40:
                        rev['seen'] = True
                    return rev['seen']
                f0 = g.nrun
                w = g.wait_until(reversing, 14000, ['SQUARE'], step=120)
                g.snap('driving: Square')
                g.check(w is not None, 'vehicle: Square brakes and reverses', 'moving backwards %s frames after Square went down' % w)
                poll_wait(g, 2, [])
                w = g.tap('L1', until=lambda: g.player() is not None and g.player()['kind'] == 'person', wait=12000, what='the man to get out')
                g.snap('left the vehicle')
                g.check(w is not None, 'vehicle: L1 gets him out again', 'controlled entity %d is a %s, %s frames after L1' % (g.controlled(), g.player()['kind'], w))
                g.check(s.bad_max <= 600, 'vehicle: 3D city on screen while driving', 'longest stretch without it %d frames; states %s' % (max(s.bad_max, 0), s.states))

    faults = g.tty_faults()
    g.check(not faults, 'no fault text on the TTY', faults[:3])
    g.note('counters: %s' % {k: v for k, v in g.counters().items() if k in ('rom_miss_count', 'cold_loads', 'ip_enters', 'ip_undef', 'ip_stat_undef', 'pp_lost', 'pad_fails', 'cd_sectors', 'st3_render', 'g_gframes')})
    return g.finish('in_level', extra=info, sheet_cols=5)


if __name__ == '__main__':
    sys.exit(main())

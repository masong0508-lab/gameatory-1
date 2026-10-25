"""Par times. A mission's par is, in this order: a number written in calibration.json's "par" (a hand override), the bots'
measurement (calibration.json's "bots": 1.3 x the bot's time, and never under the least V6 allows, 1.2 x the route at top speed
plus 5 s: the bots carry the vehicle along the line, a person has to steer), the number written in the .sfm, or the distance
formula here (route length at 0.6 of the mode's top speed, and a fixed time for the things that are not distance: a landing,
getting in, a kill, a wave of foes).

calibration.json:  {"speed": {"foot": cells/s, "drive": .., "fly": ..}, "par": {}, "turn": {..},
                    "bots": {"m3.gr1": {"time": s, "finished": true, "kind": ..}}}
"""
import json
import math
import os

import misfmt as F

# cells a second at the mode's top speed (replaced by calibration.json's measured numbers)
DEFAULT_SPEED = {'foot': 3.0, 'drive': 9.0, 'fly': 11.0}
CRUISE = 0.6                                   # a player keeps this much of the top speed over a route
SLACK = 1.5
BOT_MARGIN = 1.3                               # a par over the bot's time
FOOT_PAR_MAX = 300                             # the longest limit a hunt on foot may have (seconds; the generators keep to it)
OVERHEAD = {F.OP_LAND: 4, F.OP_ENTER: 3, F.OP_DESTROY: 4, F.OP_CHASE: 15, F.OP_BLAST: 20, F.OP_FOES: 12, F.OP_BOSS: 60,
            F.OP_TALK: 3, F.OP_BRIEF: 3, F.OP_ESCORT: 10, F.OP_STUNT: 8, F.OP_JUMP: 6, F.OP_DELIVER: 4, F.OP_COLLECT: 1.5,
            F.OP_CRATES: 3, F.OP_SPACE: 2, F.OP_DOCK: 4}
MODE_NAME = {1: 'foot', 2: 'drive', 3: 'fly'}


def load(path):
    try:
        with open(path) as f:
            d = json.load(f)
    except FileNotFoundError:
        d = {}
    d.setdefault('speed', dict(DEFAULT_SPEED))
    for k, v in DEFAULT_SPEED.items():
        d['speed'].setdefault(k, v)
    d.setdefault('par', {})
    d.setdefault('bots', {})
    return d


def start_mode(m):
    f = m.flags
    if f & F.MS_FLY:
        return 'fly'
    if f & F.MS_DRIVE:
        return 'drive'
    if f & F.MS_FOOT:
        return 'foot'
    return None


def route(m, default='drive'):
    """[(mode, distance in cells, extra seconds)] for the mission's objectives, in order."""
    cur = start_mode(m) or default
    pos = m.start
    out = []
    for o in m.objs:
        if o.op == F.OP_ENTER and o.mode:
            cur = MODE_NAME[o.mode]
        mode = MODE_NAME.get(o.mode) or cur
        pts = []
        if o.op == F.OP_RACE and o.places:
            laps = max(1, o.b)
            pts = list(o.places) * laps
            if laps > 1:
                pts.append(o.places[0])
        elif o.op == F.OP_CHECK or o.op in (F.OP_RINGS, F.OP_COLLECT, F.OP_DELIVER, F.OP_DESTROY, F.OP_CRATES):
            pts = list(o.places)
            if o.op == F.OP_CRATES and o.drop is not None:
                pts = [q for p in o.places for q in (p, o.drop)]
        elif o.op in (F.OP_GOTO, F.OP_LAND, F.OP_CHASE, F.OP_FOES, F.OP_BOSS, F.OP_DEFEND):
            pts = list(o.places)
        elif o.op == F.OP_ESCORT:
            pts = list(o.places)
        d = 0.0
        for p in pts:
            if pos is not None:
                dx, dy, dh = p.x - pos.x, p.y - pos.y, (p.h - pos.h) / 1024.0
                d += math.sqrt(dx * dx + dy * dy + (dh * dh if mode == 'fly' else 0))
            pos = p
        extra = OVERHEAD.get(o.op, 0)
        if o.op in (F.OP_SURVIVE, F.OP_DEFEND):
            extra += o.b
        if o.op == F.OP_FOES:
            extra += (o.n or 1) * 4
        if o.op == F.OP_DESTROY:
            extra += len(o.places) * 4
        if o.op == F.OP_COLLECT:
            extra += len(o.places) * 1.5
        if o.op == F.OP_WAIT:
            extra += o.b / 30.0
        out.append((mode, d, extra))
    return out


def estimate(m, speed):
    """Seconds: the route at CRUISE of the top speed, plus the fixed times, times SLACK."""
    t = 0.0
    for mode, d, extra in route(m):
        t += d / (speed[mode] * CRUISE) + extra
    return t * SLACK


def top_time(m, speed):
    """The fastest the route could be flown at the top speed (the least a limit may be)."""
    return sum(d / speed[mode] for mode, d, extra in route(m))


def limit_floor(top):
    """The least a time limit may be (V6): the route flown at top speed, 1.2 x over, and 5 s."""
    return int(math.ceil(top * 1.2 + 5))


def bot_par(t, top):
    """A bot's time t on a route that takes top seconds at top speed -> the par: 1.3 x t, and not under the limit V6 asks."""
    return max(int(math.ceil(BOT_MARGIN * t)), limit_floor(top))


def final_par(m, cal):
    """(par seconds, where it came from)."""
    key = m.key
    if key in cal.get('par', {}):
        return int(cal['par'][key]), 'cal'
    b = cal.get('bots', {}).get(key)
    if b and b.get('time'):
        return bot_par(b['time'], top_time(m, cal['speed'])), 'bot'
    if m.par_src:
        return m.par_src, 'sfm'
    return max(10, int(round(estimate(m, cal['speed'])))), 'formula'

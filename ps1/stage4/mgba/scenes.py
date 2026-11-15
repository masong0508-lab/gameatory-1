"""Reach and drive the standard test scenes of Star-FlyBack (Payback mod) in the emulator, the same inputs on any build.

    from emu import Emu
    import scenes
    e = Emu(rom, elf)             # elf optional (it makes the mode and pause checks exact and gives the game-tick counter)
    scenes.boot_to_level(e)       # language/intro/title menus -> single player rampage, map 0 (Freedom City), on foot, clock running
    scenes.walk(e, 600)           # walk about for 600 frames (never stands still; the pad plan changes every 60 frames)
    scenes.pause(e)               # START: Payback's pause menu (returns True once the game clock has stopped)
    scenes.unpause(e)             # leave it
    scenes.arwing(e)              # call the Arwing (hold SELECT, release) and board it; returns True when flying

Addresses that are Payback's own are fixed in the ROM (stuntfox/src/pbapi.h); the mode and the game-tick counter come from the ELF.
"""
import numpy as np

PB_CLOCK, PB_MAP, PB_LIVES, PB_RAMPAGE = 0x02001e00, 0x02001d40, 0x02001e4e, 0x02001d39
FOOT, DRIVE, FLY = 0, 1, 2
S2F_MODE, S2F_PAUSED = 18, 20          # byte offsets in s2f (stage2.h: x y z speed i32, heading u16, then mode, docked, paused ...)


def title_visible(frame):
    """the orange STAR-FLYBACK logo of the title menu (a count of its pixels in the top band)"""
    r = frame[5:40, 20:220].astype(int)
    n = ((r[:, :, 0] > 200) & (r[:, :, 1] > 70) & (r[:, :, 1] < 200) & (r[:, :, 2] < 120)).sum()
    return n > 300


def clock(e):
    """Payback's level clock (about 30 a second while the game runs, 0 outside a level)"""
    return e.r32(PB_CLOCK)


def mode(e):
    """FOOT, DRIVE or FLY (needs the ELF: s2f.mode); None without it"""
    return e.r8(e.S['s2f'] + S2F_MODE) if 's2f' in e.S else None


def in_level(e, map=None):
    return clock(e) > 0 and e.r8(PB_RAMPAGE) == 1 and (map is None or e.r16(PB_MAP) == map)


def game_frames(e):
    """the count of Payback's game ticks (each reads the keys once): key_calls with the ELF, else None"""
    return e.r32(e.S['key_calls']) if 'key_calls' in e.S else None


def boot_to_level(e, tries=3):
    """From power-on: skip the logos, find the title menu, then Play game > slot > name > Single player rampage > Play game.
    Leaves the player on foot at the start of map 0's rampage with the clock running; raises if that does not happen."""
    e.run(300, [])
    for i in range(60):                       # intro: A skips a logo; look for the title between presses
        e.run(30, [])
        if title_visible(e.frame):
            break
        if i % 2:
            e.tap('A', 6, 0)
    else:
        raise RuntimeError('boot: the title menu never came up (pc %08x)' % e.pc)
    e.run(60, [])
    e.tap('A', 6, 80)                          # Play game -> select slot
    e.tap('A', 6, 60)                          # slot -> name
    e.tap('A', 6, 60)                          # name (OK) -> game menu
    e.tap('DOWN')
    e.tap('DOWN')                              # Single player rampage
    e.tap('A', 6, 60)                          # rampage setup (map 0, Freedom City, average)
    e.tap('A', 6, 600)                         # Play game: the level loads
    for _ in range(tries):
        if in_level(e, 0):
            break
        e.tap('A', 6, 120)                     # a card still up
    if not in_level(e, 0):
        raise RuntimeError('boot: the rampage did not start (clock %d map %d)' % (clock(e), e.r16(PB_MAP)))
    e.run(60, [])
    return e


# the pad plan of a walk (scenes.py of the old tests): forward, round the corners, a punch, back
WALK_PLAN = [['UP']] * 3 + [['UP', 'LEFT']] * 2 + [['UP']] * 3 + [['UP', 'RIGHT']] * 2 + [['A']] * 3 + [['DOWN']] * 2 + [['UP', 'LEFT']] * 2


def walk(e, frames, plan=None, step=60):
    """walk about on foot for `frames` frames, the pad changing every `step` frames; calls e.run so e.on_frame sees each frame"""
    plan = plan or WALK_PLAN
    n = 0
    i = 0
    while n < frames:
        k = min(step, frames - n)
        e.run(k, plan[i % len(plan)])
        n += k
        i += 1
    e.run(0, [])


def pause(e, frames=0):
    """START opens Payback's pause menu. True when the game clock has stopped (it then stays stopped); runs `frames` more frames paused."""
    c0 = clock(e)
    e.run(8, ['START'])
    e.run(30, [])
    c1 = clock(e)
    e.run(30, [])
    ok = clock(e) == c1 and c1 >= c0
    if frames:
        e.run(frames, [])
    return ok


def unpause(e):
    """leave the pause menu (START again); True when the clock runs"""
    e.run(8, ['START'])
    e.run(30, [])
    c = clock(e)
    e.run(30, [])
    return clock(e) > c


def arwing(e, wait=400):
    """Call the Arwing: hold SELECT for 45 frames, let go (the call goes out on release), wait for it to be flown (mode FLY).
    With the ELF the mode is checked; without it a fixed wait is used. Returns True when flying (always True without the ELF)."""
    e.run(45, ['SELECT'])
    e.run(0, [])
    if mode(e) is None:
        e.run(150, [])                       # (it takes 65 frames or so)
        return True
    for _ in range(wait // 10):
        if mode(e) == FLY:
            break
        e.run(10, [])
    else:
        return False
    e.run(30, [])
    return True

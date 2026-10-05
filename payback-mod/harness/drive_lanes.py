#!/usr/bin/env python3
"""Drive a car through each stunt park lane in a modded ROM and report airtime.

    python3 payback-mod/harness/drive_lanes.py payback-stunt.gba [--shots out_dir]

Needs the mGBA libretro core built with mgba-harness.patch (see README).
Boots the ROM, starts Rampage in Freedom City, takes the parked tank, swaps it
for a car, then drives each lane from its start point holding A.
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from retro import Emu  # noqa: E402
from paybackmod import stuntpark  # noqa: E402

PLAYER_POS = (0x2008df8, 0x2009398, 0x2009478, 0x2009484)  # copies of the player's x, y
TANK = 0x2009934          # parked tank entity in Freedom City (x +4, y +8, z +0xc, heading +0x12)
CAR_DESC = 0x08354c5c     # descriptor of a regular car; writing it to entity+0x1c swaps the model
GROUND_Z = 19904

BOOT = ([(300, None), (4, 'A'), (200, None), (4, 'START'), (200, None), (4, 'START'), (160, None),
         (4, 'A'), (120, None), (4, 'A'), (120, None)] + [(4, 'DOWN'), (12, None)] * 6 +
        [(4, 'A'), (150, None)] * 3 +                                    # name entry -> game menu
        [(4, 'DOWN'), (20, None), (4, 'DOWN'), (20, None), (4, 'A'), (200, None),   # single player rampage
         (4, 'A'), (600, None)] + [(4, 'A'), (60, None)] * 3)           # play, dismiss messages

LANES = [('A: kicker, whoops, tabletop', stuntpark.LANE_A_START, 760, 79.0),
         ('B: deck climb and drop', stuntpark.LANE_B_START, 720, 46.0)]


def boot_into_car(rom):
    e = Emu('gba', rom)
    for n, b in BOOT:
        e.run(n, [b] if b else [])
    x, y = e.r32(TANK + 4), e.r32(TANK + 8)
    for attempt in range(8):            # L walks to the nearest door; passing traffic can steal it
        for dx, dy in ((1200, 0), (-1200, 0), (0, 1200), (0, -1200))[attempt % 4:attempt % 4 + 1]:
            for a in PLAYER_POS:
                e.write32(a, x + dx)
                e.write32(a + 4, y + dy)
        e.run(3)
        e.run(8, ['L'])
        e.run(240)
        if struct.unpack('<h', e.read(0x2001db0, 2))[0] >= 0:
            break
    else:
        raise SystemExit('could not get into the tank')
    e.write32(TANK + 0x1c, CAR_DESC)
    e.run(60, ['LEFT', 'A'])
    return e


def drive(e, start, frames):
    sx, sy, ang = start
    for _ in range(6):
        e.write32(TANK + 4, int(sx * 2048))
        e.write32(TANK + 8, int(sy * 2048))
        e.write8(TANK + 0x12, ang & 0xff)
        e.write8(TANK + 0x13, ang >> 8)
        e.run(10)
    log, shots = [], []
    for f in range(frames):
        e.run(1, ['A'])
        log.append((e.r32(TANK + 4) / 2048, e.r32(TANK + 8) / 2048, (GROUND_Z - (e.r32(TANK + 0xc) & 0xffff)) / 16))
        if f % 60 == 0:
            shots.append(e.frame.copy())
    return log, shots


def airtime(log):
    """Longest stretch (in cells) where the car's height dropped faster than any ramp allows."""
    best = cur = 0.0
    for (x0, _, h0), (x1, _, h1) in zip(log, log[1:]):
        falling = h1 < h0 - 1.5
        cur = cur + abs(x1 - x0) if falling else 0.0
        best = max(best, cur)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--shots', help='save a contact sheet per lane in this folder')
    a = ap.parse_args()
    ok = True
    for name, start, frames, goal in LANES:
        e = boot_into_car(a.rom)
        log, shots = drive(e, start, frames)
        xs = [p[0] for p in log]
        reached = max(xs) >= goal if start[2] < 2880 else min(xs) <= goal
        print(f'Lane {name}: peak height {max(p[2] for p in log):.0f}, '
              f'longest fall {airtime(log):.1f} cells, end x {xs[-1]:.1f} -> {"ok" if reached else "STUCK"}')
        ok &= reached
        if a.shots:
            from PIL import Image
            os.makedirs(a.shots, exist_ok=True)
            sheet = Image.new('RGB', (240 * 4, 160 * ((len(shots) + 3) // 4)))
            for i, im in enumerate(shots):
                sheet.paste(im, (240 * (i % 4), 160 * (i // 4)))
            sheet.save(os.path.join(a.shots, f'lane_{name[0]}.png'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()

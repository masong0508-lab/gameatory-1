# Stunt Fox

Two ways to play it, both built from your own Payback ROM:

- **Stunt Fox x Payback** (`--merge`): Payback itself, with Stunt Fox inside it. Payback keeps
  running Payback's city (traffic, people, police, missions, the phone, the minimap, sound) while
  Stunt Fox draws the city with its faster renderer, drives your car with its stunt physics and
  brings the Arwing whenever you hold SELECT. Each of Payback's vehicles gets its own model
  (saloons, sports cars, vans, pickups, the limo, buses, police cars with flashing lights, the
  tank), and people walk. Buildings have rows of windows and shop fronts, roads have centre
  lines and zebra crossings (from Payback's own lane data), and the parks have trees.
- **Stunt Fox** on its own: the stunt arena, the city and space without Payback's game.

## Stunt Fox x Payback

    python3 build.py "Payback (Europe) (En,Fr,De,Es,It).gba" --merge -o stuntfox-payback.gba --bps stuntfox-payback.bps

The build patches a copy of the ROM; the `.bps` patch applies to the untouched Payback ROM.

| Button | Does |
| --- | --- |
| Hold SELECT | The Arwing lands next to you and you take off (in a car you get out first) |
| Tap SELECT | Payback's phone, as before |
| L | Payback's get in / get out of a car |
| A / B / R | In a car: gas, brake, boost |
| Hold SELECT, landed on a street | Get out of the Arwing; it stays parked there |

How it fits: `src/merge.c` (the glue), `src/merge.ld` (which of Payback's memory it borrows),
`src/keyhook.s`, and `build_merge()` in `build.py`, which redirects Payback's calls to its world
renderer, keypad reader and palette fade.

## Stunt Fox on its own

A GBA game with its own flat-shaded 3D engine: drive a Blue Falcon style car around a stunt
arena with a real loop, hop into the Arwing parked beside you, fly over Payback's city and keep
climbing into space to land on the station.

Everything here is new code. The only thing taken from Payback is the city's layout
(streets, kerbs, plazas and building footprints and heights), and it is read from **your own
Payback ROM at build time**. No ROM data is stored in this repository.

### Build

Needs Python 3, clang and ld.lld (no devkitARM).

    python3 build.py "Payback (Europe) (En,Fr,De,Es,It).gba" -o stuntfox.gba

### Controls

Car

| Button | Does |
| --- | --- |
| A | Accelerate |
| B | Brake, then reverse |
| Left / Right | Steer (in the air: spin) |
| Up / Down | In the air: pitch for flips |
| R | Boost jet (refills when you let go) |
| L | Handbrake drift (in the air: roll) |
| SELECT | Get in the Arwing (called to you if it's far away) |
| START | Back to the start line |

Arwing (Star Fox style: Up dives, Down climbs)

| Button | Does |
| --- | --- |
| A | Full thrust; on the ground hold it and the Arwing takes off by itself |
| B | Air brake / wheel brake |
| Up / Down | Nose down / nose up |
| Left / Right | Bank and turn (on the ground: steer) |
| L / R | Rudder; double tap for a barrel roll |
| SELECT | Back in the car (in the air the car drops out of the Arwing) |

Hold SELECT + START to see the frame rate.

## What is where

- `src/render.c`, `src/fill.s`: the polygon renderer (mode 4, ARM code in IWRAM).
- `src/citydraw.c`, `src/world.c`: the city, built by `tools/mkworld.py` from the ROM.
- `src/physics.c`, `src/car.c`, `src/ship.c`: rigid-body physics. Springs, tyres and impacts
  act where they happen, so the car pitches, rolls, flips and falls off the loop when it is
  too slow. Nothing is scripted.
- `src/space.c`, `src/models.c`: sky by altitude, stars, the station and asteroids.
- `tools/sim/`: runs the physics on a PC for testing (`tools/sim/run.sh loop 200`).

# Stunt Fox

A GBA game with its own flat-shaded 3D engine: drive a Blue Falcon style car around a stunt
arena with a real loop, hop into the Arwing parked beside you, fly over Freedom City and keep
climbing into space to land on the station.

Everything here is new code. The only thing taken from Payback is Freedom City's layout
(streets, kerbs, plazas and building footprints and heights), and it is read from **your own
Payback ROM at build time**. No ROM data is stored in this repository.

## Build

Needs Python 3, clang and ld.lld (no devkitARM).

    python3 build.py "Payback (Europe) (En,Fr,De,Es,It).gba" -o stuntfox.gba

## Controls

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

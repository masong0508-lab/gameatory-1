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
The car radio also plays our remixes of Payback's songs 1, 2 and 4 (a 32 MiB ROM): they are
rendered from your ROM by `tools/music` at build time, which needs numpy and scipy and takes a
few minutes the first time (cached in `build/radio`). `--no-remixes` builds without them, as
does a machine without numpy or scipy; the radio then plays Payback's own songs.

On foot it is Payback, with these added:

| Button | Does |
| --- | --- |
| Hold SELECT | Calls the Arwing: it flies in, sets down beside you and you climb in (in a car you get out first) |
| Tap SELECT | Payback's phone, as before; it also swings the camera back behind you |
| SELECT + D-pad | Left / Right turn the camera round you, Up / Down zoom in and out |
| SELECT + Up, held | Zoom in past the closest chase view and it becomes first person, on foot or in a car (your own body and car are not drawn; SELECT + Left / Right look round; SELECT + Down steps back) |
| Hold Up / Down | Walk on / back up (a quick tap still picks the next or previous weapon) |
| L | Payback's get in / get out of a car |
| START | Payback's pause menu |

Bailing out is always there: L in a car at speed, or SELECT held in the Arwing in the air, and the
man is thrown clear as a ragdoll of his own (his own jacket and trousers), tumbles, bounces and gets
up where he lands, on a street, a roof or a bridge deck; come down in the water and he floats to the
nearest bank and climbs out there (he is never left to drown).

People sent flying (by a car, a blast, a shot or a punch) going limp as ragdolls is a secret: on the
hangar's OPTIONS screen press L, L, R, R, L, R and the banner says RAGDOLLS UNLOCKED; they fly in
their own clothes, bounce off the street, roofs, ramps and walls, settle, and get up again where
they came to rest (Payback goes on as before underneath: who died, the score and the stars are
its). A car throws them up when it reaches them, over it if you keep going, ahead if you brake,
off to its side when it only clips them; a missile throws everyone near where it bursts, in the
street among them as on one of them. They are not there to begin with because a crowd of them in the air costs frames (one or two
bodies cost about half a frame a second). Once unlocked, the OPTIONS line RAGDOLLS turns them
ON / OFF; the code again makes them WACKY (further, spinning launches, lower gravity, near-superball
bounces), and again puts them back. With them on (or FALL DAMAGE on), a fall of a storey or more on
foot (off a roof, a ledge, a bridge) tumbles him as a ragdoll too; walking down a ramp, a stair or off a kerb never does.

FALL DAMAGE ON / OFF (off to begin with): on, the man's own tumble costs health when it lands after a
real fall (off a roof, a ledge, a bridge, or out of the Arwing high up), the harder the more; a fatal
one leaves him lying where he came down, an ordinary death with no banner (a life lost, and back
as after any other); a kerb, a car bail-out at street level and a landing in the water cost nothing. All of these are remembered with the other options.

In a car

| Button | Does |
| --- | --- |
| A / B | Gas / brake, then reverse |
| A + B, or B while steering (at speed) | Handbrake slide: the tail swings out and the nose turns about twice as fast, the speed mostly stays; let go and the grip comes back over a moment |
| Left / Right | Steer (in the air: spin) |
| Up / Down | In the air: pitch for flips |
| R | Boost (refills when you let go) |
| L | Get out: standing, Payback's; at speed you BAIL OUT, thrown clear as a ragdoll, tumble, bounce and get up unhurt while the empty car rolls on (and never into you) until it stops or crashes |
| SELECT + R | The radio's next song (press both at the same moment, whatever the D-pad is doing; one held first and then the other keeps its own job) |

Arwing (Up dives, Down climbs; the hangar's STICK line swaps them)

| Button | Does |
| --- | --- |
| A | Full thrust; on the ground hold it and the Arwing takes off and climbs out |
| B | Air brake / wheel brake |
| Up / Down | Nose down / nose up; let go and it levels out |
| Left / Right | Bank and turn (on the ground: steer) |
| R | Lasers |
| L | Missile (more at the shipyard) |
| Hold SELECT near Fox Station | Docking: the tractor beam takes you in |
| Hold SELECT, landed on a street | Get out; the Arwing stays parked there |
| Hold SELECT in the air | BAIL OUT: you jump, fall and bounce as a ragdoll wherever you land (street, roof, deck, water) and are on foot there; the empty Arwing noses down and crashes (no credits or shield lost), and holding SELECT calls the next one. Not in space |

In the hangar Up / Down choose, A takes a job or buys (a second A confirms a purchase), B goes
back. There is no barrel roll and no rudder here: L and R are the guns.

How it fits: `src/merge.c` (the glue), `src/merge.ld` (which of Payback's memory it borrows),
`src/keyhook.s`, and `build_merge()` in `build.py`, which redirects Payback's calls to its world
renderer, keypad reader and palette fade. The title is STAR-FLYBACK: `tools/mklogo.py` draws it at build
time (our own letters, burning in Payback's style) as the menu logo and as a title card that
`src/title.c` shows in place of Payback's intro films, which flash the screen white. Payback's
death and bonus banners (TOASTED!, SPLATTERED!, OBLITERATED!, BUSTED! and the rest) and its crime
report on the phone ("You are charged with ...") are left out: a death still costs a life and you
come back as before, and Game over!, Mission complete! and Level complete! stay.

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
- `src/stage2.h`, `src/s2core.c`, `src/pbapi.h` (stage 2, merge build only): the frame state and
  events the packages share, the hook dispatch (a weak stub for every package's entry point, so each
  builds and plays alone), the debug mailbox the tests read, and every Payback address stage 2 uses, named.
  `tools/s2build.py` is the build's one call into it; after linking, `tools/memguard.py`,
  `tools/pbapi_check.py` and `tools/lint_text.py` check the memory map, the addresses against the ROM,
  and that stage-2 code never prints through the ticker. `tools/mkconst.py` turns the tables the code used
  to build at start-up into ROM constants. `tests/s2/` has the hook demo, the override build, the check
  tests and the before/after gates (each file says how it runs).

## Speed

Payback's own game takes a quarter to a third of every frame, so what is left for the picture is
what the renderer does not spend on things nobody sees. A side of a building is drawn only above
the cells beside it (`side_cover` in `src/citydraw.c`: the part behind them is inside them), a
wall hidden by a nearer one is skipped column by column (`tex_occlude`), and the polygon buckets
in use are found from a bitmap, not by looking at all 1024 (`src/render.c`). What it spends: a
wall column is stepped straight between its two exact ends, and cut in 2, 4 or 8 pieces (each with
exact ends of its own) where one run would put the texture more than a pixel out, which is what a
tall wall close by, seen from above or below or with the camera rolled, does (`wall_split` in
`src/tex.c`; on a sample of frames the worst wall error goes from 2.7 to 1.0 pixels, the share of
wall pixels over a pixel out from 14% to under 1%). The ground of a banking Arwing is stepped in
40 pixel pieces, a pixel or two out at 15 degrees of bank, more over the bottom rows when low.

## Game settings

Title menu > Game options (it takes the place of "Set language"; build.py renames the line and
sends it to `sf_title_opts`, which runs the page in a small loop of its own), or Hangar (Fox Station) >
OPTIONS > GAME SETTINGS. Left and right change a line, A puts it back to its
default, B leaves. The list scrolls.

- Rampage and rules: target, time, difficulty, wanted stars, lives, damage taken, score multiplier.
- Car: top speed, acceleration, grip, handbrake slide, steering, gravity, boost power, endless boost.
- Arwing: speed, shield, endless missiles.
- Ragdolls: gravity, bounce. Chase camera: close to farthest.
- Performance: speed, draw distance, textures on/off, trees and lamps (none, fewer, normal), traffic, frame counter.
  Draw distance Near is the biggest saving where the view is open (Real Park on foot goes from
  about 14 to 30 frames a second), Textures off the next (2 to 4 frames in the heavy places); both
  together take the Big Track with the Arwing parked from 13 to 24.
  Speed (Normal, Fast, Fastest) is for the places that stay under 24 frames a second even then. Normal
  is the game as it was (the 3D picture is the same to the pixel). With Fast or Fastest the game times
  its own frames: while they come at 25 a second or less it gives up one step (two when far off) of a
  list of ten, and when they all come at 30 it takes one back, waiting longer each time it had to
  undo that (the step that gives the tiles back waits at least 48 looks of 8 frames, twice that after
  each undo, so the tiles do not come and go). A step is, all at once: fewer trees, people and cars drawn
  nearer in, fewer added, Payback's tiles on walls, roofs and the ground ending sooner, and the city's
  reach shorter (each building by its own distance, not its block's). Fast stops at the seventh step (the
  reach 80/256 of the usual, no trees, tiles only within 400 units on walls, 250 on the ground); Fastest
  goes on to the tenth (no tiles at all from the eighth, the reach 40/256 at the ninth: a few streets, and
  28/256 at the tenth, which only Real Park and the like ever reach). The page says so under the line.
  Measured on the 44 test scenes (11 maps, each on foot, walking, the Arwing parked, the Arwing climbing
  out; one run each, a scene moves by 2 frames a second between runs, the climbing ones by more): Normal
  12.4 to 30 (mean 21.9, 29 of 44 under 24), Fast 20.6 to 30 (mean 28.1; 40 of 44 at 24 or more, Real Park
  and the Arwing parked at Isla Nublar stay under), Fastest 26.8 to 30 (mean 29.3, all 44 at 24 or more).
  A parked Arwing is also let go still once nothing
  has touched it for a second (its physics stop until a key or a push).

They are kept in spare bits of the progress words (settings.c); the extra ones live in a word of
their own at 0x0203ff90 (just under the progress copy), checked and put back the same way.

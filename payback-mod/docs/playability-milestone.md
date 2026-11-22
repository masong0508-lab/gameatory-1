# Stunt Fox playability milestone

This pass builds from the canonical repository source and exercises the private
ROM in mGBA 0.10.5. The earlier standalone source kit used a separately maintained
builder; it is not the reproducible source for this updated build. Use this
repository and the runtime metadata bundled here.

## What changed in play

- **Stadium retry:** SELECT+START while driving a road vehicle in free-roam
  Mute/Neo City stops the car at the stadium loop run-up. It resets the game's
  separate longitudinal speed as well as XYZ velocity, clears stunt state, and
  suppresses the ordinary pause action. It is disabled on foot, in story mode,
  and in the Arwing/space map.
- **Reliable Arwing return:** landing and leaving the helicopter returns the
  player to Neo City. The earlier code rejected the last valid entity index,
  which is exactly where the player appeared in the reproduced failure.
- **Clean level reloads:** quitting from space and starting story or free roam
  loads the correct city. The original engine preserves the scratch state and
  reuses the grid address, so a simple pointer cookie was insufficient.
- **Smoother loops:** entry preserves lateral position, exit reaches the same
  endpoint as the trajectory, brake input approaches zero, and a completed
  turn displays “Loop clear!” once. Build keys do not also steer/brake/throttle
  an active loop.
- **Safer construction:** map swaps remove the cursor, cursor restoration checks
  its saved index and map identity, and construction preserves the boundary
  and game-generated RAM columns.
- **Correct height writes:** Z is a signed 16-bit field. Stunt/cheat height edits
  now preserve the adjacent orientation field that the old 32-bit writes damaged.

The 800-cell stadium, existing street network, generated Neo blocks, space
arena, half gravity, faster cars, English renames and builder pieces remain.
Live construction is not saved across map changes or level reloads.

## Evidence and limits

The test reports identify the exact ROM with SHA-256. The full original ROM is
never part of CI or source artifacts.

### ROM-free checks

The 35-test suite includes map codec/BPS tests, source/runtime integrity checks,
and 11 tests executing the actual production runtime C against synthetic memory.
The C tests cover inclusive entity indices, bounded pointers, cursor ownership,
same-address map reloads, landed Arwing exits, neighboring-field preservation,
loop physics/input boundaries, retry restrictions and signed headings.

The builder's runtime metadata records the compiled code's length/hash and hashes
of C, assembly, linker input and build script. Compilation uses a snapshot and
rejects a source change during the build. Injection checks the exact original
keypad call before modifying it, validates all 85 build-column entries and three
map pointers, and preflights allocation limits.

### Actual mGBA checks

`harness/smoke_gameplay.py` cold-boots, enters a vehicle, stages repeatable stadium
lanes, records a full loop completion, exercises every builder action and cursor
cleanup, tests the map edge, and verifies an EWRAM checkpoint round trip.
Its inherited lane fixture substitutes a regular-car descriptor into a tank;
this synthetic setup is explicitly separate from natural-vehicle behavior.

`harness/test_retry.py` enters an existing road vehicle using L, without replacing
its descriptor, and checks stadium retry while stopped, moving, turning and
reversing. It then accelerates from the retry point through a complete loop.
Testing this real-vehicle path exposed the separate longitudinal-speed state
that XYZ velocity resets alone did not stop.

`harness/test_transitions.py` uses a parked stadium helicopter and real L/A/START
inputs for entry, takeoff, flight, pause/resume, landing and exit. It checks that
the player can move afterward and that story/free-roam reloads have the correct
flags and complete 16,384-cell ROM grid, excluding legitimate dynamic RAM columns.
The earlier supplied and canonical baselines each failed five of these 21 checks.

Setup teleports make scenarios repeatable. These are scripted integration tests,
not a full manual playthrough. Native game-save formats, physical hardware,
extended soak testing and completion of every story mission remain untested.

### Rendering-rate measurement

The gameplay smoke report measures 600 emulated video frames while driving the
same stadium lane. It records the core's actual refresh frequency, changed video
images, and mode-4 display-page flips. Page flips approximate the 3D scene's
update rate; changed output images can be more frequent because of sprites/UI.
Emulator host throughput is not game FPS, and one scene is not a whole-game
performance guarantee. Use the generated before/after reports for the exact
numbers associated with a build.

## Memory and map-state cost

The mod continues to use the existing 64-byte scratch range at
`0x0203ffc0..0x0203ffff`; state identity occupies previously unused bytes in that
range. The active grid remains the original engine's one 64 KiB pointer array.
The reload markers add two 60-byte ROM columns with identical boundary geometry,
not additional RAM grids. Checking a single protected corner pointer detects
reloads without scanning the city every frame.

## Reproduce

Build with the root README command and use the matching `editor.json` for the
emulator scripts. The independent artifact verifier applies the BPS patch with
a separate decoder and checks exact output equality, the GBA header, runtime
injection, all map pointers, marker geometry, the 800 stadium cells, preserved
road cells, the space perimeter and pad recognition.

The source ROM must have SHA-1
`08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7`. Every build report supplies the
resulting ROM and patch hashes; never mix a runtime metadata file from another
build with a ROM under test.

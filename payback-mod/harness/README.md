# Test harness

`retro.py` drives an mGBA libretro core without a window or audio device. A stock
core supports scripted buttons, screenshots, savestates, and reads/writes to
canonical GBA RAM through the memory map supplied by the core. The optional
`mgba-harness.patch` adds CPU memory watchpoints.

## Use a stock mGBA core

Install Pillow and an mGBA libretro core, then set `MGBA_CORE` to the absolute
shared-library path. Debian's `libretro-mgba` 0.10.5 package was used for the
runtime checks. A typical Debian/Ubuntu installation is:

```sh
sudo apt-get install libretro-mgba python3-pil
export MGBA_CORE=/usr/lib/x86_64-linux-gnu/libretro/mgba_libretro.so
python3 payback-mod/harness/drive_lanes.py /path/to/payback-stunt-fox.gba --shots /tmp/stunt-lanes
python3 payback-mod/harness/test_transitions.py /path/to/payback-stunt-fox.gba \
  --symbols payback-mod/paybackmod/editor.json --out /tmp/stunt-transitions
python3 payback-mod/harness/test_retry.py /path/to/payback-stunt-fox.gba \
  --out /tmp/stunt-retry
```

`test_transitions.py` cold-boots free roam, enters a parked Arwing with normal
button input, flies, pauses/resumes, lands, exits, walks, and reloads both story
and free roam through the game menus. It also checks cursor cleanup across the
map change and compares the complete grid against each ROM map. Supply
`editor.json` from the **same build as the ROM**. The output folder contains
screenshots and `report.json`; a failed check produces a nonzero exit status.
The setup places the player next to the existing stadium Arwing. Its checkpoint
round trip tests emulator savestates, not the game's native save format.

`test_retry.py` enters a real traffic vehicle with **L**, without modifying the
vehicle's model or motion state. It checks stadium retries while stopped,
moving forward, turning in both directions, reversing, and turning in reverse.
Each case must stay completely stopped for 120 emulated frames after retry. It
then holds **A** to complete the loop from the retry position. This is the test
to use for normal retry and vehicle-control behavior.

`drive_lanes.py` retains its older synthetic lane fixture: it replaces a parked
tank's model with a car and teleports it to controlled start points. It is useful
for repeatable terrain/airtime comparisons, but its mixed vehicle state is not
representative of normal stopped-car or steering behavior.

For an unprivileged environment, `apt-get download libretro-mgba` followed by
`dpkg-deb -x` into a local directory also works when its runtime dependencies
are already installed. Point `MGBA_CORE` to the extracted shared library. No
game ROM is part of the emulator or source toolkit.

```python
from retro import Emu

with Emu('gba', '/path/to/payback-stunt-fox.gba') as game:
    game.run(300)
    game.press('A')
    game.shot('/tmp/boot.png')
    checkpoint = game.save_state()
    grid = game.u32(0x03000d60)
    game.run(60, ['A'])
    game.load_state(checkpoint)
```

Only one emulator instance may be active per process because libretro cores
have global state. Use `close()` or the context manager before opening another.
Set `capture_video=False` to avoid image conversion when measuring execution
time; this does not change emulated hardware timing. Emulator throughput is
different from the game's rendered frame rate and should be reported separately.

Stock-core memory operations use the core's backing RAM. They accept canonical
addresses, reject unsupported mirrored ranges and ROM writes, and do not emulate
hardware-register write side effects. They are suitable for placing a vehicle,
reading world state, and asserting RAM changes. Use normal button input to test
player controls. `watch()` and `hits()` explicitly report that a patched core is
required when those exports are absent.

## Optional watchpoint core

From the repository root, build mGBA with the harness patch:

```sh
git clone https://github.com/mgba-emu/mgba /tmp/mgba
git -C /tmp/mgba apply "$PWD/payback-mod/harness/mgba-harness.patch"
cmake -S /tmp/mgba -B /tmp/mgba/build \
  -DBUILD_LIBRETRO=ON -DBUILD_QT=OFF -DBUILD_SDL=OFF
cmake --build /tmp/mgba/build --target mgba_libretro
export MGBA_CORE=/tmp/mgba/build/mgba_libretro.so
python3 payback-mod/harness/drive_lanes.py /path/to/payback-stunt-fox.gba
```

The patch targets a particular mGBA source layout; if upstream changes prevent
it from applying, the stock-core workflow remains available for gameplay tests.

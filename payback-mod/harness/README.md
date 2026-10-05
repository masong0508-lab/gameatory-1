# Test harness

Headless libretro frontend (`retro.py`) driving an mGBA libretro core patched with
`mgba-harness.patch` (memory read/write exports and a watchpoint log).

```
git clone https://github.com/mgba-emu/mgba && cd mgba && git apply ../mgba-harness.patch
mkdir build && cd build && cmake .. -DBUILD_LIBRETRO=ON -DBUILD_QT=OFF -DBUILD_SDL=OFF && make mgba_libretro
MGBA_CORE=$PWD/mgba_libretro.so python3 drive_lanes.py payback-stunt-fox.gba
```

# Read me first: a much faster PS1 emulator is available (added 2026-11-22)

pcsxr under Xvfb needs minutes of wall time to reach a level. The headless libretro rig in `ps1/rig/` is much faster
(cores and openboot: `ps1/rig/README.md`):

    cd ps1/rig
    python3 retro_ps1.py pcsx_rearmed <disc.cue|.bin|.chd> <outdir> <frames> --shots 600,1200 --keys "1200-1206:CROSS;1500-1506:CROSS" --opt pcsx_rearmed_bios=HLE

- 9000 video frames run in about 16 seconds (PCSX-ReARMed core, HLE BIOS, software GPU, 320x240 frames saved as PNG).
- Python API: `from retro_ps1 import Emu` (see the docstring): exact frame stepping, per-frame pad input, PS1 RAM peeks
  (e.r32(0x80xxxxxx)), save states, screenshots. One Emu per process. core.log in the out dir holds the core's log.
- Sessions: `sessions/boot_to_title.py` presses through the language and logo screens to the title menu,
  `sessions/new_game_to_level.py` goes on into a level; with `tools/ob_session.py` they run on SwanStation and Beetle
  with openboot (`ps1/rig/RIG.md`).
- Note: under this core the old "menu assist" did not press anything by itself; real pad input works.
- Prefer this rig over pcsxr for boot and gameplay checks; keep one final pcsxr boot only if you want a second opinion.
- Results are emulator-only: the port targets DuckStation on Android.
- The disc packer puts the licence text at LBA 4 since commit d0d0010 (`ps1/stage5/discpack/mkdisc2.py` and the
  prepared tree's `tools7/mkdisc2.py`).

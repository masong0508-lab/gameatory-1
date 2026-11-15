# Stage 12: PS1 "PPU-lite" for the plain Payback disc (code only)

Code only: no Payback code, assets, ROM or audio in this folder. EMULATOR-ONLY results (PCSXR HLE BIOS, unicorn MIPS/GPU model, mGBA for the reference frames). Disc and README with numbers: builds/ps1/"Payback PS1 (original game, release candidate v2)".

## Apply
Base: stage 10 tree (stage7/integration + stage8 + stage10 patches). Copy `ps1rt/ppu12.h` into the tree's `ps1rt/`, apply `patches/ps1rt_rt.c.patch` (diff against the stage 10 rt.c) and `patches/t_sim4.py.patch` (MMIO hooks for the sim). Build: `tools12/build.sh NAME "extra cflags"` (needs the ROM path in the ROM env var; same flags as stage 10: NPAGES=56 PRD=pr_lb WORLDPRD=pr_l ... -DSF3_DEFER -DPADDBG), then `tools7/mkdisc2.py --iso out/NAME.iso --out DIR/NAME --default-tracks`.

## What it contains
- `ps1rt/ppu12.h`: the PPU-lite. `ppu_flush` replays the draw ring (ids 0x20 DISPCNT, 1 fade_flip, 2 blit_image, 3 effect, 4 blit_image_m4, 6 clear page) into a VRAM/OAM/PAL shadow at GBA vcount 160; `pp_draw` uploads the mode 4 page + CLUT rows and draws the OBJ layer (affine, 4/8 bpp, 1D/2D, flips, semi-transparent, BG2 priority) with FT4 quads; `pp_draw(oy,1)` is the level path drawn over the sf3 frame.
- `patches/ps1rt_rt.c.patch`: hooks (DISPCNT write, ring flush in adv_lines, present composition), E3/E4/E5 packing fix, PRESENT_MENU, resident `bx rN` veneer copies (cold_find) so the renderer is not switched off by group loads, renderer re-init after an overlay load (pause menu).
- `tools12/`: test tools: `tour12.py` (state-aware PCSXR tour: screenshots tagged with the guest frame, pad Down/Up at the title, level, Start for pause; ffmpeg capture), `flash.py` (flash check), `cmpshot.py`/`cmp2.py`/`icmp.py` (pixel diffs vs mGBA frames), `gsim*.py` (unicorn MIPS + GPU model, state injection), `objmodel.py`/`pvm.py`/`pagerender.py` (independent OBJ/page model), ARM-sim probes (`arm*.py`) used to study gfx_fade_flip.

## Known gaps
Bloom/glow (run-time patched IWRAM routine inside gfx_fade_flip is not translated), menu 3D models (gfx_view3d), BLDY hardware fades, assumed BLDCNT/BLDALPHA constants, point sampling. See the disc README.

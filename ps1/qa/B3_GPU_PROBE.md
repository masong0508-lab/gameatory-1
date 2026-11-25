# Synthetic B3 GPU / GTE acceptance probe

This is not a gameplay or FPS test. It uses the production B3 packet
header and the current PS1 GTE/GPU definitions to draw a synthetic
quad and convex fan via linked-list DMA2, read back seven VRAM pixels,
and compare sixteen real GTE projections with the scaled GBA lens.

Run with the owner's private rc10 MODE2/2352 BIN/CUE and QA kit:
```sh
export RIG_CORES=/private/qa/cores
python3 ps1/qa/b3_gpu_probe.py --carrier /private/rc10/payback_rc10.cue \
  --core swanstation --sys /private/qa/system --out /private/gpu-swan
python3 ps1/qa/b3_gpu_probe.py --carrier /private/rc10/payback_rc10.cue \
  --core beetle --sys /private/qa/system --out /private/gpu-beetle
```

The carrier is copied into a new private directory, its boot executable
replaced with the synthetic test, and affected sector checks regenerated.
The source disc is untouched. **Never publish the carrier copy**, even
though the executed code is synthetic. Only the numeric report may be
shared. The script does not capture screenshots or run the original game.

Private stock-emulator tests of the exact B3 header and probe C source
(Clang 17) passed on SwanStation and Beetle: all seven VRAM samples
matched, no packet failures, and all sixteen GTE projections were within
one pixel of the reference. The first local synthetic probe had an
incorrect GPU drawing-area register encoding and failed Beetle's pixel
readback; after correcting the test's register encoding, both cores
passed. This was a fixture defect, not a gameplay finding.

The producer itself is still opt-in and not connected to B2 gameplay.
The integrated build must separately prove scene ownership, city/map
feature parity, memory layout, HUD composition, and frame pacing.

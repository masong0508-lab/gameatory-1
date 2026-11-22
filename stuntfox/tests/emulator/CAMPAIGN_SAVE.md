# Native campaign save acceptance

Run from `stuntfox/` after building a merged ROM and its matching ELF:

```sh
export MGBA_CORE=/absolute/path/to/mgba_libretro.so
python3 tests/emulator/campaign_save.py /absolute/path/to/merged.gba \
  --elf /absolute/path/to/merged.elf --out /absolute/path/to/new-results-directory
```

The harness uses the stock mGBA libretro core, Pillow, and `llvm-nm` or `nm`.
The output directory must be new or empty. Every stage has its own operating
system process and private native save file. Only libretro memory kind 0 is
persisted; emulator save/load-state methods are disabled. Reports identify the
ROM and ELF by SHA-256 and record each worker's process ID, inputs, setup,
screenshots, campaign image, native slot state and pass/fail checks.

## What the test establishes

The writer boots through the game's profile/story menus and boards the Arwing
with Select. It starts the campaign and uses Save Now through the hangar menu.
The game's initial 300 credits pay for the larger missile rack. Paint, both
flight controls, ragdoll options, radio selection and all 31 game-setting
sliders are changed through normal input. A new process must restore the exact
campaign image, live equipment and every option from the native EEPROM file.

A second writer buys a jet pack through the shop and saves a later campaign
fixture. Its independent cold reader must retain the jet pack, chapter unlock,
completed-act bits and EVA reward receipt bits. The campaign is then stopped
through its menu and continued in a new process; its purchases, options and
complete campaign image must return intact. Another worker changes a setting
and stops while the game is partway through writing its next EEPROM slot. A new
process must recover the previous complete save. The harness independently
checks each slot's header and CRC and the campaign image's own CRC.

Compatibility checks load a checksum-correct image using the old zero-spare
equipment representation, and start a campaign from an existing 512-byte
Payback profile. The game must preserve Payback's first 512 bytes while proving
and using the larger EEPROM. The migrated campaign is then cold-booted again.

## Setup and limits

The test makes a single documented ship-pose adjustment near Fox Station to
shorten travel. It does not force the docking state; the game's tractor beam
and docking sequence complete through input. Shop results and successful-save
flags are never forced, and the game performs every EEPROM write itself.

The advanced writer explicitly grants 900 credits, unlocks chapter index 3,
sets chapter-zero act bits to 3 through the existing debug mailbox, and seeds
the two EVA receipt bits at `Prog.spare[9]`. These are persistence fixtures,
not evidence that those missions were earned or completed. The jet-pack
purchase and EEPROM write still run through the actual game menus. Every setup
write appears in the worker report.

The old-format compatibility file is a separate fixture: it clears only the
16 optional equipment-extension bytes in valid slots and recalculates their
checksums. The original captured save remains untouched.

This acceptance covers the merged engine's 8 KiB campaign EEPROM. A physical
512-byte chip's password-only fallback is covered by the block-device models in
`tests/save/run.py`; mGBA's expandable EEPROM does not certify that hardware
behavior. These results also do not establish full campaign completion,
mid-level world resume or saved emulator execution state.

## Equipment/settings extension

`SgProgress` remains 32 bytes and `Prog` remains 260 bytes. The first sixteen
equipment bytes retain their existing layout. Its sixteen spare bytes now hold:

| Offset in `SgProgress.spare` | Meaning |
| --- | --- |
| 0–1 | ASCII `S`, extension version 1 |
| 2 | Jet pack, four ragdoll flags, and two radio-mode bits |
| 3 | Shield setting's three packed bits |
| 4–7 | Existing options word 2, little-endian |
| 8–11 | Existing options word 3, little-endian |
| 12–15 | Existing extra-options word, little-endian |

The campaign's existing CRC protects the extension. `opt_load` validates each
decoded option against its allowed range, and the extra-options RAM mirror is
rewritten from those validated choices. Old zero-spare images and unknown
extension versions load their original equipment fields and leave the current
extras alone. On a cold boot those extras are defaults. A password similarly
retains the player's current extras because passwords have no tagged extension.

The production codec also has a ROM-free regression gate:

```sh
python3 tests/save/progress.py
```

It compiles the actual equipment codec and settings packer with ASan/UBSan and
checks full round trips, old/unknown versions, invalid choices, field limits,
jet-pack/ragdoll/radio flags and the unchanged 32-byte image size.

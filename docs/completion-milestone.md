# Merged game completion milestone

This milestone adds playable completion to the larger **Star-FlyBack merged
GBA game**. It closes the empty ending path, exposes the existing space-walk
activities through normal station controls, and fixes campaign-save losses.
The earlier `payback-mod` stadium game and standalone build remain separate
targets. This is not a finished PlayStation port or a certification of every
campaign mission.

## What now works

### Campaign ending and postgame

Finishing the final act commits its normal reward and existing finale/Ace
progress, then returns a living pilot to the station. If the player is outside
the Arwing, the game asks them to return before beginning the ending. Pause,
death and an active space walk cannot trigger an unsafe transition.

The ending has three readable cards: campaign completion, Ace mode, and the
return home. **A** advances, **B** revisits a previous card, and holding A does
not skip the sequence. The last A enters Fox Station without activating a
second action underneath it. A build without station data falls back to the
hangar. The cards cover the underlying game HUD.

Payback's native bitmap banner and arrow draws occur after the custom frame
callback. Five verified call sites now forward through small wrappers that
give an active station room or ending card control of the screen. Their state
updates continue, and ordinary city, flight and menu drawing still forwards
the original arguments. The production-wrapper regression checks both paths.

Completed chapters stay available for postgame travel, contracts, medals and
the station's activities. A completed story city can be left immediately;
its normal debrief still takes A to continue. Loading completed progress does
not replay the ending or issue the final-act reward again.

### Station space walks

Start the campaign through **L** in the hangar. Buy the **JET PACK** for 900 CR
at the shipyard or the workshop's upgrades console. The workshop uses the
same second-A purchase confirmation as the other upgrades.

From the hangar's main menu, **B** enters the station. Press **L**, select
**SPACE WALKS**, and press **A**. The Nav holo map also opens this board with
**Right**; Left returns to the map. A valid assignment launches the Arwing.
The board explains a missing campaign or jet pack and preserves a current
mission, flight job or walk. Cancelling a walk requires a second A.

| Assignment | Completion condition | First clear | Replay |
| --- | --- | ---: | ---: |
| Beacon Patrol | Reach beacon A outside the Arwing | 150 CR | 50 CR |
| Moon Survey | Land beside the survey post on the moon | 300 CR | 75 CR |
| Orbital Relay | Reach B, then C, then board the Arwing | 500 CR | 100 CR |

Follow the highlighted marker in flight. Hold **SELECT** to bail out at space
altitude. The jet pack uses the D-pad to move/turn, **A** to rise, **B** to
descend and **L** to brake. Hold SELECT to recall the ship and board it.
Orbital Relay pays only after safe boarding, not after the second beacon.

The board marks first clears with a star and shows the current reward. Three
receipt bits use one previously spare campaign byte; the save layout does
not grow. Crew-dialogue records and other campaign fields are preserved.
Map changes, death or cancellation clear unfinished work without a reward.
The activities can then be accepted again from the station.

### Native campaign saves

The existing 32-byte equipment record had 16 unused bytes. A tagged extension
now stores the jet pack, ragdoll/radio choices, shield choice and the 31 game
settings in that space. The outer campaign format remains 260 bytes and the
native EEPROM remains 8 KiB. Older zero-spare records retain their established
behavior; unknown extension versions are ignored, and setting indices are
checked before use.

An additional cold-boot bug affected **Stop Campaign → Continue Campaign**.
The stopped image existed on EEPROM, but Continue could replace its inventory
with the new process's defaults. Explicitly continuing that stopped native
image now restores its stored equipment and options. Stopping and continuing
within one session still retains the player's live free-play purchases.

Use **L → SAVE NOW** in the hangar, or **SAVE...** in the station, and wait for
the saved status before closing. Use native emulator saves when checking
persistence. Passwords remain a smaller progress-transfer format; they do not
replace a complete native campaign save.

## Build and test

The private build uses the supplied untouched European Payback ROM and
`--no-remixes`, so it retains the original music. LLVM 19, NumPy and Pillow
are required. From the repository root:

```sh
python3 stuntfox/build.py ORIGINAL.gba --merge --no-remixes \
  -o merged.gba --bps merged.bps
python3 tools/check.py --report test-results.json
```

Set `MGBA_CORE` to a stock mGBA libretro core. Each emulator run must use the
ELF from the same ROM build and a new output directory:

```sh
python3 stuntfox/tests/emulator/smoke.py merged.gba \
  --elf stuntfox/build/merge/stuntfox-merge.elf --mode merge --out /tmp/sf-smoke
python3 stuntfox/tests/emulator/ending.py merged.gba \
  --elf stuntfox/build/merge/stuntfox-merge.elf --out /tmp/sf-ending
python3 stuntfox/tests/emulator/eva.py merged.gba \
  --elf stuntfox/build/merge/stuntfox-merge.elf --out /tmp/sf-eva
python3 stuntfox/tests/emulator/campaign_save.py merged.gba \
  --elf stuntfox/build/merge/stuntfox-merge.elf --out /tmp/sf-save
```

The ROM-free gate includes production-code checks for ending transitions,
postgame travel, stopped-campaign continuation, space-walk eligibility and
rewards, and the settings/equipment codec under ASan/UBSan. Existing save
interruption, VM/fuzz, radio, ARM linkage and PS1 allocation checks also run.

## Evidence and limits

The downloadable completion validation JSON records exact ROM/ELF/patch
hashes, the final source commit, CI status, full per-check results and setup
instrumentation. Its scope is deliberately explicit:

The completed integration run passed 9 ordinary merged-game checks, 20 ending
checks, 76 space-walk checks and 74 native campaign-save checks. The save matrix
used eleven fresh OS processes. A last font correction adds the previously
missing first-clear star: exhaustive ROM and ELF comparison proves every
changed byte is inside that glyph's existing 32-byte slot. All game code,
addresses, save data layouts and other assets are identical to the exercised
build. The delivered ROM separately cold-loads the earned space-walk save and
checks the visible stars through real station controls.

| Integration check | What is actually exercised | Fixture or limitation |
| --- | --- | --- |
| Basic merged smoke | Story boot, walking, Arwing entry/takeoff, pause, bail-out and recovery | Real buttons and read-only memory inspection |
| Ending | Real final mission event, normal payment, three cards, pause/back/held-A behavior, station movement and round-trip postgame travel | Earlier acts and final objective predicates are seeded; this is not an earned full campaign playthrough |
| Space walks | Workshop navigation/purchase, board controls, actual beacon movement and moon contact, recall/boarding, cancellation, replay pay and earned receipt reload | Docking/travel positions and a 600-credit purchase budget shorten setup; no assignment, contact, reward or boarding flags are forced |
| Campaign saves | Real menu purchases/settings/save operations, fresh-process reloads, partial-write recovery, legacy-format compatibility and stopped-campaign continuation | Docking is positioned; later unlocks and a jet-pack budget are documented fixtures; no savestates |

The GBA postlink guards remain enabled. The main renderer scratch allocation
uses 5,180 of 5,184 bytes, so future rendering changes still have only four
bytes of headroom there. No guard is relaxed for these gameplay additions.

All 66 campaign acts have not been played end to end. Optional remix audio,
Pizza Boy A, long-duration soak tests and physical hardware remain unverified.
The additional activities have been exercised with the travel fixtures above;
their natural flight routes have not all been timed as full player runs.

## PlayStation continuation

This work also distinguishes the simulator's deliberately extended memory
from a physical PS1 layout, and fixes interpreter-disabled diagnostic builds.
Physical memory guards remain strict. See [PS1 status](../ps1/STATUS.md) for
the private baseline's actual progress and remaining acceptance work.

The current PS1 runtime accepts an 8 MiB baseline. Porting this larger 16 MiB
merged game still requires the address-space expansion, merged guest coverage
and renderer/backend work described there. A passing GBA milestone does not
establish PS1 gameplay, memory-card, audio or real-BIOS acceptance.

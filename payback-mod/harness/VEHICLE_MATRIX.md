# Original GBA Payback: independent mGBA vehicle control matrix

This is the **original unchanged European 8 MiB cartridge** reference for deciding whether PS1 vehicle behavior is a port bug. Run this with a privately installed **mGBA libretro core**, not SwanStation, and with the owner's SHA-1 verified ROM. The script never modifies a vehicle's type, model, descriptor, movement parameters or game code. It repositions only the *player* beside an already spawned vehicle to make entry deterministic, then uses controller input.

```sh
export MGBA_CORE=/private/cores/mgba_libretro.so
python3 payback-mod/harness/vehicle_matrix.py \
  '/private/Payback (Europe) (En,Fr,De,Es,It).gba' \
  --out /private/gba-vehicle-matrix.json --survey-frames 6000 --require-all
```

The last flag deliberately returns **3** when any of the **18 descriptor indices, 0–17**, was not independently observed **and entered**, so one naturally spawned but inaccessible vehicle does not count as covered. It does not spawn missing models or misrepresent a vehicle-type absence as a control pass. Repeat over additional naturally selectable maps or captured routes until types are actually observed. To examine another map, supply `--from-state /private/other_map.state` with a **private mGBA savestate made from the SAME original ROM and emulator core**; the report records the observed guest map ID. Neither the savestate nor a dump of the map is ever uploaded. The initial survey starts a standard Rampage route and records naturally appearing entity descriptors (without serializing any private game data). Its report is **PRIVATE**, numeric and incomplete by default. It is not meant to certify missions, collisions, tank cannon, or all 11 maps.

Crucially, index **k17** resolves to original descriptor **0x08354EF0**, explicitly identified as the *helicopter*, not an ordinary road car. Its test plan includes **L entry, a separate L takeoff, A flight, B descent, L landing, and L exit after landing**. The existing modded-ROM `test_transitions.py` mGBA test uses exactly this general pattern. The control sequence is **source-derived**, and must still be empirically verified against the unchanged original ROM before claiming PS1 equivalence or closing issue #14. The original game's **z decreases when climbing**: L takeoff requires a meaningful negative z delta, B descent a positive delta, and L landing a return near the entry-ground z (not merely remaining in the helicopter). Ground-car tests use A forward, A+Left/Right and L exit. **B braking/reverse is recorded as numeric diagnostic evidence**, not a fabricated hard movement gate from a standstill. Position adjustments and artificial world conditions are marked in the report; this cannot substitute for natural walk-up play.

The script checks the original ROM SHA-1 (`08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7`) and requires `MGBA_CORE` before it starts an emulator. It uses `payback-mod/harness/retro.py` and the repository's tested boot sequence. It leaves screenshots/video disabled and never writes save data, CD content, dialogue or game graphics. If the core is unavailable, it **fails before play**; a type that naturally appears but cannot be entered is listed separately in **`not_entered`**, never mislabeled a confirmed control defect. Only failures *after verified entry* appear in `failed`; missing or unentered types are not release-certified.

ROM-free regression:

```sh
python3 -m unittest discover -s payback-mod/harness -p 'test_vehicle_matrix.py' -v
```

**Owner/Claude action for actual coverage:** provide/install a compatible mGBA libretro `.so` privately, then run this tool on the owner's untouched ROM. Share only the numeric per-type input/position/heading/height/exit results and core version; never attach the ROM, core, screenshots, saves or the private report file publicly. Compare k17 after takeoff and touchdown in GBA to the same actions on PS1 rc8, not to car-only Cross-on-ground checks.

Claude independently tested the original ROM in mGBA: on the map-0 seed route nine of eighteen vehicle descriptors appeared. The tank k11 passed, helicopter k17 took off, flew, descended, landed and exited; types absent or not entered remain **unverified**, not failed gameplay. The earlier version of this survey falsely failed the working helicopter because it interpreted upward motion as positive z. This revision corrects that test-tool error; it does not alter helicopter physics.

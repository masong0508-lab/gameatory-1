# Payback PS1 (original game, release candidate)

EMULATOR-ONLY results: everything below was run in PCSXR 1.9.94 (HLE substitute BIOS, interpreter CPU, GL plugin, headless). Not run in DuckStation, with a real BIOS, or on hardware.

Files: `Payback PS1 (original game, release candidate).cue` + `.bin` (same folder; open the .cue). 593 MiB, 58.8 min, MODE2/2352: data track 1 + 14 CD-DA tracks (2-15). Built from your own Payback (Europe) ROM; it contains data derived from it, for your own use only, never share or commit. Payback song 3 is not on it.

## What it is
The plain Payback ROM translated to PS1 code (no Stunt Fox / Star-FlyBack mod code, no Star-FlyBack menus or settings; disc label PAYBACK, save file BESLES-99902PAYBACK "PAYBACK SAVE"). Payback's own title, menus, rampage logic and missions run as Payback code. The city is drawn by our sf3 PS1 renderer (the 11 city maps come from the Star-FlyBack map dumps, they are not Payback data).

## The big gap: Payback's 2D layer is not drawn
Menus, text, hearts/score/minimap (Payback tile/OAM/bitmap drawing) have no PS1 back end in any stage so far (PPU-lite was never built). Payback's menu images are blitted by stubbed routines that only log. So in the menus the screen shows a debug view (boxes where images would go, a palette swatch grid, counters, and the line "MENU 2D LAYER NOT DRAWN"). The sf3 renderer draws the level with its own small HUD (ENG/OVF/LOD/MAP, SCORE, HP, CLK). Navigating menus by hand is blind; see the menu assist.

## Menu assist (how it gets from the title to a level)
The disc replays the stock game's menu path (title > Play game > slot > name > Single player rampage > rampage setup (city 1, Freedom City) > Play game), frame-timed from power-on, OR-ed with your real pad. Verified: the level starts at GBA frame 1103 (not a snapshot). After the level starts, only the real pad counts.
It assumes an EMPTY memory card (first run). With a card that already holds a Payback save the menu has a different shape and the timed path goes off: that is what stalled the earlier title-boot disc (card with an old save, still in menus after 1616 GBA frames, 120 s); it was never a speed problem. Use a blank card for a first run, or navigate by hand.

## Maps
Payback's own rampage setup offers 3 cities (strings in the ROM: 1. Freedom City, 2. Los Francos City, 3. Corona City; 2 and 3 are unlocked by progress or a keyword) and the rampage kinds. Arena is only in its MULTIPLAYER SETUP (link cable). There is no faithful in-menu path to 11 maps, so our switch stays: **L2 / R2 = previous / next of the 11 maps**, loaded from the CD (276-310 sectors each, a few seconds). The view moves to the new map's start point; the Payback logic keeps running Freedom City. The renderer only draws when Payback's own city is 1 (Freedom City); Los Francos/Corona run their logic but get no 3D view.

## Controls (PS1 pad)
D-pad/stick move, Cross = A, Circle/Square = B, Start/Select, L1/R1, L2/R2 map switch, R3 first person, Triangle in a car = bail out (ragdoll). Hold a key for 2+ presents in the emulator (a present is 2-8 s wall there).
Radio (hold Select, press): R1 next, L1 previous, Triangle stop/start, Square mode. Tracks per the stage 6 mapping: 2-12 the eleven tracker-module remix edits, 13-15 the three Payback remixes (songs 1, 2, 4). Modes: REMIXES 2-12, ALL 2-15, "ORIGINALS" 13-15 (the three Payback-song remixes).

## Measured (scripted state-aware tour, pad keys via xdotool; shipped disc, real timing, blank card)
| step | result |
|---|---|
| power-on > title > menus > level | OK, 332 s wall, level start at GBA frame 1103 |
| first renders | OK, 357 s |
| L2 > map 10, L2 > map 9, R2 > map 10, R2 > map 0 | all 4 OK (298, 276, 298, 310 CD sectors, 0 errors) |
| radio Select+R1 | CD-DA play command track 3 OK; Select+Triangle: stop OK |
| D-pad Up held, other keys | pad word seen by the runtime; no player motion visible (about 2 s of game time passed in the emulator) |
Same tour on a test build (faster VCOUNT mode, track files cut to 30 s): 10/10, 309-329 s. That fast mode did not matter: the real-timing disc reached frame 651 in 29.6 s vs 661 in 34.8 s, so the shipped disc keeps real timing and no fast mode is needed. Whole boot-to-level is about 5.5 minutes in PCSXR (about 0.5 s wall per GBA-frame group in menus, 2.5-8 s per presented frame in the level); real console speed unknown.
Interpreter fallback (stage 8) is in: 3 interpreter entries during the tour, 0 RT_MISS panics, 0 faults, 0 primitive overflows. Its stage 8 soak limits still apply (not re-soaked here).
Memory card: on a blank card the save file is created at boot (directory entry and checksums valid). Writing a real in-game save was not exercised (menus are invisible), and loading a save is the case that breaks the menu assist.
Flash check (5 fps capture of the slow emulator, scripts in stage7/release): 0 opposing mean-luminance swings above 10%; biggest mean-luminance step 0.23 (black to level at boot). The pessimistic metric (each distinct frame = 1/30 s) reads 6 events > 25% area in a 30-frame window (limit 3) because the tour makes 4 map cuts and the boot cut within seconds; each map change is one cut after a CD load, not a flicker, but that metric does fail.

## Other known limits
- DuckStation/real BIOS/hardware untested; HLE BIOS only. Slow: PS1 speed unknown.
- Cold translated code not in the disc's cold prefix is interpreted (slow, but no panic).
- Not in this build: Los Francos/Corona drawing, Payback's HUD/minimap, menu images, Payback's own SFX (CD-DA radio only), loops/first person pad R3 not re-verified here.

# Payback: Stunt Fox

A mod of Payback (GBA, Europe) that mixes in Race Drivin' / Stunt Race FX stunts and F-Zero / Star Fox flavour.
This repo holds only the build tooling. Bring your own ROM: `Payback (Europe) (En,Fr,De,Es,It).gba`
(SHA-1 `08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7`).

```
python3 payback-mod/build.py "Payback (Europe) (En,Fr,De,Es,It).gba" -o payback-stunt-fox.gba
python3 payback-mod/build.py "Payback (Europe) (En,Fr,De,Es,It).gba" --bps payback-stunt-fox.bps
```

What the build changes:
- Freedom City's stadium becomes a stunt park (kicker jump, 0x200 deck drop, whoops, tabletops).
- Jump ramps in traffic lanes across the city, each facing its lane's traffic.
- Half gravity for longer jumps (`--gravity normal|half|low`).
- Alien colour scheme (green and blue swapped in the 3D view).
- Expansion renames: menus, cities (Mute City, Big Blue, Corneria) and vehicles.
- In-game build mode: hold SELECT, then A = kicker ramp ahead, B = platform, R = raise, L = clear.

See `payback-mod/docs/payback-notes.md` for the reverse-engineering notes and
`payback-mod/harness/` for the headless emulator test harness.

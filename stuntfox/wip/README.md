Parked work (not built): Payback's own tiles in Stunt Fox's renderer.

- Tiles: 32 x 32, 8 bpp, ids below 0x318 at ROM 0x0ce0bc + id * 0x400; Payback's live table
  of tile pointers is at 0x02002c60 (some cached in VRAM / IWRAM). A cell's tile id is
  tex | (attr & 3) << 8 of its top record; side ids are the low 10 bits of the side words,
  sides ordered -y, +x, +y, -x. Tiles map unrotated: column along x, row along y.
- Palette: ROM 0x6367a8 with red and blue swapped is Payback's in-game palette.
- mkpal.py makes the colour tables; texrun.s has the 2 x 2 texel inner loops; tex.h the plan.

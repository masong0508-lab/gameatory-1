# Payback (Europe) reverse-engineering notes

All addresses are for SHA-1 08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7.

## Maps
- Level grid table: 11 pointers at ROM 0x1aa8b4 (level 0 = Freedom City, used by Rampage and story level 1).
- Grid: 128x128 cells, index `x*128+y`, 2048 world units per cell, bitstream format in `paybackmod/mapcodec.py`.
- Decoded into EWRAM at level load; RAM pointer to the grid is at 0x03000d60. Writing a column pointer there takes effect immediately.
- Columns: 60 bytes = three 20-byte block records (`paybackmod/blocks.py`). Original table at 0x081aa8e0, referenced only by literals at 0x3c674 and 0x3cf50; the build moves it to 0x08800000.
- Street lane flags (column byte 3): 1 = traffic drives -y, 4 = +y, 2 = +x, 8 = -x, 0x20 = kerb strip.

## Entities
- Pointer list 0x03000c60, count s16 at 0x0300000c, structs of 0x168 bytes from 0x020089c0.
- x +4, y +8, z +0xc (low 16 bits, ground 19904, z = 19904 - 16*(h-0x100)), heading +0x12 (5760 per turn, 0 = +y, 1440 = +x), descriptor +0x1c, state +0x10f (2 player on foot, 3 traffic, 4 parked).
- Player = 0x02009394; vehicle index s16 at 0x02001db0 (-1 on foot). Parked vehicle placements for Freedom City at ROM 0x309da8 (count, then x, y, type/heading words).

## Physics
- Vertical integrator around 0x08017500: gravity `lsls r3,r1,#3` at 0x175dc, gravity term `lsls r6,r2,#2` at 0x17576 and 0x175ec.
- Cars only leave the ground where it drops away; the slope a car can climb is at most 0x20 per cell.

## Text and colour
- Strings are u32 offsets from ROM 0x31ce20; English UI entries 0x30b2e4-0x30c7f8, English mission text 0x312560-0x3149dc.
- BG palette fade at 0x080777f0 rebuilds colours as c0 | c1<<5 | c2<<10 (three write paths at 0x80778ee, 0x8077932, 0x8077968).
- Keypad is read once per tick by 0x08072f68, called from the game loop at 0x0800e9a8.

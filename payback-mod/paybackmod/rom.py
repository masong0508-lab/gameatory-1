"""Edits to a Payback (Europe) ROM: map columns, level grids and physics tweaks."""
import hashlib
import struct

from .mapcodec import GBA, LEVEL_TABLE, COLUMN_BASE, decode, encode

# Payback (Europe) (En,Fr,De,Es,It).gba, 8 MiB
PAYBACK_EU_SHA1 = '08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7'

OLD_TABLE_START, OLD_TABLE_END = COLUMN_BASE - GBA, 0x2f6de8
NEW_BASE = 0x800000                  # column table moves here, above the original 8 MiB
BASE_LITERALS = (0x3c674, 0x3cf50)   # the only two references to the column table base
MAX_COLUMNS = 1 << 15                # grid literals are 15 bits
STRING_BASE = 0x31ce20               # string table entries are offsets from here
ENGLISH_TABLES = ((0x30b2e4, 0x30c7f8), (0x312560, 0x3149dc))


class PaybackRom:
    """A Payback ROM extended to 16 MiB with the column table relocated so new columns fit."""

    def __init__(self, data, check=True):
        if check and hashlib.sha1(data).hexdigest() != PAYBACK_EU_SHA1:
            raise ValueError('not Payback (Europe) (En,Fr,De,Es,It); expected SHA-1 ' + PAYBACK_EU_SHA1)
        assert len(data) == 0x800000
        self.orig = bytes(data)
        self.d = bytearray(data) + bytearray(0x800000)
        tbl = data[OLD_TABLE_START:OLD_TABLE_END]
        self.d[NEW_BASE:NEW_BASE + len(tbl)] = tbl
        self.ncols = len(tbl) // 60 + 1
        for lit in BASE_LITERALS:
            assert struct.unpack_from('<I', self.d, lit)[0] == COLUMN_BASE
            struct.pack_into('<I', self.d, lit, GBA + NEW_BASE)
        self.free = NEW_BASE + 60 * MAX_COLUMNS   # grid streams go after the addressable columns
        self.new_columns = {}
        self.painted = {}

    def column(self, idx):
        o = NEW_BASE + 60 * idx
        return bytes(self.d[o:o + 60])

    def add_column(self, data60):
        """Append a column (deduplicated) and return its number."""
        assert len(data60) == 60
        if data60 in self.new_columns:
            return self.new_columns[data60]
        assert self.ncols < MAX_COLUMNS
        o = NEW_BASE + 60 * self.ncols
        self.d[o:o + 60] = data60
        self.new_columns[data60] = self.ncols
        self.ncols += 1
        return self.ncols - 1

    def grid(self, level):
        """The level's grid as column numbers, indexed x * 128 + y."""
        g, _ = decode(self.orig, level)
        return [(p - COLUMN_BASE) // 60 for p in g]

    def set_grid(self, level, idx):
        bs = encode(idx)
        o = self.free
        self.d[o:o + len(bs)] = bs
        self.free += (len(bs) + 3) & ~3
        struct.pack_into('<I', self.d, LEVEL_TABLE + 4 * level, GBA + o)

    def paint(self, level, cells):
        """Replace cells of a level: cells maps (x, y) -> 60-byte column."""
        g = self.grid(level)
        for (x, y), col in cells.items():
            g[x * 128 + y] = self.add_column(col)
        self.set_grid(level, g)
        self.painted[level] = g

    # Vertical physics (routine around 0x08017500, run every logic tick):
    #   lsls r3, r1, #3   at 0x175dc  adds 8*t to the vertical speed (gravity)
    #   lsls r6, r2, #2   at 0x17576 and 0x175ec  is the 4*(t*t+t) gravity term in the height step
    GRAVITY = {'normal': (3, 2), 'half': (2, 1), 'low': (1, 0)}

    def set_gravity(self, mode):
        g, i = self.GRAVITY[mode]
        assert self.d[0x175dc:0x175de] == b'\xcb\x00'
        assert self.d[0x17576:0x17578] == self.d[0x175ec:0x175ee] == b'\x96\x00'
        struct.pack_into('<H', self.d, 0x175dc, 0x000b | (g << 6))
        for o in (0x17576, 0x175ec):
            struct.pack_into('<H', self.d, o, 0x0016 | (i << 6))

    # Text: every UI and mission string is reached through a table of u32 offsets from STRING_BASE.
    # Replacement strings go in free space and only the English entries are repointed.
    def alloc(self, data, align=4):
        self.free = (self.free + align - 1) & ~(align - 1)
        o = self.free
        self.d[o:o + len(data)] = data
        self.free += len(data)
        return o

    def english_strings(self):
        for a, b in ENGLISH_TABLES:
            for o in range(a, b, 4):
                v = struct.unpack_from('<I', self.d, o)[0]
                t = STRING_BASE + v
                if 0 < v < 0x800000 and t < len(self.d) and self.d[t - 1] == 0:
                    yield o, bytes(self.d[t:self.d.index(b'\0', t)])

    def retext(self, exact=None, replace=None):
        """exact: {old string: new string}; replace: [(old substring, new substring)]."""
        exact, replace = exact or {}, replace or []
        made = {}
        for o, s in list(self.english_strings()):
            t = s.decode('latin-1')
            new = exact.get(t, t)
            for a, b in replace:
                new = new.replace(a, b)
            if new != t:
                if new not in made:
                    made[new] = self.alloc(new.encode('latin-1') + b'\0', 1)
                struct.pack_into('<I', self.d, o, made[new] - STRING_BASE)
        return len(made)

    def retext_inplace(self, old, new):
        """Overwrite a string where it sits (shared by every language); new must not be longer."""
        o = self.d.find(old.encode('latin-1') + b'\0')
        assert o > 0 and len(new) <= len(old)
        self.d[o:o + len(old)] = new.encode('latin-1').ljust(len(old), b'\0')

    # Palette fade (0x080777f0) rebuilds each BG colour as c0 | c1 << 5 | c2 << 10.
    # Swapping the two shifts in its three BG write paths swaps green and blue for the
    # whole 3D view and the menu backdrops (sprites and the HUD keep their colours).
    BG_SHIFTS = (0x80778ee, 0x80778f2, 0x8077932, 0x8077936, 0x8077968, 0x807796c)

    def swap_bg_green_blue(self):
        for i, a in enumerate(self.BG_SHIFTS):
            o = a - GBA
            op = struct.unpack_from('<H', self.d, o)[0]
            want = 5 if i % 2 == 0 else 10
            assert op >> 11 == 0 and (op >> 6) & 31 == want, hex(a)
            struct.pack_into('<H', self.d, o, (op & ~(31 << 6)) | ((15 - want) << 6))

    # Build mode: a hook replaces the keypad-reader call in the game loop. The code goes in the
    # old column table area, which the relocation above freed and which is in BL range.
    HOOK_CALL = 0x0800e9a8
    BUILD_BASE = 0x081b0000

    def add_build_mode(self, code, syms, flats, ramps):
        """flats: 17 columns (0x100 + 0x20*i); ramps: 4 x 16 columns rising toward +y, +x, -y, -x."""
        o = self.BUILD_BASE - GBA
        self.d[o:o + len(code)] = code
        table = [self.col_ptr(self.add_column(c)) for c in list(flats) + [c for d in ramps for c in d]]
        struct.pack_into('<%dI' % len(table), self.d, syms['cols'] - GBA, *table)
        h1, h2 = struct.unpack_from('<HH', self.d, self.HOOK_CALL - GBA)
        assert h1 >> 11 == 0x1e and h2 >> 11 == 0x1f, 'expected a bl at the hook site'
        off = syms['hook'] - (self.HOOK_CALL + 4)
        struct.pack_into('<HH', self.d, self.HOOK_CALL - GBA,
                         0xf000 | ((off >> 12) & 0x7ff), 0xf800 | ((off >> 1) & 0x7ff))

    def col_ptr(self, idx):
        return GBA + NEW_BASE + 60 * idx

    def add_space(self, syms, space_cells, free_roam_cells):
        """Store full pointer grids (space, level 0, free-roam city); the hook swaps between them."""
        city = self.painted.get(0) or self.grid(0)
        space = [self.add_column(c) for c in space_cells]
        neo = [self.add_column(c) for c in free_roam_cells]
        ptrs = []
        for g in (space, city, neo):
            o = self.alloc(struct.pack('<16384I', *[self.col_ptr(i) for i in g]))
            ptrs.append(GBA + o)
        struct.pack_into('<3I', self.d, syms['maps'] - GBA, *ptrs)

    # Vehicle descriptors: 0x3c bytes each from 0x08354af4 to the helicopter at 0x08354ef0.
    # Measured in the emulator: +0x1a is engine power, +0x1c steering rate, +0x16 top speed.
    VEHICLES = range(0x354af4, 0x354ef0, 0x3c)

    def tune_vehicles(self, power=1.6, steer=1.4, speed=1.3):
        for a in self.VEHICLES:
            for off, k in ((0x1a, power), (0x1c, steer), (0x16, speed)):
                v = struct.unpack_from('<h', self.d, a + off)[0]
                struct.pack_into('<h', self.d, a + off, max(-32768, min(32767, round(v * k))))

    def data(self):
        return bytes(self.d)

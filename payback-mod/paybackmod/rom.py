"""Edits to a Payback (Europe) ROM: map columns, level grids and physics tweaks."""
import collections
import hashlib
from pathlib import Path
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
RUNTIME_SOURCES = ('asm/build.sh', 'asm/editor.c', 'asm/hook.s', 'asm/link.ld')
RUNTIME_BASE, RUNTIME_LIMIT = 0x081b0000, 0x081c0000
RUNTIME_COLUMNS, RUNTIME_MAPS = 85, 3
REBUILD_RUNTIME = 'rebuild the runtime with sh payback-mod/asm/build.sh'


def validate_runtime(code, metadata, source_root=None):
    """Reject stale/corrupt compiled code and unsafe injection layouts before ROM writes.

    The source check is used by normal builds and by the compiler before publishing
    its output. Callers injecting a supplied artifact still get byte/hash/layout checks.
    """
    if (not isinstance(metadata, dict) or type(metadata.get('format_version')) is not int or
            metadata['format_version'] != 1):
        raise ValueError('runtime metadata has no supported provenance; ' + REBUILD_RUNTIME)
    if not isinstance(code, (bytes, bytearray)) or not code:
        raise ValueError('runtime code must be a nonempty byte string; ' + REBUILD_RUNTIME)
    if type(metadata.get('code_size')) is not int or metadata['code_size'] != len(code):
        raise ValueError('runtime code length does not match metadata; ' + REBUILD_RUNTIME)
    if metadata.get('code_sha256') != hashlib.sha256(code).hexdigest():
        raise ValueError('runtime code hash does not match metadata; ' + REBUILD_RUNTIME)
    sources = metadata.get('source_sha256')
    if not isinstance(sources, dict) or set(sources) != set(RUNTIME_SOURCES):
        raise ValueError('runtime source provenance is incomplete; ' + REBUILD_RUNTIME)
    for name, digest in sources.items():
        if (not isinstance(digest, str) or len(digest) != 64 or
                any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('runtime source hash is invalid: ' + name)
    for name in ('hook', 'cols', 'maps'):
        if type(metadata.get(name)) is not int:
            raise ValueError('runtime symbol must be an integer: ' + name)
    hook, cols, maps = (metadata[k] for k in ('hook', 'cols', 'maps'))
    if not RUNTIME_BASE <= (hook & ~1) <= RUNTIME_BASE + len(code) - 2:
        raise ValueError('runtime hook is outside the compiled code')
    if cols != ((RUNTIME_BASE + len(code) + 3) & ~3):
        raise ValueError('runtime column table must immediately follow aligned code')
    if maps != cols + 4 * RUNTIME_COLUMNS:
        raise ValueError('runtime map table must follow all 85 column pointers')
    if maps + 4 * RUNTIME_MAPS > RUNTIME_LIMIT:
        raise ValueError('runtime code and tables exceed the reserved injection region')
    if source_root is not None:
        for name in RUNTIME_SOURCES:
            try:
                actual = hashlib.sha256((Path(source_root) / name).read_bytes()).hexdigest()
            except OSError as exc:
                raise ValueError('runtime source unavailable: ' + name) from exc
            if actual != sources[name]:
                raise ValueError('compiled runtime is stale for ' + name + '; ' + REBUILD_RUNTIME)


def _column_records(columns, count, label):
    columns = list(columns)
    if len(columns) != count:
        raise ValueError(f'{label}: expected {count} columns, got {len(columns)}')
    if any(not isinstance(c, (bytes, bytearray)) or len(c) != 60 for c in columns):
        raise ValueError(f'{label}: every map column must be 60 bytes')
    return [bytes(c) for c in columns]


class ColumnIndex:
    """Every column the 11 shipped grids use, indexed by its layer signature, so a map built
    from Payback's own vocabulary (tools/content/mkarena.py) picks columns that already exist,
    the most used first, and adds a new one only when none matches.

    A layer is (b0, b1, b2, b3, h0, h1, shape, flags, tile, attr, sides): the bytes of one 20-byte
    record, as blocks.py names them; a column's signature is its three layers. uses[idx] counts the
    cells that hold it over all maps, maps[idx] says which maps."""

    def __init__(self, rom):
        self.rom = rom
        self.uses = collections.Counter()
        self.maps = collections.defaultdict(set)
        for lv in range(11):
            g = rom.orig_grid(lv)
            self.uses.update(g)
            for c in set(g):
                self.maps[c].add(lv)
        self._sig = {}
        self.by_sig = collections.defaultdict(list)
        for c in sorted(self.uses):
            self.by_sig[self.signature(rom.column(c))].append(c)

    @staticmethod
    def layer(rec):
        return (rec[0], rec[1], rec[2], rec[3]) + struct.unpack_from('<HHBBBB4H', rec, 4)

    @classmethod
    def signature(cls, col60):
        return tuple(cls.layer(col60[20 * k:20 * k + 20]) for k in range(3))

    def sig(self, idx):
        if idx not in self._sig:
            self._sig[idx] = self.signature(self.rom.column(idx))
        return self._sig[idx]

    def find(self, pred, maps=None):
        """Column numbers whose signature satisfies pred, most used first (ties: lowest number)."""
        out = [c for c in self.uses if (maps is None or self.maps[c] & set(maps)) and pred(self.sig(c))]
        return sorted(out, key=lambda c: (-self.uses[c], c))

    def common(self, pred, maps=None):
        """The most used column satisfying pred, or None."""
        f = self.find(pred, maps)
        return f[0] if f else None

    def lookup(self, col60):
        """The shipped column with exactly this signature (most used), or None."""
        hit = self.by_sig.get(self.signature(col60))
        return max(hit, key=lambda c: (self.uses[c], -c)) if hit else None


class PaybackRom:
    """A Payback ROM extended to 16 MiB with the column table relocated so new columns fit."""

    def __init__(self, data, check=True):
        if len(data) != 0x800000:
            raise ValueError(f'expected an 8 MiB Payback GBA ROM, got {len(data)} bytes')
        if check and hashlib.sha1(data).hexdigest() != PAYBACK_EU_SHA1:
            raise ValueError('not Payback (Europe) (En,Fr,De,Es,It); expected SHA-1 ' + PAYBACK_EU_SHA1)
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
        self.marker_columns = []
        self.painted = {}
        self._orig_grids = {}
        self._index = None
        self.runtime_metadata = None

    def orig_grid(self, level):
        """The level's grid as Payback shipped it (decoded once; grid() decodes every time)."""
        if level not in self._orig_grids:
            self._orig_grids[level] = self.grid(level)
        return self._orig_grids[level]

    def column_index(self):
        if self._index is None:
            self._index = ColumnIndex(self)
        return self._index

    def column(self, idx):
        o = NEW_BASE + 60 * idx
        return bytes(self.d[o:o + 60])

    def add_column(self, data60):
        """Append a column (deduplicated) and return its number."""
        if len(data60) != 60:
            raise ValueError(f'map columns must be 60 bytes, got {len(data60)}')
        if data60 in self.new_columns:
            return self.new_columns[data60]
        if self.ncols >= MAX_COLUMNS:
            raise ValueError('map column index limit (32768 columns) exceeded')
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
        o = self.alloc(bs)
        struct.pack_into('<I', self.d, LEVEL_TABLE + 4 * level, GBA + o)

    def paint(self, level, cells):
        """Replace cells of a level: cells maps (x, y) -> 60-byte column."""
        g = list(self.painted.get(level) or self.grid(level))   # (a level may be painted more than once)
        for x, y in cells:
            if not (0 <= x < 128 and 0 <= y < 128):
                raise ValueError(f'paint cell ({x}, {y}) is outside the 128x128 map')
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
        if align < 1 or align & (align - 1):
            raise ValueError('allocation alignment must be a positive power of two')
        o = (self.free + align - 1) & ~(align - 1)
        if o + len(data) > len(self.d):
            raise ValueError('mod exceeds the 16 MiB ROM capacity')
        self.d[o:o + len(data)] = data
        self.free = o + len(data)
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
    BUILD_BASE = RUNTIME_BASE
    KEYPAD_READER = 0x08072f68

    def add_build_mode(self, code, syms, flats, ramps, plates):
        """flats: 17 columns (0x100 + 0x20*i); ramps: 4 x 16 columns rising toward +y, +x, -y, -x;
        plates: the loop plate, boost plate and two cursor columns."""
        validate_runtime(code, syms)
        flats = _column_records(flats, 17, 'build platforms')
        ramps = list(ramps)
        if len(ramps) != 4:
            raise ValueError('build ramps: expected 4 directions')
        ramps = [_column_records(row, 16, 'build ramp direction') for row in ramps]
        plates = _column_records(plates, 4, 'build plates and cursors')
        records = flats + [c for row in ramps for c in row] + plates
        if self.ncols + len(set(records) - self.new_columns.keys()) > MAX_COLUMNS:
            raise ValueError('map column index limit (32768 columns) exceeded')
        h1, h2 = struct.unpack_from('<HH', self.d, self.HOOK_CALL - GBA)
        if h1 >> 11 != 0x1e or h2 >> 11 != 0x1f:
            raise ValueError('expected a Thumb BL at the runtime hook site')
        original_off = ((h1 & 0x7ff) << 12) | ((h2 & 0x7ff) << 1)
        if original_off & (1 << 22):
            original_off -= 1 << 23
        if self.HOOK_CALL + 4 + original_off != self.KEYPAD_READER:
            raise ValueError('runtime hook does not call the original keypad reader')
        off = (syms['hook'] & ~1) - (self.HOOK_CALL + 4)
        if off & 1 or not -(1 << 22) <= off < (1 << 22):
            raise ValueError('runtime hook is outside Thumb BL range')
        o = self.BUILD_BASE - GBA
        self.d[o:o + len(code)] = code
        table = [self.col_ptr(self.add_column(c)) for c in records]
        struct.pack_into('<%dI' % len(table), self.d, syms['cols'] - GBA, *table)
        struct.pack_into('<HH', self.d, self.HOOK_CALL - GBA,
                         0xf000 | ((off >> 12) & 0x7ff), 0xf800 | ((off >> 1) & 0x7ff))
        self.runtime_metadata = dict(syms, source_sha256=dict(syms['source_sha256']))

    def col_ptr(self, idx):
        return GBA + NEW_BASE + 60 * idx

    def add_space(self, syms, space_cells, free_roam_cells):
        """Store full pointer grids (space, level 0, free-roam city); the hook swaps between them."""
        if not getattr(self, 'runtime_metadata', None) or syms != self.runtime_metadata:
            raise ValueError('space maps require the same validated runtime that was installed')
        space_cells = _column_records(space_cells, 16384, 'space grid')
        free_roam_cells = _column_records(free_roam_cells, 16384, 'free-roam grid')
        city = self.painted.get(0) or self.grid(0)
        if len(city) != 16384 or any(type(i) is not int or not 0 <= i < self.ncols for i in city):
            raise ValueError('city grid contains invalid column indices')
        additions = set(space_cells) | set(free_roam_cells)
        # Two deliberately unique copies of the unchanged corner identify the live
        # variant. The original loader reuses the same RAM grid on level reload,
        # so the grid address and scratch flags alone cannot identify a new level.
        if self.ncols + len(additions - self.new_columns.keys()) + 2 > MAX_COLUMNS:
            raise ValueError('map column index limit (32768 columns) exceeded')
        if ((self.free + 3) & ~3) + 3 * 16384 * 4 > len(self.d):
            raise ValueError('space grids exceed the 16 MiB ROM capacity')
        space = [self.add_column(c) for c in space_cells]
        neo = [self.add_column(c) for c in free_roam_cells]
        markers = []
        for grid, corner in ((space, space_cells[0]), (neo, free_roam_cells[0])):
            marker = self.ncols
            offset = NEW_BASE + 60 * marker
            self.d[offset:offset + 60] = corner
            self.ncols += 1
            grid[0] = marker
            markers.append(marker)
        # Do not enter these copies in new_columns: regular deduplication must
        # never hand a marker pointer to any other map cell or the base city.
        self.marker_columns = getattr(self, 'marker_columns', []) + markers
        self.map_marker_pointers = dict(space=self.col_ptr(markers[0]), neo=self.col_ptr(markers[1]))
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

"""Collision check: our world against Payback's own collision, cell by cell and edge by edge.

Payback's answer comes from Payback itself: its map-collision code (the swept wall test
0x0803b8a0, its floor routine in IWRAM, the object pushes of 0x08000e10) runs under the unicorn
CPU emulator on a RAM snapshot of the game, on the grid being checked. Our answer comes from the
code that ships: src/physics.c, src/world.c and src/car.c built for the host (tools/colhost.c)
on the world tools/mkworld.py builds, plus what citydraw.c draws from it (railings, props).

For every cell and every walkable surface in it (the floors Payback's floor routine can put
you on), and every edge of the cell:
  heights   Payback's floor at 5 points against our physics surface there (the drawn floor is
            the same table): floating or sinking
  person    whether Payback lets a man walk across, against what is drawn there: a Payback wall
            with nothing drawn is an invisible wall; walking through a drawn wall or railing
  car       whether Payback lets a car across, against our stunt car driven across
and for every street object on a floor people or cars get to (Payback pushes both out of a
circle about it): whether we draw it there, and whether our car is stopped by it where Payback's
is; and every water cell beside a floor people get to (Payback lets them in to sink).

Classes start P_ (person), C_ (car), H_ (heights), O_ (objects), W_ (water), I_ (no mismatch: a
railing drawn open from the side Payback lets you across it, one way); gridNN.json has
their counts and examples, gridNN_marks.json every cell and edge, --png a picture per group.

Usage:
  colcheck.py ROM --ram PREFIX [--grid G] [--world world.bin] [--out DIR] [--png] [--unpainted]
ROM is the player's Payback (Europe) ROM. PREFIX.ewram / PREFIX.iwram: EWRAM and IWRAM of
Payback with any level loaded (any grid: the grid table in it is replaced by grid G's). The grid
is the one build.py --merge ships: with the phones tools/mksolo.py paints (--unpainted: as
Payback has it). Without --world, mkworld builds grid G's merged world. Heights are compared
with the world's yoff added (Little Chicago's streets are at 0). Needs: pip install unicorn; gcc.
"""
import argparse
import collections
import ctypes
import json
import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SF = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SF, '..', 'payback-mod'))
from paybackmod.rom import PaybackRom, NEW_BASE   # noqa: E402

N = 128
PCELL = 2048                 # Payback units per cell
CELL = 1024                  # ours
Z0 = 19904                   # Payback z of height 0x100 (our 0)
DIRS = ((0, -1), (1, 0), (0, 1), (-1, 0))     # edge e of a cell: -y, +x, +y, -x (mkworld's order)
HEAD = (2880, 1440, 0, 4320)                  # Payback heading along each (5760 a turn, 0 = +y)


YOFF = 0                     # the world's yoff (world.h): added to Payback's heights


def h_units(z):
    """Payback z (16 per height step, 19904 at 0x100) -> our height in units."""
    return ((Z0 - z) >> 1) + YOFF


def payback_rom(rom_bytes, painted=True):
    """Payback as build.py --merge ships it: its grids with mksolo's phones."""
    rom = PaybackRom(rom_bytes)
    if painted:
        import mksolo
        mksolo.offer_every_map(rom.d)
        mksolo.add_phones(rom)
    return rom


def grid_of(rom, g):
    return rom.painted.get(g) or rom.grid(g)


# ---- Payback, run by unicorn ----

class Payback:
    SCR = 0x0201b640          # free EWRAM: out buffers
    FLOOR = 0x030060f8        # IWRAM ARM: floor(out, ent, cx, cy, x, y) -> (layer, z)
    VENEER_R5 = 0x0807c804    # Thumb "bx r5"
    MOVE = 0x08017348         # one entity's move: x += vx * dt / 4 ..., then the wall test 0x0803b8a0
    PUSH = 0x08000e10         # one entity against the objects and people around it
    GRID = 0x0202c720         # decoded grid: column pointers, x * 128 + y
    RET = 0x100

    def __init__(self, image, ewram, iwram, cols):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_INTR
        from unicorn import arm_const as A
        self.A = A
        u = self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        for base, size in ((0, 0x4000), (0x02000000, 0x40000), (0x03000000, 0x8000), (0x04000000, 0x1000),
                           (0x05000000, 0x1000), (0x06000000, 0x18000), (0x07000000, 0x1000),
                           (0x08000000, 0x2000000)):
            u.mem_map(base, size)
        u.mem_write(0x08000000, bytes(image))
        u.mem_write(self.RET, b'\x70\x47\x00\x00')
        ew = bytearray(ewram)
        assert struct.unpack_from('<I', iwram, 0xd60)[0] == self.GRID
        struct.pack_into('<16384I', ew, self.GRID - 0x02000000, *[0x08000000 + NEW_BASE + 60 * c for c in cols])
        heap0 = struct.unpack_from('<I', iwram, 0xc40)[0] - 0x02000000
        ew[heap0:heap0 + 0x10000] = bytes(0x10000)       # nobody else about: no entity occupancy
        self.ew, self.iw = bytes(ew), bytes(iwram)
        self.reset()
        u.hook_add(UC_HOOK_INTR, self._swi)
        n = struct.unpack_from('<h', iwram, 0xc)[0]
        ents = self.ents = list(struct.unpack_from('<%dI' % n, iwram, 0xc60))
        self.man = ents[struct.unpack_from('<h', ew, 0x1db8)[0]]          # the one the player controls
        # a car: a traffic car's record, made a saloon (vehicle descriptor 0, the commonest car)
        cars = [e for e in ents if e != self.man and self.u32(e + 0x1c) < 0x08354ef0]
        self.car = max(cars, key=lambda e: self.u.mem_read(e + 0x10f, 1)[0] == 3)
        self.w32(self.car + 0x1c, 0x08354af4)
        self.w8(self.car + 0x5b, 1)                                          # (walls on)
        self.ew = bytes(self.u.mem_read(0x02000000, 0x40000))
        self.dt = self.r32(0x03000010)

    def reset(self):
        self.u.mem_write(0x02000000, self.ew)
        self.u.mem_write(0x03000000, self.iw)

    def _swi(self, u, intno, data):
        A = self.A
        pc = u.reg_read(A.UC_ARM_REG_PC)
        op = struct.unpack('<H', u.mem_read(pc - 2, 2))[0] & 0xff
        r0, r1 = u.reg_read(A.UC_ARM_REG_R0), u.reg_read(A.UC_ARM_REG_R1)
        s = lambda v: v - (1 << 32) if v & 0x80000000 else v
        if op == 6:
            a, b = s(r0), s(r1)
            q = int(a / b) if b else 0
            u.reg_write(A.UC_ARM_REG_R0, q & 0xffffffff)
            u.reg_write(A.UC_ARM_REG_R1, (a - q * b) & 0xffffffff)
            u.reg_write(A.UC_ARM_REG_R3, abs(q))
        elif op == 8:
            import math
            u.reg_write(A.UC_ARM_REG_R0, math.isqrt(r0))
        else:
            raise RuntimeError('swi %x at %x' % (op, pc))

    def call(self, fn, *args, stack=()):
        A, u = self.A, self.u
        sp = 0x03007e00 - 4 * len(stack)
        if stack:
            u.mem_write(sp, struct.pack('<%di' % len(stack), *stack))
        for i, a in enumerate(args):
            u.reg_write(A.UC_ARM_REG_R0 + i, a & 0xffffffff)
        u.reg_write(A.UC_ARM_REG_SP, sp)
        u.reg_write(A.UC_ARM_REG_LR, self.RET | 1)
        u.emu_start(fn | 1, self.RET, count=5000000)

    def r32(self, a): return struct.unpack('<i', self.u.mem_read(a, 4))[0]
    def u32(self, a): return struct.unpack('<I', self.u.mem_read(a, 4))[0]
    def s16(self, a): return struct.unpack('<h', self.u.mem_read(a, 2))[0]
    def w32(self, a, v): self.u.mem_write(a, struct.pack('<I', v & 0xffffffff))
    def w16(self, a, v): self.u.mem_write(a, struct.pack('<H', v & 0xffff))
    def w8(self, a, v): self.u.mem_write(a, bytes([v & 0xff]))

    def floor(self, ent, x, y, z):
        """Payback's floor under (x, y) for someone at height z: (layer, z)."""
        self.w16(ent + 0xc, z)
        self.u.reg_write(self.A.UC_ARM_REG_R5, self.FLOOR)
        self.call(self.VENEER_R5, self.SCR, ent, x >> 11, y >> 11, stack=(x, y))
        return self.s16(self.SCR), self.s16(self.SCR + 2)

    def place(self, ent, x, y, z, head):
        lay, zf = self.floor(ent, x, y, z)
        for a, v in ((4, x), (8, y), (0xf0, x), (0xf4, y), (0xe4, x), (0xe8, y)):
            self.w32(ent + a, v)
        self.w16(ent + 0xc, zf)
        self.w32(ent + 0xf8, zf)
        self.w16(ent + 0xcc, lay)
        self.w16(ent + 0xce, lay)
        self.w16(ent + 0x44, 0)
        self.w16(ent + 0xe, 0)
        self.w32(ent + 0x10, head << 16)
        return lay, zf

    def tick(self, ent, vx, vy, objects):
        """One logic tick of Payback moving ent at (vx, vy): its move and wall test, its feet
        onto the floor (0x080208c0 does that for people), then the objects about. Returns the
        wall test's push for a car (x, y signs: the side a wall pushed it toward; 0 0 for none)."""
        x, y, z = self.r32(ent + 4), self.r32(ent + 8), self.s16(ent + 0xc)
        for a, v in ((0xf0, x), (0xf4, y), (0xe4, x), (0xe8, y), (0xf8, z)):
            self.w32(ent + a, v)
        self.w16(ent + 0x40, vx)
        self.w16(ent + 0x42, vy)
        self.w32(self.SCR, 0)
        self.call(self.MOVE, self.SCR, ent)
        hit = struct.unpack('<bb', self.u.mem_read(self.SCR, 2))
        self.w16(ent + 0xc, self.s16(ent + 0xd8))
        if objects:
            self.w8(ent + 0x152, 0xfe)
            self.call(self.PUSH, self.ents.index(ent))
        return hit


class PaybackMap:
    """Payback's answers for one grid."""

    def __init__(self, pb, rom, cols):
        self.pb, self.rom, self.cols = pb, rom, cols
        self.colb = {}
        self.cache = {}
        self.wet = {}
        self.step = 128                            # Payback units a tick (about a walk)
        self.v = (self.step * 4 + pb.dt - 1) // pb.dt

    def col(self, i):
        c = self.cols[i]
        if c not in self.colb:
            self.colb[c] = self.rom.column(c)
        return self.colb[c]

    def objects(self, i):
        """Street objects in cell i: [(record, type, turn)] (byte 1 of a record, byte 0 turns it)."""
        b = self.col(i)
        return [(k, b[20 * k + 1], b[20 * k]) for k in range(3) if b[20 * k + 1] and b[20 * k + 8]]

    def surfaces(self, i):
        """The floors in cell i Payback can stand you on: [(layer, z at the cell centre)]. Water
        (records of type 0x4000) is left out: Payback lets people in and they sink (seen in the
        emulator: dropped in at street height, the man went down past z 24900 with a splash)."""
        b = self.col(i)
        x, y = divmod(i, N)
        base, out, seen = 1500, [], set()
        for k in range(3):
            h0, h1, shape = struct.unpack_from('<hhB', b, 20 * k + 4)
            flags = b[20 * k + 11] & 0x70
            top = base - h0
            if shape and flags and flags != 0x40:
                ref = base - h1 if shape != 1 and h0 >= h1 else top
                lay, z = self.pb.floor(self.pb.man, x * PCELL + 1024, y * PCELL + 1024, ref * 16)
                if lay == k and lay not in seen:
                    seen.add(lay)
                    out.append((lay, z))
            base = top
        return out

    def water(self, i, layer=False):
        """The water's surface in cell i (Payback height), or None: where Payback's floor routine
        puts someone at the surface in the water (not on a floor laid over it, as Little Chicago's
        and Los Francos' covered pools). layer: its layer instead."""
        if i not in self.wet:
            b = self.col(i)
            base, self.wet[i] = 0, (None, None)
            for k in range(3):
                h0, shape = struct.unpack_from('<hB', b, 20 * k + 4)[0], b[20 * k + 8]
                if shape and b[20 * k + 11] & 0x70 == 0x40:
                    if k < 2 and b[20 * k + 28]:
                        break               # (a block right on it: nobody gets in)
                    x, y = divmod(i, N)
                    lay, _ = self.pb.floor(self.pb.man, x * PCELL + 1024, y * PCELL + 1024, (1500 - base - h0) * 16)
                    if lay == k:
                        self.wet[i] = (base + h0, k)
                    break
                base += h0
        return self.wet[i][layer]

    def heights(self, i, z):
        """Payback's floor at the centre and the four quarter points of cell i, for someone at z."""
        x, y = divmod(i, N)
        return [self.pb.floor(self.pb.man, x * PCELL + fx, y * PCELL + fy, z) for fx, fy in QUARTERS]

    def walk(self, car, x, y, z, e, dist, objects):
        """Payback moves a man (car: a saloon) from (x, y) on the floor nearest z along e, a tick
        at a time, until it has gone dist or is stopped. Returns (how far it got, end z, end
        layer)."""
        pb = self.pb
        pb.reset()
        ent = pb.car if car else pb.man
        dx, dy = DIRS[e]
        pb.place(ent, x, y, z, HEAD[e])
        along, last, still = 0, 0, 0
        for _ in range(dist // self.step + 3):
            hit = pb.tick(ent, dx * self.v, dy * self.v, objects)
            along = (pb.r32(ent + 4) - x) * dx + (pb.r32(ent + 8) - y) * dy
            if car and hit[0] * dx + hit[1] * dy < 0:
                break                                # (a car is not put back: Payback bounces it off)
            if along >= dist:
                break
            still = still + 1 if along <= last + 8 else 0
            if still > 2:
                break
            last = along
        return along, pb.s16(ent + 0xc), pb.s16(ent + 0xcc)

    def cross(self, i, e, z, car):
        """Can a man (car: a car) on the floor at z in cell i go across its edge e, walls alone
        (street objects are checked on their own)? Returns (crossed, end z, end layer). A man
        starts at the cell centre and walks to the next cell's centre; a car starts with its nose
        at the edge (1470 ahead of its middle) and has crossed when its middle is 256 past it."""
        x, y = divmod(i, N)
        dx, dy = DIRS[e]
        j = (x + dx) * N + y + dy
        key = (self.cols[i], self.cols[j], e, z, car)
        if key not in self.cache:
            back = 1472 - 1024 if car else 0
            cx, cy = x * PCELL + 1024 - dx * back, y * PCELL + 1024 - dy * back
            goal = back + 1024 + (256 if car else 1024)
            along, zz, lay = self.walk(car, cx, cy, z, e, goal, False)
            self.cache[key] = (along >= back + 1024 + (256 if car else 512), zz, lay)
        return self.cache[key]

    def circle(self, i, typ, turn):
        """Where 0x08000e10 has the street object of type typ, turned turn, in cell i: its middle
        (x, y) and its descriptor's radius (Payback units)."""
        d = self.rom.d
        ox, oy, r = struct.unpack_from('<hhh', d, 0x353f00 + typ * 0x3c - 0x14)
        a = turn * 5760 // 256
        c = struct.unpack_from('<h', d, 0x669aaa + 2 * a)[0]
        s = struct.unpack_from('<h', d, 0x666daa + 2 * a)[0]
        x, y = divmod(i, N)
        return x * PCELL + 1024 + ((c * ox + s * oy) >> 8), y * PCELL + 1024 + ((c * oy - s * ox) >> 8), r

    def object_block(self, i, z, car):
        """Does a street object in cell i stop a man (car) on the floor at z? Walks across the
        cell both ways along x and y, on 5 (car: 3) lines; returns how many of the walks it
        stops, against walls alone."""
        x, y = divmod(i, N)
        cx, cy = x * PCELL + 1024, y * PCELL + 1024
        lines = (-768, -384, 0, 384, 768) if not car else (-512, 0, 512)
        run = 1648 if not car else 1024 + 1470 + 1024 + 574
        stopped = 0
        for e, (dx, dy) in enumerate(DIRS):
            for lat in lines:
                sx = cx - dx * (run // 2) + (dy and lat)
                sy = cy - dy * (run // 2) + (dx and lat)
                if car:
                    sx, sy = sx - dx * 574, sy - dy * 574
                a1 = self.walk(car, sx, sy, z, e, run, True)[0]
                if a1 < run - 64 and self.walk(car, sx, sy, z, e, run, False)[0] >= run - 64:
                    stopped += 1
        return stopped


QUARTERS = ((1024, 1024), (512, 512), (1536, 512), (512, 1536), (1536, 1536))


# ---- ours: the shipped physics on the host, and the drawn world ----

class Ours:
    def __init__(self, world_path, build_dir):
        src = os.path.join(SF, 'src')
        lib = os.path.join(build_dir, 'libcol.so')
        tables = os.path.join(build_dir, 'tables.c')
        import mkassets
        mkassets.main(tables)                  # (the sin table the physics turns with)
        t = open(tables).read().replace('"../../src/gba.h"', '"gba.h"')
        open(tables, 'w').write(t)
        subprocess.check_call(['gcc', '-O2', '-shared', '-fPIC', '-fno-builtin', '-w', '-I' + src] +
                              [os.path.join(src, f) for f in ('fx.c', 'world.c', 'physics.c', 'car.c', 'loops.c')] +
                              [tables, os.path.join(HERE, 'colhost.c'), '-o', lib])
        self.L = ctypes.CDLL(lib)
        assert self.L.col_load(world_path.encode()) > 0
        self.world = open(world_path, 'rb').read()
        self._parse()

    def _parse(self):
        w = self.world
        assert w[:4] in (b'SFW2', b'SFW3', b'SFW4')
        old = w[:4] == b'SFW2'          # (before walls: railings all drawn on the ground, flat decks)
        new = w[:4] == b'SFW4'          # (heights in wider units: see world.h)
        self.hb = 40 if new else 0
        cnt = struct.unpack_from('<8I', w, 4)
        offs = struct.unpack_from('<13I', w, 36)
        self.ntree = cnt[6]
        self.fence = collections.defaultdict(set)     # cell -> (edge, height) of railings drawn on it
        self.open = collections.defaultdict(set)      # cell -> (edge, height) of those drawn open from it
        # cell -> [(kind (0 1 tree, 6 bench, 7 bin, 8 lamp), x, z, base, radius cars stop at)] (units)
        self.objs = collections.defaultdict(list)
        for k in range(cnt[6]):
            if old:
                x, z, h, kind = struct.unpack_from('<HHBB', w, offs[9] + 6 * k)
                base = r = 0
            else:
                x, z, h, kind, base, r = struct.unpack_from('<HHBBbB', w, offs[9] + 8 * k)
            if 2 <= kind <= 5:
                y = 0 if old else (base << 8 | h) * 32 if new else struct.unpack('b', bytes([h]))[0] * 32
                self.fence[(x & 127) * N + z].add((kind - 2, y))
                if new and x & 128:
                    # (one way: light, no posts, from the next cell, where Payback lets you across)
                    dx, dz = DIRS[kind - 2]
                    self.open[((x & 127) + dx) * N + z + dz].add((kind - 2 ^ 2, y))
            elif old and kind >= 6:      # (props at the cell's middle)
                self.objs[(x & 127) * N + z].append((kind, (x & 127) * CELL + 512, z * CELL + 512, 0, 0))
            else:
                self.objs[(x * 4 // CELL) * N + z * 4 // CELL].append((kind, x * 4, z * 4, base * (64 if new else 32), r * 4))
        self.cells = [struct.unpack_from('<hhBB', w, offs[6] + 6 * i) for i in range(N * N)]
        self.decks = [struct.unpack_from('<bb', w, offs[12] + (2 if old else 4) * i) for i in range(N * N)]
        nparts = (struct.unpack_from('<I', w, 36)[0] - 36) // 4
        self.decks2 = [struct.unpack_from('<bb', w, struct.unpack_from('<I', w, 36 + 4 * 14)[0] + 4 * i)
                       for i in range(N * N)] if nparts > 14 else [(0, 0)] * (N * N)

    def surface(self, x, y, z): return self.L.col_surface(x, y, z)
    def ground(self, x, z): return self.L.col_ground(x, z)

    def deck(self, i, k=0):
        b, t = (self.decks, self.decks2)[k][i]
        return ((b + self.hb) * 64, (t + self.hb) * 64) if b or t else None

    def edge_floor(self, i, e, y):
        """Our floor at the middle of edge e of cell i, just inside, for someone at height y in
        the cell (units): a slope's height there, not at the cell's middle."""
        x, z = divmod(i, N)
        dx, dz = DIRS[e]
        return self.surface(x * CELL + 512 + dx * 496, y + 400, z * CELL + 512 + dz * 496)

    def railing(self, i, e, y):
        """A railing drawn on edge e of cell i, standing about height y (units)?"""
        x, z = divmod(i, N)
        dx, dz = DIRS[e]
        j = (x + dx) * N + z + dz
        return any(f == e and abs(h - y) < 256 for f, h in self.fence[i]) or \
            any(f == e ^ 2 and abs(h - y) < 256 for f, h in self.fence[j])

    def railing_open(self, i, e, y):
        """The railing on edge e of cell i drawn open (one way) as seen from i?"""
        return any(f == e and abs(h - y) < 256 for f, h in self.open[i])

    def object_block(self, i, y):
        """How many of the walks Payback's car makes across cell i (PaybackMap.object_block) a
        street object stops our car at: stopped with them, through without."""
        x, z = divmod(i, N)
        cx, cz = x * CELL + 512, z * CELL + 512
        run = (1024 + 1470 + 1024 + 574) // 2
        out, stopped = (ctypes.c_int * 6)(), 0
        for e, (dx, dz) in enumerate(DIRS):
            for lat in (-256, 0, 256):
                sx = cx - dx * (run // 2 + 287) + (dz and lat)
                sz = cz - dz * (run // 2 + 287) + (dx and lat)
                got = []
                for on in (1, 0):
                    self.L.col_posts(on)
                    self.L.col_drive(sx, y + 100, sz, (32768, 16384, 0, 49152)[e], 40, 90, run, out)
                    got.append(out[3] >= run - 32)
                stopped += not got[0] and got[1]
        self.L.col_posts(1)
        return stopped

    def drive(self, i, e, y):
        """Our stunt car from cell i's centre-ish across edge e, from height y (units): crossed?"""
        x, z = divmod(i, N)
        dx, dz = DIRS[e]
        cx, cz = x * CELL + 512, z * CELL + 512
        back = 736 - 512                               # (the same start as Payback's car)
        heading = (32768, 16384, 0, 49152)[e]          # ours: 0 = +z, 16384 = +x
        out = (ctypes.c_int * 6)()
        reach = back + 512 + 128
        self.L.col_posts(0)                            # (walls alone, as Payback's is tested)
        # (on our floor where it starts: on a steep ramp that is well off the middle's height)
        y = max(y, self.surface(cx - dx * back, y + 512, cz - dz * back))
        self.L.col_drive(cx - dx * back, y + 100, cz - dz * back, heading, 40, 90, reach, out)
        self.L.col_posts(1)
        return out[3] >= reach - 4


# ---- the check ----

def world_for(rom_bytes, g, rom):
    """Grid g's merged world, built by mkworld as build.py builds it."""
    import mkworld
    return mkworld.build(rom_bytes, merge=True, level=g, rom=rom, limits=False)


def _around(i):
    x, y = divmod(i, N)
    return [(x + dx) * N + y + dy for dx, dy in DIRS if 0 <= x + dx < N and 0 <= y + dy < N]


def check(rom_bytes, ram, g, world_path, out, build_dir, log=print, rom=None):
    global YOFF
    rom = rom or payback_rom(rom_bytes)
    cols = grid_of(rom, g)
    YOFF = struct.unpack_from('<i', open(world_path, 'rb').read(), 32)[0]
    pb = Payback(rom.d, open(ram + '.ewram', 'rb').read(), open(ram + '.iwram', 'rb').read(), cols)
    pm = PaybackMap(pb, rom, cols)
    us = Ours(world_path, build_dir)
    inside = lambda x, y: 2 <= x < N - 2 and 2 <= y < N - 2      # (merge.c keeps the car off the outer two)

    surf = [pm.surfaces(i) for i in range(N * N)]

    def flood(car):
        """The floors a man (a car) can get to from the streets and pavements, by Payback's rules:
        {(cell, floor z)}."""
        seen, todo = set(), []
        for i in range(N * N):
            if pm.col(i)[3] & (0x0f if car else 0x2f) and surf[i] and inside(*divmod(i, N)):
                z = min(surf[i], key=lambda s: abs(s[1] - Z0 - 2 * YOFF))[1]     # (nearest the street)
                seen.add((i, z))
                todo.append((i, z))
        while todo:
            i, z = todo.pop()
            x, y = divmod(i, N)
            for e, (dx, dy) in enumerate(DIRS):
                if not inside(x + dx, y + dy):
                    continue
                ok, z2, lay = pm.cross(i, e, z, car)
                j = (x + dx) * N + y + dy
                if ok:
                    zz = next((s[1] for s in surf[j] if s[0] == lay), None)
                    if zz is not None and (j, zz) not in seen:
                        seen.add((j, zz))
                        todo.append((j, zz))
        return seen

    foot = flood(False)
    log('grid %d: %d floors on foot' % (g, len(foot)))
    drive = flood(True)
    log('grid %d: %d floors by car' % (g, len(drive)))

    counts = collections.Counter()
    examples = collections.defaultdict(list)
    marks = collections.defaultdict(list)        # class -> [(cell, edge or -1)], for the pictures

    def note(cls, i, e=-1, **info):
        counts[cls] += 1
        marks[cls].append((i, e))
        if len(examples[cls]) < 10:
            examples[cls].append(dict(cell=list(divmod(i, N)), edge=e, **info))

    def multi(i):
        return len(surf[i]) > 1 or us.deck(i) is not None

    # floors: Payback's height under a man against what our physics stands him (the car) on
    for (i, z) in sorted(foot | drive):
        x, y = divmod(i, N)
        worst = 0
        for (fx, fy), (lay, zz) in zip(QUARTERS, pm.heights(i, z)):
            want = h_units(zz)
            got = us.surface(x * CELL + fx // 2, want + 32, y * CELL + fy // 2)
            if abs(got - want) > abs(worst):
                worst = got - want
        if abs(worst) > 32:
            cls = ('H_ours_higher' if worst > 0 else 'H_ours_lower') + ('_deck' if multi(i) else '')
            note(cls, i, payback=h_units(z), ours_minus_payback=worst)

    # edges a man meets, from every floor he can get to
    wet_in = set()          # the water Payback lets someone into
    for (i, z) in sorted(foot):
        x, y = divmod(i, N)
        zu = h_units(z)
        for e, (dx, dy) in enumerate(DIRS):
            if not inside(x + dx, y + dy):
                continue
            j = (x + dx) * N + y + dy
            ok, z2, lay2 = pm.cross(i, e, z, False)
            # what is drawn at the edge: a railing at the floor's height there, a step up from our
            # floor just this side of it to just across (a box side; a slope carries on), a deck's side
            near = us.edge_floor(i, e, zu)
            rail = us.railing(i, e, near)
            bx, by = (x + dx) * CELL + 512 - dx * 448, (y + dy) * CELL + 512 - dy * 448
            rise = us.surface(bx, near + 32, by) - near
            side = any(d is not None and d[0] < zu + 256 and d[1] > zu + 96 for d in (us.deck(j), us.deck(j, 1)))
            wet = '_water' if pm.water(j) is not None else ''
            if ok and wet and lay2 == pm.water(j, True):
                wet_in.add(j)
            if not ok and not rail and rise < 96 and not side:
                note('P_invisible_wall' + ('_deck' if multi(i) or multi(j) else '') + wet, i, e, rise=rise)
            elif ok and rail:
                # (a railing Payback stops you at from the other side only: its one-way walls; seen
                # from here, drawn open (draw_fence), it tells no lie)
                back = pm.cross(j, e ^ 2, z2, False)[0]
                note(('I_railing_drawn_open' if us.railing_open(i, e, near) else 'P_walks_through_railing'
                      if back else 'P_oneway_railing') + wet, i, e)
            elif ok and (rise > 192 or side) and h_units(z2) < near + rise - 96:
                note('P_walks_through_wall' + wet, i, e, rise=rise, payback_end=h_units(z2) - zu)
            elif ok and rise > 192:
                # (no side stops him, and Payback's floor routine stands him on the top we draw)
                note('P_lifted_onto_wall', i, e, rise=rise)

    # edges a car meets: Payback's saloon against our car, both on Payback's roads and floors
    for (i, z) in sorted(drive):
        x, y = divmod(i, N)
        zu = h_units(z)
        for e, (dx, dy) in enumerate(DIRS):
            if not inside(x + dx, y + dy):
                continue
            pok, _, lay2 = pm.cross(i, e, z, True)
            ook = us.drive(i, e, zu)
            rail = us.railing(i, e, us.edge_floor(i, e, zu))
            wet = '_water' if pm.water((x + dx) * N + y + dy) is not None else ''
            if pok and wet and lay2 == pm.water((x + dx) * N + y + dy, True):
                wet_in.add((x + dx) * N + y + dy)
            if pok and not ook:
                # (a slope of more than about 35 degrees: Payback walks and drives up anything)
                steep = any(2 <= c[2] <= 5 and abs(c[1] - c[0]) > 720 for c in (us.cells[i], us.cells[(x + dx) * N + y + dy]))
                note('C_invisible_wall' + ('_steep' if steep else '') + wet, i, e)
            elif ook and not pok:
                note('C_drives_through_wall' + ('_railing' if rail else '') + wet, i, e)
            elif ook and rail:
                z2 = pm.cross(i, e, z, True)[1]
                back = pm.cross((x + dx) * N + y + dy, e ^ 2, z2, True)[0]
                note(('I_railing_drawn_open' if us.railing_open(i, e, us.edge_floor(i, e, zu)) else
                      'C_drives_through_drawn_railing' if back else 'C_oneway_railing') + wet, i, e)

    # water: Payback lets you in and you sink; ours is a surface you stand (drive) on
    for i in sorted(wet_in):
        x, y = divmod(i, N)
        wu = (pm.water(i) - 0x100) * 8 + YOFF
        got = us.surface(x * CELL + 512, wu + 32, y * CELL + 512)
        if got >= wu - 32:
            note('W_water_is_solid_in_ours', i, water=wu, ours=got)

    # street objects: Payback pushes people and cars out of a circle about each (0x08000e10).
    # Is something drawn there, and is our car stopped where Payback's is?
    for i in range(N * N):
        obs = pm.objects(i)
        if not obs or not inside(*divmod(i, N)):
            continue
        for k, typ, turn in obs:
            z = next((s[1] for s in surf[i] if s[0] == k), None)
            if z is None or ((i, z) not in foot and (i, z) not in drive):
                continue
            px, py, pr = pm.circle(i, typ, turn)
            tag = '_type%d' % typ
            near = [o for o in us.objs[i] if abs(o[1] - px / 2) < 48 and abs(o[2] - py / 2) < 48 and
                    abs(o[3] - h_units(z)) < 64]
            if not near:
                note(('O_drawn_elsewhere' if us.objs[i] else 'O_undrawn') + tag, i, at=[px // 2, py // 2],
                     drawn=[o[1:4] for o in us.objs[i]])
            elif near[0][4] < pr // 4 - 8:
                note('O_car_radius_short' + tag, i, payback=pr // 4, ours=near[0][4])
            if (i, z) in drive:
                theirs, ours = pm.object_block(i, z, True), us.object_block(i, h_units(z))
                if theirs and not ours:
                    note('O_car_drives_through' + ('_drawn' if near else '_undrawn') + tag, i, payback=theirs)
                elif ours and not theirs:
                    note('O_car_stopped_where_payback_is_not' + tag, i, ours=ours)
    summary = dict(grid=g, foot_floors=len(foot), drive_floors=len(drive), counts=dict(sorted(counts.items())),
                   examples={k: v for k, v in sorted(examples.items())}, payback_runs=len(pm.cache))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'grid%02d.json' % g), 'w') as f:
        json.dump(summary, f, indent=1)
    with open(os.path.join(out, 'grid%02d_marks.json' % g), 'w') as f:
        json.dump(marks, f)
    return summary, marks, us


GROUPS = (('person', 'P_'), ('car', 'C_'), ('height', 'H_'), ('objects', 'O_'), ('water', 'W_'))
PALETTE = ((255, 40, 40), (255, 170, 0), (255, 240, 60), (0, 230, 120), (0, 200, 255), (70, 110, 255),
           (190, 90, 255), (255, 110, 200), (255, 255, 255), (150, 255, 0), (160, 100, 60), (0, 140, 140))


def picture(path, us, marks, g, group):
    """One class group's mismatches over the city (grey by height; edges as bars on the edge,
    cells filled), with the counts."""
    from PIL import Image, ImageDraw
    name, prefix = group
    S = 8
    im = Image.new('RGB', (N * S + 330, N * S), (16, 16, 20))
    d = ImageDraw.Draw(im)
    for i, c in enumerate(us.cells):
        x, y = divmod(i, N)
        v = max(30, min(200, 70 + c[1] // 24))
        rgb = (v, v, v) if us.deck(i) is None else (v, v, min(255, v + 50))
        d.rectangle([x * S, y * S, x * S + S - 1, y * S + S - 1], fill=rgb)
    for i, es in us.fence.items():
        x, y = divmod(i, N)
        for e, _ in es:
            _bar(d, x, y, e, S, (40, 90, 40), 1)
    merged = collections.defaultdict(list)            # (a street object's type left out)
    for k, v in marks.items():
        if k.startswith(prefix):
            merged[re.sub(r'_type\d+$', '', k)] += v
    keys = sorted(merged, key=lambda k: -len(merged[k]))
    ly = 6
    for n, k in enumerate(keys):
        col = PALETTE[n % len(PALETTE)]
        for i, e in merged[k]:
            x, y = divmod(i, N)
            if e < 0:
                d.rectangle([x * S + 1, y * S + 1, x * S + S - 2, y * S + S - 2], outline=col)
            else:
                _bar(d, x, y, e, S, col, 2)
        d.rectangle([N * S + 8, ly, N * S + 18, ly + 10], fill=col)
        d.text((N * S + 24, ly), '%s %d' % (k, len(merged[k])), fill=(230, 230, 230))
        ly += 15
    d.text((N * S + 8, N * S - 30), 'grid %d: %s (x right, y down)' % (g, name), fill=(230, 230, 230))
    im.save(path)


def _bar(d, x, y, e, S, col, w):
    if e == 0:
        d.rectangle([x * S, y * S, x * S + S - 1, y * S + w - 1], fill=col)
    elif e == 2:
        d.rectangle([x * S, y * S + S - w, x * S + S - 1, y * S + S - 1], fill=col)
    elif e == 1:
        d.rectangle([x * S + S - w, y * S, x * S + S - 1, y * S + S - 1], fill=col)
    else:
        d.rectangle([x * S, y * S, x * S + w - 1, y * S + S - 1], fill=col)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('--ram', required=True, help='PREFIX of PREFIX.ewram / PREFIX.iwram')
    ap.add_argument('--grid', type=int, default=0)
    ap.add_argument('--world', help="our world.bin (default: mkworld's merged world of the grid)")
    ap.add_argument('--out', default='colcheck_out')
    ap.add_argument('--png', action='store_true')
    ap.add_argument('--unpainted', action='store_true', help="Payback's own grid, without mksolo's phones")
    a = ap.parse_args()
    rom_bytes = open(a.rom, 'rb').read()
    rom = payback_rom(rom_bytes, not a.unpainted)
    build_dir = tempfile.mkdtemp(prefix='colcheck')
    world = a.world
    if not world:
        data, _ = world_for(rom_bytes, a.grid, rom)
        world = os.path.join(build_dir, 'world%02d.bin' % a.grid)
        open(world, 'wb').write(data)
    summary, marks, us = check(rom_bytes, a.ram, a.grid, world, a.out, build_dir, rom=rom)
    print(json.dumps(dict(grid=a.grid, foot=summary['foot_floors'], drive=summary['drive_floors'],
                          counts=summary['counts']), indent=1))
    if a.png:
        for grp in GROUPS:
            picture(os.path.join(a.out, 'grid%02d_%s.png' % (a.grid, grp[0])), us, marks, a.grid, grp)


if __name__ == '__main__':
    main()

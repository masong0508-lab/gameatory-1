"""Fox Station's rooms as meshes: the walls, floor and props of each room in the model format the renderer reads
(MVert, MFace, one normal a face), the walker's boxes, the camera nodes and the places to use. station.py packs them; this
file also draws a room the way the game would, for a quick look (python3 tools/content/stgeo.py [room] [out.png]).

Room frame: x to the right, y up, z away from the camera, in units (a cell of the city is 1024). Every camera looks along +z
(no yaw), so the D-pad means the same on every screen and a cut never turns the controls round. A room is a shell seen from
inside with its front wall left out (the camera stands outside it, so the wall's inward face is culled by the renderer),
and props are boxes with a top, a front and two sides: nothing is ever seen from behind. Limits: 56 vertices (the renderer's
per-model stack), 40 faces, 8 boxes for the walker.
"""
import math
import sys

# palette.h
M_ROAD, M_KERB, M_GRASS, M_PLAZA, M_CONCRETE, M_GLASS, M_BRICK, M_TEAL, M_CREAM, M_STEEL = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
M_SKY, M_CAR, M_ACCENT, M_SHIP, M_GLOW, M_STUNT = 0, 11, 12, 13, 14, 15
MF_TWO, MF_GLOW, MF_IN, MF_BACK = 1, 2, 4, 8
MAX_V, MAX_F, MAX_BOX = 56, 90, 8
STRIP = 1200                           # the widest a wall, a floor or a stripe is drawn in one piece     # a part's points; faces in a room (the frame's polygons); boxes the walker bumps
H = 1300                                   # ceiling height


class Mesh:
    """Parts of at most 56 vertices each (the renderer keeps a model's points on its stack); a primitive never straddles two."""
    def __init__(self, name, sx=1.0):
        self.name = name
        self.sx = sx                       # the x of every primitive but the shell is scaled by this (rooms were drawn 2500 wide)
        self.parts = [([], [])]            # (vertices, faces) with the faces' indices local to the part
        self.boxes = []

    @property
    def v(self):
        return [p for part in self.parts for p in part[0]]

    @property
    def f(self):
        return [f for part in self.parts for f in part[1]]

    def _room_for(self, n):
        if len(self.parts[-1][0]) + n > MAX_V:
            self.parts.append(([], []))
        return self.parts[-1]

    def quad(self, pts, mat, normal, flags=0):
        # (the rasteriser's edge steps overflow on a polygon thousands of units wide at close range: wide quads go in strips)
        xs = [p[0] for p in pts]
        if len(pts) == 4 and max(xs) - min(xs) > STRIP:
            if abs(pts[1][0] - pts[0][0]) + abs(pts[3][0] - pts[2][0]) > abs(pts[3][0] - pts[0][0]) + abs(pts[2][0] - pts[1][0]):
                pts = [pts[1], pts[2], pts[3], pts[0]]             # (so that p0->p3 and p1->p2 are the edges that run along x)
            n = -(-(max(xs) - min(xs)) // STRIP)
            lerp = lambda p, q, t: tuple(p[i] + (q[i] - p[i]) * t // n for i in range(3))
            for k in range(n):
                self.quad([lerp(pts[0], pts[3], k), lerp(pts[1], pts[2], k), lerp(pts[1], pts[2], k + 1), lerp(pts[0], pts[3], k + 1)], mat, normal, flags)
            return
        vs, fs = self._room_for(len(pts))
        base = len(vs)
        vs.extend(tuple(int(c) for c in p) for p in pts)
        fs.append((len(pts), mat, flags, list(range(base, base + len(pts))), normal))

    def prop(self, x0, x1, z0, z1, h, top, side, front=None, glow=False, y0=0, solid=True):
        """A box from y0 to h: top, front (toward the camera), left and right sides, the front glowing if asked."""
        front = side if front is None else front
        x0, x1 = int(x0 * self.sx), int(x1 * self.sx)
        vs, fs = self._room_for(8)
        b = len(vs)
        a = list(range(b, b + 8))
        vs.extend(((x0, y0, z0), (x1, y0, z0), (x1, h, z0), (x0, h, z0), (x0, y0, z1), (x1, y0, z1), (x1, h, z1), (x0, h, z1)))
        fs.append((4, top, 0, [a[3], a[2], a[6], a[7]], (0, 1, 0)))
        fs.append((4, front, MF_GLOW if glow else 0, [a[0], a[1], a[2], a[3]], (0, 0, -1)))
        fs.append((4, side, 0, [a[0], a[3], a[7], a[4]], (-1, 0, 0)))
        fs.append((4, side, 0, [a[1], a[5], a[6], a[2]], (1, 0, 0)))
        if solid and h > 120:
            self.boxes.append((x0, z0, x1, z1))

    def floor_mark(self, x0, x1, z0, z1, mat, glow=False):
        """A flat patch on the floor (a rug, a pad, a stripe), sorted by its far edge so it lies on the floor."""
        y = 3
        x0, x1 = int(x0 * self.sx), int(x1 * self.sx)
        self.quad([(x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0)], mat, (0, 1, 0), MF_BACK | (MF_GLOW if glow else 0))

    def wall_mark(self, x0, x1, y0, y1, z, mat, glow=False):
        """A flat patch on the back wall (a window, a screen, a poster)."""
        x0, x1 = int(x0 * self.sx), int(x1 * self.sx)
        # (one that starts at the floor sorts by its middle: by its far edge it ties with the wall behind it, and the tie is lost)
        self.quad([(x0, y0, z), (x0, y1, z), (x1, y1, z), (x1, y0, z)], mat, (0, 0, -1), (MF_BACK if y0 >= 100 else 0) | (MF_GLOW if glow else 0))

    def shell(self, hx, hz, floor, wall, ceil, side=None):
        """The room's walls: floor, back wall, left and right walls, ceiling (the front is left open)."""
        side = wall if side is None else side
        h = H
        self.quad([(-hx, 0, -hz), (-hx, 0, hz), (hx, 0, hz), (hx, 0, -hz)], floor, (0, 1, 0), MF_BACK | MF_IN)
        self.quad([(-hx, 0, hz), (-hx, h, hz), (hx, h, hz), (hx, 0, hz)], wall, (0, 0, -1), MF_BACK | MF_IN)
        self.quad([(-hx, 0, -hz), (-hx, h, -hz), (-hx, h, hz), (-hx, 0, hz)], side, (1, 0, 0), MF_BACK | MF_IN)
        self.quad([(hx, 0, hz), (hx, h, hz), (hx, h, -hz), (hx, 0, -hz)], side, (-1, 0, 0), MF_BACK | MF_IN)
        self.quad([(-hx, h, -hz), (hx, h, -hz), (hx, h, hz), (-hx, h, hz)], ceil, (0, -1, 0), MF_BACK | MF_IN)


class Room:
    def __init__(self, name, hx, hz, title, sx=1.0):
        self.name, self.title = name, title
        self.hx, self.hz = hx, hz
        self.sx = sx
        self.mesh = Mesh(name, sx)
        self.cams = []      # (px, py, pz, ty, tz, x0, x1, z0, z1)
        self.uses = []      # (kind, arg, x, z, r, sx, sz, label, ly, flags)
        self.crew = []      # (crew, x, z, yaw, model, body, legs, fur)
        self.ceil_c, self.floor_c = M_ROAD, M_ROAD
        self.zmin = ZMIN

    def cam(self, px, py, pz, ty, tz, x0, x1, z0, z1):
        self.cams.append((px, py, pz, ty, tz, x0, x1, z0, z1))

    def use(self, kind, arg, x, z, r, label='', ly=700, sx=0, sz=0, flags=0):
        k = self.sx
        self.uses.append((kind, arg, int(x * k), z, r, int(sx * k), sz, label, ly, flags))

    def person(self, crew, x, z, yaw=0, model=0, body=M_TEAL, legs=M_ROAD, fur=0):
        self.crew.append((crew, int(x * self.sx), z, yaw, model, body, legs, fur))


# use kinds (station.h U_*)
U_DOOR, U_TALK, U_TERM, U_PAD = 1, 2, 3, 4
# terminals (station.h T_*)
T_NONE, T_BRIEF, T_CONTRACT, T_TRAVEL, T_SHOP, T_PAINT, T_MAP, T_TROPHY, T_COMMS, T_MSGS, T_RECAP, T_LOG, T_QUICK = range(13)
# rooms
HANGAR, HUB, OPS, WORKSHOP, NAV, LOUNGE, TROPHY, COMMS, QUARTERS = range(9)
CREW = {'ROOK': 1, 'PIP': 2, 'NOVA': 3, 'DUSTY': 4, 'QUILL': 5, 'JUNO': 6, 'KESTREL': 7, 'SABLE': 8}
# fur (a crew's ears, tail and muzzle, in cream and stunt red so they read on any body colour and the grass): bit 0 ears (16 vertices), bit 1 tail (8), bit 2 muzzle (8); <= 24 each
FUR_EARS, FUR_TAIL, FUR_MUZZLE = 1, 2, 4

HX, HZ = 1500, 1000                 # an ordinary room, 3000 by 2000 (drawn 2500 wide: SX stretches it)
SX = 1.2
STD_CAM = lambda r, cx=0: (cx, 1100, -r.hz - 450, 250, 600)      # one camera just outside the open front


def std_room(name, title, floor, wall, ceil, side=None, hx=HX, hz=HZ, sx=SX):
    r = Room(name, hx, hz, title, sx)
    r.mesh.shell(hx, hz, floor, wall, ceil, side)
    r.ceil_c, r.floor_c = ceil, floor
    return r


ZMIN = -560                          # the nearest the walker may come: below that the floor is under the bottom of the picture


def door_front(r, to, label, sx=0):
    """The way out: a lit pad on the near floor, the trigger on it, and where one arrives from `to` (well clear of it)."""
    r.mesh.floor_mark(sx - 260, sx + 260, -650, -380, M_ACCENT, glow=True)
    r.use(U_DOOR, to, sx, -515, 270, label=label, ly=40, sx=sx, sz=140)


def build_rooms():
    rooms = {}

    # ---- the hub: a long hall, the hangar door at its left end, a door in the back wall for each room ----
    hx, hz = 2800, 1000
    r = std_room('HUB', 'FOX STATION', M_ROAD, M_TEAL, M_ROAD, M_STEEL, hx=hx, hz=hz, sx=1.0)
    m = r.mesh
    for i, x in enumerate((-2000, -1330, -660, 10, 680, 1350, 2020)):      # seven doors, 670 apart
        m.wall_mark(x - 230, x + 230, 0, 760, hz - 4, M_GLASS if i != 6 else M_ROAD)
        m.wall_mark(x - 260, x + 260, 760, 800, hz - 4, M_ACCENT)
    m.floor_mark(-hx + 40, -hx + 560, -300, 300, M_ACCENT)               # the hangar pad
    m.floor_mark(-2400, 2400, -60, 60, M_CONCRETE)                        # a stripe along the hall
    m.prop(-hx + 60, -hx + 260, 520, 920, 520, M_STEEL, M_CONCRETE)       # lockers at the left end
    m.prop(hx - 260, hx - 60, 520, 920, 520, M_STEEL, M_CONCRETE)
    m.prop(-120, 120, -460, -260, 300, M_ACCENT, M_STEEL)                 # a bench
    r.person(8, -1000, 300, 0, 0, M_TEAL, M_ROAD, FUR_EARS | FUR_TAIL)   # Sable, the ground liaison
    r.cam(-1500, 1120, -hz - 520, 160, 300, -hx, -750, -hz, hz)
    r.cam(0, 1120, -hz - 520, 160, 300, -1050, 1050, -hz, hz)
    r.cam(1500, 1120, -hz - 520, 160, 300, 750, hx, -hz, hz)
    r.use(U_DOOR, HANGAR, -hx + 300, 0, 300, label='HANGAR', ly=700, sx=-hx + 760, sz=0)
    labels = ['OPS', 'SHOP', 'NAV', 'REST', 'HALL', 'COMMS', 'BUNKS']
    for i, x in enumerate((-2000, -1330, -660, 10, 680, 1350, 2020)):
        r.use(U_DOOR, OPS + i, x, hz - 180, 260, label=labels[i], ly=860, sx=x, sz=hz - 760)
    rooms[HUB] = r

    # ---- ops: the briefing table, a board of contracts, Rook ----
    r = std_room('OPS', 'OPS', M_ROAD, M_STEEL, M_ROAD, M_STEEL)
    m = r.mesh
    m.floor_mark(-700, 700, 160, 900, M_STEEL)
    m.prop(-520, 520, 330, 730, 430, M_TEAL, M_STEEL)                      # the table
    m.prop(-420, 420, 560, 700, 520, M_GLASS, M_STEEL, glow=True, y0=430, solid=False)   # the map on it
    m.prop(-1180, -760, 850, 950, 880, M_STEEL, M_ROAD, M_GLASS, glow=True)    # the contracts board
    m.prop(760, 1180, 850, 950, 880, M_STEEL, M_ROAD, M_GLASS, glow=True)      # the travel list
    m.wall_mark(-300, 300, 600, 1000, 1000 - 4, M_STEEL)
    m.wall_mark(-260, 260, 640, 960, 1000 - 6, M_GLOW, glow=True)
    r.cam(*STD_CAM(r), -r.hx, r.hx, -r.hz, r.hz)
    r.person(1, -240, 200, 0, 0, M_BRICK, M_ROAD, FUR_EARS | FUR_TAIL)
    r.use(U_TERM, T_CONTRACT, -970, 730, 340, label='CONTRACTS', ly=980)
    r.use(U_TERM, T_TRAVEL, 970, 730, 340, label='TRAVEL', ly=980)
    r.use(U_TERM, T_BRIEF, 0, 130, 280, label='BRIEFING', ly=700)
    door_front(r, HUB, 'HUB')
    rooms[OPS] = r

    # ---- the workshop: Pip, the bench of upgrades, the paint rack ----
    r = std_room('WORKSHOP', 'WORKSHOP', M_CONCRETE, M_CREAM, M_ROAD, M_CONCRETE)
    m = r.mesh
    m.floor_mark(-500, 500, 100, 800, M_ROAD)                              # the Arwing's pad
    m.prop(-1180, -700, 800, 960, 520, M_ACCENT, M_STEEL, M_STEEL)       # the bench
    m.prop(-1180, -980, 330, 700, 880, M_STEEL, M_ROAD, M_GLASS, glow=True)   # upgrades console
    m.prop(700, 1180, 800, 960, 560, M_ACCENT, M_STEEL)                  # parts shelf
    m.prop(960, 1180, 330, 700, 880, M_STEEL, M_ROAD, M_GLASS, glow=True)      # paint console
    m.prop(-160, 160, 360, 700, 340, M_STEEL, M_ROAD)                    # a nose cone on a stand
    m.wall_mark(-450, 450, 500, 1000, 1000 - 4, M_STEEL)
    r.cam(*STD_CAM(r), -r.hx, r.hx, -r.hz, r.hz)
    r.person(2, 420, 380, 36000, 1, M_STUNT, M_STEEL, FUR_EARS)
    r.use(U_TERM, T_SHOP, -1060, 200, 360, label='UPGRADES', ly=1000)
    r.use(U_TERM, T_PAINT, 1060, 200, 360, label='PAINT', ly=1000)
    door_front(r, HUB, 'HUB')
    rooms[WORKSHOP] = r

    # ---- nav: the holo table in the middle, Nova ----
    r = std_room('NAV', 'NAV', M_ROAD, M_ROAD, M_ROAD, M_STEEL)
    m = r.mesh
    m.floor_mark(-800, 800, 100, 900, M_STEEL)
    m.prop(-600, 600, 330, 750, 380, M_STEEL, M_ROAD)
    m.prop(-500, 500, 400, 680, 440, M_GLASS, M_GLASS, M_GLOW, glow=True, y0=380, solid=False)
    m.prop(-1180, -900, 780, 960, 800, M_STEEL, M_ROAD, M_GLASS, glow=True)
    m.prop(900, 1180, 780, 960, 800, M_STEEL, M_ROAD, M_GLASS, glow=True)
    m.wall_mark(-1000, 1000, 380, 1050, 1000 - 4, M_ROAD)
    m.wall_mark(-940, 940, 420, 1010, 1000 - 6, M_GLASS, glow=True)
    r.cam(*STD_CAM(r), -r.hx, r.hx, -r.hz, r.hz)
    r.person(3, 760, 360, 30000, 0, M_STEEL, M_ROAD, FUR_EARS | FUR_TAIL)
    r.use(U_TERM, T_MAP, 0, 120, 360, label='HOLO MAP', ly=760)
    door_front(r, HUB, 'HUB')
    rooms[NAV] = r

    # ---- the lounge: a couch, a long window on the stars, Dusty ----
    r = std_room('LOUNGE', 'LOUNGE', M_PLAZA, M_BRICK, M_ROAD, M_BRICK)
    m = r.mesh
    m.floor_mark(-800, 800, 150, 850, M_BRICK)
    m.wall_mark(-900, 900, 380, 1000, 1000 - 4, M_STEEL)
    m.wall_mark(-860, 860, 420, 960, 1000 - 6, M_ROAD, glow=False)
    m.prop(-700, 700, 760, 940, 360, M_TEAL, M_TEAL, M_STEEL)          # the couch
    m.prop(-700, 700, 900, 960, 640, M_TEAL, M_STEEL)                   # its back
    m.prop(-360, 360, 300, 560, 300, M_CREAM, M_STEEL)                   # a low table
    m.prop(850, 1120, 700, 960, 940, M_STEEL, M_ROAD, M_GLASS, glow=True)    # the recap screen
    m.prop(-1150, -960, 160, 360, 420, M_ACCENT, M_STEEL)                # a stool
    r.cam(*STD_CAM(r), -r.hx, r.hx, -r.hz, r.hz)
    r.person(4, -560, 520, 20000, 1, M_ACCENT, M_STEEL, FUR_EARS | FUR_TAIL)
    r.use(U_TERM, T_RECAP, 985, 560, 340, label='RECAP', ly=1000)
    door_front(r, HUB, 'HUB')
    rooms[LOUNGE] = r

    # ---- the trophy hall: plinths with medals along the wall, Quill ----
    r = std_room('TROPHIES', 'TROPHY HALL', M_CREAM, M_CREAM, M_ROAD, M_STEEL)
    m = r.mesh
    m.floor_mark(-500, 500, -600, 900, M_ACCENT)
    for k, x in enumerate((-1000, -400, 200, 800)):
        m.prop(x, x + 220, 700, 920, 520, M_STEEL, M_CONCRETE, M_STEEL)
        m.prop(x + 40, x + 180, 740, 880, 700, M_ACCENT, M_ACCENT, M_ACCENT, glow=True, y0=520, solid=False)
    m.prop(-1180, -1000, 160, 700, 300, M_STEEL, M_ROAD)
    r.cam(*STD_CAM(r), -r.hx, r.hx, -r.hz, r.hz)
    r.person(5, 640, 320, 33000, 0, M_BRICK, M_ROAD, FUR_EARS | FUR_MUZZLE)
    r.use(U_TERM, T_TROPHY, -560, 560, 380, label='MEDALS', ly=760)
    door_front(r, HUB, 'HUB')
    rooms[TROPHY] = r

    # ---- comms: banks of screens, Juno ----
    r = std_room('COMMS', 'COMMS', M_ROAD, M_STEEL, M_ROAD, M_STEEL)
    m = r.mesh
    m.prop(-1180, -520, 820, 960, 760, M_STEEL, M_ROAD, M_GLASS, glow=True)
    m.prop(520, 1180, 820, 960, 760, M_STEEL, M_ROAD, M_GLASS, glow=True)
    m.prop(-260, 260, 700, 960, 420, M_STEEL, M_ROAD)
    m.prop(-200, 200, 760, 940, 620, M_GLASS, M_GLASS, M_GLOW, glow=True, y0=420, solid=False)
    m.wall_mark(-700, 700, 700, 1100, 1000 - 4, M_ROAD)
    m.prop(-1180, -980, 200, 520, 640, M_STEEL, M_ROAD, M_GLASS, glow=True)
    r.cam(*STD_CAM(r), -r.hx, r.hx, -r.hz, r.hz)
    r.person(6, -520, 500, 3000, 0, M_TEAL, M_STEEL, FUR_EARS | FUR_MUZZLE)
    r.use(U_TERM, T_COMMS, 0, 520, 380, label='COMMS', ly=760)
    r.use(U_TERM, T_MSGS, -1060, 380, 330, label='MESSAGES', ly=760)
    door_front(r, HUB, 'HUB')
    rooms[COMMS] = r

    # ---- the quarters: a bunk, a desk, Kestrel (after chapter 7 the door opens) ----
    r = std_room('QUARTERS', 'QUARTERS', M_PLAZA, M_CONCRETE, M_ROAD, M_CONCRETE)
    m = r.mesh
    m.floor_mark(-700, 700, 150, 800, M_STEEL)
    m.prop(-1180, -600, 600, 960, 360, M_STUNT, M_STEEL, M_STEEL)       # the bunk
    m.prop(500, 1180, 800, 960, 520, M_ACCENT, M_STEEL)                # a desk
    m.prop(700, 1000, 840, 940, 880, M_STEEL, M_ROAD, M_GLASS, glow=True, y0=520, solid=False)
    m.wall_mark(-300, 300, 520, 1020, 1000 - 4, M_STEEL)
    m.wall_mark(-260, 260, 560, 980, 1000 - 6, M_STUNT)
    r.cam(*STD_CAM(r), -r.hx, r.hx, -r.hz, r.hz)
    r.person(7, 320, 420, 30000, 2, M_GLASS, M_STEEL, FUR_EARS | FUR_TAIL)
    r.use(U_TERM, T_LOG, 0, 130, 340, label='KESTREL LOG', ly=700)
    door_front(r, HUB, 'HUB')
    rooms[QUARTERS] = r

    return rooms


# ---- a look at a room, as the game would draw it ----
BASE = [None, (7, 7, 10), (19, 19, 18), (6, 17, 7), (21, 17, 12), (20, 20, 21), (8, 15, 25), (23, 10, 8), (5, 21, 20),
        (27, 25, 18), (12, 13, 17), (5, 10, 29), (31, 27, 4), (28, 28, 29), (31, 14, 3), (31, 6, 11)]
LIGHT = (12, 17, 22, 27)
SUN = (6553, 13107, 7372)


def shade(mat, normal, glow):
    if glow:
        lv = 3
    else:
        n = [int(round(c * 16384)) for c in normal]
        l = (n[0] * SUN[0] + n[1] * SUN[1] + n[2] * SUN[2]) >> 14
        lv = min(3, (l + 16384) >> 13)
    r, g, b = BASE[mat]
    return tuple(min(255, int(c * LIGHT[lv] / 27 * 255 / 31)) for c in (r, g, b))


def project(p, cam, focal=136):
    px, py, pz, ty, tz = cam[:5]
    fx, fy, fz = 0, ty - py, tz - pz
    n = math.sqrt(fy * fy + fz * fz)
    fy, fz = fy / n, fz / n
    d = (p[0] - px, p[1] - py, p[2] - pz)
    z = d[1] * fy + d[2] * fz
    y = d[1] * fz - d[2] * fy             # up vector (0, fz, -fy)
    x = d[0]
    return x, y, z


def clip_near(poly, near=24):
    out = []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        if a[2] >= near:
            out.append(a)
        if (a[2] >= near) != (b[2] >= near):
            t = (near - a[2]) / (b[2] - a[2])
            out.append(tuple(a[k] + (b[k] - a[k]) * t for k in range(3)))
    return out


def preview(room, cam, out, walker=None, crew=True):
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (240, 160), (8, 8, 12))
    d = ImageDraw.Draw(img)
    polys = []
    m = room.mesh
    for vs, fs in m.parts:
      for (n, mat, flags, idx, normal) in fs:
        pts = [project(vs[i], cam) for i in idx]
        # back-face cull as model_draw does: normal . (v0 - cam) < 0
        v0 = vs[idx[0]]
        c = (v0[0] - cam[0], v0[1] - cam[1], v0[2] - cam[2])
        if normal[0] * c[0] + normal[1] * c[1] + normal[2] * c[2] >= 0:
            continue
        pts = clip_near(pts)
        if len(pts) < 3:
            continue
        zs = [p[2] for p in pts]
        key = max(zs) if flags & MF_BACK else sum(zs) / len(zs)
        polys.append((key, [(120 + 136 * p[0] / p[2], 80 - 136 * p[1] / p[2]) for p in pts], shade(mat, normal, flags & MF_GLOW)))
    if crew:
        for (cid, x, z, yaw, model, body, legs) in room.crew:
            polys.append((project((x, 0, z), cam)[2], 'person', (x, z, body)))
    if walker:
        polys.append((project((walker[0], 0, walker[1]), cam)[2], 'person', (walker[0], walker[1], M_ACCENT)))
    for key, pts, col in sorted(polys, key=lambda t: -t[0]):
        if pts == 'person':
            x, z, body = col
            a, b = project((x, 0, z), cam), project((x, 330, z), cam)
            if a[2] > 24:
                sx, sy0, sy1 = 120 + 136 * a[0] / a[2], 80 - 136 * a[1] / a[2], 80 - 136 * b[1] / a[2]
                w = 70 / a[2] * 136 / 2
                d.rectangle([sx - w / 2, sy1, sx + w / 2, sy0], fill=shade(body, (0, 0, -1), False))
        else:
            d.polygon(pts, fill=col)
    img = img.resize((720, 480), Image.NEAREST)
    img.save(out)


def check(rooms):
    for k, r in rooms.items():
        m = r.mesh
        assert len(m.f) <= MAX_F, '%s: %d faces' % (r.name, len(m.f))
        assert len(m.boxes) <= MAX_BOX, '%s: %d boxes' % (r.name, len(m.boxes))
        assert len(m.parts) <= 4, '%s: %d parts' % (r.name, len(m.parts))
        assert 1 <= len(r.cams) <= 3, r.name
        for vs, fs in m.parts:
            assert len(vs) <= MAX_V
            for f in fs:
                assert all(0 <= i < len(vs) for i in f[3]) and 3 <= f[0] <= 6
            for x, y, z in vs:
                assert abs(x) < 32000 and abs(y) < 32000 and abs(z) < 32000
        for c in r.cams:
            assert -32768 <= min(c) and max(c) < 32768
        # every way in puts the walker inside the walls, clear of every box and of every door's reach (no bounce, no stuck start)
        for u in r.uses:
            if u[0] != U_DOOR:
                continue
            kind, to, ux, uz, ur, sx, sz = u[:7]
            t = rooms.get(to)
            if t is None:
                continue
            for d in t.uses:
                if d[0] == U_DOOR and d[1] == k:                  # the door of `to` that leads back here: where one arrives is its (sx, sz)
                    bx, bz = d[5], d[6]
                    assert abs(bx) <= t.hx - 130 and ZMIN <= bz <= t.hz - 130, '%s: arrival (%d, %d) outside the walls' % (t.name, bx, bz)
                    for x0, z0, x1, z1 in t.mesh.boxes:
                        assert not (x0 - 130 < bx < x1 + 130 and z0 - 130 < bz < z1 + 130), '%s: arrival inside a box' % t.name
                    for o in t.uses:
                        if o[0] == U_DOOR and o is not d:
                            assert (o[2] - bx) ** 2 + (o[3] - bz) ** 2 > (o[4] + 100) ** 2, '%s: arrival inside the reach of door %s' % (t.name, o[7])
                    assert (d[2] - bx) ** 2 + (d[3] - bz) ** 2 > (d[4] + 100) ** 2, '%s: arrival on its own door (%s)' % (t.name, d[7])


if __name__ == '__main__':
    rooms = build_rooms()
    check(rooms)
    which = sys.argv[1] if len(sys.argv) > 1 else None
    for k, r in rooms.items():
        print('%-9s %3d verts %2d faces %d parts %d boxes %d cams %d uses %d crew' % (r.name, len(r.mesh.v), len(r.mesh.f), len(r.mesh.parts), len(r.mesh.boxes),
                                                                         len(r.cams), len(r.uses), len(r.crew)))
        if which and (which == r.name or which == 'all'):
            for i, c in enumerate(r.cams):
                preview(r, c, '/tmp/st_%s_%d.png' % (r.name.lower(), i) if len(sys.argv) < 3 else sys.argv[2].replace('.png', '_%s%d.png' % (r.name.lower(), i)),
                        walker=(0, c[7] + 300 if len(c) > 7 else 0))

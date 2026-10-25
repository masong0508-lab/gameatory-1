"""Builds Stunt Fox: python3 build.py "Payback (Europe) (En,Fr,De,Es,It).gba" -o stuntfox.gba

The Payback ROM provides the city layout (and the cartridge logo); it is read, never copied
into this repository. Needs clang and ld.lld.

With --merge it builds Stunt Fox into Payback itself instead: the output is the player's own
Payback ROM, patched so that Payback's game runs as before but Stunt Fox draws the world
(see src/merge.c). --bps also writes that as a patch.
"""
import argparse
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src')
BUILD = os.path.join(HERE, 'build')
GEN = os.path.join(BUILD, 'gen')
sys.path.insert(0, os.path.join(HERE, 'tools'))
sys.path.insert(0, os.path.join(HERE, '..', 'payback-mod'))
import mkworld   # noqa: E402
import mkassets  # noqa: E402
import mkpal    # noqa: E402
import mksolo   # noqa: E402
import mklogo   # noqa: E402
import mkmusic  # noqa: E402
import mkmip    # noqa: E402
import mkplanet  # noqa: E402
import mkconst  # noqa: E402
import s2build  # noqa: E402
import mkradio  # noqa: E402

CFLAGS = ['--target=armv4t-none-eabi', '-mcpu=arm7tdmi', '-O2', '-ffreestanding', '-fno-builtin',
          '-nostdlib', '-ffunction-sections', '-Wall', '-Wno-unused-function']
ARM_FILES = {'render.c', 'citydraw.c', 'fx.c', 'physics.c', 'model.c'}  # hot code: ARM, IWRAM


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit('failed: ' + ' '.join(cmd))
    if r.stderr.strip():
        sys.stderr.write(r.stderr)
    return r.stdout


def build(payback, out):
    os.makedirs(GEN, exist_ok=True)
    rom = open(payback, 'rb').read()
    data, stats = mkworld.build(rom)
    open(os.path.join(GEN, 'world.bin'), 'wb').write(data)
    mkassets.main(os.path.join(GEN, 'tables.c'))
    objs = []
    sources = [os.path.join(SRC, f) for f in sorted(os.listdir(SRC))
               if f.endswith(('.c', '.s')) and f not in MERGE_ONLY]
    sources.append(os.path.join(GEN, 'tables.c'))
    for src in sources:
        name = os.path.basename(src)
        obj = os.path.join(BUILD, name + ('.iw.o' if name in ARM_FILES else '.o'))
        if src.endswith('.s'):
            run(['clang', '--target=armv4t-none-eabi', '-mcpu=arm7tdmi', '-c', src, '-o', obj,
                 '-Wa,-I' + GEN])
        else:
            mode = '-marm' if os.path.basename(src) in ARM_FILES else '-mthumb'
            run(['clang'] + CFLAGS + [mode, '-I' + SRC, '-c', src, '-o', obj])
        objs.append(obj)
    elf = os.path.join(BUILD, 'stuntfox.elf')
    run(['ld.lld', '-T', os.path.join(SRC, 'gba.ld'), '--gc-sections', '-e', '_start', '-o', elf] + objs)
    run(['llvm-objcopy', '-O', 'binary', elf, out])
    img = bytearray(open(out, 'rb').read())
    img[4:0xa0] = rom[4:0xa0]                     # logo from the player's own cartridge
    img[0xa0:0xac] = b'STUNT FOX\0\0\0'
    img[0xac:0xb0] = b'BSFE'
    img[0xb0:0xb2] = b'01'
    img[0xb2] = 0x96
    img[0xb3:0xbd] = bytes(10)
    img[0xbd] = (-sum(img[0xa0:0xbd]) - 0x19) & 0xff
    while len(img) % 4:
        img.append(0)
    open(out, 'wb').write(img)
    return stats, len(img)


# --merge: Stunt Fox inside Payback
MERGE_ONLY = {'merge.c', 'keyhook.s', 'guard.s', 'rechash.s', 'traffic.c', 'tex.c', 'texrun.s', 'draw2d.c',
              'spacegame.c', 'settings.c', 'title.c', 'props.c', 'ragdoll.c', 'radio.c', 'radiodec.s', 'cart32.s',
              'planet.c'}
MERGE_ONLY |= set(s2build.S2_SOURCES)         # (stage 2: tools/s2build.py)
MERGE_SKIP = {'main.c', 'hud.c', 'crt0.s', 'assets.s'}   # (the worlds go above 8 MiB instead)
NWORLD = 11                                   # Payback's level grids (src/world.h)
GBA = 0x08000000
MERGE_CALLS = (0x080177fa, 0x08017692)        # Payback's two calls to its world renderer
MERGE_RENDERER = 0x0800adac
MERGE_KEYS = 0x0800e9a8                       # Payback's call to its keypad reader
MERGE_READER = 0x08072f68
MERGE_FADE = 0x0806c82c                       # Payback's palette fade, called from 23 places
MERGE_MENU = (0x080249be, 0x08037fe4)         # after a level: Payback asks its game menu what next
MERGE_FADES = ((0x080777ec, 'sf_fade_add', 3),   # its other fades: + a level (toward white) ...
               (0x080779bc, 'sf_fade_mul', 6),   # ... and * a level (toward black), twice
               (0x08077f44, 'sf_fade_mul2', None))
MERGE_TITLE = (0x0803874e, 0x080294c4)        # the title menu's 'Set language' line: our settings page
MERGE_ZOOM = 0x0803c75a                       # the + fade that whitens the zoom into a new level: sf_fade_zoom
MERGE_BASE = 0x081b0000                       # see src/merge.ld
# Payback's crime report (0x0806cb18, from 13 places: every death, a bust, mission ends...) is
# written as Payback writes it (the man's counts added to the game's totals, then cleared) but
# never put on the phone: "You committed ..." and "You are charged with ..." alike. The movs
# before its three queue calls becomes a branch to its return.
MERGE_NO_REPORT = (0x0806ccaa, 0x2001, 0xe007)   # movs r0, #1 -> b 0x0806ccbc
# Payback's big flying-letter banner (0x08039bc8, void; r0-r3 are dead after it at each site) on a
# death or a bonus: TOASTED!/NUKED!, SPLATTERED!/OBLITERATED!, WASTED!, FLATTENED!, DROWNED!,
# BUSTED!, IRONY BONUS!, COPKILLER BONUS!. Each bl becomes two nops; the lives, respawn, saved
# score and bonus score around them stay. (Game over!, Level complete!, Mission complete!/failed!,
# Kill frenzy!, New high score! and the phone's ANSWER THE PHONE are other calls, untouched.)
MERGE_BANNER = 0x08039bc8
MERGE_NO_POPUPS = (0x08011198, 0x0801163c,    # Splattered! / Obliterated!
                   0x0801178a,                # Toasted! / Nuked!
                   0x08011fea,                # Wasted!
                   0x08016232, 0x08016766,    # Flattened!
                   0x0801a03a, 0x08020832,    # Drowned!
                   0x0802174e, 0x080217ca,    # Busted!
                   0x080161c6, 0x080166fa,    # Irony bonus!
                   0x0800053e, 0x0800082e)    # Copkiller bonus!
MERGE_PHYS = (0x080193f4, 0x080174ec)         # its entity update's call to its physics (sf_phys)
MERGE_PICK = ((0x0803cf6a, 0x0803cf74), 0x0807801c)   # the mission place chooser's two draws of its rand (sf_pick_rand)
# Payback's frame limiter (0x0802471c) waits until a frame has lasted as long as the one before
# it, then leaves that wait out of the game time it counts (dt): the wait was lost time. It now
# waits only for its 2-vblank minimum (dt is clamped to 4..19 ticks of 1/120 s either way).
MERGE_PACE = (0x0802472c, 0x6826, 0x2604)     # ldr r6, [r4] (the last dt) -> movs r6, #4
# Payback's effect records (sparks, debris, the puff of a pick-up: 0x02015bc4, slot n of the four kinds at 0x90 * n + 0x24 * kind)
# are written by one emitter (0x08073bb0, from 15 places) up to slot 99, but our `scr` lies over slots 64..99 (src/merge.ld): a
# burst that finds 64 of a kind alive (an explosion chain, a medal's pop-up) overwrote our polygon lists, and the frame never ended.
# Our renderer draws none of them: the emitter now stops at slot 63 (cmp r3, #99 -> cmp r3, #63; a full kind drops the burst).
MERGE_FX_CAP = (0x08073c06, 0x2b63, 0x2b3f)
# The car radio (src/radio.c): Payback's sound interrupt calls its sequencer and its music pass
# through sf_seq and sf_mus; its radio's two picks draw 1 + random(6) and play through sf_play.
MERGE_RADIO_CALLS = ((0x08075d4a, 0x08075dd0, 'sf_seq'), (0x08075da8, 0x0807c800, 'sf_mus'),
                     (0x0807747a, 0x08076c98, 'sf_play'), (0x080774ce, 0x08076c98, 'sf_play'))
MERGE_RADIO_PICKS = (0x08077472, 0x080774c6)  # movs r0, #3 (tools/mkmusic.py) -> movs r0, #6
# The remixes make the cartridge 32 MiB, whose EEPROM is only at 0x0DFFFF00 up. Payback's EEPROM
# library builds 0x0D000000 in four places (movs rN, #0xd0; lsls rN, rN, #20) in functions that
# have saved lr: each becomes a call that loads 0x0DFFFF00 (src/cart32.s).
MERGE_EEPROM = ((0x0807c4c6, 4), (0x0807c5be, 4), (0x0807c64e, 0), (0x0807c676, 0))
EEPROM_LIB = (0x0807c3ac, 0x0807c800)         # (and nowhere else in it)
ROM_SIZE = 0x2000000
# Getting out of a vehicle (0x0800ea04) Payback tries a door, the other door and one more spot,
# and refuses where all three are water: the driver went down with the car and drowned. Now he
# gets out at the last of them, into the water, and swims (merge.c, swimming).
MERGE_WATER_EXIT = (0x0800eebe, (0x2301, 0x425c, 0x46a3))   # fp = -1 (nowhere) -> nops
PB_IWRAM = 0x087d9ab8                         # the ROM image of Payback's IWRAM code
PB_HOT_WORDS = (0x030030b0, 0x03003c04, 0x03003c08, 0x03003c0c, 0x03003c10)   # as in merge.c
# Payback's VIEW REPLAY recorder (0x08072234) writes a bit stream from heap0 + 0x20000 =
# 0x0203c720 on, about 9 bytes a second of play: after four minutes it reached our variables
# (keep, src/merge.ld) and credits became recorder bits, later the game froze. Its limit and
# both clears of its buffer now stop short of keep (a replay then holds about four minutes).
MERGE_REPLAY_CAP = ((0x0807243c, 0x389c, 0x8c0),   # the limit
                    (0x0807291c, 0x38a4, 0x8c8),   # the clears: a new recording ...
                    (0x08072a44, 0x38a4, 0x8c8))   # ... and a level starting
# Three of Payback's health writes, its street objects' harm to a vehicle, its police's "is the
# player wanted" and a knock's push on a velocity go through src/guard.s (a bl over the two
# instructions there), and its call to the wall response of a moving vehicle through sf_hook_wall:
# so the man under the Arwing and our car are not hurt (or arrested) by what they cannot see, the
# man on foot is not ended from full health by one blast or shot we do not draw (sf_guard in
# src/merge.c), and our car feels the knocks Payback gives its record (sf_knock).
# Payback's cap on the people and traffic it adds: ldr r1,=0x02001dfc; ldr r3,[r1]; adds r3,#8;
# cmp r3,#20; ble; movs r3,#20 (then cmp r2,r3), at its spawner's door and twice inside. sf_hook_traffic (keyhook.s)
# returns it moved by GAME SETTINGS' traffic.
MERGE_TRAFFIC_CAP = (0x080039fc, 0x08003b20, 0x08003b98)
MERGE_GUARDS = ((0x08000b96, (0x9f17, 0x8010), 'sf_hook_blast'),   # an explosion's harm
                (0x080140da, (0x1a42, 0x8022), 'sf_hook_knock'),   # a knock's harm, to one
                (0x08014178, (0x1b72, 0x8022), 'sf_hook_knock2'),  # ... and to the other
                (0x08015134, (0x880a, 0x1a10), 'sf_hook_shot'),    # a shot's harm
                (0x08021472, (0x5618, 0x2802), 'sf_hook_police'),  # the police: wanted > 2?
                (0x0800147a, (0x3268, 0x8810), 'sf_hook_objhit'),  # a street object's harm, to a vehicle or a man
                (0x08013bbc, (0x1855, 0x8005), 'sf_hook_kick'),    # a knock's push, to one: x ...
                (0x08013bec, (0x1855, 0x8005), 'sf_hook_kick'),    # ... and y
                (0x08013c74, (0x1884, 0x802c), 'sf_hook_kick2'),   # ... and to the other, x ...
                (0x08013ca6, (0x1884, 0x802c), 'sf_hook_kick2'))   # ... and y
MERGE_WALL = (0x0801759e, 0x0807050c)        # (inside the physics sf_phys may skip: see merge.c)
# Payback's keypad reader answers a press of SELECT by queuing the phone's past lines again
# (0x0803962c). It would do that every tick of a hold of SELECT (our Arwing call), as the
# decoded SELECT it checks is held off: sf_keys replays the past on a tap itself (merge.c).
MERGE_SELECT = (0x08073134, 0x0803962c)
# Payback's vehicles as we draw them. Its descriptors (0x08354af4 + k * 0x3c, k 0..127, class 0:
# k 0..27 and the police at 45..48) give its knock (0x080135bc: 4 circles of radius +0xe, from +0x14
# behind the record to +0x12 ahead) and its wall sweep their size, in its units (2 to ours): sized
# for its sprites, about twice the models we draw centred on the record, so it knocked traffic a car
# length before the bumpers met. They get the size of the model merge.c draws for each instead (half
# width, ahead, behind, at its scale), read from merge.c's looks[] and picked as its vehicle_kind
# picks; the helicopter keeps Payback's (merge.c meets it as drawn, car_bump). car.c sizes the car we
# drive from the same bytes.
MODEL_SIZE = {'saloon': (114, 235, 235), 'limo': (114, 340, 340), 'pickup': (120, 245, 245),
              'sport': (127, 238, 245), 'van': (120, 245, 245), 'bus': (132, 520, 520), 'tank': (152, 300, 300)}
VEH_DESC, VEH_HELI, VEH_LOOK0 = 0x08354af4, 0x08354ef0, 0x1a


def merge_looks():
    """merge.c's looks[] (model, scale) and vehicle_kind's police picks"""
    import re
    src = open(os.path.join(SRC, 'merge.c')).read()
    body = re.search(r'VehicleLook looks\[\] = \{(.*?)\n\};', src, re.S).group(1)
    looks = [(m.group(1), int(m.group(2)) or 256) for m in re.finditer(r'\{&mdl_(\w+),\s*\w+,\s*(\d+),', body)]
    pol = {m.group(1): int(m.group(2)) for m in re.finditer(r'#define (POLICE_CAR|POLICE_VAN) (\d+)', src)}
    kind = re.search(r'static int vehicle_kind\(const u8 \*e\)\n\{(.*?)\n\}', src, re.S).group(1)
    assert 'POLICE_CAR' in kind and ('POLICE_VAN' in kind) == ('POLICE_VAN' in pol), 'vehicle_kind changed: mirror it here'
    return looks, pol


MERGE_CRATE_FX = (0x080034f6, 0x08075640)    # a crate opened: its burst, through src/props.c sf_crate_fx
FILM_PLAYER = 0x03001660                      # Payback's film player (IWRAM), see src/title.c
FILM_CALLS = ((0x080236bc, 0x086f7cd8, 'sf_studio_film'),   # (literals: the film, then the player)
              (0x08025530, 0x08700ccc, 'sf_intro_film'))
LOGO_DESC = 0x08099444                        # Payback's menu logo: u16 w, u8 h, u8 0, u32 offset
LOGO_BASE = 0x0809d694                        # (from here); it is drawn at x = 56 in the menu
LOGO_X = ((0x08038392, 0x2138),               # movs r1, #56 (the menu)
          (0x0803081c, 0x3980),               # subs r1, #128 (the credits' last page, ...
          (0x08030832, 0x3940))               # subs r1, #64   ... from its centre, two ways)


def vehicle_sizes(d, mark):
    """our drawn sizes over Payback's vehicle descriptors (as merge.c's vehicle_kind draws them)"""
    looks, pol = merge_looks()
    n = 0
    for k in range(128):
        a = VEH_DESC - GBA + k * 0x3c
        if d[a + 0x26] != 0 or a + GBA == VEH_HELI:
            continue
        look = d[a + 0x38] - VEH_LOOK0
        assert 0 <= look < 26, 'expected a vehicle look at %x' % (a + GBA)
        if d[a + 0x27]:                                  # the police
            look = pol['POLICE_VAN'] if look == pol.get('POLICE_VAN') else pol['POLICE_CAR']
        elif look >= len(looks):
            look = 0
        name, scale = looks[look]
        hw, fr, rr = (2 * v * scale // 256 for v in MODEL_SIZE[name])
        mark(a + GBA + 0xe, 2, 'vehicle %d width' % k)
        mark(a + GBA + 0x12, 4, 'vehicle %d length' % k)
        struct.pack_into('<h', d, a + 0xe, hw)
        struct.pack_into('<hh', d, a + 0x12, fr, rr)
        n += 1
    assert n == 31, 'expected 31 vehicle descriptors, found %d' % n


def bl_target(d, site):
    """Where the Thumb bl at site goes, or None."""
    h1, h2 = struct.unpack_from('<HH', d, site - 0x08000000)
    if (h1 & 0xf800) != 0xf000 or (h2 & 0xf800) != 0xf800:
        return None
    off = (h1 & 0x7ff) << 12 | (h2 & 0x7ff) << 1
    off -= (1 << 23) if off & (1 << 22) else 0
    return site + 4 + off


NAME = 'Star-FlyBack'
TEXT_AREA = (0x300000, 0x360000)              # Payback's game text, all five languages


def rename(d):
    """Star-FlyBack everywhere Payback says its own name: the cartridge title and every line of
    game text that names it (in place: a line that grows drops its last sentence or words)."""
    d[0xa0:0xac] = NAME.upper().encode()
    d[0xbd] = -(sum(d[0xa0:0xbd]) + 0x19) & 0xff  # header checksum
    n = 0
    lo, hi = TEXT_AREA
    for word in (b'Payback', b'PayBack', b'PAYBACK'):
        new_word = (NAME.upper() if word.isupper() else NAME).encode()
        at = d.find(word, lo, hi)
        while at >= 0:
            start = d.rfind(b'\0', lo, at) + 1
            end = d.index(b'\0', at)
            old = bytes(d[start:end])
            line = old.replace(word, new_word)
            if len(line) > len(old):
                cut = line.rfind(b'. ', 0, len(old) - 1)
                if cut > len(old) // 2:
                    line = line[:cut + 1]
                else:
                    cut = line.rfind(b' ', 0, len(old) + 1)
                    line = line[:cut] if cut > 0 else line[:len(old)]
            d[start:end] = line + bytes(len(old) - len(line))
            n += 1
            at = d.find(word, end, hi)
    return n


def build_merge(payback, out, bps_out=None, remixes=True):
    from paybackmod.rom import PaybackRom, NEW_BASE, OLD_TABLE_START, OLD_TABLE_END
    from paybackmod import bps
    os.makedirs(GEN, exist_ok=True)
    orig = open(payback, 'rb').read()
    rom = PaybackRom(orig)                    # checks it is Payback (Europe); moves the column table
    mksolo.offer_every_map(rom.d)             # every map in single-player rampage ...
    phones = mksolo.add_phones(rom)           # ... with phones (so missions and a target) on each
    loops = s2build.pre_world(rom, orig)      # (stage 2: an arena regrids its map and stamps its loops)
    mkmusic.drop_song(rom.d, bl_target)       # one song less (tools/mkmusic.py)
    # a world for each of Payback's maps, above its 8 MiB (after the addressable columns)
    grids = [rom.painted.get(m) or rom.grid(m) for m in range(NWORLD)]
    where, stats, worlds = [], [], []
    for m in range(NWORLD):
        data, st = mkworld.build(orig, merge=True, level=m, rom=rom, loops=loops)
        where.append(GBA + rom.alloc(data))
        stats.append(st)
        worlds.append(data)
    print('worlds: %d KiB at 0x%08x-0x%08x' % ((GBA + rom.free - where[0]) // 1024, where[0], GBA + rom.free))
    mkassets.main(os.path.join(GEN, 'tables.c'))
    mkconst.main(os.path.join(GEN, 'consttab.c'), os.path.join(GEN, 'tables.c'))   # (in ROM: RAM is short)
    mkpal.main(orig, os.path.join(GEN, 'pbtables.c'))
    nmip = mkmip.main(orig, worlds, os.path.join(GEN, 'pbmip.c'))   # (every map's ground tiles)
    mkplanet.main(orig, worlds, os.path.join(GEN, 'planetdata.c'))      # (each map's planet look)
    mklogo.main(orig, os.path.join(GEN, 'logo.c'))
    with open(os.path.join(GEN, 'merge_sig.c'), 'w') as f:
        f.write('/* generated by build.py: where each map\'s world is, and cells of each map with their\n'
                '   column pointers (cells no other map shares, without objects: a ringing phone\'s cell\n'
                '   points into RAM) */\n')
        f.write('#include "../../src/gba.h"\nconst u32 *const world_table[%d] = {%s};\n'
                % (NWORLD, ', '.join('(const u32 *)0x%08x' % a for a in where)))
        f.write('const u32 merge_sig[%d][32][2] = {\n' % NWORLD)
        for m, grid in enumerate(grids):
            cells, k = [], 0
            while len(cells) < 32:
                c = (k * 509 + 77) % len(grid)
                k += 1
                col = rom.column(grid[c])
                if not (col[0] | col[1]) and all(g[c] != grid[c] for g in grids if g is not grid):
                    cells.append(c)
            f.write('    {%s},\n' % ', '.join('{%d, 0x%08x}' % (c, rom.col_ptr(grid[c])) for c in cells))
        f.write('};\n')
    s2src, s2ld = s2build.pre_link(rom, orig, GEN)   # (stage 2: its blobs above 8 MiB, its sources)
    objs = []
    sources = [os.path.join(SRC, f) for f in sorted(os.listdir(SRC))
               if f.endswith(('.c', '.s')) and f not in MERGE_SKIP and f not in s2build.S2_SOURCES]
    sources += [os.path.join(GEN, 'tables.c'), os.path.join(GEN, 'merge_sig.c'), os.path.join(GEN, 'pbtables.c'),
                os.path.join(GEN, 'logo.c'), os.path.join(GEN, 'pbmip.c'), os.path.join(GEN, 'planetdata.c'), os.path.join(GEN, 'consttab.c')] + s2src
    for src in sources:
        name = os.path.basename(src)
        obj = os.path.join(BUILD, 'merge', name + '.o')
        os.makedirs(os.path.dirname(obj), exist_ok=True)
        if src.endswith('.s'):
            run(['clang', '--target=armv4t-none-eabi', '-mcpu=arm7tdmi', '-c', src, '-o', obj,
                 '-Wa,-I' + GEN])
        else:
            run(['clang'] + CFLAGS + ['-mthumb', '-DMERGE', '-I' + SRC, '-I' + GEN, '-c', src, '-o', obj])
        objs.append(obj)
    elf = os.path.join(BUILD, 'merge', 'stuntfox-merge.elf')
    run(['ld.lld', '-T', os.path.join(SRC, 'merge.ld'), '--gc-sections', '-e', 'sf_frame', '-o', elf] + s2ld + objs)
    blob = os.path.join(BUILD, 'merge', 'stuntfox-merge.bin')
    run(['llvm-objcopy', '-O', 'binary', elf, blob])
    code = open(blob, 'rb').read()
    nm = subprocess.run(['llvm-nm', elf], capture_output=True, text=True).stdout
    sym = {p[2]: int(p[0], 16) for p in (l.split() for l in nm.splitlines()) if len(p) == 3}
    o = MERGE_BASE - 0x08000000
    assert OLD_TABLE_START <= o and o + len(code) <= OLD_TABLE_END, 'Stunt Fox does not fit'
    rom.d[o:o + len(code)] = code

    patched = {}                              # every halfword we change in Payback's code: once only

    def mark(at, n, what):
        for h in range(at, at + n, 2):
            assert h not in patched, '%x: %s, and %s already' % (h, what, patched[h])
            patched[h] = what

    def put_bl(site, new):
        mark(site, 4, 'bl %x' % new)
        off = (new & ~1) - (site + 4)
        struct.pack_into('<HH', rom.d, site - 0x08000000, 0xf000 | ((off >> 12) & 0x7ff), 0xf800 | ((off >> 1) & 0x7ff))

    def redirect(site, old, new):
        assert bl_target(rom.d, site) == old, 'expected a call to %x at %x' % (old, site)
        put_bl(site, new)
    for site in MERGE_CALLS:
        redirect(site, MERGE_RENDERER, sym['sf_frame'])
    redirect(MERGE_KEYS, MERGE_READER, sym['sf_keyhook'])
    redirect(MERGE_MENU[0], MERGE_MENU[1], sym['sf_menu'])
    redirect(MERGE_TITLE[0], MERGE_TITLE[1], sym['sf_title_opts'])
    assert bytes(rom.d[0x326fd6:0x326fe2]) == b'Set language', 'expected the language line'
    rom.d[0x326fd6:0x326fe2] = b'Game options'       # (the same length)
    fades = [a for a in range(0x08000000, 0x08100000, 2) if bl_target(rom.d, a) == MERGE_FADE]
    assert len(fades) == 23, 'expected 23 calls to the palette fade, found %d' % len(fades)
    for site in fades:
        redirect(site, MERGE_FADE, sym['sf_fade'])
    for fn, hook, count in MERGE_FADES:        # (so none of them can flash the screen white)
        sites = [a for a in range(0x08000000, 0x08100000, 2) if bl_target(rom.d, a) == fn]
        assert count is None or len(sites) == count, 'expected %d calls to %x, found %d' % (count, fn, len(sites))
        for site in sites:
            redirect(site, fn, sym['sf_fade_zoom' if site == MERGE_ZOOM else hook])
    redirect(*MERGE_PHYS, sym['sf_phys'])
    for site in MERGE_PICK[0]:
        redirect(site, MERGE_PICK[1], sym['sf_pick_rand'])
    for site, old, hook in MERGE_RADIO_CALLS:
        redirect(site, old, sym[hook])
    for site in MERGE_RADIO_PICKS:
        assert struct.unpack_from('<H', rom.d, site - GBA)[0] == 0x2003, 'expected the radio pick at %x' % site
        struct.pack_into('<H', rom.d, site - GBA, 0x2006)
    eep = [a for a in range(*EEPROM_LIB, 2) if rom.d[a - GBA + 1] >> 3 == 4 and rom.d[a - GBA] == 0xd0
           and struct.unpack_from('<H', rom.d, a - GBA + 2)[0] == 0x0500 | (rom.d[a - GBA + 1] & 7) * 9]
    assert eep == [a for a, _ in MERGE_EEPROM], 'EEPROM addresses not as expected: %s' % eep
    for site, r in MERGE_EEPROM:
        assert rom.d[site - GBA + 1] & 7 == r
        off = (sym['sf_eep_r%d' % r] & ~1) - (site + 4)
        struct.pack_into('<HH', rom.d, site - GBA, 0xf000 | ((off >> 12) & 0x7ff), 0xf800 | ((off >> 1) & 0x7ff))
    for (site, old, new), what in ((MERGE_NO_REPORT, 'crime report'), (MERGE_PACE, 'frame limiter'), (MERGE_FX_CAP, 'effect cap')):
        assert struct.unpack_from('<H', rom.d, site - 0x08000000)[0] == old, '%s not at %x' % (what, site)
        mark(site, 2, what)
        struct.pack_into('<H', rom.d, site - 0x08000000, new)
    site, ops = MERGE_WATER_EXIT
    assert struct.unpack_from('<3H', rom.d, site - 0x08000000) == ops, 'expected the water exit at %x' % site
    mark(site, 6, 'water exit')
    struct.pack_into('<3H', rom.d, site - 0x08000000, 0x46c0, 0x46c0, 0x46c0)
    fx0, fx_slot = 0x02015bc4, 0x90               # (the emitter's last slot is the immediate it compares against: scr must lie past it)
    assert sym['__scr'] >= fx0 + fx_slot * ((MERGE_FX_CAP[2] & 0xff) + 1), 'scr lies over the effect records the emitter can reach'
    for lit, old, new in MERGE_REPLAY_CAP:
        assert struct.unpack_from('<I', rom.d, lit - 0x08000000)[0] == old, 'expected the replay length at %x' % lit
        mark(lit, 4, 'replay cap')
        struct.pack_into('<I', rom.d, lit - 0x08000000, new)
    for site, ops, hook in MERGE_GUARDS:
        assert struct.unpack_from('<HH', rom.d, site - 0x08000000) == ops, 'expected other code at %x' % site
        put_bl(site, sym[hook])
    for site in MERGE_NO_POPUPS:
        assert bl_target(rom.d, site) == MERGE_BANNER, 'expected a call to the banner at %x' % site
        mark(site, 4, 'pop-up')
        struct.pack_into('<HH', rom.d, site - 0x08000000, 0x46c0, 0x46c0)
    for site in MERGE_TRAFFIC_CAP:
        a = site - 0x08000000
        assert rom.d[a + 1] == 0x49 and bytes(rom.d[a + 2:a + 14]) == bytes.fromhex('0b680833142b00dd14239a42'), 'expected the traffic cap at %x' % site
        put_bl(site, sym['sf_hook_traffic'])
        mark(site + 4, 8, 'traffic cap')
        struct.pack_into('<HHHH', rom.d, site + 4 - 0x08000000, 0x46c0, 0x46c0, 0x46c0, 0x46c0)
    redirect(MERGE_WALL[0], MERGE_WALL[1], sym['sf_hook_wall'])
    redirect(MERGE_SELECT[0], MERGE_SELECT[1], sym['sf_hook_select'])
    vehicle_sizes(rom.d, mark)
    redirect(MERGE_CRATE_FX[0], MERGE_CRATE_FX[1], sym['sf_crate_fx'])
    # stage 2: its redirects, then the checks (memguard: nothing of ours on Payback's goals, commands, mission
    # state or replay recorder, keep's headroom; pbapi_check; lint_text)
    s2build.post_link(rom, sym, elf, redirect,
                      lambda fn: [a for a in range(GBA, 0x08100000, 2) if bl_target(rom.d, a) == fn], orig, s2src)
    hs, he, hl = sym['__hot_start'], sym['__hot_end'], sym['__hot_lma']   # merge.c's hot_mine
    assert hs <= PB_HOT_WORDS[0] and PB_HOT_WORDS[-1] + 4 <= he - 4, "Payback's words are not inside hot"
    for a in (hs + 4, he - 4):
        o, p = hl - MERGE_BASE + a - hs, PB_IWRAM - 0x08000000 + a - 0x03000000
        assert a not in PB_HOT_WORDS and code[o:o + 4] != rom.d[p:p + 4], 'hot_mine: %x is no sign of us' % a
    for k in ('4', '6', '7', '8', '10', '11', '2'):   # merge.c tells ours from Payback's by their first word
        ks, ke, kl = sym['__hot%s_start' % k], sym['__hot%s_end' % k], sym['__hot%s_lma' % k]
        o, p = kl - MERGE_BASE, PB_IWRAM - 0x08000000 + ks - 0x03000000
        assert ke > ks and code[o:o + 4] != rom.d[p:p + 4], 'hot%s: %x is no sign of us' % (k, ks)
    for lit, film, hook in FILM_CALLS:         # no films: they flash white (src/title.c)
        a = lit - 0x08000000
        assert struct.unpack_from('<II', rom.d, a) == (film, FILM_PLAYER), 'expected a film call at %x' % lit
        mark(lit + 4, 4, 'film')
        struct.pack_into('<I', rom.d, a + 4, sym[hook] | 1)
    a = LOGO_DESC - 0x08000000                 # the STAR-FLYBACK logo (tools/mklogo.py)
    assert struct.unpack_from('<HBBI', rom.d, a) == (128, 63, 0, 0xd9a), 'expected the menu logo'
    mark(LOGO_DESC, 8, 'logo')
    struct.pack_into('<HBBI', rom.d, a, mklogo.LOGO_W, mklogo.LOGO_H, 0, sym['sf_menu_logo'] - LOGO_BASE)
    for site, op in LOGO_X:                    # wider: drawn further left, still centred
        assert struct.unpack_from('<H', rom.d, site - 0x08000000)[0] == op
        mark(site, 2, 'logo x')
        imm = (op & 0xff) + (1 if op >> 11 == 7 else -1) * ((mklogo.LOGO_W - 128) // 2)
        assert 0 <= imm < 256
        struct.pack_into('<H', rom.d, site - 0x08000000, (op & 0xff00) | imm)
    rename(rom.d)
    try:                                       # the radio's remixes (renders cached in build/radio)
        if not remixes:
            raise mkradio.Unavailable('--no-remixes')
        streams, rep = mkradio.blob(payback, BUILD)
    except mkradio.Unavailable as e:           # (sf_play finds no streams: Payback's songs only)
        print('radio: no remixes (%s); the radio plays Payback\'s own songs' % e)
        streams = None
    assert len(rom.d) <= mkradio.BASE - GBA
    if streams:
        rom.d += bytes(ROM_SIZE - len(rom.d))
        rom.d[mkradio.BASE - GBA:mkradio.BASE - GBA + len(streams)] = streams
        print('radio: %d KiB of remixes at 0x%08x-%s, %s' % (len(streams) // 1024, mkradio.BASE, rep['end'],
              ', '.join('song %s %.2f bits/sample' % (n, v['bits_per_sample']) for n, v in rep['songs'].items())))
    img = rom.data()
    open(out, 'wb').write(img)
    if bps_out:
        moves = [(NEW_BASE, OLD_TABLE_START, OLD_TABLE_END - OLD_TABLE_START)]
        patch = bps.encode(orig, img, moves)
        assert bps.apply(orig, patch) == img
        open(bps_out, 'wb').write(patch)
    stats[0]['phones'] = sum(len(v) for v in phones.values())
    stats[0]['mip tiles'] = nmip
    return stats, len(code)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('payback')
    ap.add_argument('-o', '--out', default='stuntfox.gba')
    ap.add_argument('--merge', action='store_true', help='build Stunt Fox into Payback itself')
    ap.add_argument('--bps', help='with --merge: also write a BPS patch for the Payback ROM')
    ap.add_argument('--no-remixes', action='store_true', help="with --merge: the radio plays Payback's own songs "
                    'only (no remixes to render: quicker, needs no numpy or scipy)')
    a = ap.parse_args()
    if a.merge:
        stats, size = build_merge(a.payback, a.out, a.bps, not a.no_remixes)
        print('wrote %s (Payback with Stunt Fox, %d KiB of code and data), world 0 %s' % (a.out, size // 1024, stats[0]))
    else:
        stats, size = build(a.payback, a.out)
        print('wrote %s (%d KiB), world %s' % (a.out, size // 1024, stats))

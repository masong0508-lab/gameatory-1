"""The models are ROM const now (the keep diet's second round): what start-up built in RAM in the old build is, model by
model, what the new build has in ROM, each one dereferenced: the corner and face tables, the normals, the counts and the
radius. Also the asteroids, trimmed to the 12 there are (rocks, rock_m).

    SP=<harness folder> OLD_ROM= OLD_ELF= NEW_ROM= NEW_ELF= python3 tests/s2/models.py      (from stuntfox/)

Both ROMs are started the same way (the harness's merged_state) and run on a little; the old ELF says where the Model
structs are in RAM, the new ELF where they are in ROM. A model's tables (v, f, normal) lie in ROM in both builds.
"""
import json
import os
import struct
import subprocess
import sys

START = os.getcwd()
SP = os.environ['SP']
sys.path.insert(0, SP + '/work')
os.chdir(SP + '/work')
from retro import Emu          # noqa: E402
from mstate import merged_state  # noqa: E402

MODELS = ['mdl_car', 'mdl_arwing', 'mdl_hub', 'mdl_ring', 'mdl_rock', 'mdl_ped', 'mdl_heli', 'mdl_bay', 'mdl_raider',
          'mdl_carrier', 'mdl_pod', 'mdl_medal', 'mdl_crate', 'mdl_gate', 'mdl_beacon', 'mdl_boom',
          'mdl_saloon', 'mdl_limo', 'mdl_pickup', 'mdl_sport', 'mdl_van', 'mdl_bus', 'mdl_tank', 'mdl_stand',
          'mdl_stride_a', 'mdl_stride_b', 'mdl_punch', 'mdl_swim', 'mdl_hero']
MVERT, MFACE, N3 = 6, 9, 6               # sizeof the three table entries
STRUCT = 16


def symbols(elf):
    out = {}
    for line in subprocess.run(['llvm-nm', '-S', elf], capture_output=True, text=True).stdout.splitlines():
        p = line.split()
        if len(p) == 4:
            out[p[3]] = (int(p[0], 16), int(p[1], 16))
        elif len(p) == 3:
            out[p[2]] = (int(p[0], 16), 0)
    return out


def dump(rom, elf, ram):
    """One ROM, started and run on: the Model structs (RAM, or ROM when ram is false), the asteroids."""
    sym = symbols(elf)
    e = Emu('gba', rom)
    merged_state(e)
    e.run(30)
    img = open(rom, 'rb').read()
    out = {'models': {}}
    for n in MODELS:
        a, size = sym[n]
        raw = bytes(e.read(a, size)) if ram else img[a - 0x08000000:a - 0x08000000 + size]
        out['models'][n] = raw.hex()
    out['rocks'] = bytes(e.read(sym['rocks'][0], 12 * 16)).hex()
    out['nrocks'] = bytes(e.read(sym['nrocks'][0], 4)).hex()
    out['rock_m'] = bytes(e.read(sym['rock_m'][0], 12 * 36)).hex()
    out['rocks_size'] = sym['rocks'][1]
    out['rock_m_size'] = sym['rock_m'][1]
    return out


def deref(rom_img, raw):
    """A model struct's bytes -> its contents, the tables read from the ROM image."""
    got = []
    for i in range(len(raw) // STRUCT):
        v, f, nv, nf, rad, nrm = struct.unpack_from('<IIBBhI', raw, i * STRUCT)
        for p in (v, f, nrm):
            assert 0x08000000 <= p < 0x0a000000, 'a table outside ROM: %08x' % p
        rd = lambda p, n: rom_img[p - 0x08000000:p - 0x08000000 + n]
        got.append((nv, nf, rad, rd(v, nv * MVERT), rd(f, nf * MFACE), rd(nrm, nf * N3)))
    return got


def main():
    if len(sys.argv) > 1:
        print(json.dumps(dump(sys.argv[1], sys.argv[2], sys.argv[3] == '1')))
        return
    old_rom, old_elf, new_rom, new_elf = (os.path.join(START, os.environ[k]) for k in ('OLD_ROM', 'OLD_ELF', 'NEW_ROM', 'NEW_ELF'))

    def child(rom, elf, ram):
        out = subprocess.run([sys.executable, os.path.abspath(__file__), rom, elf, '1' if ram else '0'], capture_output=True,
                             text=True, env=dict(os.environ, PYTHONPATH=''))
        if out.returncode:
            sys.exit(out.stderr)
        return json.loads(out.stdout.strip().splitlines()[-1])
    old, new = child(old_rom, old_elf, True), child(new_rom, new_elf, False)
    ro, rn = open(old_rom, 'rb').read(), open(new_rom, 'rb').read()
    so, sn = symbols(old_elf), symbols(new_elf)
    bad = tot = 0
    for n in MODELS:
        a, b = deref(ro, bytes.fromhex(old['models'][n])), deref(rn, bytes.fromhex(new['models'][n]))
        same = a == b and len(a) == so[n][1] // STRUCT
        bad += not same
        tot += sum(m[1] for m in b)
        print('%-12s %d model(s), %3d faces  %s' % (n, len(b), sum(m[1] for m in b), 'identical' if same else 'DIFFERENT'))
        if not same:
            for k, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    print('   model %d: old nv %d nf %d r %d, new nv %d nf %d r %d; v %s f %s normals %s' % (
                        k, x[0], x[1], x[2], y[0], y[1], y[2], x[3] == y[3], x[4] == y[4], x[5] == y[5]))
        if 0x0203d000 <= sn[n][0] < 0x02040000:
            bad += 1
            print('%s is still in keep' % n)
    print('%d faces compared' % tot)
    for k in ('rocks', 'nrocks', 'rock_m'):
        same = old[k] == new[k]
        bad += not same
        print('%-12s identical to the first 12 of the old %d' % (k, so[k][1]) if same else '%-12s DIFFERENT' % k)
    ok = new['rocks_size'] == 12 * 16 and new['rock_m_size'] == 12 * 36
    bad += not ok
    print('rocks %d bytes, rock_m %d bytes (old %d, %d)' % (new['rocks_size'], new['rock_m_size'], old['rocks_size'], old['rock_m_size']))
    print('models: %s' % ('ALL IDENTICAL' if not bad else '%d DIFFERENT' % bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

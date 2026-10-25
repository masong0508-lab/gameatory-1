"""The keep diet's proof: what start-up built in RAM in the old build is, bit for bit, what the new build has in ROM.

    SP=<harness folder> OLD_ROM= OLD_ELF= NEW_ROM= NEW_ELF= python3 tests/s2/consttab.py

Both ROMs are started the same way (the harness's merged_state) and run on a little; the old ELF says where
ring_v, ring_f, gate_v, gate_f, stars, rock_w (and rock_m, which stays in RAM and turns with the asteroids
once the camera is high, so it is read at once) are in its RAM, the new ELF where the generated tables
(consttab.c) are in its ROM. Also the face normals (nbuf, tnbuf, hero_n), which were ROM tables before too.
"""
import json
import os
import subprocess
import sys

START = os.getcwd()
SP = os.environ['SP']
sys.path.insert(0, SP + '/work')
os.chdir(SP + '/work')
from retro import Emu          # noqa: E402
from mstate import merged_state  # noqa: E402


def symbols(elf):
    out = {}
    for line in subprocess.run(['llvm-nm', '-S', elf], capture_output=True, text=True).stdout.splitlines():
        p = line.split()
        if len(p) == 4:
            out[p[3]] = (int(p[0], 16), int(p[1], 16))
        elif len(p) == 3:
            out[p[2]] = (int(p[0], 16), 0)
    return out


def dump(rom, elf, want):
    """One ROM, started and run on: what is in its memory at the symbols in want (name -> bytes asked for)."""
    sym = symbols(elf)
    e = Emu('gba', rom)
    merged_state(e)
    e.run(30)
    return {n: e.read(sym[n][0], k).hex() for n, k in want.items()}


def main():
    # (the emulator core is one library with one game in it: each ROM is read in a process of its own)
    old_rom, old_elf, new_rom, new_elf = (os.path.join(START, os.environ[k]) for k in ('OLD_ROM', 'OLD_ELF', 'NEW_ROM', 'NEW_ELF'))
    if len(sys.argv) > 1:
        rom, elf, want = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
        print(json.dumps(dump(rom, elf, want)))
        return
    so, sn = symbols(old_elf), symbols(new_elf)
    tables = (('ring_v', 'gen_ring_v', None), ('ring_f', 'gen_ring_f', None), ('gate_v', 'gen_gate_v', None),
              ('gate_f', 'gen_gate_f', None), ('stars', 'gen_stars', None), ('rock_w', 'gen_rock_w', 12 * 12))
    want_old = {r: g_n or sn[g][1] for r, g, g_n in tables}
    want_old['rock_m'] = 12 * 36
    want_new = {g: g_n or sn[g][1] for r, g, g_n in tables}
    want_new['rock_m'] = 12 * 36

    def child(rom, elf, want):
        out = subprocess.run([sys.executable, os.path.abspath(__file__), rom, elf, json.dumps(want)],
                             capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=''))
        if out.returncode:
            sys.exit(out.stderr)
        return {k: bytes.fromhex(v) for k, v in json.loads(out.stdout.strip().splitlines()[-1]).items()}
    old, new = child(old_rom, old_elf, want_old), child(new_rom, new_elf, want_new)
    bad = 0
    # (old RAM table, new ROM table, bytes that count: rock_w had 16 slots, 12 are used)
    for ram, gen, _ in tables:
        a, b = old[ram], new[gen]
        same = a == b
        bad += not same
        print('%-12s %4d bytes  %s' % (gen, len(b), 'identical' if same else 'DIFFERENT'))
        if not same:
            i = next(k for k in range(len(b)) if a[k] != b[k])
            print('   first difference at byte %d: old %02x, new %02x' % (i, a[i], b[i]))
    # the yaw array makes rock_m: both builds' rock_m (12 x 36 bytes), read before an asteroid has turned
    same = old['rock_m'] == new['rock_m']
    bad += not same
    print('%-12s %4d bytes  %s' % ('rock_m', 12 * 36, 'identical' if same else 'DIFFERENT'))
    # nothing else of these is left in the new build's RAM
    for gone in ('ring_v', 'ring_f', 'gate_v', 'gate_f', 'stars', 'rock_w'):
        if gone in sn and 0x0203d000 <= sn[gone][0] < 0x02040000:
            bad += 1
            print('%s is still in keep' % gone)
    # face normals: ROM before and after
    ro, rn = open(old_rom, 'rb').read(), open(new_rom, 'rb').read()
    for g in ('gen_nbuf', 'gen_tnbuf', 'gen_hero_n'):
        a = ro[so[g][0] - 0x08000000:][:so[g][1]]
        b = rn[sn[g][0] - 0x08000000:][:sn[g][1]]
        bad += a != b or len(a) != len(b) or not a
        print('%-12s %4d bytes  %s' % (g, len(b), 'identical' if a == b and a else 'DIFFERENT'))
    print('consttab: %s' % ('ALL IDENTICAL' if not bad else '%d DIFFERENT' % bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()

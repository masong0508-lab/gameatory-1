"""Probe P12 (stage2.md 5): Payback's tagged spawn on every map. For each of the 11 maps: the vehicle types the map itself has
(the descriptors of its own entities below 30; 49 is the man, 55 and up people) and the two tanks (11 and 23) are spawned with
pb_spawn_tagged through the debug mailbox (dbg 53), 60 frames on the tag is found again (pb_ent_by_tag), the record is of the type
asked, its tag word at +0x14c is still the tag after 120 more (dbg 54), pb_kill (dbg 55) makes it a wreck (state 6) and clears the
tag, and the game still runs. The types a map does not have are spawned too, to see what happens (printed, not held to).

    SP=<harness folder> ROM=x.gba ELF=x.elf python3 tests/s2/p12.py [maps]       (from stuntfox/)

Prints one line per map: its own types and for each type spawned: ok, or what went wrong. ALL PASS or FAIL."""
import h
from h import *
import gridstate

TANKS = (11, 23)
ck = Check()
merged_state(e)
maps = [int(a) for a in sys.argv[1:]] or list(range(11))
table = {}
for g in maps:
    gridstate.grid_state(e, g)
    e.run(60)
    own = sorted(set(k for i, a, k, st, p, hp in ents() if 0 <= k < 30))
    base = e.save_state()
    others = [k for k in (0, 5, 15) if k not in own]       # (types the map has not, a car or two)
    row = {}
    for k in own + [t for t in TANKS if t not in own] + others:
        e.load_state(base)
        run(10)
        t0 = r32(S['key_calls'])
        spawned = mb(53, k)
        run(60)
        q = mb(54, k)
        tagged = q is not None and q >= 0 and bool(q >> 16 & 1)
        typ_ok = q is not None and q >= 0 and (q & 255) == k
        st1 = q >> 8 & 255 if q is not None and q >= 0 else -1
        run(120)
        q2 = mb(54, k)
        kept = q2 is not None and q2 >= 0 and bool(q2 >> 16 & 1)
        r = mb(55, k)
        run(30)
        after = mb(54, k)
        wreck = r is not None and r >= 0 and (r & 255) == 6 and bool(r >> 8 & 1)
        alive = r32(S["key_calls"]) - t0 > 20                # (the game runs about 16 of its frames a second)
        ok = bool(spawned == 1 and typ_ok and tagged and kept and wreck and alive)
        row[k] = ok
        if k in own:
            ck(ok, 'map %2d type %2d (its own): spawned, tag kept, pb_kill wrecks it' % (g, k),
               'spawn %s type %s tag %s kept %s kill %s state %s alive %s' % (spawned, typ_ok, tagged, kept, r, st1, alive))
    note = ' '.join('%d:%s' % (k, 'ok' if v else 'NO') for k, v in row.items())
    print('map %2d own %s | %s' % (g, own, note), flush=True)
    table[g] = row
print('tanks (11, 23) on the maps that spawn them: %s' % {g: [k for k in TANKS if table[g].get(k)] for g in table})
ck.done()

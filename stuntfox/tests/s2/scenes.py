"""The first minute on foot, in a car and in the Arwing, the same inputs on any build: a picture and the position every
second, saved under $OUT and in $OUT/scenes_$TAG.json. tests/s2/scenecmp.py sets two runs side by side.

    SP=.. OUT=dir TAG=name [SKEW=frames] ROM=x.gba ELF=x.elf python3 tests/s2/scenes.py      (from stuntfox/)

SKEW starts the script that many frames late: two runs of one build a few frames apart show how much of a difference
between two builds is only where in the frame the first key landed.
"""
import json
import h
from h import *

OUT, TAG, SKEW = os.environ['OUT'], os.environ['TAG'], int(os.environ.get('SKEW', '0'))
WANT = os.environ.get('SCENES', 'foot,car,arwing').split(',')
res = {}
merged_state(e)
run(30 + SKEW)
base = e.save_state()
fm_start(TAG)


def snap(scene, i, pos):
    e.frame.save('%s/scenes_%s_%s_%02d.png' % (OUT, TAG, scene, i))
    res[scene].append([round(v, 3) for v in pos])


def foot():
    res['foot'] = []
    plan = [['UP']] * 3 + [['UP', 'LEFT']] * 2 + [['UP']] * 3 + [['UP', 'RIGHT']] * 2 + [['A']] * 3 + [['DOWN']] * 2 + [[]] * 2
    for i, k in enumerate(plan):
        run(60, k)
        snap('foot', i, epos(ctl() or PL))


def car_scene():
    res['car'] = []
    c = get_car()
    res['car_jacked'] = bool(c and modename() == 'DRIVE')
    print('car', c and (c[2], c[3]), modename())
    plan = [['A']] * 4 + [['A', 'LEFT']] * 2 + [['A']] * 2 + [['A', 'RIGHT']] * 2 + [['B']] * 2 + [[]]
    for i, k in enumerate(plan):
        run(60, k)
        snap('car', i, epos(ctl() or PL))


def arwing():
    res['arwing'] = []
    e.run(45, ['SELECT'])
    for _ in range(40):
        if modename() == 'FLY':
            break
        run(10)
    run(30)
    plan = [['A']] * 4 + [['A', 'LEFT']] * 2 + [['A']] * 2 + [['A', 'UP']] * 2 + [['A', 'RIGHT']] * 2 + [['A', 'R']] * 2 + [['A']] * 2
    for i, k in enumerate(plan):
        run(60, k)
        snap('arwing', i, [v / 1024 for v in ship()])


for name, fn in (('foot', foot), ('car', car_scene), ('arwing', arwing)):
    if name in WANT:
        e.load_state(base)
        run(2)
        fn()
res['flash'] = fm_report()
json.dump(res, open('%s/scenes_%s.json' % (OUT, TAG), 'w'))
print('done', TAG, {k: len(v) for k, v in res.items() if isinstance(v, list)})

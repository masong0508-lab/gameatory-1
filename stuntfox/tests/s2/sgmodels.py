"""The city foes' models (src/sgmodels.h): the face normals baked in src/sgnorm.inc are what model_init gives the same
faces now (tools/sgnorm.py --check, host-compiled), and every face of the seven models names vertices that exist.

    python3 tests/s2/sgmodels.py        (from stuntfox/)
"""
import re
import subprocess
import sys

ok = True
r = subprocess.run([sys.executable, 'tools/sgnorm.py', '--check'], capture_output=True, text=True)
print('%s  sgnorm.inc is what model_init gives  %s' % ('PASS' if r.returncode == 0 else 'FAIL', r.stdout.strip()))
ok &= r.returncode == 0

src = open('src/sgmodels.h').read()
for name in ('turret', 'wing', 'hull', 'disc', 'wing_lo', 'hull_lo', 'disc_lo'):
    v = re.search(name + r'_v\[\]\s*=\s*\{(.*?)\};', src, re.S)
    f = re.search(name + r'_f\[\]\s*=\s*\{(.*?)\};', src, re.S)
    if not v or not f:
        print('FAIL  %s: vertex or face table not found' % name)
        ok = False
        continue
    nv = len(re.findall(r'\{[^{}]*\}', v.group(1))) + 6 * v.group(1).count('DISC_V(')       # (a ring of the disc is six points)
    faces = re.findall(r'F([34])\(([^()]*)\)', f.group(1))
    top = 0
    for n, args in faces:
        idx = [int(x) for x in args.split(',')[2:]]            # (F3(paint, flags, a, b, c))
        top = max(top, max(idx))
    good = nv > 0 and faces and top < nv
    print('%s  %-6s %d vertices, %d faces, highest vertex used %d' % ('PASS' if good else 'FAIL', name, nv, len(faces), top))
    ok &= bool(good)
print('ALL PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)

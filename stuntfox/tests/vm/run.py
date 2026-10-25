"""T0, the mission VM on the PC. From stuntfox/:   python3 tests/vm/run.py [--update]

Builds the demo blob (mkdemo.py), compiles src/mission.c and src/hudline.c as they are against pbmock.c with the host
compiler, runs t_vm (cases, adversarial runs, the fuzz) and compares the three golden traces in tests/vm/golden/.
--update rewrites the traces (read the diff before keeping it). Also checks that every name the engine's sources take
from Payback's API (pbapi.h) the mock has too, so the mock cannot drift."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'build', 'vm')
TRACES = ('act1', 'ring', 'timeout')
KEEP = 0
SAN = ['-fsanitize=address,undefined', '-fno-sanitize-recover=undefined']


def host_cc():
    """The host compiler with the sanitizers if one of them has the runtime, else clang plain."""
    t = os.path.join(OUT, 'probe.c')
    open(t, 'w').write('int main(void) { return 0; }\n')
    for cc in ([os.environ['HOSTCC']] if 'HOSTCC' in os.environ else ['gcc', 'clang']):
        if subprocess.run([cc] + SAN + [t, '-o', os.path.join(OUT, 'probe')], capture_output=True).returncode == 0:
            return cc, SAN
    return os.environ.get('HOSTCC', 'clang'), []


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode and not kw.get('check_ok'):
        pass
    return r


def api_names(path):
    """The pb_ / PB_ / PBG_ / PBE_ names a file uses."""
    s = open(path).read()
    s = re.sub(r'/\*.*?\*/|//[^\n]*', '', s, flags=re.S)
    return set(re.findall(r'\b(pb_[a-z_0-9]+|PB[A-Z_0-9]*|PBG_[A-Z_]+|PBE_[A-Z_]+|B_[A-Z0-9]+)\b', s))


def main():
    os.makedirs(OUT, exist_ok=True)
    update = '--update' in sys.argv
    bad = 0
    # the mock has every name the engine uses, and each of them exists in pbapi.h too
    real, mock = (open(os.path.join(ROOT, p)).read() for p in ('src/pbapi.h', 'tests/vm/pbmock.h'))
    for f in ('mission.c', 'hudline.c', 'msn_draw.c'):
        for n in sorted(api_names(os.path.join(ROOT, 'src', f))):
            if n.startswith('PBA_'):
                continue
            if not re.search(r'\b%s\b' % n, real):
                print('FAIL  %s uses %s, which pbapi.h does not have' % (f, n))
                bad += 1
            elif f != 'msn_draw.c' and not re.search(r'\b%s\b' % n, mock):
                print('FAIL  %s uses %s, which pbmock.h does not have' % (f, n))
                bad += 1
    demo = os.path.join(OUT, 'demo.bin')
    r = sh([sys.executable, os.path.join(HERE, 'mkdemo.py'), demo])
    print(r.stdout.strip(), r.stderr.strip())
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import mkassets                                  # (the font the device draws with: hudline.c inks from it)
    font = os.path.join(OUT, 'font.c')
    with open(font, 'w') as f:
        f.write('#include <stdint.h>\nconst uint32_t font_tiles[512] = {%s};\n' % ','.join('0x%08x' % v for v in mkassets.font_tiles()))
    exes = []
    cc, san = host_cc()
    # two builds: the sanitizers (gcc, -O1) and the device's own compiler's optimiser (clang, -O2: it reorders stores the
    # way the ARM build does, which found a store through a wider type moved past the fields it was meant to keep)
    for name, cc_, flags in (('san', cc, ['-O1'] + san), ('opt', 'clang', ['-O2'])):
        exe = os.path.join(OUT, 't_vm_' + name)
        cmd = [cc_, '-m64', '-g'] + flags + ['-Wall', '-Wno-unused-function',
               '-include', os.path.join(HERE, 'pbmock.h'), '-I' + os.path.join(ROOT, 'src'), '-I' + HERE,
               os.path.join(ROOT, 'src', 'mission.c'), os.path.join(ROOT, 'src', 'hudline.c'), os.path.join(HERE, 'pbmock.c'), font,
               os.path.join(HERE, 't_vm.c'), '-o', exe]
        r = sh(cmd)
        if r.returncode:
            if name == 'opt' and not subprocess.run(['which', 'clang'], capture_output=True).stdout:
                continue
            print(r.stdout, r.stderr)
            print('FAIL  the host build (%s)' % name)
            sys.exit(1)
        exes.append((name, cc_, exe))
        print('host build %s: %s %s' % (name, cc_, ' '.join(flags)))
    for name, _, exe in exes:
        r = sh([exe, demo])
        print(r.stdout.strip().splitlines()[-3] if r.stdout.strip() else '', '|', name)
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else '', r.stderr[-2000:])
        bad += r.returncode != 0
    exe = exes[0][2]
    h1, h2 = (sh([exe, demo, 'fuzz']).stdout for _ in range(2))
    if h1 == h2 and h1.startswith('hash'):
        print('PASS  the fuzz is deterministic: the same seed twice in fresh processes, %s' % h1.strip())
    else:
        print('FAIL  the fuzz is not deterministic: %r %r' % (h1, h2))
        bad += 1
    gold = os.path.join(HERE, 'golden')
    os.makedirs(gold, exist_ok=True)
    for t in TRACES:
        r = sh([exe, demo, t])
        path = os.path.join(gold, t + '.txt')
        if update:
            open(path, 'w').write(r.stdout)
            print('wrote', path)
        elif not os.path.exists(path) or open(path).read() != r.stdout:
            print('FAIL  golden trace %s differs' % t)
            open(os.path.join(OUT, t + '.new'), 'w').write(r.stdout)
            bad += 1
        else:
            print('PASS  golden trace %s (%d lines)' % (t, r.stdout.count('\n')))
    print('ALL PASS' if not bad else '%d FAILED' % bad)
    sys.exit(1 if bad else 0)


main()

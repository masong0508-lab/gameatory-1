#!/usr/bin/env python3
"""Builds and runs the PS1 ragdoll reference solver's tests (tools/ragdoll_ps1_test.c): determinism (and the recorded
golden hash), energy, bounce and surfaces, rest and sleep, tunnelling through thin walls and decks, scenes (stairs,
slope, corner, roof), the car, the motors, a random soak. Also under the undefined-behaviour checker. Exit 0 when all pass.
    python3 tests/s2/ragdoll_ps1.py"""
import os
import subprocess
import sys
import tempfile

T = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools')


def main():
    tmp = tempfile.mkdtemp(prefix='rpt')
    bad = 0
    for tag, flags in (('O2', ['-O2']), ('O0', ['-O0']), ('ubsan', ['-O1', '-fsanitize=undefined', '-fno-sanitize-recover=undefined'])):
        exe = os.path.join(tmp, 'rpt_' + tag)
        subprocess.check_call(['gcc', '-Wall', '-Wextra', '-Werror'] + flags + ['-I' + T, '-o', exe, os.path.join(T, 'ragdoll_ps1_test.c'),
                                                                                 os.path.join(T, 'ragdoll_ps1_ref.c'), '-lm'])
        r = subprocess.run([exe], capture_output=True, text=True)
        out = r.stdout + r.stderr
        sys.stdout.write('== %s ==\n%s' % (tag, out if tag == 'O2' else '\n'.join(l for l in out.splitlines() if 'golden' in l or 'ALL OK' in l or 'FAIL' in l or 'runtime error' in l) + '\n'))
        bad += r.returncode != 0
    print('ragdoll_ps1: %s' % ('ALL OK' if not bad else 'FAILED'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

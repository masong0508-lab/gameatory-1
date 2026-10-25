"""T0, the campaign's save code on the PC. From stuntfox/:   python3 tests/save/run.py

Compiles src/save.c as it is (plain C: the machine's part is behind -DSV_HOST) with the host compiler and the
sanitizers where they work, and runs t_save: the image's crc, the password codec round trip and its error catching, the
two slots with a power cut at every write of a save (clean, half-written and garbage blocks), 50 saves in a row, a
damaged slot, the sequence count wrapping, and the 4 Kbit / 64 Kbit identify against models of a genuine 64 Kbit chip, a
4 Kbit chip that wraps long block numbers, one that reads their first six bits, and one that holds no long write."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'build', 'savetest')
SAN = ['-fsanitize=address,undefined', '-fno-sanitize-recover=undefined']


def main():
    os.makedirs(OUT, exist_ok=True)
    probe = os.path.join(OUT, 'probe.c')
    open(probe, 'w').write('int main(void) { return 0; }\n')
    cc, san = None, []
    for c in ([os.environ['HOSTCC']] if 'HOSTCC' in os.environ else ['gcc', 'clang']):
        if subprocess.run([c] + SAN + [probe, '-o', os.path.join(OUT, 'probe')], capture_output=True).returncode == 0:
            cc, san = c, SAN
            break
        cc = cc or c
    exe = os.path.join(OUT, 't_save')
    cmd = [cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Wno-unused-parameter', '-DSV_HOST'] + san + \
          [os.path.join(HERE, 't_save.c'), os.path.join(ROOT, 'src', 'save.c'), '-o', exe]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout + r.stderr)
    if r.returncode:
        sys.exit('compile failed')
    r = subprocess.run([exe])
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""wp_run.py DISC OUTDIR [timeout_s]: run a -DWPOSE disc in pcsxr (HLE BIOS, emulator-only) under an own Xvfb and grab 640x480 screenshots at every
"WP k ... SETTLED" log line (3 grabs ~0.2 s apart: p<k>_a/b/c.png).  Run it as:  xvfb-run -a -s "-screen 0 800x600x24" python3 wp_run.py ..."""
import sys, os, time, subprocess
disc = os.path.abspath(sys.argv[1]); out = os.path.abspath(sys.argv[2]); tmo = int(sys.argv[3]) if len(sys.argv) > 3 else 1800
os.makedirs(out, exist_ok=True); log = out + '/pcsxr.log'
cfgdir = os.path.dirname(disc)
f = open(log, 'wb')
p = subprocess.Popen(['stdbuf', '-o0', '/usr/games/pcsxr', '-nogui', '-psxout', '-cdfile', disc, '-runcd'], cwd=cfgdir, stdout=f, stderr=subprocess.STDOUT)
t0 = time.time(); pos = 0; seen = set()
try:
    while time.time() - t0 < tmo and p.poll() is None:
        time.sleep(0.05)
        d = open(log, 'rb').read()
        new = d[pos:].split(b'\n')
        if len(new) > 1:
            pos += sum(len(l) + 1 for l in new[:-1])
            for l in new[:-1]:
                l = l.decode('latin1').strip().lstrip('* ').strip()
                if l.startswith('WP ') and 'SETTLED' in l:
                    k = int(l.split()[1])
                    for c in 'abc':
                        subprocess.run(['import', '-window', 'root', '-crop', '640x480+0+0', '+repage', '%s/p%02d_%s.png' % (out, k, c)])
                        time.sleep(0.1)
                    print(l, flush=True)
                if l.startswith('WP DONE'): raise SystemExit
finally:
    p.kill(); p.wait()

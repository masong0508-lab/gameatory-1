import sys, struct, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obrig import Emu2
core, disc, out, sysdir, frames = sys.argv[1:6]
opts = dict(kv.split('=', 1) for kv in sys.argv[6:])
e = Emu2(core, disc, out, opts, sysdir=sysdir)
e.run(int(frames))
s = bytes(e.save_state())
open(out + '/state.bin', 'wb').write(s[:1 << 20])
print('state size', len(s), s[:16])
for key in (b'BACKED_PC', b'BACKED_new_PC', b'GPR', b'BACKED_LDWhich', b'CP0.Regs', b'IPCache'):
    i = s.find(key)
    print(key, hex(i), s[i - 4:i + len(key) + 24].hex() if i >= 0 else '')

import sys, struct, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obrig import Emu2, format_trace
core, disc, out, sysdir, frames = sys.argv[1:6]
opts = dict(kv.split('=', 1) for kv in sys.argv[6:])
e = Emu2(core, disc, out, opts, sysdir=sysdir)
e.run(int(frames))
ram = bytes(e.read(0, 0x10000))
open(out + '/ram64k.bin', 'wb').write(ram)
def words(a, n): return ' '.join('%08x' % w for w in struct.unpack_from('<%dI' % n, ram, a))
for a in (0x60, 0x80, 0xa0, 0xb0, 0xc0, 0x1000, 0x1010, 0x1020, 0x2000, 0x2010, 0x5000):
    print('%05x: %s' % (a, words(a, 4)))
nz = [i for i in range(0, 0x10000, 0x100) if any(ram[i:i + 0x100])]
print('non-zero 256-byte blocks in the first 64K:', ' '.join('%x' % (b >> 8) for b in nz)[:600])
print(format_trace(e.trace()))
print('tty:', bytes(e.tty_poll())[:600])
e.shot(out + '/final.png')
print('size', e.size, 'frames', e.frames)
print('dbg words 0x130..: ' + ' '.join('%08x' % w for w in struct.unpack_from('<4I', ram, 0x1130)))
n = struct.unpack_from('<I', ram, 0x1c00)[0]
print('cd boot log (%d): ' % n + ' '.join('%06x' % w for w in struct.unpack_from('<%dI' % min(n, 63), ram, 0x1c04)))

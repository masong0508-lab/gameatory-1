import sys, struct, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obrig import Emu2, format_trace, load_syms
core, disc, out, sysdir, frames, sym = sys.argv[1:7]
opts = dict(kv.split('=', 1) for kv in sys.argv[7:])
e = Emu2(core, disc, out, opts, sysdir=sysdir)
e.run(int(frames))
s = bytes(e.save_state())
print('state size', len(s))
open(out + '/state.bin', 'wb').write(s)
# search: 36 words r0..r31,hi,lo,pc,npc with r0 == 0, sp in RAM, pc/npc in RAM or ROM and npc - pc in (4, small)
hits = []
for o in range(0, min(len(s), 0x4000) - 144, 1):
    w = struct.unpack_from('<36I', s, o)
    if w[0] == 0 and 0x80000000 <= w[29] < 0x80200000 and (0x80000000 <= w[34] < 0x80200000 or 0xbfc00000 <= w[34] < 0xbfc80000) and 0 < ((w[35] - w[34]) & 0xffffffff) <= 8:
        hits.append((o, w))
for o, w in hits[:3]:
    print('offset %#x: pc %08x npc %08x sp %08x ra %08x  at %08x v0 %08x v1 %08x a0 %08x t0 %08x t1 %08x' % (o, w[34], w[35], w[29], w[31], w[1], w[2], w[3], w[4], w[8], w[9]))

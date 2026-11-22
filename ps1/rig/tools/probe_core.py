import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from obrig import Emu2
core, disc, out = sys.argv[1], sys.argv[2], sys.argv[3]
sysdir = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != '-' else None
frames = int(sys.argv[5]) if len(sys.argv) > 5 else 30
opts = dict(o.split('=', 1) for o in sys.argv[6:])
try:
    e = Emu2(core, disc, out, opts, sysdir=sysdir)
    e.run(frames)
    print('frames', e.frames, 'size', e.size, 'fps', e.fps, 'fmt', e.fmt)
    for k, v in sorted(e.vardefs.items()): print('VAR', k, '=', v[:300])
    print('asked-but-undefined', sorted(set(e.asked) - set(e.vardefs)))
    print('messages', e.messages)
    print('unknown env', sorted(e.unknown_env))
    try: print('ram size', len(e.ram))
    except Exception as ex: print('ram', ex)
    e.shot(out + '/final.png')
except Exception as ex:
    print('EXC', ex)

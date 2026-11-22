# Session for obrun.py: what the pad driver of the runtime (ps1rt/hw_pad.h) does with the controller the core emulates.
# Runs until the first pad transfers have happened, then prints pad_id (ID byte of the last poll), pad_cfg_tries and the three
# words of pad_cfg_log (bytes exchanged | reply byte 1 << 8 | reply byte 2 << 16 for the commands Enter config, Set analog,
# Exit config), then holds DOWN for OB_HOLD frames and reports whether the runtime saw it (pad_raw, active high).
import os
HOLD = int(os.environ.get('OB_HOLD', '900')); MAXF = int(os.environ.get('OB_MAXF', '6000'))
def st(label):
    lg = [S.e.r32(S.syms['pad_cfg_log'] + 4 * i) for i in range(3)] if 'pad_cfg_log' in S.syms else []
    S.mark(label, pad_polls=S.g('pad_polls'), pad_fails=S.g('pad_fails'), pad_id='%02x' % S.e.r8(S.syms['pad_id']), pad_analog=S.g('pad_analog'),
           pad_cfg_tries=S.g('pad_cfg_tries'), pad_raw='%04x' % (S.g('pad_raw') & 0xffff),
           cfg_enter=('%d bytes, reply %02x %02x' % (lg[0] & 0xff, (lg[0] >> 8) & 0xff, (lg[0] >> 16) & 0xff)) if lg else None,
           cfg_analog=('%d bytes, reply %02x %02x' % (lg[1] & 0xff, (lg[1] >> 8) & 0xff, (lg[1] >> 16) & 0xff)) if lg else None,
           cfg_exit=('%d bytes, reply %02x %02x' % (lg[2] & 0xff, (lg[2] >> 8) & 0xff, (lg[2] >> 16) & 0xff)) if lg else None)
S.run(600)
f = 0
while S.g('pad_polls') < 1 and f < MAXF:
    S.run(10); f += 10
st('after_first_poll')
while S.g('pad_polls') < 4 and f < MAXF:
    S.run(10); f += 10
st('after_4_polls')
p0 = S.g('pad_polls'); seen = 0
for _ in range(HOLD // 10):
    S.run(10, ['DOWN'])
    if S.g('pad_raw') & 0x40:
        seen += 1
S.mark('hold_down', frames=HOLD, polls_during_hold=S.g('pad_polls') - p0, samples_with_down_in_pad_raw=seen, pad_id='%02x' % S.e.r8(S.syms['pad_id']))
S.run(60)
st('end')

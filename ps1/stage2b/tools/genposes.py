import json, math, sys
d = json.load(open('build/gba_poses_all.json'))
P = [('foot_start', 9728, 403, 2070, 0, -3660)]
for tag in ('street', 'cross', 'ramp', 'bridge', 'water'):
    v = d[tag]; f = v['f']; yaw = round(math.atan2(f[0], f[2]) * 65536 / (2 * math.pi)) & 0xffff
    pitch = round(math.asin(f[1] / 16384) * 65536 / (2 * math.pi)); P.append((tag, v['pos'][0], v['pos'][1], v['pos'][2], yaw, pitch))
P.append(('high', 9728, 5200, 1200, 0, -9000))
P.append(('river_fly', 24000, 2600, 6000, 16384, -4000))
open('src/poses.h', 'w').write('static const Pose poses[] = {\n' + ''.join('  { %d, %d, %d, %d, %d },  /* %d %s */\n' % (x, y, z, ya, pi, i, t) for i, (t, x, y, z, ya, pi) in enumerate(P)) + '};\n')
print(open('src/poses.h').read())

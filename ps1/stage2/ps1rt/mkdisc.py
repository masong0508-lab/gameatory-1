#!/usr/bin/env python3
"""mkdisc.py: build a PS1 disc image set (cue + bin) from a 2048-byte-sector ISO plus CD-DA tracks.  Code only: nothing from any game or music file is stored here.
usage: mkdisc.py --iso in.iso --out DIR/NAME [--tracks list.txt | --track file.mp3 ...] [--seconds N] [--music-dir DIR]
  data track  = the ISO as MODE2/2352 Form 1 (sync, header, subheader 00 00 08 00, EDC, ECC computed), starts at LBA 0
  audio tracks = ffmpeg -> 44.1 kHz 16-bit stereo, one bin per track, 2 s silent pregap (INDEX 00/01), tracks numbered from 2
  tracklist.txt: one mp3 file name per line (resolved in --music-dir); '#' comments.  Names containing 'song 3' are refused (Payback song 3 stays out).
The audio bins are build output on the user's machine; never commit them."""
import argparse, os, re, struct, subprocess, sys
ap = argparse.ArgumentParser()
ap.add_argument('--iso', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--tracks'); ap.add_argument('--track', action='append', default=[])
ap.add_argument('--music-dir', default='/mnt/project-files/stunt-fox/music/mods/remixes')
ap.add_argument('--seconds', type=float, default=0, help='truncate every audio track (test discs)')
a = ap.parse_args()
names = list(a.track)
if a.tracks:
    names += [l.strip() for l in open(a.tracks) if l.strip() and not l.startswith('#')]
for n in names:
    if re.search(r'song\s*3', n, re.I): sys.exit('refused (Payback song 3 is excluded): ' + n)
# ---- EDC / ECC (standard CD-ROM Yellow Book, same algorithm as the ECM tools)
EDC = []
for i in range(256):
    e = i
    for _ in range(8): e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
    EDC.append(e)
F = [0]*256; B = [0]*256
for i in range(256):
    j = (i << 1) ^ (0x11d if i & 0x80 else 0); j &= 0xff; F[i] = j; B[i ^ j] = i
def edc(d):
    e = 0
    for x in d: e = (e >> 8) ^ EDC[(e ^ x) & 255]
    return e
def ecc(sec, major, minor, mult, inc, dst):
    size = major * minor
    for mj in range(major):
        idx = (mj >> 1) * mult + (mj & 1); ea = eb = 0
        for _ in range(minor):
            t = sec[12 + idx]; idx += inc
            if idx >= size: idx -= size
            ea ^= t; eb ^= t; ea = F[ea]
        ea = B[F[ea] ^ eb]; sec[dst + mj] = ea; sec[dst + mj + major] = ea ^ eb
def bcd(v): return (v // 10) * 16 + v % 10
def mode2f1(lba, data):
    s = bytearray(2352); s[0] = 0; s[1:11] = b'\xff' * 10; s[11] = 0
    s[16:20] = bytes([0, 0, 8, 0]); s[20:24] = bytes([0, 0, 8, 0]); s[24:24+2048] = data
    s[0x818:0x81c] = struct.pack('<I', edc(s[16:0x818]))
    ecc(s, 86, 24, 2, 86, 0x81c); ecc(s, 52, 43, 86, 88, 0x8c8)
    f = lba + 150; s[12] = bcd(f // 4500); s[13] = bcd(f // 75 % 60); s[14] = bcd(f % 75); s[15] = 2
    return bytes(s)
iso = open(a.iso, 'rb').read(); iso += b'\0' * ((-len(iso)) % 2048)
base = a.out; os.makedirs(os.path.dirname(os.path.abspath(base)), exist_ok=True); stem = os.path.basename(base)
with open(base + ' (track 01).bin', 'wb') as f:
    for i in range(len(iso) // 2048): f.write(mode2f1(i, iso[i*2048:(i+1)*2048]))
cue = ['FILE "%s (track 01).bin" BINARY' % stem, '  TRACK 01 MODE2/2352', '    INDEX 01 00:00:00']
total_sec = len(iso) // 2048 / 75.0 + 2
for k, n in enumerate(names):
    path = n if os.path.isabs(n) else os.path.join(a.music_dir, n)
    cmd = ['ffmpeg', '-v', 'error', '-i', path, '-f', 's16le', '-ar', '44100', '-ac', '2']
    if a.seconds: cmd += ['-t', str(a.seconds)]
    pcm = subprocess.run(cmd + ['-'], check=True, capture_output=True).stdout
    pcm = b'\0' * (150 * 2352) + pcm; pcm += b'\0' * ((-len(pcm)) % 2352)
    t = k + 2; fn = '%s (track %02d).bin' % (stem, t); open(os.path.join(os.path.dirname(os.path.abspath(base)), fn), 'wb').write(pcm)
    cue += ['FILE "%s" BINARY' % fn, '  TRACK %02d AUDIO' % t, '    INDEX 00 00:00:00', '    INDEX 01 00:02:00']
    total_sec += len(pcm) / 2352 / 75.0
    print('track %02d  %6.1f s  %s' % (t, len(pcm) / 2352 / 75.0 - 2, os.path.basename(n)))
open(base + '.cue', 'w').write('\n'.join(cue) + '\n')
print('disc length %.1f min (limit 74)' % (total_sec / 60))
if total_sec > 74 * 60: sys.exit('over 74 minutes')

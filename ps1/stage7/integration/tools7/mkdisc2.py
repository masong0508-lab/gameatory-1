#!/usr/bin/env python3
"""mkdisc2.py: ISO (2048-byte sectors) + CD-DA audio -> PS1 disc image, single .bin + .cue (MODE2/2352).
Code only. No game or music data is stored in this directory; the audio bin is build output on the user's machine, never commit it.
  usage: mkdisc2.py --iso game.iso --out DIR/NAME [--region U|E|J] [--tracks list.txt | --default-tracks | --track f.mp3 ...]
                    [--music-dir D] [--seconds N] [--split]
  Layout (what verify_disc.py checks):
    LBA 0..11   licence area: Mode 2 Form 2 sectors (subheader 00 00 20 00, EDC), region string "Licensed by Sony Computer
                Entertainment Inc./America/Europe" in the licence block. The Sony logo image is NOT included (we do not ship it),
                emulators (DuckStation, PCSXR, ReARMed) do not check the licence block; a real console needs a modchip anyway.
    LBA 12..15  Mode 2 Form 1 sectors, empty
    LBA 16..    the ISO as Mode 2 Form 1 (sync, MSF header, subheader 00 00 08 00, EDC, P/Q ECC), data track 01
    audio       tracks 02.. : 2 s pregap (INDEX 00 -> INDEX 01) of silence, then 44.1 kHz 16-bit stereo PCM (ffmpeg), sector aligned
  The ISO's own system area (LBA 0..15, empty from genisoimage) is replaced; the ISO9660 volume descriptors stay at LBA 16.
  Payback song 3 is refused by name. Total length is checked against 74 min (80 min with --allow-80)."""
import argparse, os, re, struct, subprocess, sys
REGION = {'J': b'Inc.', 'U': b'Amer  ica ', 'E': b'Euro  pe '}
DEFAULT_MODS = os.environ.get('MUSIC_MODS', '/mnt/project-files/stunt-fox/music/mods/remixes')     # the 11 tracker-module '(PS1 remix final)' MP3s
DEFAULT_PB = os.environ.get('MUSIC_PB', '/mnt/project-files/stunt-fox/music/remixes-ps1')          # 'Star-FlyBack PS1 Remix - Song 1/2/4.mp3'
def default_tracks():
    out = sorted(os.path.join(DEFAULT_MODS, f) for f in os.listdir(DEFAULT_MODS) if f.endswith('(PS1 remix final).mp3'))
    out += [os.path.join(DEFAULT_PB, 'Star-FlyBack PS1 Remix - Song %d.mp3' % n) for n in (1, 2, 4)]
    return out
EDC = []
for i in range(256):
    e = i
    for _ in range(8): e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
    EDC.append(e)
F = [0]*256; B = [0]*256
for i in range(256):
    j = ((i << 1) ^ (0x11d if i & 0x80 else 0)) & 0xff; F[i] = j; B[i ^ j] = i
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
def head(lba):
    s = bytearray(2352); s[1:11] = b'\xff' * 10
    f = lba + 150; s[12] = bcd(f // 4500); s[13] = bcd(f // 75 % 60); s[14] = bcd(f % 75); s[15] = 2
    return s
def form1(lba, data):
    s = head(lba); s[16:24] = bytes([0, 0, 8, 0]) * 2; s[24:2072] = data
    s[0x818:0x81c] = struct.pack('<I', edc(s[16:0x818])); ecc(s, 86, 24, 2, 86, 0x81c); ecc(s, 52, 43, 86, 88, 0x8c8)
    return bytes(s)
def form2(lba, data):
    assert len(data) <= 2324
    s = head(lba); s[16:24] = bytes([0, 0, 0x20, 0]) * 2; s[24:24+len(data)] = data
    s[0x92c:0x930] = struct.pack('<I', edc(s[16:0x92c]))
    return bytes(s)
def license_block(region):
    # 12 x 2324 bytes: the region/licence text, rest zero (no logo image)
    txt = b'          Licensed  by          Sony Computer Entertainment ' + REGION[region] + b'   '
    blk = bytearray(12 * 2324); blk[0:len(txt)] = txt
    return [bytes(blk[i*2324:(i+1)*2324]) for i in range(12)]
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iso', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--region', default='U', choices='JUE')
    ap.add_argument('--tracks'); ap.add_argument('--track', action='append', default=[]); ap.add_argument('--default-tracks', action='store_true')
    ap.add_argument('--music-dir', default=DEFAULT_MODS)
    ap.add_argument('--seconds', type=float, default=0, help='truncate each audio track (test discs)')
    ap.add_argument('--split', action='store_true', help='one bin per track instead of a single bin')
    ap.add_argument('--allow-80', action='store_true')
    a = ap.parse_args()
    names = list(a.track)
    if a.default_tracks: names += default_tracks()
    if a.tracks: names += [l.strip() for l in open(a.tracks) if l.strip() and not l.startswith('#')]
    for n in names:
        if re.search(r'song\s*3', n, re.I): sys.exit('refused (Payback song 3 is excluded): ' + n)
    iso = open(a.iso, 'rb').read(); iso += b'\0' * ((-len(iso)) % 2048)
    nsec = len(iso) // 2048
    if nsec < 17: sys.exit('iso too small')
    d = os.path.dirname(os.path.abspath(a.out)); os.makedirs(d, exist_ok=True); stem = os.path.basename(a.out)
    data = bytearray()
    lic = license_block(a.region)
    for i in range(12): data += form2(i, lic[i])
    for i in range(12, 16): data += form1(i, b'\0' * 2048)
    for i in range(16, nsec): data += form1(i, iso[i*2048:(i+1)*2048])
    tracks = []   # (track no, pcm incl. pregap)
    for k, n in enumerate(names):
        path = n if os.path.isabs(n) else os.path.join(a.music_dir, n)
        cmd = ['ffmpeg', '-v', 'error', '-i', path, '-f', 's16le', '-ar', '44100', '-ac', '2']
        if a.seconds: cmd += ['-t', str(a.seconds)]
        pcm = b'\0' * (150 * 2352) + subprocess.run(cmd + ['-'], check=True, capture_output=True).stdout
        pcm += b'\0' * ((-len(pcm)) % 2352); tracks.append((k + 2, pcm)); print('track %02d  %6.1f s  %s' % (k + 2, len(pcm) / 2352 / 75 - 2, os.path.basename(n)))
    total = nsec + sum(len(p) // 2352 for _, p in tracks)
    print('data track: %d sectors (%.1f MiB), disc %d sectors = %.2f MiB, %.1f min (limit %d)' % (nsec, nsec*2352/2**20, total, total*2352/2**20, total/75/60, 80 if a.allow_80 else 74))
    if total / 75 > (80 if a.allow_80 else 74) * 60: sys.exit('over capacity')
    def msf(s): return '%02d:%02d:%02d' % (s // 4500, s // 75 % 60, s % 75)
    if a.split:
        open(os.path.join(d, stem + ' (track 01).bin'), 'wb').write(data)
        cue = ['FILE "%s (track 01).bin" BINARY' % stem, '  TRACK 01 MODE2/2352', '    INDEX 01 00:00:00']
        for t, p in tracks:
            fn = '%s (track %02d).bin' % (stem, t); open(os.path.join(d, fn), 'wb').write(p)
            cue += ['FILE "%s" BINARY' % fn, '  TRACK %02d AUDIO' % t, '    INDEX 00 00:00:00', '    INDEX 01 00:02:00']
    else:
        with open(os.path.join(d, stem + '.bin'), 'wb') as f:
            f.write(data); [f.write(p) for _, p in tracks]
        cue = ['FILE "%s.bin" BINARY' % stem, '  TRACK 01 MODE2/2352', '    INDEX 01 00:00:00']; pos = nsec
        for t, p in tracks:
            cue += ['  TRACK %02d AUDIO' % t, '    INDEX 00 ' + msf(pos), '    INDEX 01 ' + msf(pos + 150)]; pos += len(p) // 2352
    open(os.path.join(d, stem + '.cue'), 'w').write('\r\n'.join(cue) + '\r\n')
main()

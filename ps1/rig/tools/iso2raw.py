#!/usr/bin/env python3
"""iso2raw.py --iso IN.iso --out DIR [--name NAME]: TEST-ONLY raw disc image (one MODE2/2352 track, .bin + .cue) from a
plain 2048-byte-per-sector ISO image, for cores that want raw sectors.  Every sector becomes mode 2 form 1 (sync, BCD
address, sub-header 00 00 08 00 twice, 2048 data bytes, EDC, P/Q ECC with the address taken as zero, ECMA-130).
Nothing is added: no licence data, no audio tracks.  150 empty sectors are appended as a guard behind the last file.
--sysarea-from RAW.bin copies the 16 raw sectors of the system area from an existing raw image of the project (Beetle PSX
refuses data reads from a disc whose system area carries no licence line; this tool does not write one itself)."""
import argparse, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_disc import fix_sector  # noqa: E402


def bcd(v): return (v // 10) * 16 + v % 10


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--iso', required=True); ap.add_argument('--out', required=True); ap.add_argument('--name', default=None)
    ap.add_argument('--sysarea-from', default=None)
    a = ap.parse_args()
    d = open(a.iso, 'rb').read()
    if len(d) % 2048 or d[0x8001:0x8006] != b'CD001':
        sys.exit('%s: not a 2048-byte-per-sector ISO9660 image' % a.iso)
    name = a.name or os.path.splitext(os.path.basename(a.iso))[0]
    os.makedirs(a.out, exist_ok=True)
    n = len(d) // 2048
    sync = b'\x00' + b'\xff' * 10 + b'\x00'
    sysarea = open(a.sysarea_from, 'rb').read(16 * 2352) if a.sysarea_from else b''
    with open(os.path.join(a.out, name + '.bin'), 'wb') as f:
        for lba in range(n + 150):
            if lba < 16 and len(sysarea) == 16 * 2352:
                f.write(sysarea[lba * 2352:(lba + 1) * 2352]); continue
            data = d[lba * 2048:(lba + 1) * 2048] if lba < n else bytes(2048)
            m = lba + 150
            head = bytes([bcd(m // 4500), bcd((m // 75) % 60), bcd(m % 75), 2])
            sub = bytes([0, 0, 0x08, 0]) * 2
            f.write(fix_sector(sync + head + sub + data + bytes(280)))
    open(os.path.join(a.out, name + '.cue'), 'w').write('FILE "%s.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n' % name)
    print('%s: %d sectors (+150 guard)%s -> %s/%s.cue' % (a.iso, n, ', system area copied from ' + a.sysarea_from if sysarea else '', a.out, name))


if __name__ == '__main__':
    main()

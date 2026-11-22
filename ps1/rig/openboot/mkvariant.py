#!/usr/bin/env python3
"""mkvariant.py IN OUT FLAGS: pad the linked image to 512 KiB and set the behaviour flags word at 0x150 (see ob.h)."""
import struct
import sys

def main():
    src, dst, flags = sys.argv[1], sys.argv[2], int(sys.argv[3], 0)
    d = bytearray(open(src, 'rb').read())
    assert len(d) <= 0x80000, 'image larger than the 512 KiB ROM'
    assert struct.unpack_from('<I', d, 0x154)[0] == 0x3154424f, 'no flags marker at 0x154'
    d += b'\0' * (0x80000 - len(d))
    struct.pack_into('<I', d, 0x150, flags)
    open(dst, 'wb').write(d)
    print('%s: %d bytes, flags 0x%x' % (dst, len(d), flags))

main()

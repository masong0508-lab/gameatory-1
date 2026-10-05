"""BPS patch writer and applier (the format used by Floating IPS, beat and Rom Patcher JS)."""
import zlib

SOURCE_READ, TARGET_READ, SOURCE_COPY, TARGET_COPY = range(4)
MIN_RUN = 8


def _num(x):
    out = bytearray()
    while True:
        b = x & 0x7f
        x >>= 7
        if x == 0:
            out.append(0x80 | b)
            return bytes(out)
        out.append(b)
        x -= 1


def _signed(x):
    return _num((abs(x) << 1) | (x < 0))


def _match(a, i, b, j, limit):
    """Length of the common run a[i:] == b[j:], up to limit (memcmp-sized steps)."""
    limit = min(limit, len(a) - i, len(b) - j)
    if limit <= 0:
        return 0
    n, step = 0, 64
    while n < limit:
        k = min(step, limit - n)
        if a[i + n:i + n + k] == b[j + n:j + n + k]:
            n += k
            step *= 2
        elif step > 1:
            step = max(1, step // 4)
        else:
            break
    return n


def encode(source, target, moves=()):
    """Make a BPS patch. `moves` lists (target_offset, source_offset, length) blocks that
    were copied from elsewhere in the source, so they cost a SourceCopy instead of raw bytes."""
    out = bytearray(b'BPS1' + _num(len(source)) + _num(len(target)) + _num(0))
    src_rel = tgt_rel = 0
    literal = bytearray()
    lit_at = 0

    def flush():
        nonlocal literal
        if literal:
            out.extend(_num(((len(literal) - 1) << 2) | TARGET_READ) + literal)
            literal = bytearray()

    i, n_t = 0, len(target)
    while i < n_t:
        n = _match(source, i, target, i, n_t - i)
        if n >= MIN_RUN:
            flush()
            out.extend(_num(((n - 1) << 2) | SOURCE_READ))
            i += n
            continue
        moved = False
        for t0, s0, ln in moves:
            if t0 <= i < t0 + ln:
                j = s0 + (i - t0)
                n = _match(source, j, target, i, t0 + ln - i)
                if n >= MIN_RUN:
                    flush()
                    out.extend(_num(((n - 1) << 2) | SOURCE_COPY) + _signed(j - src_rel))
                    src_rel = j + n
                    i += n
                    moved = True
                break
        if moved:
            continue
        if i > 0:
            n = _match(target, i - 1, target, i, n_t - i)   # run of a repeated byte
            if n >= MIN_RUN:
                flush()
                out.extend(_num(((n - 1) << 2) | TARGET_COPY) + _signed(i - 1 - tgt_rel))
                tgt_rel = i - 1 + n
                i += n
                continue
        literal.append(target[i])
        i += 1
    flush()
    out += zlib.crc32(source).to_bytes(4, 'little') + zlib.crc32(target).to_bytes(4, 'little')
    out += zlib.crc32(out).to_bytes(4, 'little')
    return bytes(out)


def apply(source, patch):
    def num():
        nonlocal p
        data, shift = 0, 1
        while True:
            x = patch[p]
            p += 1
            data += (x & 0x7f) * shift
            if x & 0x80:
                return data
            shift <<= 7
            data += shift

    assert patch[:4] == b'BPS1', 'not a BPS patch'
    assert zlib.crc32(patch[:-4]) == int.from_bytes(patch[-4:], 'little'), 'patch is corrupt'
    p = 4
    src_size, tgt_size, meta = num(), num(), num()
    p += meta
    if len(source) != src_size or zlib.crc32(source) != int.from_bytes(patch[-12:-8], 'little'):
        raise ValueError('this patch is for a different source file')
    t = bytearray(tgt_size)
    o = src_rel = tgt_rel = 0
    while p < len(patch) - 12:
        x = num()
        cmd, n = x & 3, (x >> 2) + 1
        if cmd == SOURCE_READ:
            t[o:o + n] = source[o:o + n]
        elif cmd == TARGET_READ:
            t[o:o + n] = patch[p:p + n]
            p += n
        else:
            d = num()
            d = -(d >> 1) if d & 1 else d >> 1
            if cmd == SOURCE_COPY:
                src_rel += d
                t[o:o + n] = source[src_rel:src_rel + n]
                src_rel += n
            else:
                tgt_rel += d
                dist = o - tgt_rel
                if dist >= n:
                    t[o:o + n] = t[tgt_rel:tgt_rel + n]
                elif dist > 0:              # overlapping copy repeats the last `dist` bytes
                    t[o:o + n] = (bytes(t[tgt_rel:o]) * (n // dist + 1))[:n]
                else:
                    for k in range(n):
                        t[o + k] = t[tgt_rel + k]
                tgt_rel += n
        o += n
    assert zlib.crc32(t) == int.from_bytes(patch[-8:-4], 'little'), 'output CRC mismatch'
    return bytes(t)

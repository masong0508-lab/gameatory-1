#!/usr/bin/env python3
"""Milestone B (PS1): give natively compiled Stunt Fox C the GBA's memory semantics (ps1/merged/README.md).

Input: the LLVM IR (text, clang 18, mipsel) of one Stunt Fox C file.  Output: the same IR in which
  - every load and store whose address is not provably host memory (an alloca, a global compiled natively) goes through the runtime's
    guest memory model (sfmem.c: __sf_ld8/16/32 and __sf_st8/16/32, a host address takes the fast path, a guest one the runtime's h_memrd /
    h_memwr, i.e. exactly what translated Payback does with the same value);
  - a constant guest address of a plain RAM window (EWRAM, IWRAM, PAL, VRAM, OAM) becomes its host address (t2m memory model 'P': registers
    and memory hold host addresses for guest RAM, guest addresses for ROM), so Payback's pointers and ours have one form;
  - llvm.memcpy / llvm.memset / memcpy / memset / memmove / memcmp go to the guest-aware __sf_ copies;
  - a call through a pointer, or to a constant address, goes through __sf_fnmap: a native function is called directly, a Stunt Fox function
    compiled natively is found by its GBA address (sfnat_entries.c), anything else is a guest call (sf_gthunk, sfglue.s).
Usage: irmem.py IN.ll OUT.ll NATIVE_GLOBALS.txt ROM_GLOBALS.txt"""
import re, sys

RAM = [(0x02000000, 0x40000, 0x801b0000), (0x03000000, 0x1000000, 0x801f0000), (0x05000000, 0x400, 0x80180000),
       (0x06000000, 0x18000, 0x80181000), (0x07000000, 0x400, 0x80180400)]


def host_of(v):
    for g, n, h in RAM:
        if g <= v < g + n:
            return h + ((v - g) & 0x7fff if g == 0x03000000 else v - g)
    return None


def h2g_const(h):
    """sfmem.c __sf_h2g for a constant (a host RAM-window address back to its guest one), as a signed i32 literal"""
    for g, n, hb in RAM:
        sz = 0x8000 if g == 0x03000000 else n
        if hb <= h < hb + sz:
            v = g + h - hb
            break
    else:
        v = h
    return v - (1 << 32) if v >= 1 << 31 else v


def split_top(s, sep=','):
    """split s at top-level separators (not inside () [] {} <> or quotes)"""
    out, depth, cur, q = [], 0, [], False
    for ch in s:
        if ch == '"':
            q = not q
        if not q:
            if ch in '([{<':
                depth += 1
            elif ch in ')]}>':
                depth -= 1
            elif ch == sep and depth == 0:
                out.append(''.join(cur))
                cur = []
                continue
        cur.append(ch)
    out.append(''.join(cur))
    return out


INTTOPTR = re.compile(r'inttoptr \(i32 (-?\d+) to ptr\)')
GLOBAL = re.compile(r'@([\w.$]+|"[^"]+")')
SIZE = {'i8': 1, 'i16': 2, 'i32': 4, 'ptr': 4, 'i1': 1}


class Rewriter:
    def __init__(s, native, rom):
        s.native, s.rom = native, rom
        s.stat = {}

    def count(s, k):
        s.stat[k] = s.stat.get(k, 0) + 1

    def const_map(s, text):
        """guest RAM constants -> host constants (anywhere in an instruction)"""
        def sub(m):
            v = int(m.group(1)) & 0xffffffff
            h = host_of(v)
            if h is None:
                return m.group(0)
            s.count('const_ram')
            return 'inttoptr (i32 %d to ptr)' % (h - (1 << 32) if h >= 1 << 31 else h)
        return INTTOPTR.sub(sub, text)

    def kind(s, op, hostvals):
        """'host' (plain access), 'io' (constant IO register), 'guest' (needs the runtime)"""
        op = op.strip()
        if op.startswith('%'):
            return 'host' if op in hostvals else 'guest'
        m = INTTOPTR.search(op)
        if m:
            v = int(m.group(1)) & 0xffffffff
            if v >= 0x80000000:
                return 'host'
            return 'guest'
        g = GLOBAL.search(op)
        if g:
            name = g.group(1).strip('"')
            if name in s.rom:
                return 'guest'
            return 'host'
        if op in ('null', 'undef', 'poison'):
            return 'guest'
        return 'guest'

    def run(s, lines):
        out = []
        hostvals = set()
        allocas = set()
        for ln in lines:
            if ln.startswith('define '):
                hostvals = set()
                allocas = set()
            ln = s.const_map(ln)
            st = ln.strip()
            m = re.match(r'(%[\w.]+) = (alloca) ', st)
            if m:
                hostvals.add(m.group(1))
                allocas.add(m.group(1))
            m = re.match(r'(%[\w.]+) = getelementptr (inbounds )?([^,]+), ptr (.*)$', st)
            if m:
                base = split_top(m.group(4))[0]
                if s.kind(base, hostvals) == 'host':
                    hostvals.add(m.group(1))
            m = re.match(r'(%[\w.]+) = (?:bitcast|addrspacecast) ptr (\S+) to ptr', st)
            if m and s.kind(m.group(2), hostvals) == 'host':
                hostvals.add(m.group(1))
            m = re.match(r'(%[\w.]+) = select i1 [^,]+, ptr ([^,]+), ptr ([^,]+)$', st.split(', !')[0])
            if m and s.kind(m.group(2), hostvals) == 'host' and s.kind(m.group(3), hostvals) == 'host':
                hostvals.add(m.group(1))
            ind = ln[:len(ln) - len(ln.lstrip())]
            # a pointer as a number is a GUEST address (Stunt Fox compares and hashes them as on the GBA: (u32)g < 0x02000000, ...),
            # a number as a pointer is the host address of a guest RAM one: Payback's RAM holds host pointers (t2m 'P'), our C builds and
            # checks guest ones, so both conversions go through the runtime's mapping (sfmem.c __sf_h2g / __sf_g2h; any other value is kept)
            m = re.match(r'(%[\w.]+) = ptrtoint ptr (%[\w.]+) to i32(.*)$', st)
            if m and not m.group(2).startswith('%__sfm') and m.group(2) not in allocas:
                s.count('h2g')
                out.append(ind + '%s = call i32 @__sf_h2g(ptr %s)' % (m.group(1), m.group(2)))
                continue
            # a pointer comparison compares guest addresses: Payback's RAM holds RAM pointers in both forms (host from translated code,
            # guest from its ROM tables), so (u8 *)g < (u8 *)0x02000000 and p == q only agree with the GBA after __sf_h2g on both sides
            m = re.match(r'(%[\w.]+) = icmp (\w+) ptr (.*)$', st.split(', !')[0])
            if m:
                ops = [x.strip() for x in split_top(m.group(3))]
                if len(ops) == 2 and any(INTTOPTR.fullmatch(o) for o in ops) and 'null' not in ops:
                    # (only against a constant: two pointers of one walk, p < end, keep the one form they were made in)
                    vals = []
                    for o in ops:
                        c = INTTOPTR.fullmatch(o)
                        if c:
                            h = int(c.group(1)) & 0xffffffff
                            vals.append(str(h2g_const(h)))
                        elif o.startswith('%'):
                            t = s.tmp()
                            out.append(ind + '%s = call i32 @__sf_h2g(ptr %s)' % (t, o))
                            vals.append(t)
                        else:
                            t = s.tmp()
                            out.append(ind + '%s = ptrtoint ptr %s to i32' % (t, o))
                            vals.append(t)
                    s.count('icmp_ptr')
                    out.append(ind + '%s = icmp %s i32 %s, %s' % (m.group(1), m.group(2), vals[0], vals[1]))
                    continue
            m = re.match(r'(%[\w.]+) = inttoptr i32 (%[\w.]+) to ptr(.*)$', st)
            if m and not m.group(2).startswith('%__sfm'):
                s.count('g2h')
                out.append(ind + '%s = call ptr @__sf_g2h(i32 %s)' % (m.group(1), m.group(2)))
                continue
            m = re.match(r'(%[\w.]+) = load (volatile )?(i1|i8|i16|i32|i64|ptr), ptr (.*)$', st)
            if m:
                dst, vol, ty, rest = m.groups()
                parts = split_top(rest)
                op = parts[0].strip()
                al = 0
                for p in parts[1:]:
                    p = p.strip()
                    if p.startswith('align '):
                        al = int(p.split()[1])
                k = s.kind(op, hostvals)
                if k == 'host':
                    s.count('ld_host')
                    out.append(ln)
                    continue
                s.count('ld_guest')
                out.extend(ind + x for x in s.load(dst, ty, op, al))
                continue
            m = re.match(r'store (volatile )?(i1|i8|i16|i32|i64|ptr) (.*)$', st)
            if m:
                vol, ty, rest = m.groups()
                parts = split_top(rest)
                val = parts[0].strip()
                op = parts[1].strip()
                assert op.startswith('ptr '), ln
                op = op[4:]
                al = 0
                for p in parts[2:]:
                    p = p.strip()
                    if p.startswith('align '):
                        al = int(p.split()[1])
                k = s.kind(op, hostvals)
                if k == 'host':
                    s.count('st_host')
                    out.append(ln)
                    continue
                s.count('st_guest')
                out.extend(ind + x for x in s.store(ty, val, op, al))
                continue
            if re.search(r'\b(tail |musttail |notail )?call ', st) and not st.startswith('declare'):
                out.extend(ind + x for x in s.call(st, hostvals))
                continue
            out.append(ln)
        return out

    nl = 0

    def tmp(s):
        s.nl += 1
        return '%%__sfm%d' % s.nl

    def load(s, dst, ty, op, al):
        if ty in ('i1', 'i8'):
            t = s.tmp()
            r = ['%s = call i32 @__sf_ld8(ptr %s)' % (t, op)]
            r.append('%s = trunc i32 %s to %s' % (dst, t, ty))
            return r
        if ty == 'i16':
            t = s.tmp()
            fn = '__sf_ld16' if al == 0 or al >= 2 else '__sf_ld16u'
            return ['%s = call i32 @%s(ptr %s)' % (t, fn, op), '%s = trunc i32 %s to i16' % (dst, t)]
        if ty in ('i32', 'ptr'):
            fn = '__sf_ld32' if al == 0 or al >= 4 else '__sf_ld32u'
            if ty == 'i32':
                return ['%s = call i32 @%s(ptr %s)' % (dst, fn, op)]
            t = s.tmp()
            return ['%s = call i32 @%s(ptr %s)' % (t, fn, op), '%s = inttoptr i32 %s to ptr' % (dst, t)]
        if ty == 'i64':
            return ['%s = call i64 @__sf_ld64(ptr %s)' % (dst, op)]
        raise SystemExit('load type ' + ty)

    def store(s, ty, val, op, al):
        if ty in ('i1', 'i8'):
            t = s.tmp()
            return ['%s = zext %s %s to i32' % (t, ty, val), 'call void @__sf_st8(ptr %s, i32 %s)' % (op, t)]
        if ty == 'i16':
            t = s.tmp()
            fn = '__sf_st16' if al == 0 or al >= 2 else '__sf_st16u'
            return ['%s = zext i16 %s to i32' % (t, val), 'call void @%s(ptr %s, i32 %s)' % (fn, op, t)]
        if ty == 'i32':
            fn = '__sf_st32' if al == 0 or al >= 4 else '__sf_st32u'
            return ['call void @%s(ptr %s, i32 %s)' % (fn, op, val)]
        if ty == 'ptr':
            t = s.tmp()
            fn = '__sf_st32' if al == 0 or al >= 4 else '__sf_st32u'
            return ['%s = ptrtoint ptr %s to i32' % (t, val), 'call void @%s(ptr %s, i32 %s)' % (fn, op, t)]
        if ty == 'i64':
            return ['call void @__sf_st64(ptr %s, i64 %s)' % (op, val)]
        raise SystemExit('store type ' + ty)

    REN = {'memcpy': '__sf_memcpy', 'memset': '__sf_memset', 'memmove': '__sf_memmove', 'memcmp': '__sf_memcmp', 'strlen': '__sf_strlen'}

    def call(s, st, hostvals):
        # intrinsics
        m = re.match(r'(?:(%[\w.]+) = )?(?:tail |musttail |notail )?call (void|ptr) @llvm\.(memcpy|memmove)\.p0\.p0\.i32\((.*)\)(.*)$', st)
        if m:
            a = split_top(m.group(4))
            d, sr, n = (x.strip() for x in a[:3])
            s.count(m.group(3))
            return ['call ptr @__sf_%s(%s, %s, %s)' % (m.group(3), d.split('noundef ')[-1] if False else d, sr, n)]
        m = re.match(r'(?:(%[\w.]+) = )?(?:tail |musttail |notail )?call void @llvm\.memset\.p0\.i32\((.*)\)(.*)$', st)
        if m:
            a = split_top(m.group(2))
            d, v, n = (x.strip() for x in a[:3])
            t = s.tmp()
            s.count('memset')
            vv = v.split()[-1]
            return ['%s = zext i8 %s to i32' % (t, vv), 'call ptr @__sf_memset(%s, i32 %s, %s)' % (d, t, n)]
        if '@llvm.' in st.split('(')[0]:
            return [st]
        m = re.match(r'(?:(%[\w.]+) = )?((?:tail |musttail |notail )?)call ((?:[\w]+ )*?)(void|i1|i8|i16|i32|i64|ptr|\{[^}]*\}|double|float) (.*)$', st)
        if not m:
            return [st]
        dst, tail, attrs, rty, rest = m.groups()
        # callee
        if rest.startswith('@'):
            name = GLOBAL.match(rest).group(1).strip('"')
            if name in s.REN:
                s.count('ren_' + name)
                return [st.replace('@' + name + '(', '@' + s.REN[name] + '(', 1)]
            return [st]
        # find the callee expression: up to the '(' that starts the argument list at depth 0
        depth, i = 0, 0
        while i < len(rest):
            ch = rest[i]
            if ch == '(' and depth == 0 and i > 0 and not rest[:i].rstrip().endswith('inttoptr') and rest[:i].strip() != '':
                break
            if ch in '([{<':
                depth += 1
            elif ch in ')]}>':
                depth -= 1
            i += 1
        callee = rest[:i].strip()
        args = rest[i:]
        if callee.startswith('inttoptr'):
            v = int(INTTOPTR.search(callee).group(1)) & 0xffffffff
            s.count('call_const')
        else:
            s.count('call_ptr')
        t = s.tmp()
        pre = '%s = call ptr @__sf_fnmap(ptr %s)' % (t, callee)
        head = (dst + ' = ' if dst else '') + 'call ' + attrs + rty + ' ' + t
        return [pre, head + args]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    src, dst, natf, romf = args[:4]
    native = set(open(natf).read().split())
    rom = set(open(romf).read().split())
    R = Rewriter(native, rom)
    lines = open(src).read().split('\n')
    out = R.run(lines)
    decl = ['declare i32 @__sf_ld8(ptr)', 'declare i32 @__sf_ld16(ptr)', 'declare i32 @__sf_ld16u(ptr)', 'declare i32 @__sf_ld32(ptr)',
            'declare i32 @__sf_ld32u(ptr)', 'declare i64 @__sf_ld64(ptr)', 'declare void @__sf_st8(ptr, i32)', 'declare void @__sf_st16(ptr, i32)',
            'declare void @__sf_st16u(ptr, i32)', 'declare void @__sf_st32(ptr, i32)', 'declare void @__sf_st32u(ptr, i32)',
            'declare void @__sf_st64(ptr, i64)', 'declare ptr @__sf_memcpy(ptr, ptr, i32)', 'declare ptr @__sf_memmove(ptr, ptr, i32)',
            'declare ptr @__sf_memset(ptr, i32, i32)', 'declare ptr @__sf_fnmap(ptr)', 'declare i32 @__sf_h2g(ptr)', 'declare ptr @__sf_g2h(i32)']
    text = '\n'.join(out)
    if '--outline' in sys.argv:
        text = re.sub(r'@(__sf_(?:ld|st)(?:8|16|32|64)u?)\(', r'@\1_o(', text)
        decl = [re.sub(r'@(__sf_(?:ld|st)(?:8|16|32|64)u?)\(', r'@\1_o(', d) for d in decl]
    for k, v in Rewriter.REN.items():          # declarations of the renamed libc functions
        text = re.sub(r'^declare ([^@]*)@%s\(' % k, r'declare \1@%s(' % v, text, flags=re.M)
    have = set(re.findall(r'^declare [^@]*@(\w+)\(', text, re.M)) | set(re.findall(r'^define [^@]*@(\w+)\(', text, re.M))
    extra = [d for d in decl if re.search(r'@(\w+)\(', d).group(1) not in have]
    open(dst, 'w').write(text + '\n' + '\n'.join(extra) + '\n')
    print('%s: %s' % (src.split('/')[-1], ' '.join('%s=%d' % kv for kv in sorted(R.stat.items()))))


if __name__ == '__main__':
    main()

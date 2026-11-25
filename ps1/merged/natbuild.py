#!/usr/bin/env python3
"""Milestone B stage B2 (PS1): compile Stunt Fox's own C natively for MIPS-I (README.md in this directory).

usage: natbuild.py STUNTFOX_DIR GBA_BUILD_DIR OUT_DIR
  STUNTFOX_DIR   the repository's stuntfox/ (its src/ is copied, never changed)
  GBA_BUILD_DIR  stuntfox/build of the merged GBA build that made the ROM on the disc (build/gen: the generated tables;
                 build/merge/stuntfox-merge.elf: the guest addresses).  Both derive from the player's ROM: private, never committed.
  OUT_DIR        work directory; writes sfnat.o (all native Stunt Fox code and data), sfnat_gen.c (the entry table guest address -> native
                 function, the guest-call stubs of Stunt Fox's assembly functions), sfnat_syms.ld (guest addresses of the tables left in the
                 ROM), sfnat_sections.txt (input section sizes, for the placement) and natbuild.log.
Steps: copy the sources into OUT_DIR/b (gba.h replaced by ps1/merged/include/gba.h; tex.c's target("arm") attributes dropped in the copy),
clang -Os -emit-llvm per file, irmem.py (guest memory model), llvm-link with sfmem.c, opt -Os (inlines the helpers), codegen for MIPS-I."""
import os, re, shutil, subprocess, sys, json
from b3_profile import choose_profile

HERE = os.path.dirname(os.path.abspath(__file__))
# B3 adds a measured, size-gated native candidate for per-frame code/tables.
# SFNAT_PROFILE=b2 retains the previous hybrid configuration for comparisons.
SKIP = {'main.c', 'hud.c'}                       # build.py MERGE_SKIP (C files)
GEN_NATIVE = ['pbtables.c', 'tables.c']
GEN_ROM = ['consttab.c', 'logo.c', 'merge_sig.c', 'pbmip.c', 'planetdata.c']   # read where they lie in the ROM (RAM is short)
# functions written in C for the PS1 in place of Stunt Fox's ARM assembly (sfport.c); the other assembly functions run in the interpreter
PORTED = {'fill_trap', 'rec_hash', 'tex_hrun', 'tex_hrun4', 'tex_vrun', 'tex_mrun1', 'tex_vrun4', 'tex_mrun', 'tex_walk'}
RUNTIME = {'sf_rd', 'sf_wr', 'sf_resolve', 'sf_native_of', 'sf_gthunk', 'sf_gtarget', '__sf_guest_lr'}
LINKER = re.compile(r'^__(hot\d*b?_(start|end|lma|save)|data_(start|end|lma)|bss_(start|end)|keep_canary|pool_a(_end)?|scr)$')
CF = ['--target=mipsel-none-elf', '-march=mips1', '-mno-abicalls', '-mfp32', '-msoft-float', '-fno-pic', '-ffreestanding', '-fno-builtin',
      '-G0', '-mno-gpopt', '-mno-check-zero-division', '-fomit-frame-pointer', '-Wno-everything']


def run(cmd, log):
    r = subprocess.run(cmd, capture_output=True, text=True)
    log.write('$ ' + ' '.join(cmd) + '\n' + r.stdout + r.stderr)
    if r.returncode:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit('natbuild: failed: ' + ' '.join(cmd[:3]) + ' ...')
    return r.stdout


def gba_symbols(elf, log):
    out = run(['llvm-nm', elf], log)
    syms, count = {}, {}
    for line in out.splitlines():
        p = line.split()
        if len(p) != 3:
            continue
        a, t, n = int(p[0], 16), p[1], p[2]
        count[n] = count.get(n, 0) + 1
        syms[n] = (a, t)
    return syms, count


def gba_ram_objects(elf, log, path):
    """the GBA build's RAM variables by file (FILE symbols open each object's locals): pin.py's table"""
    secs = {}
    for line in run(['llvm-readelf', '-S', '-W', elf], log).splitlines():
        m = re.match(r'\s*\[\s*(\d+)\]\s+(\S+)', line)
        if m:
            secs[m.group(1)] = m.group(2)
    kind = {'.data': 'data', '.bss': 'bss', '.radio': 'bss', '.scratch': 'bss', '.scratch2': 'bss'}
    f, rows = '-', []
    for line in run(['llvm-readelf', '-s', '-W', elf], log).splitlines():
        p = line.split()
        if len(p) < 8 or not p[0].endswith(':'):
            continue
        if p[3] == 'FILE':
            f = p[7]
        elif p[3] == 'OBJECT' and secs.get(p[6]) in kind:
            rows.append('%s %s %s %s %s' % (f if p[4] == 'LOCAL' else '-', p[7], p[1], p[2], kind[secs[p[6]]]))
    # a variable gcc split (v.0, v.1, ... side by side) and clang may not: also as one object "v" over the whole span
    grp = {}
    for r in rows:
        f, n, ad, sz, k = r.split()
        m = re.match(r'^(.*)\.(\d+)$', n)
        if m:
            grp.setdefault((f, m.group(1), k), []).append((int(ad, 16), int(sz)))
    have = {(r.split()[0], r.split()[1]) for r in rows}
    for (f, v, k), parts in grp.items():
        parts.sort()
        if len(parts) > 1 and (f, v) not in have and all(parts[i][0] + parts[i][1] == parts[i + 1][0] for i in range(len(parts) - 1)):
            rows.append('%s %s %08x %d %s' % (f, v, parts[0][0], parts[-1][0] + parts[-1][1] - parts[0][0], k))
    open(path, 'w').write('\n'.join(rows) + '\n')


def main():
    sfdir, gbadir, out = (os.path.abspath(x) for x in sys.argv[1:4])
    opt = os.environ.get('SFNAT_OPT', '-Os')
    os.makedirs(out, exist_ok=True)
    log = open(os.path.join(out, 'natbuild.log'), 'w')
    b = os.path.join(out, 'b')
    shutil.rmtree(b, ignore_errors=True)
    shutil.copytree(os.path.join(sfdir, 'src'), os.path.join(b, 'src'))
    shutil.copytree(os.path.join(gbadir, 'gen'), os.path.join(b, 'build', 'gen'))
    for h in os.listdir(os.path.join(HERE, 'include')):
        shutil.copy(os.path.join(HERE, 'include', h), os.path.join(b, 'src', h))
    tex = os.path.join(b, 'src', 'tex.c')               # (MIPS has no ARM state: the attribute is an error there, nothing else changes)
    t = open(tex).read()
    t2 = t.replace('target("arm"), ', '').replace(', target("arm")', '').replace('__attribute__((target("arm")))', '')
    assert 'target("arm")' not in t2
    open(tex, 'w').write(t2)
    inc = ['-nostdinc', '-isystem', os.path.join(HERE, 'libc'), '-isystem', '/usr/lib/llvm-18/lib/clang/18/include',
           '-DMERGE', '-DPS1', '-I' + os.path.join(b, 'src'), '-I' + os.path.join(b, 'build', 'gen')]
    profile, only, keep_native, hot = choose_profile()
    compact_report = None
    compact = os.environ.get('SFNAT_COMPACT_MATH', '0')
    if compact not in ('0', '1'):
        raise SystemExit('SFNAT_COMPACT_MATH must be 0 or 1')
    if compact == '1':
        from compact_math import apply, TABLES, NEW
        compact_report = apply(b)
        keep_native = (set(keep_native) - set(TABLES)) | NEW
        log.write('compact math: '+json.dumps(compact_report, sort_keys=True)+'\n')
    srcs = sorted(os.path.join(b, 'src', f) for f in os.listdir(os.path.join(b, 'src'))
                  if f.endswith('.c') and f not in SKIP and (not only or f[:-2] in only))
    srcs += [os.path.join(b, 'build', 'gen', f) for f in GEN_NATIVE]
    # An explicit typo must not silently reduce native coverage.
    if only - {os.path.basename(s)[:-2] for s in srcs}:
        raise SystemExit('natbuild: unknown native file(s): ' +
                         ' '.join(sorted(only - {os.path.basename(s)[:-2] for s in srcs})))
    ir = os.path.join(out, 'ir')
    os.makedirs(ir, exist_ok=True)
    # the ROM tables: their globals are read at their guest addresses
    rom = set()
    for f in GEN_ROM:
        ll = os.path.join(ir, 'rom_' + f[:-2] + '.ll')
        run(['clang'] + CF + ['-O0'] + inc + ['-S', '-emit-llvm', os.path.join(b, 'build', 'gen', f), '-o', ll], log)
        rom |= set(re.findall(r'^@([\w.]+) = (?:dso_local )?(?:local_unnamed_addr )?(?:unnamed_addr )?constant', open(ll).read(), re.M))
    # read-only data that the ROM holds at a known address (a unique name of the GBA build): read from there (rom_pg pages, sfglue.h
    # sf_rd), not linked a second time into the PS1's RAM; the hot tables of the renderer stay native
    gs, gc = gba_symbols(os.path.join(gbadir, 'merge', 'stuntfox-merge.elf'), log)
    romconst = {n for n, (a, t) in gs.items() if gc[n] == 1 and a >> 24 == 8 and t in 'rRtT' and n not in keep_native}
    rom |= romconst | {n for n, (a, t) in gs.items() if t == 'A' and a >> 24 in (8, 9)}   # (and the blobs the GBA link places: s2_blob, st_blob)
    # Selected native scalar tables must never be classified as guest ROM
    # globals by irmem. All generated assets remain in the private build.
    rom -= keep_native
    open(os.path.join(out, 'rom_globals.txt'), 'w').write('\n'.join(sorted(rom)) + '\n')
    open(os.path.join(out, 'native_globals.txt'), 'w').write('\n')
    lls = []
    gba_ram_objects(os.path.join(gbadir, 'merge', 'stuntfox-merge.elf'), log, os.path.join(out, 'gba_ram.txt'))
    # the GBA build's .data initial image (every file's, the interpreted ones' too): place.py fills the native image's bytes that no native
    # variable covers from it, and datacheck.py compares the linked image with it (build directory only, never committed)
    run(['llvm-objcopy', '-O', 'binary', '--only-section=.data', os.path.join(gbadir, 'merge', 'stuntfox-merge.elf'),
         os.path.join(out, 'gba_data.bin')], log)
    for line in run(['llvm-readelf', '-S', '-W', os.path.join(gbadir, 'merge', 'stuntfox-merge.elf')], log).splitlines():
        m = re.match(r'\s*\[\s*\d+\]\s+\.data\s+\S+\s+([0-9a-f]+)\s+\S+\s+([0-9a-f]+)', line)
        if m:
            open(os.path.join(out, 'gba_data.txt'), 'w').write('0x%s 0x%s\n' % (m.group(1), m.group(2)))
    if os.path.exists(os.path.join(out, 'pin_report.txt')):
        os.remove(os.path.join(out, 'pin_report.txt'))
    for s in srcs:
        n = os.path.basename(s)[:-2]
        ll = os.path.join(ir, n + '.ll')
        run(['clang'] + CF + [opt, '-ffunction-sections', '-fdata-sections'] + inc + ['-S', '-emit-llvm', s, '-o', ll], log)
        run(['opt', '-passes=instnamer', '-S', ll, '-o', ll], log)     # (named values: the rewrite adds and drops instructions)
        src_ll = open(ll).read()
        fns = set(re.findall(r'^(?:define|declare) [^@]*@([\w.$]+)\(', src_ll, re.M))
        def to_rom(m):
            # (not a table of functions: the guest form of an IWRAM function is Payback's code on the PS1)
            if m.group(1) not in romconst or any(f in fns for f in re.findall(r'@([\w.$]+)', m.group(0)[len(m.group(1)) + 1:])):
                return m.group(0)
            r, d = m.group(2), 0                    # the type: up to the space after its brackets close
            for q, ch in enumerate(r):
                if ch in '[{<':
                    d += 1
                elif ch in ']}>':
                    d -= 1
                elif ch == ' ' and d == 0:
                    break
            return '@%s = external constant %s' % (m.group(1), r[:q])
        txt, k = re.subn(r'^@([\w.]+) = (?:internal |private |dso_local |local_unnamed_addr |unnamed_addr )*constant (.*)$', to_rom, src_ll, flags=re.M)
        # __builtin_return_address(0) of a function the guest calls (merge.c sf_pick_rand tells Payback's two callers apart by it): the
        # guest's lr of this entry (sfglue.h), not the native return address
        txt, k = re.subn(r'call ptr @llvm\.returnaddress\(i32 0\)', 'call ptr @__sf_guest_lr()', txt)
        if k:
            txt += '\ndeclare ptr @__sf_guest_lr()\n'
        open(ll, 'w').write(txt)
        rw = os.path.join(ir, n + '.mem.ll')
        log.write(run([sys.executable, os.path.join(HERE, 'irmem.py'), ll, rw, os.path.join(out, 'native_globals.txt'),
                       os.path.join(out, 'rom_globals.txt')] + ([] if n in hot else ['--outline']), log))
        pn = os.path.join(ir, n + '.pin.ll')
        run([sys.executable, os.path.join(HERE, 'pin.py'), rw, pn, os.path.basename(s), os.path.join(out, 'gba_ram.txt'),
             os.path.join(out, 'pin_report.txt')], log)
        lls.append(pn)
    mem = os.path.join(ir, 'sfmem.ll')
    run(['clang'] + CF + [opt] + os.environ.get('SFMEM_FLAGS', '').split() + ['-S', '-emit-llvm', os.path.join(HERE, 'sfmem.c'), '-o', mem], log)
    port = os.path.join(ir, 'sfport.ll')
    run(['clang'] + CF + [opt] + inc + ['-S', '-emit-llvm', os.path.join(HERE, 'sfport.c'), '-o', port], log)
    prw = os.path.join(ir, 'sfport.mem.ll')
    run(['opt', '-passes=instnamer', '-S', port, '-o', port], log)
    run([sys.executable, os.path.join(HERE, 'irmem.py'), port, prw, os.path.join(out, 'native_globals.txt'), os.path.join(out, 'rom_globals.txt')], log)
    linked = os.path.join(out, 'sf.bc')
    run(['llvm-link', '-o', linked, mem, prw] + lls, log)
    # the functions the guest enters: the ROM's patches (build.py names them) and Stunt Fox's assembly (interpreted; its relocations name
    # them): kept whole (@llvm.used) though the optimiser inlines them, so that the guest reaches native code, never the GBA copy
    want = set(re.findall(r"'([A-Za-z_]\w*)'", open(os.path.join(sfdir, 'build.py')).read()))
    for o in os.listdir(os.path.join(gbadir, 'merge')):
        if o.endswith('.s.o'):
            for line in run(['llvm-objdump', '-r', os.path.join(gbadir, 'merge', o)], log).splitlines():
                p = line.split()
                if len(p) == 3 and re.match(r'^[A-Za-z_]\w*$', p[2]):
                    want.add(p[2])
    txt = run(['llvm-dis', linked, '-o', '-'], log)
    have = set(re.findall(r'^define [^@]*@([\w.$]+)\(', txt, re.M))
    keep = sorted(want & have)
    um = re.search(r'^@llvm\.used = appending global \[(\d+) x ptr\] \[(.*)\], section "llvm.metadata"$', txt, re.M)
    arr = ', '.join('ptr @%s' % n for n in keep)
    if um:
        txt = txt[:um.start()] + '@llvm.used = appending global [%d x ptr] [%s, %s], section "llvm.metadata"' % (int(um.group(1)) + len(keep), um.group(2), arr) + txt[um.end():]
    else:
        txt += '\n@llvm.used = appending global [%d x ptr] [%s], section "llvm.metadata"\n' % (len(keep), arr)
    open(os.path.join(out, 'sf.keep.ll'), 'w').write(txt)
    declared_fns = set(re.findall(r'^declare [^@]*@([\w.$]+)\(', txt, re.M))
    log.write('kept for the guest: %s\n' % ' '.join(keep))
    linked = os.path.join(out, 'sf.keep.ll')
    optd = os.path.join(out, 'sf.opt.bc')
    run(['opt', opt.replace('-O', '-O') if opt != '-Oz' else '-Oz', linked, '-o', optd], log)
    obj = os.path.join(out, 'sfnat.o')
    run(['clang'] + CF + [opt, '-ffunction-sections', '-fdata-sections', '-mllvm', '-disable-mips-delay-filler', '-c', optd, '-o', obj], log)
    # symbols: what the native object defines and needs
    nm = run(['llvm-nm', obj], log)
    defined, undef = {}, set()
    for line in nm.splitlines():
        p = line.split()
        if len(p) == 2 and p[0] == 'U':
            undef.add(p[1])
        elif len(p) == 3:
            defined[p[2]] = p[1]
    # every symbol of the module gets the prefix sfn_ (Stunt Fox's names meet the runtime's: sv_load, __bss_start, ...), bar the runtime's own
    ren = os.path.join(out, 'sfnat_rename.txt')
    with open(ren, 'w') as f:
        for n in sorted(set(defined) | undef):
            if n not in RUNTIME:
                f.write('%s sfn_%s\n' % (n, n))
    run(['llvm-objcopy', '--redefine-syms=' + ren, obj], log)
    gsyms, gcount = gba_symbols(os.path.join(gbadir, 'merge', 'stuntfox-merge.elf'), log)
    with open(os.path.join(out, 'gba_linker.txt'), 'w') as f:     # merge.ld's symbols (place.py: the native module's take their RAM values)
        for n, (a, t) in sorted(gsyms.items()):
            if LINKER.match(n):
                f.write('%s 0x%08x\n' % (n, a))
    stubs, absol, bad = [], [], []
    for u in sorted(undef):
        if u in RUNTIME or LINKER.match(u):
            continue
        if u in declared_fns and u in gsyms and gsyms[u][1] in 'Tt' and u not in PORTED:
            stubs.append((u, gsyms[u][0]))          # a Stunt Fox function left interpreted (SFNAT_ONLY): a guest call
        elif u in rom or (u in gsyms and gsyms[u][1] == 'A'):
            absol.append((u, gsyms[u][0]))
        elif u in gsyms and gsyms[u][1] in 'bBdD' and gsyms[u][0] >> 24 == 2 and gcount[u] == 1:
            absol.append((u, 0x801b0000 + gsyms[u][0] - 0x02000000))   # a variable of a file left interpreted: its host image (pin.py)
        elif u in gsyms and gsyms[u][1] in 'Tt' and u not in PORTED:
            stubs.append((u, gsyms[u][0]))
        else:
            bad.append(u)
    if bad:
        raise SystemExit('natbuild: undefined and not provided: ' + ' '.join(bad))
    # s2core.c gives every package's entry a weak stub (stage2.h); on the GBA the package's strong definition wins at link time.  A package
    # left interpreted (station.c's st_view, ...) is strong in the GBA build only: its guest stub (strong) overrides the native weak one
    weak_over = sorted(n for n, t in defined.items() if t in 'Ww' and n in gsyms and gsyms[n][1] in 'Tt' and n not in PORTED
                       and re.match(os.environ.get('SFNAT_WEAK', ''), n))
    stubs += [(n, gsyms[n][0]) for n in weak_over]
    log.write('weak native entries overridden by interpreted strong ones: %s\n' % ' '.join(weak_over))
    ents, iw = [], []
    for n, t in defined.items():
        if t in 'Tt' and n in gsyms and gcount[n] == 1 and gsyms[n][1] in 'Tt' and not n.startswith('__sf_'):
            # Stunt Fox's IWRAM code (0x03...) goes to a table of its own: on the PS1 IWRAM keeps Payback's code at those addresses
            # (hot_install copies nothing), so sfglue.h takes such a target as ours only when Stunt Fox's interpreted code calls it
            (iw if gsyms[n][0] >> 24 == 3 else ents).append((gsyms[n][0] & ~1, n))
    ents.sort()
    iw.sort()
    glob = [n for _, n in ents + iw if defined[n] == 't']           # static in Stunt Fox, but the guest reaches it: the entry table needs it global
    if glob:
        run(['llvm-objcopy'] + ['--globalize-symbol=sfn_' + n for n in sorted(set(glob))] + [obj], log)
    with open(os.path.join(out, 'sfnat_gen.c'), 'w') as f:
        f.write('/* generated by ps1/merged/natbuild.py: guest addresses from the private GBA build; never committed */\n')
        f.write('typedef unsigned int u32; typedef unsigned long long u64;\n')
        f.write('u64 sf_guest_call(u32 t, const u32 *a);\n')
        # a guest stub is three instructions: the guest address in $8, then sf_gstub, which hands sixteen argument words (a0-a3 and the
        # caller's twelve stack words, as sfglue.h's SF_NARG: a V3 by value is three) to sf_guest_call and returns its r0/r1 in v0/v1
        f.write('__asm__(".set push\\n.set noreorder\\n.set noat\\n.text\\n"\n'
                '"sf_gstub:\\n  addiu $29,$29,-88\\n  sw $31,84($29)\\n  sw $4,16($29)\\n  sw $5,20($29)\\n  sw $6,24($29)\\n  sw $7,28($29)\\n"\n')
        for k in range(0, 12, 4):            # (MIPS I: a loaded register is not ready for the next instruction; four loads, then four stores)
            f.write('"%s%s"\n' % (''.join('  lw $%d,%d($29)\\n' % (9 + i, 104 + 4 * (k + i)) for i in range(4)),
                                  ''.join('  sw $%d,%d($29)\\n' % (9 + i, 32 + 4 * (k + i)) for i in range(4))))
        f.write('"  move $4,$8\\n  jal sf_guest_call\\n  addiu $5,$29,16\\n  lw $31,84($29)\\n  nop\\n  jr $31\\n  addiu $29,$29,88\\n"\n')
        for n, a in stubs:
            f.write('".globl sfn_%s\\nsfn_%s:\\n  lui $8,0x%04x\\n  j sf_gstub\\n  ori $8,$8,0x%04x\\n"\n' % (n, n, a >> 16, a & 0xffff))
        f.write('".set pop\\n");\n')
        names = sorted({n for _, n in ents + iw})
        for n in names:
            f.write('extern char sfn_%s[];\n' % n)
        f.write('const u32 sfnat_nent = %d;\nconst u32 sfnat_ent[][2] = {\n' % len(ents))
        for a, n in ents:
            f.write('  {0x%08xu, (u32)sfn_%s},\n' % (a, n))
        f.write('};\n')
        f.write('const u32 sfnat_niw = %d;\nconst u32 sfnat_iw[][2] = {\n' % len(iw))
        for a, n in iw:
            f.write('  {0x%08xu, (u32)sfn_%s},\n' % (a, n))
        f.write('  {0, 0}\n};\n')
    with open(os.path.join(out, 'sfnat_syms.ld'), 'w') as f:
        for n, a in absol:
            f.write('sfn_%s = 0x%08x;\n' % (n, a))
    # input sections and their sizes (placement)
    hdr = run(['llvm-readelf', '-S', '-W', obj], log)
    secs = []
    for line in hdr.splitlines():
        m = re.match(r'\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+([0-9a-f]+)\s+\S+\s+(\S*)\s+\S+\s+\S+\s+(\d+)', line)
        if m and 'A' in m.group(4):
            secs.append((m.group(1), m.group(2), int(m.group(3), 16), int(m.group(5))))
    with open(os.path.join(out, 'sfnat_sections.txt'), 'w') as f:
        for s in secs:
            f.write('%s %s %d %d\n' % s)
    tot = {}
    for name, typ, size, al in secs:
        k = name.split('.')[1] if name.count('.') else name
        tot[k] = tot.get(k, 0) + size
    print('natbuild: %d files, entries %d, guest stubs %d (%s), ROM symbols %d' % (len(srcs), len(ents), len(stubs),
                                                                              ' '.join(n for n, _ in stubs), len(absol)))
    print('natbuild: section bytes ' + ' '.join('%s=%d' % kv for kv in sorted(tot.items())))
    kept = sorted(n for n in keep_native if n in defined and defined[n] in 'rR')
    report = dict(profile=profile, native_files=[os.path.basename(s) for s in srcs],
                  requested_native_tables=sorted(keep_native), linked_native_tables=kept,
                  native_entries=len(ents), iwram_entries=len(iw),
                  guest_stubs=len(stubs), section_bytes=tot, compact_math=compact_report)
    with open(os.path.join(out, 'b3_native_census.json'), 'w') as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write('\n')
    print('natbuild: profile %s, resident scalar tables %s' % (profile, ' '.join(kept)))


if __name__ == '__main__':
    main()

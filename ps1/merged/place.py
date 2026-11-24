#!/usr/bin/env python3
"""Milestone B stage B2 (PS1): where native Stunt Fox goes in RAM (README.md: "B2 layout").

usage: place.py NATDIR COLD_HOST OUT.ld OUT.h
  NATDIR     natbuild.py's output (sfnat_sections.txt: input sections of sfnat.o and their sizes)
  COLD_HOST  first byte of the cold-group arena (0x80030000 + the translated blob's size)
With sf3 and the PS1 ragdoll solver off (B2: Stunt Fox draws its own picture and runs its own ragdolls), their RAM holds native Stunt Fox:
  R3  the renderer region 0x80199000..0x801b0000 after the PPU code that lives there (-DPP_INSF): code only (no data: a guest read of a
      host address there would be folded into VRAM by rt.c vram_over)
  R2  the ragdoll region 0x80165000..0x8017a000 (after the page cache), before the runtime's page-frame table (.dl.bss.pg_fr): code only
  R1  from SF_NAT_LO up to 0x80119000: the rest of the code, all read-only data, the entry table, the initial image of .data; it covers
      the renderer's world window and buffers (unused without sf3) and the top cold groups: SF_NAT_LO is a cold-group boundary and
      rt.c cold_find interprets every group that reaches it (never loads it over native code)
  stack 0x80119000..0x8011c000 (12 KiB): the native stack (sfglue.h; the GBA ran Stunt Fox on Payback's IWRAM stack)
  data  Stunt Fox's variables on the host images of merge.ld's regions: keep 0x0203d000 (canary, .data, .bss), radio 0x0203ffec, scr
        0x02017fc4 (.scratch), scr2 0x020075a8 (.scratch2): the guest memory picture stays the one stuntfox/memmap.txt proved safe.
Writes the linker script (ps1rt/ps1.ld with those regions) and sfnat_place.h (SF_NAT_LO, the native stack)."""
import re
import sys

EW = 0x801b0000
def host(g): return EW + g - 0x02000000


def main():
    natdir, cold_host, out_ld, out_h = sys.argv[1], int(sys.argv[2], 0), sys.argv[3], sys.argv[4]
    secs = []
    for line in open(natdir + '/sfnat_sections.txt'):
        n, t, size, al = line.split()
        secs.append((n, t, int(size), max(1, int(al))))
    text = sorted([s for s in secs if s[0].startswith('.text')], key=lambda s: -s[2])
    ro = [s for s in secs if s[0].startswith('.rodata')]
    caps = {'R3': 0x801b0000 - 0x80199000 - 0x2400 - 0x1800, 'R2': 0x8017a000 - 0x80165000 - 0x1000 - 0x40}
    used = {'R3': 0, 'R2': 0}
    where = {'R3': [], 'R2': [], 'R1': []}
    for s in text:
        a = (s[2] + 3) & ~3
        for r in ('R3', 'R2'):
            if used[r] + a + 16 <= caps[r]:
                used[r] += a
                where[r].append(s[0])
                break
        else:
            where['R1'].append(s[0])
    r1 = sum((s[2] + 15) & ~15 for s in secs if s[0] in set(where['R1'])) + sum((s[2] + 15) & ~15 for s in ro)
    g = open(natdir + '/sfnat_gen.c').read()            # the entry table (8 bytes an entry) and the guest stubs (about 100 bytes each)
    r1 += 8 * int(re.search(r'sfnat_nent = (\d+)', g).group(1)) + 128 * g.count('sf_guest_call(0x') + 0x200
    stack_lo, top = 0x80119000, 0x8011c000
    lo = stack_lo - r1
    k = (lo - cold_host) // 16384          # the cold group that holds lo: native code starts at its start
    nat_lo = cold_host + k * 16384
    assert nat_lo > 0x800a8100, 'native Stunt Fox would reach the boot image (%x)' % nat_lo
    def lst(r):
        return ' '.join('*sfnat.o(%s)' % n for n in where[r]) or ''
    # pinned variables (pin.py): one output section each, at the host image of the GBA address; .data's carry their place in the image
    gsz = {}
    for line in open(natdir + '/gba_ram.txt'):
        f, n, ad, sz, k = line.split()
        gsz[int(ad, 16)] = max(gsz.get(int(ad, 16), 0), int(sz))
    pins, unp = [], []
    for n, t, size, al in secs:
        m = re.match(r'\.(data|bss)\.sfv\.([0-9a-f]{8})$', n)
        if m:
            ad = int(m.group(2), 16)
            assert size <= gsz.get(ad, 0), 'native %s (%d B) is bigger than its GBA twin (%d B)' % (n, size, gsz.get(ad, 0))
            pins.append((ad, m.group(1), n))
        elif n.startswith(('.data', '.bss', '.sdata', '.sbss', '.scratch', '.radio')) and n not in ('.data', '.bss', '.sdata', '.sbss'):
            unp.append(n)
    pins.sort()
    D0, D1, B1 = 0x0203d004, 0x0203d400, 0x0203d400 + 0x22cc
    pl = []
    for ad, k, n in pins:
        nm = '.sfv_%08x' % ad
        if k == 'data':
            assert D0 <= ad < D1, n
            pl.append(' %s 0x%08x : AT(sfn___data_lma + 0x%x) { *sfnat.o(%s) }' % (nm, host(ad), ad - D0, n))
        else:
            pl.append(' %s 0x%08x (NOLOAD) : { *sfnat.o(%s) }' % (nm, host(ad), n))
    pinned = '\n'.join(pl)
    gl = []
    for line in open(natdir + '/gba_linker.txt'):
        n, v = line.split()
        v = int(v, 16)
        if n.startswith('__hot') and not n.endswith('_save') or n == '__data_lma':
            continue                    # (IWRAM code regions: empty, below; the .data image: native)
        gl.append('sfn_%s = 0x%08x;' % (n, host(v) if v >> 24 == 2 else v))
    gl = ' '.join(gl)
    unpinned = ' '.join('*sfnat.o(%s)' % n for n in unp)
    r1 += sum((s[2] + 15) & ~15 for s in secs if s[0] in set(unp)) + (D1 - D0)
    lo = stack_lo - r1
    k = (lo - cold_host) // 16384
    nat_lo = cold_host + k * 16384
    assert nat_lo > 0x800a8100, 'native Stunt Fox would reach the boot image (%x: %d bytes too many)' % (nat_lo, 0x800ab430 - lo)
    ld = r"""/* generated by ps1/merged/place.py (Milestone B stage B2, -DMERGED_NATIVE): ps1rt/ps1.ld with native Stunt Fox in the RAM of sf3 and doll.c */
ENTRY(_start)
SECTIONS{ . = 0x80010000;
 .text : { *(.text.start) *(EXCLUDE_FILE(*sfnat.o *sfnat_gen.o) .text*) *(EXCLUDE_FILE(*sfnat.o *sfnat_gen.o) .rodata*) *(EXCLUDE_FILE(*sfnat.o *sfnat_gen.o) .data*) *(EXCLUDE_FILE(*sfnat.o *sfnat_gen.o) .sdata*) }
 . = ALIGN(4); __bss_start = .; .bss : { *(EXCLUDE_FILE(*sfnat.o *sfnat_gen.o) .bss*) *(EXCLUDE_FILE(*sfnat.o *sfnat_gen.o) .sbss*) *(EXCLUDE_FILE(*sfnat.o *sfnat_gen.o) COMMON) } __bss_end = .;
 ASSERT(. < 0x80028000, "C runtime overlaps the helper table at 0x80028000")
 . = 0x80028040; __rtcold_start = .; .rtcold : { *(.rtcold.text*) *(.rtcold.rodata*) *(.rtcold.data*) } __rtcold_end = .;
 ASSERT(__rtcold_start >= 0x80028010, "cold runtime code overlaps the helper table")
 ASSERT(__rtcold_end <= 0x8002a000, "cold runtime code overlaps the ROM page-table area at 0x8002a000")
 . = 0x80030000; .blob : { *(.blob) }
 . = ALIGN(16); .bootimg : { *(.bootimg) }
 ASSERT(. <= SF_NAT_LO, "translated blob or boot image overlaps native Stunt Fox")
 . = SF_NAT_LO; .sfn1 : { *sfnat_gen.o(.text* .rodata* .data* .sdata*) *sfnat.o(.rodata* .lit*) . = ALIGN(16); *sfnat.o(.data .sdata .bss .sbss) %(unpinned)s . = ALIGN(16); __sfn1_text = .; %(R1)s }
 . = ALIGN(16); sfn___data_lma = .;
 . += %(data_size)s;
 ASSERT(. <= 0x80119000, "native Stunt Fox overlaps its stack")
 . = 0x8011c000; .coldtab : { *(.coldtab) }
 . = ALIGN(16); .rompack : { *(.rompack) }
 ASSERT(. <= __ps1_pcache_start, "resident ROM pages overlap the page cache")
 . = DEFINED(__doll_addr) ? __doll_addr : 0x80163000; __doll_start = .; .doll : { %(R2)s }
 . = ALIGN(16); __dlbss_start = .; .dlbss : { *(.dl.bss*) *(.dl.sbss*) } __dlbss_end = .;
 ASSERT(__ps1_pcache_end <= __doll_start, "ROM page cache overlaps native Stunt Fox (R2)")
 ASSERT(. <= 0x8017a000, "native Stunt Fox (R2) overlaps PPU scratch")
 . = 0x8017a000; .ppuscratch (NOLOAD) : {
   __ppu_start = .; . += 0x1000;
   __veneer_scratch = .; . += 0x1000;
 }
 ASSERT(. == 0x8017c000, "PPU scratch overlaps the draw ring")
 . = 0x80199000; .sf : { *(.sf.text*) *(.sf.rodata*) *(.sf.data*) *(.sf.sdata*) *(.sfro) %(R3)s }
 . = ALIGN(16); __sfbss_start = .; .sfbss (NOLOAD) : { *(.sf.bss*) *(.sf.sbss*) } __sfbss_end = .;
 ASSERT(. < 0x801b0000, "native Stunt Fox (R3) overlaps guest EWRAM")
 /* Stunt Fox's variables at the host images of their GBA addresses (pin.py; NOLOAD but .data: the boot image writes EWRAM, merge.c start()
    copies .data from __data_lma as on the GBA) */
%(pinned)s
 %(gl)s
 /* merge.ld's IWRAM code regions: empty on the PS1 (native code needs no IWRAM), so hot_install / hot_restore copy nothing */
 %(hot)s
 /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.gnu.attributes) *(.pdr) *(.comment) *(.mdebug*) }
}
""" % {'R1': lst('R1'), 'R2': lst('R2'), 'R3': lst('R3'), 'keep': hex(host(0x0203d000)), 'keep4': hex(host(0x0203d004)),
       'keep_end': hex(host(0x0203d000 + 0x2f90)), 'radio': hex(host(0x0203ffec)), 'radio_end': hex(host(0x0203ffec + 0x14)),
       'scr': hex(host(0x02017fc4)), 'scr_end': hex(host(0x02017fc4 + 0x1440)), 'scr2': hex(host(0x020075a8)),
       'scr2_end': hex(host(0x020075a8 + 0x3e4)), 'poola': hex(host(0x02004374)), 'poola_end': hex(host(0x02004374 + 0x28bc)),
       'pinned': pinned, 'gl': gl, 'unpinned': unpinned, 'data_size': hex(D1 - D0), 'data_end': hex(host(D1)), 'bss_end': hex(host(B1)),
       'hot': ' '.join('sfn___hot%s_start = 0x801f30b0; sfn___hot%s_end = 0x801f30b0; sfn___hot%s_lma = 0x801f30b0;' % (k, k, k)
                       for k in ('', '2', '3', '4', '5', '6', '6b', '7', '8', '9', '10', '11'))}
    ld = ld.replace('SF_NAT_LO', hex(nat_lo))
    open(out_ld, 'w').write(ld)
    open(out_h, 'w').write('/* generated by ps1/merged/place.py */\n#define SF_NAT_LO 0x%08xu\n#define SF_NAT_STACK_LO 0x%08xu\n#define SF_NAT_STACK_TOP 0x%08xu\n'
                           % (nat_lo, stack_lo, top - 16))
    print('place: R3 %d B (%d functions), R2 %d B (%d), R1 %d B from 0x%08x (cold groups from %d interpreted), stack 0x%08x..0x%08x'
          % (used['R3'], len(where['R3']), used['R2'], len(where['R2']), r1, nat_lo, k, stack_lo, top))


if __name__ == '__main__':
    main()

# Session for obrun.py: no input; run until the guest has counted OB_GF GBA frames (io_cyc / 280896) or OB_MAXF emulated
# frames have passed; a screenshot and the CPU registers at the end.  For quick "does this firmware variant get past
# guest frame N" checks.  Build independent.
import os
GF = int(os.environ.get('OB_GF', '700')); MAXF = int(os.environ.get('OB_MAXF', '40000'))
def gf(): return S.g('io_cyc') // 280896
S.run(600)
ok = S.until(lambda S: gf() >= GF and S.g('io_cyc') < (1 << 40), MAXF - 600, (), 30)
S.shot('end')
w = S.cpu_regs()
S.mark('until_gf', reached=bool(ok), target_gf=GF, gf=gf(), pc=None if w is None else '%08x' % w[34], ra=None if w is None else '%08x' % w[31],
       sp=None if w is None else '%08x' % w[29])

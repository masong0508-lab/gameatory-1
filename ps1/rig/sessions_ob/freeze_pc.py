# Session for obrun.py: run OB_FRAMES emulated frames without input, take a screenshot, then sample the CPU registers
# OB_PCS times (10 frames apart) through a save state: shows where a frozen program is looping.  Build independent.
import os
N = int(os.environ.get('OB_FRAMES', '1800'))
K = int(os.environ.get('OB_PCS', '8'))
STEP = max(1, N // 6)
done = 0
while done < N:
    n = min(STEP, N - done)
    S.run(n); done += n
    S.mark('progress', pc='%08x' % (S.cpu_pc() or 0))
S.shot('end')
pcs = []
for k in range(K):
    S.run(10); w = S.cpu_regs()
    pcs.append(None if w is None else {'pc': '%08x' % w[34], 'ra': '%08x' % w[31], 'sp': '%08x' % w[29], 'v0': '%08x' % w[2], 'v1': '%08x' % w[3]})
S.mark('pc_samples', pcs=pcs, g_nvbl=S.g('g_nvbl'), cd_sectors=S.g('cd_sectors'), pad_raw=S.g('pad_raw'))

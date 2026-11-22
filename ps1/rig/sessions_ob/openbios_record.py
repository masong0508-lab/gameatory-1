# Session for obrun.py: for a core that runs the open-source BIOS it carries inside (system directory without a firmware
# file): run OB_FRAMES frames without input, then print that BIOS' saved thread record at RAM 0x9088 (flags, flags2, r0..r31,
# returnPC, hi, lo, SR, Cause): where the program was when the BIOS gave up, and why (Cause bits 2..6 = exception code).
import os
S.run(int(os.environ.get('OB_FRAMES', '1500')))
w = [S.e.r32(0x9088 + 4 * i) for i in range(39)]
code = (w[38] >> 2) & 31
S.mark('openbios_record', returnPC='%08x' % w[34], hi='%08x' % w[35], lo='%08x' % w[36], SR='%08x' % w[37], Cause='%08x' % w[38], exception_code=code,
       sp='%08x' % w[2 + 29], ra='%08x' % w[2 + 31], word_at_80010000='%08x' % S.e.r32(0x80010000), pc=S.cpu_pc() if hasattr(S, 'cpu_pc') else None)

#!/usr/bin/env python3
"""obrig.py: extensions of the rig frontend (retro_ps1.Emu) used by the openboot / accurate-core tests.

  Emu2(core, disc, work, opts, sysdir)   like Emu, plus:
    .vardefs      {key: 'label; default|v2|...'} as announced by the core (SET_VARIABLES)
    .messages     [(frame, text)] from SET_MESSAGE / SET_MESSAGE_EXT
    .trace()      openboot trace table (see BOOTROM.md) decoded from RAM
    .tty_poll()   new bytes of openboot's TTY ring (the game's A(3Ch)/B(3Dh) putchar output)
  Symbols: load_syms(path) accepts an ELF (llvm-nm is run), an `nm` listing or a GNU-ld/lld map; None gives {}.
Nothing here is specific to one build of the game: guest RAM windows and symbol files are parameters.
"""
import ctypes as C
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from retro_ps1 import Emu, Variable   # noqa: E402

# ---- openboot fixed RAM layout (must match openboot/ob.h)
OB_TRACE = 0x00001000      # trace table (physical address)
OB_MAGIC = 0x3154424f      # 'OBT1'
OB_TTY = 0x00005000        # ring: u32 wr, u32 pad, then OB_TTY_SIZE bytes
OB_TTY_SIZE = 0x4000


class Message(C.Structure):
    _fields_ = [('msg', C.c_char_p), ('frames', C.c_uint)]


class MessageExt(C.Structure):
    _fields_ = [('msg', C.c_char_p), ('duration', C.c_uint), ('priority', C.c_uint), ('level', C.c_int),
                ('target', C.c_int), ('type', C.c_int), ('progress', C.c_int8)]


class Emu2(Emu):
    def __init__(self, *a, **k):
        self.vardefs = {}
        self.messages = []
        self.controllers = []          # port 1: (description, libretro device id) as announced by the core
        self._tty_rd = 0
        self.tty_text = bytearray()
        super().__init__(*a, **k)

    def _env(self, cmd, data):
        c = cmd & 0xffff
        try:
            if c == 16 and data:          # SET_VARIABLES
                v = C.cast(data, C.POINTER(Variable)); i = 0
                while v[i].key:
                    self.vardefs[v[i].key.decode()] = (v[i].value or b'').decode(errors='replace'); i += 1
                return True
            if c == 6 and data:           # SET_MESSAGE
                m = C.cast(data, C.POINTER(Message))[0]
                self.messages.append((self.frames, (m.msg or b'').decode(errors='replace'))); return True
            if c == 60 and data:          # SET_MESSAGE_EXT
                m = C.cast(data, C.POINTER(MessageExt))[0]
                self.messages.append((self.frames, (m.msg or b'').decode(errors='replace'))); return True
            if c == 59 and data:          # GET_MESSAGE_INTERFACE_VERSION
                C.cast(data, C.POINTER(C.c_uint))[0] = 1; return True
            if c == 35 and data:          # SET_CONTROLLER_INFO: array of {types*, num_types}; element 0 is port 1
                class _Desc(C.Structure):
                    _fields_ = [('desc', C.c_char_p), ('id', C.c_uint)]
                class _Info(C.Structure):
                    _fields_ = [('types', C.POINTER(_Desc)), ('num', C.c_uint)]
                inf = C.cast(data, C.POINTER(_Info))[0]
                self.controllers = [((inf.types[i].desc or b'').decode(errors='replace'), inf.types[i].id) for i in range(inf.num)]
                return True
            if c == 51:                   # GET_INPUT_BITMASKS
                return True
        except Exception as ex:           # never let a Python error escape into the core
            self.messages.append((self.frames, 'env error %r' % ex))
        return super()._env(cmd, data)

    # ---- openboot helpers
    def trace(self):
        return decode_trace(self.read(OB_TRACE, 0x1000))

    def tty_poll(self):
        wr, = struct.unpack('<I', self.read(OB_TTY, 4))
        out = bytearray()
        if wr - self._tty_rd > OB_TTY_SIZE:
            out += b'\n[tty ring overrun: %d bytes lost]\n' % (wr - self._tty_rd - OB_TTY_SIZE)
            self._tty_rd = wr - OB_TTY_SIZE
        while self._tty_rd < wr:
            o = self._tty_rd % OB_TTY_SIZE
            n = min(wr - self._tty_rd, OB_TTY_SIZE - o)
            out += self.read(OB_TTY + 8 + o, n); self._tty_rd += n
        self.tty_text += out
        return bytes(out)


def decode_trace(b):
    """trace table -> dict.  Layout (little endian words, see openboot/ob.h):
       0x000 magic 'OBT1'  0x004 stage  0x008 error  0x00c boot flags  0x010 pc0  0x014 t_addr  0x018 t_size  0x01c exe lba
       0x020 sp at entry  0x024 gp  0x028 game returned  0x02c tty chars  0x030 last exception cause  0x034 last epc
       0x038 last badvaddr  0x03c exceptions total  0x040 irq total  0x044 unknown-call last (table<<8|fn)  0x048 last ra of a call
       0x04c I_MASK seen at first irq  0x050 SR at entry  0x054 cd sectors read by the boot rom  0x058 boot cd retries
       0x060 +16 words: exceptions by cause code (0..15)   0x0a0 +16 words: interrupts by I_STAT bit (0..10), [11] spurious
       0x0e0 +8 words: syscall by number 0..6, [7]=other  0x100 +4: break counters ([0] total, [1] last code, [2] div0, [3] overflow)
       0x110 exceptions in a delay slot (skipped)  0x114 I_STAT before start  0x118 TCB  0x11c EVENT  0x120 STACK  0x124 last CD status
       0x128 FlushCache executed  0x12c site table overflow  0x140 +12 x {EPC, count}: unresolved exception sites
       0x200 +256 words: A(nn) calls   0x600 +256 words: B(nn)   0xa00 +128 words: C(nn)"""
    w = struct.unpack('<%dI' % (len(b) // 4), b)
    if w[0] != OB_MAGIC:
        return {'present': False, 'magic': w[0]}
    names = ['magic', 'stage', 'error', 'flags', 'pc0', 't_addr', 't_size', 'exe_lba', 'sp', 'gp', 'returned', 'tty_chars',
             'last_cause', 'last_epc', 'last_badvaddr', 'exc_total', 'irq_total', 'unk_call', 'last_call_ra', 'imask_first_irq',
             'sr_entry', 'boot_sectors', 'boot_retries', 'kernel_cd_acks']
    d = {n: w[i] for i, n in enumerate(names)}
    d['present'] = True
    d['exc'] = {i: v for i, v in enumerate(w[0x60 // 4:0x60 // 4 + 16]) if v}
    d['irq'] = {i: v for i, v in enumerate(w[0xa0 // 4:0xa0 // 4 + 16]) if v}
    d['syscall'] = {i: v for i, v in enumerate(w[0xe0 // 4:0xe0 // 4 + 8]) if v}
    d['brk'] = list(w[0x100 // 4:0x100 // 4 + 4])
    for i, n in enumerate(['bd_skipped', 'istat_boot', 'cnf_tcb', 'cnf_event', 'cnf_stack', 'cd_stat', 'flushes', 'sites_ovf']):
        d[n] = w[0x110 // 4 + i]
    d['sites'] = [(w[0x140 // 4 + 2 * i], w[0x140 // 4 + 2 * i + 1]) for i in range(12) if w[0x140 // 4 + 2 * i]]
    d['cdi_step'], d['cdi_fail'], d['extra_int3'] = w[0x130 // 4], w[0x134 // 4], w[0x138 // 4]
    n = min(w[0xc00 // 4], 63)
    d['cdlog'] = ['%02X:%s(%02x)' % (x >> 16, {1: 'INT1', 2: 'INT2', 3: 'INT3', 4: 'INT4', 5: 'INT5', 0: 'timeout'}.get(x & 0xff, 'INT%d' % (x & 0xff)), (x >> 8) & 0xff)
                  for x in w[0xc04 // 4:0xc04 // 4 + n]]
    d['A'] = {i: v for i, v in enumerate(w[0x200 // 4:0x200 // 4 + 256]) if v}
    d['B'] = {i: v for i, v in enumerate(w[0x600 // 4:0x600 // 4 + 256]) if v}
    d['C'] = {i: v for i, v in enumerate(w[0xa00 // 4:0xa00 // 4 + 128]) if v}
    return d


EXC_NAMES = {0: 'interrupt', 4: 'address error (load/fetch)', 5: 'address error (store)', 6: 'bus error (fetch)', 7: 'bus error (data)',
             8: 'syscall', 9: 'break', 10: 'reserved instruction', 11: 'coprocessor unusable', 12: 'arithmetic overflow'}
IRQ_NAMES = {0: 'VBLANK', 1: 'GPU', 2: 'CDROM', 3: 'DMA', 4: 'TMR0', 5: 'TMR1', 6: 'TMR2', 7: 'PAD/CARD', 8: 'SIO', 9: 'SPU', 10: 'PIO', 11: 'spurious'}
A_NAMES = {0x3c: 'putchar', 0x44: 'FlushCache', 0x3f: 'printf', 0x3e: 'puts', 0x33: 'malloc', 0x39: 'InitHeap', 0x70: '_bu_init',
           0x72: '_96_remove', 0x71: '_96_init', 0x54: '_96_init', 0x56: '_96_remove', 0xa0: '_boot', 0x49: 'GPU_cw', 0x2a: 'memcpy',
           0x2b: 'memset', 0x43: 'Exec', 0x42: 'Load', 0x51: 'LoadExec', 0x9c: 'SetConf', 0xa1: 'SystemError', 0x40: 'SystemErrorUnresolvedException'}
B_NAMES = {0x3d: 'putchar', 0x3f: 'puts', 0x12: 'InitPAD2', 0x13: 'StartPAD2', 0x14: 'StopPAD2', 0x18: 'ResetEntryInt', 0x19: 'HookEntryInt',
           0x17: 'ReturnFromException', 0x08: 'OpenEvent', 0x0c: 'EnableEvent', 0x0b: 'TestEvent', 0x4a: 'InitCARD2', 0x4b: 'StartCARD2',
           0x5b: 'ChangeClearPad', 0x02: 'init_timer', 0x07: 'DeliverEvent', 0x56: 'GetC0Table', 0x57: 'GetB0Table'}
C_NAMES = {0x0a: 'ChangeClearRCnt', 0x02: 'SysEnqIntRP', 0x03: 'SysDeqIntRP', 0x0d: 'SetIrqAutoAck', 0x07: 'InstallExceptionHandlers'}


def format_trace(t):
    if not t.get('present'):
        return 'no openboot trace table in RAM (magic %08x)' % t.get('magic', 0)
    L = ['openboot trace: stage %d error %d flags %#x  exe pc0 %08x t_addr %08x t_size %#x lba %d  entry sp %08x gp %08x sr %08x'
         % (t['stage'], t['error'], t['flags'], t['pc0'], t['t_addr'], t['t_size'], t['exe_lba'], t['sp'], t['gp'], t['sr_entry']),
         '  boot rom read %d sectors (%d retries); game returned to the rom: %d; tty chars %d; kernel-style CD acks %d'
         % (t['boot_sectors'], t['boot_retries'], t['returned'], t['tty_chars'], t['kernel_cd_acks'])]
    for tab, names in (('A', A_NAMES), ('B', B_NAMES), ('C', C_NAMES)):
        for fn, n in sorted(t[tab].items()):
            L.append('  %s(%02Xh) %-12s %d calls' % (tab, fn, names.get(fn, '?'), n))
    L.append('  exceptions total %d: %s' % (t['exc_total'], ', '.join('%s=%d' % (EXC_NAMES.get(c, 'cause %d' % c), n) for c, n in sorted(t['exc'].items())) or 'none'))
    L.append('  interrupts taken %d: %s  (I_MASK at first irq %#x)' % (t['irq_total'], ', '.join('%s=%d' % (IRQ_NAMES.get(c, 'irq%d' % c), n) for c, n in sorted(t['irq'].items())) or 'none', t['imask_first_irq']))
    L.append('  syscalls %s  breaks total %d (last code %#x, div0 %d, overflow %d)' % (t['syscall'] or 'none', t['brk'][0], t['brk'][1], t['brk'][2], t['brk'][3]))
    L.append('  last exception: cause %#x epc %08x badvaddr %08x; last call ra %08x; last unknown call %#x'
             % (t['last_cause'], t['last_epc'], t['last_badvaddr'], t['last_call_ra'], t['unk_call']))
    L.append('  SYSTEM.CNF tcb %#x event %#x stack %08x; I_STAT before start %#x; last CD status %#x; FlushCache executed %d; delay-slot skips %d'
             % (t['cnf_tcb'], t['cnf_event'], t['cnf_stack'], t['istat_boot'], t['cd_stat'], t['flushes'], t['bd_skipped']))
    L.append('  boot CD log (command:INT(first result byte)), first %d events: %s%s' % (len(t['cdlog']), ' '.join(t['cdlog'][:16]), ' ...' if len(t['cdlog']) > 16 else ''))
    L.append('  CD init: last step word %#x, first failure %#x, extra INT3 before a second response: %d' % (t['cdi_step'], t['cdi_fail'], t['extra_int3']))
    if t['sites'] or t['sites_ovf']:
        L.append('  unresolved exception sites (EPC x count): ' + ', '.join('%08x x %d' % s for s in t['sites']) + ('; %d more not recorded' % t['sites_ovf'] if t['sites_ovf'] else ''))
    return '\n'.join(L)


def load_syms(path):
    """name -> address from an ELF, an nm listing, or a linker map.  Unknown / missing file: {}."""
    if not path or not os.path.exists(path):
        return {}
    head = open(path, 'rb').read(4)
    if head == b'\x7fELF':
        txt = subprocess.run(['llvm-nm', path], capture_output=True, text=True).stdout
    else:
        txt = open(path, errors='replace').read()
    syms = {}
    for l in txt.splitlines():
        m = re.match(r'^\s*([0-9a-fA-F]{8})\s+[A-Za-z]\s+(\S+)\s*$', l)            # nm
        if not m:
            m = re.match(r'^\s*([0-9a-fA-F]{8})\s+[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+\d+\s+(\S+)\s*$', l)   # lld map
        if not m:
            m = re.match(r'^\s+0x([0-9a-fA-F]{8,16})\s+(\S+)\s*$', l)             # GNU ld map
        if m:
            syms.setdefault(m.group(2), int(m.group(1)[-8:], 16))
    return syms


# ---- CPU registers out of a save state (r0..r31, hi, lo, pc, npc)
def swan_regs(s, hint=None):
    """SwanStation save state ("DUCC"): sections start with a name (u32 length, characters); the CPU section is "CPU",
    then pending ticks (u32), downcount (u32), then r0..r31, hi, lo, pc, npc.  Returns (offset of the block, 36 words) or
    (None, None).  The offset moves with the length of the disc path stored in the header."""
    M = b'\x03\x00\x00\x00CPU'
    if hint is not None and hint + 144 <= len(s) and s[hint - 15:hint - 8] == M:
        return hint, struct.unpack_from('<36I', s, hint)
    i = s.find(M, 0, 0x4000)
    if i < 0 or i + 15 + 144 > len(s):
        return None, None
    w = struct.unpack_from('<36I', s, i + 15)
    return (i + 15, w) if w[0] == 0 else (None, None)


def beetle_regs(s):
    def field(name, n):
        i = s.find(name)
        return struct.unpack_from('<%dI' % n, s, i + len(name) + 4) if i >= 0 else None
    g = field(b'GPR', 32); pc = field(b'BACKED_PC', 1); npc = field(b'BACKED_new_PC', 1)
    if not g or not pc:
        return None
    return list(g) + [0, 0, pc[0], npc[0] if npc else 0]

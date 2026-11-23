"""ps1/tools/disp_patch_check.py: the dispatch boot patch words (PLAN.md Stage 2), decoded from small hand-made ELF files.

ROM-free and toolchain-free: the code words below are written with a few encoders, laid out like rt.c's rt_mcache, rd_front and
wr_front.  check_native.py runs the same tool on the really linked runtime."""
import contextlib
import importlib.util
import io
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import elf_fixture  # noqa: E402

PS1 = Path(__file__).resolve().parents[1]
TOOL = PS1 / 'tools/disp_patch_check.py'
RUNTIME = PS1 / 'stage19/ps1rt/rt.c'
spec = importlib.util.spec_from_file_location('ps1_disp_patch_check', TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

TEXT = 0x80010000
MCACHE = 0x80022000                  # rc8: the D1 table is the BSS array dsp_mcache (wave 1 had it at 0x80028400)
LQ = MCACHE + 4096                   # the D2 queue dsp_lq behind it
NOP = 0


def j(target):
    return 0x08000000 | ((target >> 2) & 0x03ffffff)


def lui(rt, imm):
    return 0x3c000000 | rt << 16 | imm


def ori(rt, rs, imm):
    return 0x34000000 | rs << 21 | rt << 16 | imm


def addiu(rt, rs, imm):
    return 0x24000000 | rs << 21 | rt << 16 | (imm & 0xffff)


def lw(rt, offset, base):
    return 0x8c000000 | base << 21 | rt << 16 | (offset & 0xffff)


def sw(rt, offset, base):
    return 0xac000000 | base << 21 | rt << 16 | (offset & 0xffff)


def addu(rd, rs, rt):
    return rs << 21 | rt << 16 | rd << 11 | 0x21


def jr(rs):
    return rs << 21 | 8


def bne(rs, rt, skip):
    """bne whose target is `skip` words after its delay slot"""
    return 0x14000000 | rs << 21 | rt << 16 | (skip & 0xffff)


def beq(rs, rt, skip):
    """beq whose target is `skip` words after its delay slot"""
    return 0x10000000 | rs << 21 | rt << 16 | (skip & 0xffff)


def srl(rd, rt, sa):
    return rt << 16 | rd << 11 | sa << 6 | 0x02


def sll(rd, rt, sa):
    return rt << 16 | rd << 11 | sa << 6


def andi(rt, rs, imm):
    return 0x30000000 | rs << 21 | rt << 16 | imm


def xori(rt, rs, imm):
    return 0x38000000 | rs << 21 | rt << 16 | imm


def sltiu(rt, rs, imm):
    return 0x2c000000 | rs << 21 | rt << 16 | imm


def rt_mcache(table=MCACHE, cc=tool.RT_CC):
    hi, lo = (table + 0x8000) >> 16, (table - (((table + 0x8000) >> 16) << 16)) & 0xffff
    return [lui(25, hi), addu(2, 2, 25), lw(25, lo, 2), lw(2, lo + 4, 2), bne(25, 1, 2), lui(25, 0x8002),
            jr(2), NOP,                                                      # hit
            ori(25, 25, 0x8008), lw(25, 0, 25),                              # rt_mslow: h_miss = HELP+8
            addu(2, 31, 0), lui(28, 0x8003), j(cc), ori(28, 28, 0x0028)]     # rt_mcc: $28 = rt_miss_ret, RT_CC


def rd_front(d3=True):
    """the ROM region test first (to the fast path past it, D3), then EWRAM and IWRAM by the region byte, else RT_MEMRD_SLOW"""
    words = [srl(25, 24, 24), andi(1, 25, 0xf9), xori(1, 1, 8), beq(1, 0, 13), addiu(1, 25, -2),     # ROM -> rd_rom (word 17)
             beq(1, 0, 6), addiu(1, 25, -3), bne(1, 0, 11 if d3 else 9), andi(25, 24, 0x7fff),        # EWRAM -> rd_ew (12), else rd_slow
             lui(1, 0x801f), j(tool.KIND), addu(25, 25, 1),                                         # IWRAM
             sll(25, 24, 14), srl(25, 25, 14), lui(1, 0x801b), j(tool.KIND), addu(25, 25, 1)]       # rd_ew
    if d3:
        words += [j(tool.ROM_PAST), NOP]                                                             # rd_rom
    return words + [j(tool.RT_MEMRD_SLOW), NOP]                                                      # rd_slow (= rd_rom without D3)


def wr_front():
    return [srl(25, 24, 24), addiu(1, 25, -2), beq(1, 0, 6), addiu(1, 25, -3), bne(1, 0, 10), andi(25, 24, 0x7fff),
            lui(1, 0x801f), beq(0, 0, 5), addu(25, 25, 1),                                          # IWRAM -> wr_st (word 13)
            sll(25, 24, 14), srl(25, 25, 14), lui(1, 0x801b), addu(25, 25, 1),                      # wr_ew
            jr(28), sw(3, 0, 25),                                                                    # wr_st
            lui(25, 0x8002), ori(25, 25, 0x8004), lw(25, 0, 25), j(tool.RT_CC), NOP]                # wr_slow


def program(mc=True, d4=True, d3=True, d2=True, patch=None, edit=None):
    """An ELF laid out like the runtime: dsp_new first, then the new code; patch/edit change words before the ELF is written."""
    blocks = {}
    if mc:
        blocks['rt_mcache'] = rt_mcache()
    if d4:
        blocks['rd_front'] = rd_front(d3)
        blocks['wr_front'] = wr_front()
    n_new = (2 if mc else 0) + (2 if d4 else (1 if d3 else 0))
    offset, where = 4 * n_new, {}
    for name, words in blocks.items():
        where[name] = offset
        offset += 4 * len(words)
    if edit:
        edit(blocks)
    new = []
    if mc:
        new += [j(TEXT + where['rt_mcache']), tool.ADDU_T8_T9]
    if d4:
        new += [j(TEXT + where['rd_front']), j(TEXT + where['wr_front'])]
    elif d3:
        new += [NOP]
    if patch:
        new = patch(new)
    words = new + [w for name in blocks for w in blocks[name]]
    functions = [('dsp_new', 0, 4 * len(new))] + [(name, where[name], 4 * len(blocks[name])) for name in blocks]
    if d2:
        functions.append(('d2_linked', offset, 0))
    functions += [('dsp_mcache', MCACHE - TEXT, 4096), ('dsp_lq', LQ - TEXT, 1024)]
    return elf_fixture.mips_elf(words, functions, text_address=TEXT)


class PatchCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ps1-disp-test-')
        self.addCleanup(self.tmp.cleanup)

    def run_tool(self, elf):
        path = Path(self.tmp.name) / 'payback.elf'
        path.write_bytes(elf)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = tool.main([str(path)])
        return status, out.getvalue()

    def assert_fails(self, elf, expected):
        status, text = self.run_tool(elf)
        self.assertEqual(status, 1, text)
        self.assertIn(expected, text)

    def test_all_four_items_decode(self):
        status, text = self.run_tool(program())
        self.assertEqual(status, 0, text)
        self.assertIn('dispatch boot patches D3 D1 D4 D2: 4 words', text)
        self.assertIn('0x80030008 <- %08x  j rt_mcache' % j(TEXT + 16), text)
        self.assertIn('0x8003000c <- 0320c021  addu $24,$25,$0', text)
        self.assertIn('rt_mcache: D1 table 0x80022000..0x80023000', text)

    def test_single_items_decode(self):
        for kwargs, label in (({'mc': False, 'd4': False, 'd2': False}, 'D3: 1 words'),
                              ({'d4': False, 'd3': False, 'd2': False}, 'D1: 2 words'),
                              ({'mc': False, 'd3': False, 'd2': False}, 'D4: 2 words'),
                              ({'d4': False}, 'D3 D1 D2: 3 words')):
            status, text = self.run_tool(program(**kwargs))
            self.assertEqual(status, 0, text)
            self.assertIn('dispatch boot patches ' + label, text)

    def test_no_dispatch_code_passes(self):
        status, text = self.run_tool(elf_fixture.clean_program())
        self.assertEqual(status, 0, text)
        self.assertIn('no dispatch boot patches', text)

    def test_patch_jump_to_the_wrong_symbol(self):
        self.assert_fails(program(patch=lambda new: [new[2]] + new[1:]), 'not `j rt_mcache`')

    def test_patch_word_count(self):
        self.assert_fails(program(patch=lambda new: new + [NOP]), 'dsp_new has 5 words, the symbols call for 4')

    def test_rt_miss_delay_slot_word(self):
        self.assert_fails(program(patch=lambda new: [new[0], NOP] + new[2:]), 'patch word at 0x8003000c')

    def test_rt_cc_target(self):
        def edit(blocks):
            blocks['rt_mcache'][12] = j(tool.RT_CC + 4)
        self.assert_fails(program(edit=edit), 'rt_mcache jumps to')

    def test_rt_miss_ret_link(self):
        def edit(blocks):
            blocks['rt_mcache'][13] = ori(28, 28, 0x002c)
        self.assert_fails(program(edit=edit), 'rt_miss_ret')

    def test_d1_table_is_dsp_mcache(self):
        def edit(blocks):
            blocks['rt_mcache'] = rt_mcache(table=0x80029000)
        self.assert_fails(program(edit=edit), 'is not dsp_mcache')

    def test_d1_table_clear_of_the_d2_queue(self):
        def edit(blocks):
            blocks['rt_mcache'] = rt_mcache(table=LQ - 8)
        self.assert_fails(program(edit=edit), 'clear of dsp_lq')

    def test_memwr_fallback_rebuilds_help4(self):
        def edit(blocks):
            blocks['wr_front'][blocks['wr_front'].index(ori(25, 25, 0x8004))] = ori(25, 25, 0x8000)
        self.assert_fails(program(edit=edit), 'HELP+4')

    def test_memrd_targets(self):
        def edit(blocks):
            blocks['rd_front'][blocks['rd_front'].index(j(tool.KIND))] = j(tool.KIND + 8)
        self.assert_fails(program(edit=edit), 'rd_front jumps to')

    def test_memrd_both_rom_entries(self):
        def edit(blocks):
            blocks['rd_front'][blocks['rd_front'].index(j(tool.KIND))] = j(tool.ROM_FAST)
        self.assert_fails(program(edit=edit), 'rd_front jumps to')

    def test_rom_past_needs_the_region_test_first(self):
        def edit(blocks):
            blocks['rd_front'][1] = andi(1, 25, 0xf8)
        self.assert_fails(program(edit=edit), 'without beginning with that test')

    def test_windows_by_the_region_byte(self):
        for name in ('rd_front', 'wr_front'):
            def edit(blocks, name=name):
                blocks[name][blocks[name].index(lui(1, 0x801b))] = lui(1, 0x801c)
            self.assert_fails(program(edit=edit), '%s does not serve EWRAM and IWRAM' % name)

    def test_mips2_word(self):
        def edit(blocks):
            blocks['wr_front'][3] = 0x00a001f4          # teq $a1,$zero,7 (MIPS II)
        self.assert_fails(program(edit=edit), 'not an R3000A instruction')

    def test_jump_in_a_delay_slot(self):
        def edit(blocks):
            blocks['rd_front'][4] = j(tool.KIND)        # the delay slot of the ROM test's beq
        self.assert_fails(program(edit=edit), 'delay slot')

    def test_branch_out_of_the_function(self):
        def edit(blocks):
            blocks['wr_front'][2] = bne(1, 0, 40)
        self.assert_fails(program(edit=edit), 'branch leaves the function')


class RuntimeSourceTests(unittest.TestCase):
    """The tool and rt.c describe the same blob words (t2m.py runtime(), cfg 'P')."""

    @classmethod
    def setUpClass(cls):
        cls.source = RUNTIME.read_text()

    def table(self, name):
        body = re.search(r'static const u32 %s\[\]\[2\]=\{(.*?)\n\};' % name, self.source, re.S).group(1)
        return {int(a, 16): int(w, 16) for a, w in re.findall(r'\{0x([0-9a-f]+)u,0x([0-9a-f]+)u\}', body)}

    def test_patched_words(self):
        patched = self.table('dsp_at')
        self.assertEqual(sorted(patched), [tool.RT_MISS, tool.RT_MISS + 4, tool.RT_MEMRD, tool.RT_MEMWR])
        self.assertEqual(patched[tool.RT_MISS], tool.ADDU_T8_T9)
        self.assertEqual(patched[tool.RT_MEMRD], j(tool.RT_MEMRD_SLOW))

    def test_kept_words_hold_the_stubs_the_new_code_uses(self):
        kept = self.table('dsp_keep')
        self.assertEqual(kept[0x80030020], j(tool.RT_CC))                      # RT_MISS: j RT_CC
        self.assertEqual(kept[0x80030028], jr(2))                              # rt_miss_ret: jr $2
        self.assertEqual(kept[0x80030010], ori(25, 25, 0x8008))                # RT_MISS: HELP+8
        self.assertEqual(kept[0x80030140], ori(25, 25, 0x8004))                # RT_MEMWR: HELP+4 (the patched word's delay slot)
        self.assertEqual(kept[tool.RT_MEMRD_SLOW + 4], ori(25, 25, 0x8000))    # RT_MEMRD_SLOW: HELP+0
        self.assertEqual(kept[0x8003007c], ori(25, 25, 0xa000))                # ROM fast path: ROMPG 0x8002a000 (D3's rom_pg)
        self.assertEqual([kept[0x8003004c], kept[0x80030050], kept[0x80030054]], tool.REGION_TEST)   # its region test
        self.assertEqual(kept[tool.ROM_PAST], sltiu(1, 25, 0xe))                # past the test, where D4's rd_front enters
        self.assertIn(tool.KIND, kept)
        self.assertIn(tool.RT_CC, kept)

    def test_reserved_tables(self):
        self.assertIn('#define MCACHE ((volatile u32*)dsp_mcache)', self.source)
        self.assertIn('#define LQ ((volatile u32*)dsp_lq)', self.source)
        self.assertIn('.set rom_pg, 0x8002a000', self.source)


if __name__ == '__main__':
    unittest.main()

"""Native GTE inline assembly is not a guest function pointer."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'merged'))
from irmem import Rewriter


class InlineAsmRewriteTests(unittest.TestCase):
    def test_gte_inline_asm_preserved(self):
        source = [
            '  tail call void asm sideeffect ".word 0x48C80000$|(1<<11)", "{$8},~{$1}"(i32 %x) #21, !srcloc !20',
            '  %v = tail call i32 asm sideeffect "mfc2 $0,$$25\\0A nop", "=r,~{$1}"() #21, !srcloc !27',
            '  call void asm sideeffect "nop", "~{$1}"()',
            '  %v2 = call i32 asm "move $0,$1", "=r,r"(i32 %x)',
        ]
        for instruction in source:
            with self.subTest(instruction=instruction):
                rw = Rewriter(set(), set())
                self.assertEqual(rw.run([instruction]), [instruction])
                self.assertNotIn('call_ptr', rw.stat)

    def test_guest_pointer_still_mapped(self):
        rw = Rewriter(set(), set())
        result = rw.run(['  %v = tail call i32 %f(i32 %x)'])
        self.assertEqual(len(result), 2)
        self.assertIn('@__sf_fnmap(ptr %f)', result[0])
        self.assertIn('call i32 %__sfm', result[1])
        self.assertEqual(rw.stat['call_ptr'], 1)


if __name__ == '__main__':
    unittest.main()

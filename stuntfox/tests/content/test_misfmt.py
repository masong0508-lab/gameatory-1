"""misfmt.py (the compiler's blob layout) against src/misdata.h: the header is compiled with the host compiler and every
record's size, every field's offset and every enum number is compared."""
import os
import re
import subprocess
import tempfile
import unittest

import common
import misfmt as F

SRC = os.path.join(common.ROOT, 'src')
GROUPS = {'OP': 'OP_', 'MO': 'MO_', 'PK': 'PK_', 'MK': 'MK_', 'CH': 'CH_', 'FF': 'FF_', 'MF': 'MF_', 'MS': 'MS_'}


def c_dump():
    """{'size:Name': n, 'off:Name.field': n, 'enum:NAME': n} read from a program built on misdata.h."""
    lines = ['#include <stdio.h>', '#include <stddef.h>', '#include "misdata.h"', 'int main(void) {']
    for name, fields in F.FIELDS.items():
        lines.append('printf("size:%s %%d\\n", (int)sizeof(%s));' % (name, name))
        for f, _c in fields:
            lines.append('printf("off:%s.%s %%d\\n", (int)offsetof(%s, %s));' % (name, f, name, f))
    for g, pre in GROUPS.items():
        for n in F.ENUMS[g]:
            lines.append('printf("enum:%s%s %%d\\n", (int)%s%s);' % (pre, n, pre, n))
    lines.append('printf("enum:OP_N %d\\n", (int)OP_N);')
    for n in ('S2_MAGIC', 'S2_VER', 'NOPLACE'):
        lines.append('printf("enum:%s %%u\\n", (unsigned)%s);' % (n, n))
    lines.append('return 0; }')
    d = tempfile.mkdtemp(prefix='misfmt')
    src, exe = os.path.join(d, 't.c'), os.path.join(d, 't')
    open(src, 'w').write('\n'.join(lines) + '\n')
    r = subprocess.run([common.HOSTCC, '-I', SRC, '-I', os.path.join(common.ROOT, 'tests', 'vm'), '-o', exe, src],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('compiling misdata.h: ' + r.stderr[-800:])
    out = subprocess.run([exe], capture_output=True, text=True, check=True).stdout
    return {k: int(v) for k, v in (ln.split() for ln in out.splitlines())}


@common.needs_cc
class MisfmtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = c_dump()

    def test_sizes(self):
        for name in F.FIELDS:
            self.assertEqual(F.SIZES[name], self.c['size:' + name], name)

    def test_offsets(self):
        for name in F.FIELDS:
            lay, _ = F.layout(name)
            for f, off, _code in lay:
                self.assertEqual(off, self.c['off:%s.%s' % (name, f)], '%s.%s' % (name, f))

    def test_every_field_is_in_the_header(self):
        src = open(os.path.join(SRC, 'misdata.h')).read()
        for name, fields in F.FIELDS.items():
            for f, _c in fields:
                self.assertRegex(src, r'\b%s\b' % f, '%s.%s is not in misdata.h' % (name, f))

    def test_enums(self):
        for g, pre in GROUPS.items():
            for n, v in F.ENUMS[g].items():
                self.assertEqual(v, self.c['enum:' + pre + n], pre + n)
        self.assertEqual(F.OP_N, self.c['enum:OP_N'])
        self.assertEqual(len(F.OPS), F.OP_N)

    def test_op_names_are_the_headers_in_order(self):
        src = open(os.path.join(SRC, 'misdata.h')).read()
        body = src[src.index('enum {\n    OP_NOP'):]
        body = body[:body.index('};')]
        names = re.findall(r'\bOP_([A-Z0-9]+)\b', body)
        self.assertEqual(names[:-1], F.OPS)                         # (the last is OP_N)

    def test_constants(self):
        self.assertEqual(F.MAGIC, self.c['enum:S2_MAGIC'])
        self.assertEqual(F.VER, self.c['enum:S2_VER'])
        self.assertEqual(F.NOPLACE, self.c['enum:NOPLACE'])


if __name__ == '__main__':
    unittest.main()

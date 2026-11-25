"""ROM-free generator and MIPS compile gate for direct wall snapshots."""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"merged"))
from sfwall import generate


class FastWallTests(unittest.TestCase):
    def test_kernel_from_current_public_source(self):
        tex = ROOT.parent/"stuntfox/src/tex.c"
        code = generate(tex.read_text())
        self.assertIn("int sf_fast_wall(", code)
        self.assertIn("wall_draw((u8*)(0x80181000u+o)", code)
        self.assertNotIn("if (sf_fast_wall(back", code)
        self.assertNotIn('target("arm")', code)
        self.assertIn("rows <= 0 || r0<0 || r1>160", code)
        with self.assertRaises(ValueError):
            generate(tex.read_text().replace("tex_vrun(dd, 1,", "other_vrun(dd, 1,"))
        cc = shutil.which("clang")
        if not cc:
            self.skipTest("clang unavailable")
        if "mips" not in subprocess.check_output([cc,"--print-targets"],text=True):
            self.skipTest("MIPS target unavailable")
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)
            for name in ("tex.h","render.h","fx.h"):
                shutil.copyfile(tex.parent/name,p/name)
            shutil.copyfile(ROOT/"merged/include/gba.h",p/"gba.h")
            (p/"sfwall.c").write_text(code)
            subprocess.run([cc,"--target=mipsel-none-elf","-march=mips1","-mabi=32",
                "-mfp32","-msoft-float","-ffreestanding","-fno-builtin","-fno-pic",
                "-mno-abicalls","-mno-check-zero-division","-G0","-O2","-fno-strict-aliasing",
                "-mllvm","-disable-mips-delay-filler","-c",str(p/"sfwall.c"),"-o",str(p/"sfwall.o")],check=True)


if __name__ == "__main__":
    unittest.main()

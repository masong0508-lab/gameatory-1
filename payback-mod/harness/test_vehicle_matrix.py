"""ROM-free checks of original-Payback vehicle identity and test plans."""
import importlib.util
import tempfile
import io
from contextlib import redirect_stderr
from pathlib import Path
import unittest

SRC=Path(__file__).with_name('vehicle_matrix.py')
s=importlib.util.spec_from_file_location('vehicle_matrix',SRC)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class VehicleMatrixTests(unittest.TestCase):
    def test_k17_is_helicopter_not_normal_car(self):
        self.assertEqual(m.HELICOPTER,17)
        self.assertEqual(m.DESC_BASE+17*m.DESC_STRIDE,0x08354EF0)
        self.assertEqual(m.kind_from_descriptor(m.HELIDESC),17)
        self.assertEqual(m.kind_from_descriptor(m.DESC_BASE),0)
        self.assertEqual(m.kind_from_descriptor(m.DESC_BASE+11*m.DESC_STRIDE),11)

    def test_descriptors_do_not_alias_or_guess(self):
        for k in range(18):
            self.assertEqual(m.kind_from_descriptor(m.DESC_BASE+k*60),k)
        for addr in (None, True, m.DESC_BASE-60, m.HELIDESC+60, m.DESC_BASE+59):
            self.assertIsNone(m.kind_from_descriptor(addr))

    def test_distinct_airborne_control_sequence(self):
        c=m.action_plan(3);h=m.action_plan(17)
        self.assertIn('A accelerate',c)
        self.assertNotIn('A accelerate',h)
        self.assertIn('L takeoff',h)
        self.assertIn('L land',h)
        self.assertEqual(h[0],'L enter')
        self.assertEqual(h[-1],'L exit')

    def test_delta_tracks_rotation_and_height_separately(self):
        a=dict(x=0,y=0,z=19904,heading=5600)
        b=dict(x=300,y=400,z=20904,heading=100)
        self.assertEqual(m.delta(a,b),dict(horizontal_units=500.0,vertical_units=1000,heading_units=260))

    def test_wrong_rom_hash_never_starts_mgba_or_claims_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            rom=Path(tmp)/'wrong.gba';rom.write_bytes(bytes(0x800000))
            dest=Path(tmp)/'not_written.json'
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    m.main([str(rom),'--out',str(dest)])
            self.assertEqual(ctx.exception.code,2)
            self.assertFalse(dest.exists())

    def test_private_report_path_required_before_emulation(self):
        out=m.HERE.parent.parent/'vehicle-should-not-exist.json'
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                m.main(['/does/not/exist.gba','--out',str(out)])
        self.assertEqual(ctx.exception.code,2)
        self.assertFalse(out.exists())

    def test_lookups_are_bounded(self):
        class Dummy:
            def s16(self,addr):return 65535 if addr==m.LAST_ENTITY else 1
        self.assertIsNone(m.entity(Dummy(),0))

if __name__=='__main__': unittest.main()
"""ROM-free tests of private input verification, including adversarial ZIPs."""
import hashlib
import io
import pathlib
import sys
import stat
import tempfile
import unittest
import warnings
import zipfile
import zlib
from unittest.mock import patch
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from check_owner_inputs import RELEASE, main, read_manifest, verify_zip


class PrivateInputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.values = {p: (f"TEST-{p}").encode("ascii") for p in sorted(RELEASE)}
        self.values.update({"s2/resident.pkl": b"synthetic-resident", "s2/cold.pkl": b"synthetic-cold"})
        self.root.joinpath("inputs").mkdir()
        for k, v in self.values.items():
            f = self.root / "inputs" / k
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(v)
        self.manifest = self.root / "manifest.sha256"
        self.rom = self.root / "rom.gba"
        self.rom.write_bytes(b"R" * (8 * 1024 * 1024))
        self.manifest.write_text("\n".join(
            f"{hashlib.sha256(v).hexdigest()}  {len(v)}  {k}"
            for k, v in self.values.items()) + "\n" +
            f"{hashlib.sha256(self.rom.read_bytes()).hexdigest()}  8388608  iso_a/ROM.BIN\n"
        )

    def call(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([str(self.manifest), *map(str, args)])
        return code, buf.getvalue()

    def package(self, entries=None):
        pkg = self.root / "bundle.zip"
        with zipfile.ZipFile(pkg, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for k, v in (self.values.items() if entries is None else entries):
                z.writestr(k, v)
        return pkg

    def test_full_dir_and_archive(self):
        for source in (self.root / "inputs", self.package()):
            status, output = self.call(source, "--rom", self.rom)
            self.assertEqual(status, 0, output)
            self.assertIn("0 error(s)", output)
            self.assertIn("Owner ROM: SHA256", output)

    def test_release_inputs_directory(self):
        for name in ("s2/resident.pkl", "s2/cold.pkl"):
            (self.root / "inputs" / name).unlink()
        status, output = self.call(self.root / "inputs", "--release")
        self.assertEqual(status, 0, output)
        self.assertIn("14 expected files", output)
        status, output = self.call(self.root / "inputs")
        self.assertEqual(status, 1)
        self.assertIn("MISSING s2/cold.pkl", output)

    def test_release_from_full_owner_zip_allows_other_known_members(self):
        # The full owner package contains 14 Track A inputs plus seven
        # documented Track B references. --release must not reject them.
        status, output = self.call(self.package(), "--release")
        self.assertEqual(status, 0, output)
        self.assertIn("14 expected files; 0 error(s)", output)
        pkg = self.package([*self.values.items(), ("unauthorized.bin", b"extra")])
        status, output = self.call(pkg, "--release")
        self.assertEqual(status, 1)
        self.assertIn("UNEXPECTED unauthorized.bin", output)

    def test_corrupt_deflate_is_reported_without_traceback(self):
        pkg = self.package()
        with patch.object(zipfile.ZipFile, "open", side_effect=zlib.error("bad data")):
            status, output = self.call(pkg)
        self.assertEqual(status, 1)
        self.assertIn("READ/CRC boot.bin", output)
        self.assertIn("error(s)", output)

    def test_mutation_detected_even_when_size_unchanged(self):
        path = self.root / "inputs/boot.bin"
        b = bytearray(path.read_bytes()); b[0] ^= 1; path.write_bytes(b)
        code, output = self.call(self.root / "inputs")
        self.assertEqual(code, 1)
        self.assertIn("HASH boot.bin", output)

    def test_crc_or_hash_mismatch_zip(self):
        entries = dict(self.values); entries["boot.bin"] = b"X" * len(entries["boot.bin"])
        status, output = self.call(self.package(entries.items()))
        self.assertEqual(status, 1)
        self.assertIn("HASH boot.bin", output)

    def test_extra_member_rejected(self):
        status, output = self.call(self.package([*self.values.items(), ("private.exe", b"do not publish")]))
        self.assertEqual(status, 1)
        self.assertIn("UNEXPECTED private.exe", output)

    def test_duplicate_member_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            pkg = self.package([*self.values.items(), ("boot.bin", b"another")])
        status, output = self.call(pkg)
        self.assertEqual(status, 1)
        self.assertIn("DUPLICATE boot.bin", output)

    def test_zip_traversal_rejected_without_extraction(self):
        pkg = self.package([*self.values.items(), ("../outside", b"danger")])
        status, output = self.call(pkg)
        self.assertEqual(status, 1)
        self.assertIn("UNSAFE ZIP PATH", output)
        self.assertFalse((self.root.parent / "outside").exists())

    def test_symlink_in_zip_rejected(self):
        zinfo = zipfile.ZipInfo("boot.bin")
        zinfo.create_system = 3
        zinfo.external_attr = (stat.S_IFLNK | 0o777) << 16
        entries = [(zinfo if k == "boot.bin" else k, v) for k, v in self.values.items()]
        status, output = self.call(self.package(entries))
        self.assertEqual(status, 1)
        self.assertIn("SYMLINK IN ZIP", output)

    def test_symlink_in_directory_rejected(self):
        target = self.root / "inputs" / "boot.bin"
        target.unlink()
        external = self.root / "external.txt"
        external.write_bytes(self.values["boot.bin"])
        target.symlink_to(external)
        status, output = self.call(self.root / "inputs")
        self.assertEqual(status, 1)
        self.assertIn("UNSAFE LINK boot.bin", output)

    def test_manifest_collision_rejected(self):
        self.manifest.write_text(self.manifest.read_text() + self.manifest.read_text().splitlines()[0] + "\n")
        with self.assertRaisesRegex(Exception, "duplicate path"):
            read_manifest(self.manifest)

    def test_rom_mismatch_detected(self):
        self.rom.write_bytes(b"Z" * 8 * 1024 * 1024)
        status, output = self.call(self.root / "inputs", "--rom", self.rom)
        self.assertEqual(status, 1)
        self.assertIn("ROM SHA256 MISMATCH", output)


if __name__ == "__main__":
    unittest.main()

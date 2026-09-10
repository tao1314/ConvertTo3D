"""Validate native Inventor input without requiring Inventor in automated tests."""

from pathlib import Path
import tempfile
import unittest

from backend.inventor import OLE_HEADER, validate_ipt


class InventorTests(unittest.TestCase):
    # Accept the compound-document signature used by real IPT samples.
    def test_accepts_real_ipt_container_header(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'part.ipt'
            source.write_bytes(OLE_HEADER + b'Inventor data')
            validate_ipt(source)

    # Reject renamed files before launching an external CAD process.
    def test_rejects_invalid_ipt_container_header(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'fake.ipt'
            source.write_bytes(b'not an IPT')
            with self.assertRaisesRegex(ValueError, 'IPT 文件头无效'):
                validate_ipt(source)

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_public import fetch


class PublicDownloadTests(unittest.TestCase):
    def test_verifies_download_and_reuses_cache(self):
        data = b"sample archive"
        expected = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cache" / "sample.csv"
            path.parent.mkdir()
            path.write_bytes(b"invalid cache")
            with patch("run_public.urlopen", return_value=io.BytesIO(data)) as download:
                fetch("https://example.com/sample", path, expected)
                fetch("https://example.com/sample", path, expected)
                download.assert_called_once()
            self.assertEqual(path.read_bytes(), data)

    def test_bad_download_is_not_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.csv"
            with patch("run_public.urlopen", return_value=io.BytesIO(b"bad archive")):
                with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                    fetch("https://example.com/sample", path, hashlib.sha256(b"expected").hexdigest())
            self.assertEqual(list(Path(folder).iterdir()), [])

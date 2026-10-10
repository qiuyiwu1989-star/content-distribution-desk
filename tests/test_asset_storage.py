import errno
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from asset_storage import deduplicate_upload


class AssetStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original = self.root / 'original'
        self.upload = self.root / 'upload'
        self.data = b'video bytes' * 150000
        self.original.write_bytes(self.data)
        self.upload.write_bytes(self.data)

    def test_identical_contents_share_inode_without_removing_old_asset(self):
        old_inode = self.original.stat().st_ino
        result = deduplicate_upload(self.upload, [self.original])
        self.assertEqual(result, {'sha256': hashlib.sha256(self.data).hexdigest(), 'shared': True})
        self.assertEqual(self.upload.stat().st_ino, old_inode)
        self.assertEqual(self.original.read_bytes(), self.data)
        self.upload.unlink()
        self.assertEqual(self.original.read_bytes(), self.data)

    def test_different_contents_same_size_keep_copy(self):
        self.original.write_bytes(b'x' * len(self.data))
        inode = self.upload.stat().st_ino
        result = deduplicate_upload(self.upload, [self.original])
        self.assertFalse(result['shared'])
        self.assertEqual(self.upload.stat().st_ino, inode)
        self.assertEqual(self.upload.read_bytes(), self.data)

    def test_link_failure_keeps_upload(self):
        inode = self.upload.stat().st_ino
        with patch('asset_storage.os.link', side_effect=OSError(errno.EXDEV, 'different device')):
            result = deduplicate_upload(self.upload, [self.original])
        self.assertFalse(result['shared'])
        self.assertEqual(self.upload.stat().st_ino, inode)
        self.assertEqual(self.upload.read_bytes(), self.data)
        self.assertEqual(set(self.root.iterdir()), {self.original, self.upload})

    def test_replace_failure_removes_temporary_link_keeps_both_assets(self):
        with patch('asset_storage.os.replace', side_effect=OSError(errno.EACCES, 'denied')):
            result = deduplicate_upload(self.upload, [self.original])
        self.assertFalse(result['shared'])
        self.assertEqual(self.upload.read_bytes(), self.data)
        self.assertEqual(self.original.read_bytes(), self.data)
        self.assertEqual(set(self.root.iterdir()), {self.original, self.upload})

    def test_self_and_missing_candidates_are_skipped(self):
        result = deduplicate_upload(self.upload, [self.upload, self.root / 'missing', self.original])
        self.assertTrue(result['shared'])


if __name__ == '__main__':
    unittest.main()

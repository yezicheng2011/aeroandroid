import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[1] / 'scripts/preinstall-apps.py'
spec = importlib.util.spec_from_file_location('preinstall', MODULE)
preinstall = importlib.util.module_from_spec(spec); spec.loader.exec_module(preinstall)

APK = b'pretend apk'
ENTRY = {'name': 'Fixture', 'package': 'com.example.fixture', 'url': 'https://example.test/app.apk',
         'sha256': hashlib.sha256(APK).hexdigest(), 'signer_sha256': 'ab' * 32}


def fetch(url, destination, content=APK):
    destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(content)


class PreinstallTests(unittest.TestCase):
    def verify(self, entry=ENTRY, info=None, downloaded=fetch):
        info = info or {'app_package': 'com.example.fixture', 'signer_sha256': 'ab' * 32}
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(preinstall, 'download', side_effect=downloaded), \
                mock.patch.object(preinstall.microg, 'apk_info', return_value=info):
            return preinstall.verified_apk(Path(folder), entry, mock.Mock()).name

    def test_pinned_apk_is_downloaded_and_checked(self):
        self.assertEqual(self.verify(), 'com.example.fixture.apk')

    def test_wrong_hash_package_or_signer_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'SHA-256 mismatch'):
            self.verify(downloaded=lambda url, destination: fetch(url, destination, b'tampered'))
        with self.assertRaisesRegex(RuntimeError, 'wrong package'):
            self.verify(info={'app_package': 'com.evil', 'signer_sha256': 'ab' * 32})
        with self.assertRaisesRegex(RuntimeError, 'wrong package'):
            self.verify(info={'app_package': 'com.example.fixture', 'signer_sha256': 'cd' * 32})

    def test_only_https_downloads(self):
        with self.assertRaisesRegex(RuntimeError, 'non-HTTPS'):
            preinstall.download('http://example.test/app.apk', Path('/nonexistent/app.apk'))


if __name__ == '__main__':
    unittest.main()

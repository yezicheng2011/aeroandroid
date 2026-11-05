import importlib.util
import hashlib
import json
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


def fetch(url, destination, sha256=None, content=APK):
    destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(content)


class PreinstallTests(unittest.TestCase):
    def verify(self, entry=ENTRY, info=None, downloaded=fetch):
        info = info or {'app_package': 'com.example.fixture', 'signer_sha256': 'ab' * 32}
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(preinstall, 'download', side_effect=downloaded), \
                mock.patch.object(preinstall.microg, 'apk_info', return_value=info):
            return preinstall.verified_apk(Path(folder), entry, mock.Mock()).name

    def test_pinned_apk_is_downloaded_and_checked(self):
        self.assertEqual(self.verify(), f"com.example.fixture-{ENTRY['sha256'][:8]}.apk")   # the name carries the pin, so two builds of one app never collide

    def test_wrong_hash_package_or_signer_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'SHA-256 mismatch'):
            self.verify(downloaded=lambda url, destination, sha256=None: fetch(url, destination, content=b'tampered'))
        with self.assertRaisesRegex(RuntimeError, 'wrong package'):
            self.verify(info={'app_package': 'com.evil', 'signer_sha256': 'ab' * 32})
        with self.assertRaisesRegex(RuntimeError, 'wrong package'):
            self.verify(info={'app_package': 'com.example.fixture', 'signer_sha256': 'cd' * 32})

    def test_mirrors_are_tried_first_then_the_pinned_url(self):
        official = 'https://f-droid.org/repo/com.aurora.store_76.apk'
        with mock.patch.dict(preinstall.os.environ, {'FDROID_MIRROR': 'https://a.example/fdroid/repo https://b.example/repo/'}):
            self.assertEqual(preinstall.candidate_urls(official), [
                'https://a.example/fdroid/repo/com.aurora.store_76.apk',
                'https://b.example/repo/com.aurora.store_76.apk', official])
            self.assertEqual(preinstall.candidate_urls('https://example.test/app.apk'), ['https://example.test/app.apk'])
        with mock.patch.dict(preinstall.os.environ, {}, clear=True):
            self.assertEqual(preinstall.candidate_urls(official), [official])

    def test_a_failing_mirror_falls_back_to_the_next_server(self):
        official = 'https://f-droid.org/repo/x.apk'
        calls = []
        def fake_open(url, timeout):
            calls.append(url)
            if 'a.example' in url: raise OSError('blocked')
            import io; return io.BytesIO(b'apk bytes')
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.dict(preinstall.os.environ, {'FDROID_MIRROR': 'https://a.example/repo/'}), \
                mock.patch.object(preinstall.urllib.request, 'urlopen', side_effect=fake_open):
            target = Path(folder) / 'x.apk'
            preinstall.download(official, target)
            self.assertEqual(target.read_bytes(), b'apk bytes')
        self.assertEqual(calls, ['https://a.example/repo/x.apk', official])

    def test_each_app_gets_the_build_the_system_can_run_preferring_native_code(self):
        apps = [{'package': 'a', 'abi': 'arm64-v8a'}, {'package': 'a', 'abi': 'x86_64'}, {'package': 'b'},
                {'package': 'c', 'abi': 'arm64-v8a'}]
        pick = lambda abilist: sorted((e['package'], e.get('abi')) for e in preinstall.choose_builds(apps, abilist))
        self.assertEqual(pick(['arm64-v8a']), [('a', 'arm64-v8a'), ('b', None), ('c', 'arm64-v8a')])        # Apple Silicon
        self.assertEqual(pick(['x86_64']), [('a', 'x86_64'), ('b', None)])                                  # Intel, no translation
        self.assertEqual(pick(['x86_64', 'arm64-v8a']), [('a', 'x86_64'), ('b', None), ('c', 'arm64-v8a')])  # Intel + translation

    def test_the_manifest_pins_both_builds_of_fennec(self):
        apps = json.loads((preinstall.MANIFEST).read_text())['apps']
        fennec = {a['abi']: a for a in apps if a['package'] == 'org.mozilla.fennec_fdroid'}
        self.assertEqual(set(fennec), {'arm64-v8a', 'x86_64'})
        self.assertEqual(fennec['arm64-v8a']['signer_sha256'], fennec['x86_64']['signer_sha256'])
        self.assertNotEqual(fennec['arm64-v8a']['sha256'], fennec['x86_64']['sha256'])

    def test_a_mirror_serving_the_wrong_file_falls_back_to_the_official_server(self):
        import io
        good = b'the real apk'
        def fake_open(url, timeout):
            return io.BytesIO(b'tampered' if 'mirror.example' in url else good)
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.dict(preinstall.os.environ, {'FDROID_MIRROR': 'https://mirror.example/repo/'}), \
                mock.patch.object(preinstall.urllib.request, 'urlopen', side_effect=fake_open):
            target = Path(folder) / 'x.apk'
            preinstall.download('https://f-droid.org/repo/x.apk', target, hashlib.sha256(good).hexdigest())
            self.assertEqual(target.read_bytes(), good)

    def test_only_https_downloads(self):
        with self.assertRaisesRegex(RuntimeError, 'non-HTTPS'):
            preinstall.download('http://example.test/app.apk', Path('/nonexistent/app.apk'))


if __name__ == '__main__':
    unittest.main()

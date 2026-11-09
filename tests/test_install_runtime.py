"""The bundled Android installer reports progress and checks pinned bytes."""
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_runtime', ROOT / 'scripts/install-runtime.py')
install_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install_runtime)


class Body:
    def __init__(self, data):
        self.data = data
        self.headers = {'Content-Length': str(len(data))}
        self._pos = 0

    def read(self, count):
        chunk = self.data[self._pos:self._pos + count]
        self._pos += count
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def progress_values(text):
    values = []
    for line in text.splitlines():
        if line.startswith('AERO_PROGRESS\t'):
            values.append(float(line.split('\t', 2)[1]))
    return values


class InstallRuntimeTests(unittest.TestCase):
    def test_status_cli_reports_a_missing_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            done = subprocess.run([sys.executable, str(ROOT / 'scripts/install-runtime.py'),
                                   'status', '--root', folder],
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(json.loads(done.stdout)['installed'])

    def test_install_refuses_to_start_without_the_license_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            done = subprocess.run([sys.executable, str(ROOT / 'scripts/install-runtime.py'),
                                   'install', '--root', folder, '--cache', folder, '--mirror', 'global'],
                                  capture_output=True, text=True, timeout=30)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn('license', done.stderr.lower())

    def test_progress_advances_and_a_bad_mirror_falls_back(self):
        good = b'android-runtime-bytes'
        digest = hashlib.sha256(good).hexdigest()
        official = 'https://dl.google.com/android/repository/runtime.zip'
        mirrored = 'https://mirrors.cloud.tencent.com/AndroidSDK/runtime.zip'
        seen = []

        def opener(request, timeout=60):
            seen.append(request.full_url)
            if request.full_url == mirrored:
                return Body(b'tampered')
            if request.full_url == official:
                return Body(good)
            raise AssertionError(request.full_url)

        lock = {'android': 17, 'archives': [
            {'name': 'runtime.zip', 'url': official, 'relative_path': 'sdk-macos/runtime.zip',
             'sha256': digest, 'kind': 'python'}]}
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            errors = io.StringIO()
            with redirect_stderr(errors):
                install_runtime.download_runtime(lock, cache, 'cn', include_catalogs=False, opener=opener)
            self.assertEqual((cache / 'sdk-macos/runtime.zip').read_bytes(), good)
        self.assertEqual(seen[0], mirrored)
        self.assertIn(official, seen)
        values = progress_values(errors.getvalue())
        self.assertGreaterEqual(len(values), 2)
        self.assertLessEqual(values[0], values[-1])
        self.assertGreater(values[-1], 0)

    def test_a_verified_file_is_not_downloaded_again(self):
        payload = b'cached'
        digest = hashlib.sha256(payload).hexdigest()
        official = 'https://example.invalid/cached.zip'

        def opener(_request, timeout=60):
            raise AssertionError('cached file should not be fetched')

        lock = {'android': 17, 'archives': [
            {'name': 'cached.zip', 'url': official, 'relative_path': 'sdk-macos/cached.zip',
             'sha256': digest, 'kind': 'jdk'}]}
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            dest = cache / 'sdk-macos/cached.zip'
            dest.parent.mkdir(parents=True)
            dest.write_bytes(payload)
            errors = io.StringIO()
            with redirect_stderr(errors):
                install_runtime.download_runtime(lock, cache, 'global', include_catalogs=False, opener=opener)
        self.assertIn('Already downloaded', errors.getvalue())

    def test_license_text_comes_from_the_catalog(self):
        xml = b'<repository><license id="android-sdk-license">Be kind.</license></repository>'
        official = install_runtime.GOOGLE_BASE + 'repository2-3.xml'

        def opener(request, timeout=60):
            self.assertEqual(request.full_url, official)
            return Body(xml)

        with tempfile.TemporaryDirectory() as folder:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                install_runtime.cmd_license(Path(folder), 'global', opener=opener)
        self.assertEqual(out.getvalue().strip(), 'Be kind.')
        self.assertIn('AERO_MIRROR\tglobal', err.getvalue())
        self.assertTrue(progress_values(err.getvalue()))

    def test_disk_check_rejects_an_impossible_requirement(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'free disk'):
                install_runtime.ensure_space(Path(folder), gigabytes=10 ** 9)


if __name__ == '__main__':
    unittest.main()

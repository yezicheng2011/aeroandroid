"""Public-country mirror selection. A failed lookup must stay on the official source."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import mirror  # noqa: E402


class MirrorTests(unittest.TestCase):
    def test_explicit_choice_does_not_touch_the_network(self):
        def boom(_url):
            raise AssertionError('lookup should not run')
        self.assertEqual(mirror.choose_mirror('cn', boom), 'cn')
        self.assertEqual(mirror.choose_mirror('global', boom), 'global')
        with self.assertRaises(ValueError):
            mirror.choose_mirror('mars', boom)

    def test_mainland_china_uses_the_mirror_and_other_countries_do_not(self):
        self.assertEqual(mirror.choose_mirror('auto', lambda _url: 'loc=CN\n'), 'cn')
        self.assertEqual(mirror.choose_mirror('auto', lambda _url: 'loc=US\n'), 'global')
        self.assertEqual(mirror.choose_mirror('auto', lambda _url: 'HK'), 'global')
        self.assertEqual(mirror.choose_mirror('auto', lambda _url: '{"countryCode":"CN"}'), 'cn')

    def test_a_failed_lookup_uses_the_official_source(self):
        def down(_url):
            raise OSError('offline')
        self.assertEqual(mirror.choose_mirror('auto', down), 'global')

        def junk(_url):
            return '<html>captcha</html>'
        self.assertEqual(mirror.choose_mirror('auto', junk), 'global')

    def test_the_first_successful_lookup_wins(self):
        def fetch(url):
            if 'cloudflare.com' in url or url.startswith('https://1.1.1.1/'):
                raise TimeoutError('blocked')
            if 'ipinfo.io' in url:
                return 'CN\n'
            raise AssertionError(url)
        self.assertEqual(mirror.choose_mirror('auto', fetch), 'cn')

    def test_china_mirror_rewrites_the_same_urls_as_build_sh(self):
        google = 'https://dl.google.com/android/repository/sys-img/android/arm64-v8a-37.0_r06.zip'
        github = 'https://github.com/Genymobile/scrcpy/releases/download/v5.0.1/scrcpy.tar.gz'
        self.assertEqual(mirror.rewrite(google, 'cn'),
                         'https://mirrors.cloud.tencent.com/AndroidSDK/sys-img/android/arm64-v8a-37.0_r06.zip')
        self.assertEqual(mirror.rewrite(github, 'cn'), 'https://gh-proxy.com/' + github)
        self.assertEqual(mirror.rewrite(google, 'global'), google)
        script = (ROOT / 'build.sh').read_text()
        self.assertIn('https://mirrors.cloud.tencent.com/AndroidSDK/', script)
        self.assertIn('https://gh-proxy.com/', script)
        self.assertIn('scripts/mirror.py', script)

    def test_cli_prints_the_forced_choice(self):
        env = {**os.environ, 'AEROANDROID_MIRROR': 'global'}
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/mirror.py'), '--choose'],
                              capture_output=True, text=True, env=env, timeout=15)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), 'global')


if __name__ == '__main__':
    unittest.main()

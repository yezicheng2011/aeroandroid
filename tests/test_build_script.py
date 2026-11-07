"""Run build.sh for real. `bash -n` only checks syntax; a variable used before it is set (which broke every
invocation once) shows up only when the script executes."""
import os
import hashlib
import json
import plistlib
import re
from pathlib import Path
import stat
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run(*args, arch=None, env=None):
    """bash -x build.sh ARGS, with an optional fake `uname` so the chip is whatever the test says."""
    with tempfile.TemporaryDirectory() as folder:
        environment = {**os.environ, **(env or {})}
        if arch:
            shim = Path(folder) / 'uname'
            shim.write_text(f'#!/bin/sh\n[ "$1" = "-s" ] && echo Darwin || echo {arch}\n')
            shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
            sysctl = Path(folder) / 'sysctl'
            sysctl.write_text('#!/bin/sh\necho 0\n'); sysctl.chmod(sysctl.stat().st_mode | stat.S_IEXEC)
            environment['PATH'] = folder + os.pathsep + environment['PATH']
        done = subprocess.run(['bash', '-x', str(ROOT / 'build.sh'), *args], capture_output=True, text=True, env=environment, timeout=60)
    return done.returncode, done.stdout, done.stderr


class BuildScriptTests(unittest.TestCase):
    def assertNoShellError(self, *streams):
        for text in streams:
            for message in ('unbound variable', 'command not found', 'syntax error', 'bad substitution'):
                self.assertNotIn(message, text)

    def test_help_and_check_run_without_shell_errors(self):
        code, out, err = run('--help')
        self.assertEqual(code, 0); self.assertIn('--no-arm-translation', out); self.assertNoShellError(out, err)
        _code, out, err = run('--check')                # fails here (not a Mac), but must reach the prerequisite check
        self.assertIn('Checking prerequisites', out); self.assertNoShellError(out, err)

    def test_every_option_is_accepted_and_bad_ones_are_refused(self):
        for options in (['--android', '17'], ['--android=17'], ['--pure'], ['--with-gpl'], ['--no-arm-translation'], ['--mirror', 'cn'],
                        ['--pure', '--no-arm-translation', '--android', '17', '--mirror', 'global']):
            _code, out, err = run(*options, '--check')
            self.assertIn('Checking prerequisites', out, options); self.assertNoShellError(out, err)
        for version in ('16', '99'):                  # Android 16 was removed: Android 17 is the only version
            code, _out, err = run('--android', version, '--check')
            self.assertEqual(code, 2); self.assertIn(f'Android {version} is no longer supported', err)
        self.assertEqual(run('--bogus')[0], 2)
        self.assertEqual(run('--mirror', 'mars', '--check')[0], 2)

    def test_gpl_extensions_require_explicit_opt_in(self):
        for options, expected in (([], '0'), (['--pure'], '0'), (['--with-gpl'], '1'),
                                  (['--with-gpl', '--pure'], '0')):
            _code, out, err = run(*options, '--check')
            self.assertIn('Checking prerequisites', out)
            self.assertRegex(err, rf'with_gpl={expected}\n')

    def test_default_download_with_a_fresh_cache_never_fetches_provisioning_archives(self):
        # Exercise the real downloader without network access or multi-GB SDK archives.
        for arch in ('arm64', 'x86_64'):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); scripts = root / 'scripts'; scripts.mkdir()
                for source in ('build.sh', 'scripts/host.sh', 'scripts/setup-offline-mac.py'):
                    shutil.copy2(ROOT / source, root / source)
                payload = b'archive'
                archives = [{'name': name, 'url': 'https://example.invalid/' + name,
                             'relative_path': relative, 'sha256': hashlib.sha256(payload).hexdigest(), 'kind': kind}
                            for name, relative, kind in (
                                ('platform.zip', 'sdk-macos/platform.zip', 'platform'),
                                ('jdk.tar.gz', 'mac-tools/jdk.tar.gz', 'jdk'),
                                ('Magisk.apk', 'provision/Magisk.apk', 'magisk'),
                                ('Vector.zip', 'provision/Vector.zip', 'vector'),
                                ('microg.apk', 'provision/microg.apk', 'microg_services'),
                                ('translation.zip', 'provision/translation.zip', 'arm_translation'))]
                lock_name = 'runtime-lock.json' if arch == 'arm64' else 'runtime-lock-x86_64.json'
                (scripts / lock_name).write_text(json.dumps({'arch': arch, 'archives': archives}))
                tools = root / 'bin'; tools.mkdir()
                shims = {'uname': f'[ "$1" = -s ] && echo Darwin || echo {arch}',
                         'sysctl': 'echo 0', 'sw_vers': 'echo 14.0', 'xcrun': 'exit 0',
                         'df': "printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 100000000 0 100000000 0%% /\\n'"}
                for name, body in shims.items():
                    path = tools / name; path.write_text('#!/bin/sh\n' + body + '\n'); path.chmod(0o755)
                curl = tools / 'curl'
                curl.write_text(f'#!{sys.executable}\n' + '''import os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['DOWNLOAD_LOG'], 'a') as log: log.write(args[-1] + '\\n')
if '-o' in args: pathlib.Path(args[args.index('-o') + 1]).write_bytes(b'archive')
''')
                curl.chmod(0o755)
                cache = root / 'runtime-cache'; log = root / 'downloads.log'
                environment = {**os.environ, 'PATH': str(tools) + os.pathsep + os.environ['PATH'],
                               'DOWNLOAD_LOG': str(log), 'ANDROID_SUBSYSTEM_CACHE': str(cache)}
                done = subprocess.run(['bash', str(root / 'build.sh'), '--download-only', '--mirror', 'global'],
                                      capture_output=True, text=True, env=environment, timeout=30)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertTrue((cache / 'sdk-macos/platform.zip').is_file())
                self.assertTrue((cache / 'mac-tools/jdk.tar.gz').is_file())
                self.assertFalse((cache / 'provision').exists())
                fetched = log.read_text()
                for excluded in ('Magisk', 'Vector', 'microg', 'translation'):
                    self.assertNotIn(excluded, fetched)

    def test_it_exports_the_lock_for_the_chip(self):
        expected = {'arm64': 'runtime-lock.json', 'x86_64': 'runtime-lock-x86_64.json'}
        for arch, name in expected.items():
            _code, _out, err = run('--check', arch=arch)
            self.assertIn(f"ANDROID_SUBSYSTEM_LOCK={ROOT}/scripts/{name} ", err + ' ', arch)

    def test_an_old_cache_is_reused_under_its_new_name_and_loses_the_android_16_files(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            old = cache / 'android16-macos'; old.mkdir()
            for name in ('platform-36_r02.zip', 'arm64-v8a-36_r02.zip', 'emulator-darwin_aarch64-16428233.zip', 'repository2-3.xml'):
                (old / name).write_text(name)
            (cache / 'android17-macos').mkdir()
            (cache / 'android17-macos/kept.zip').write_text('the Android 17 downloads are not touched')
            migrate = f'source "{ROOT}/scripts/host.sh"; migrate_old_cache "{cache}" "{ROOT}/scripts/runtime-lock.json"'
            for _ in range(2):                                      # the second run has nothing left to do
                subprocess.run(['bash', '-c', migrate], check=True, env={**os.environ, 'project_root': str(ROOT)})
            self.assertFalse(old.exists())
            self.assertEqual(sorted(p.name for p in (cache / 'sdk-macos').iterdir()), ['platform-36_r02.zip', 'repository2-3.xml'])
            self.assertTrue((cache / 'android17-macos/kept.zip').exists())
            # A cache that already has the new folder is left exactly as it is.
            (cache / 'android16-macos').mkdir(); (cache / 'android16-macos/other.zip').write_text('x')
            subprocess.run(['bash', '-c', migrate], check=True, env={**os.environ, 'project_root': str(ROOT)})
            self.assertTrue((cache / 'android16-macos/other.zip').exists())

    def test_the_arm_translation_switch_reaches_the_installer(self):
        _c, _o, err = run('--no-arm-translation', '--check', arch='x86_64')
        self.assertIn('AEROANDROID_ARM_TRANSLATION=0', err)
        _c, _o, err = run('--check', arch='x86_64')
        self.assertIn('AEROANDROID_ARM_TRANSLATION=1', err)

    def test_the_intel_notice_is_shown_on_intel_only(self):
        self.assertIn('Intel Mac detected', run('--check', arch='x86_64')[1])
        self.assertNotIn('Intel Mac detected', run('--check', arch='arm64')[1])


class PackagingTests(unittest.TestCase):
    def test_both_info_plists_are_rendered_from_the_version_file_and_one_copyright_line(self):
        script = (ROOT / 'scripts/build-mac.sh').read_text()
        version = (ROOT / 'VERSION').read_text().strip()
        copyright_line = re.search(r"^copyright='(.*)'$", script, re.M).group(1)
        templates = re.findall(r"render > \"[^\"]+\" <<'PLIST'\n(.*?)\nPLIST", script, re.S)
        self.assertEqual(len(templates), 2)                                  # the manager and the APK installer helper
        for template in templates:
            rendered = template.replace('@VERSION@', version).replace('@COPYRIGHT@', copyright_line)
            self.assertNotIn('@VERSION@', rendered)
            info = plistlib.loads(rendered.encode())
            self.assertEqual((info['CFBundleShortVersionString'], info['CFBundleVersion']), (version, version))
            self.assertEqual(info['NSHumanReadableCopyright'], copyright_line)
            self.assertEqual(info['CFBundleDevelopmentRegion'], 'en')      # macOS's own menus and dialogs follow it
            self.assertNotRegex(info.get('CFBundleDisplayName', ''), r'[\u3000-\u9fff]')   # the Dock and Finder name is English
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        self.assertEqual(len(re.findall(r'<string>\d+\.\d+\.\d+</string>', script)), 0)   # no second hard-coded version

    def test_gitignore_has_no_duplicate_entries(self):
        entries = [line for line in (ROOT / '.gitignore').read_text().splitlines() if line and not line.startswith('#')]
        self.assertEqual(len(entries), len(set(entries)))


if __name__ == '__main__':
    unittest.main()

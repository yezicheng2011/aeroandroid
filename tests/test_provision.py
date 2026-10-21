import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

MODULE = Path(__file__).resolve().parents[1] / 'scripts/provision-mac.py'
spec = importlib.util.spec_from_file_location('provision', MODULE)
provision = importlib.util.module_from_spec(spec); spec.loader.exec_module(provision)


class FakeController:
    api = 36
    image_tag = 'default'

    def __init__(self, root=None):
        self.root = Path(root) if root else None
        self.sdk = self.root / 'sdk' if self.root else None
        self.config = {'android': 16}
        self.calls = []
        self.manager_installed = True
        self.magisk_root = True
        self.su_applet = True
        self.adb_root_allowed = True
        self.boots = 0

    def ready(self):
        pass

    def device(self):
        return True

    def boot(self):
        self.boots += 1

    def stop(self):
        pass

    def configure(self, changes):
        self.config.update(changes)

    @property
    def magisk_image_dir(self):
        return self.root / 'images/16/default'

    def adb(self, *args, **kwargs):
        self.calls.append(args)
        stdout = ''
        code = 0
        if args == ('root',):
            if not self.adb_root_allowed:
                stdout = 'adbd cannot run as root in production builds'
        elif args == ('shell', 'id', '-u'):
            stdout = '0\n'
        elif args == ('shell', '/debug_ramdisk/magisk', '-v'):
            stdout = '30.7:MAGISK:R (30700)\n'
        elif args == ('shell', '/debug_ramdisk/magisk', 'su', '-c', 'id'):
            code = 0 if self.su_applet else 1
            stdout = 'uid=0(root) gid=0(root)\n' if self.magisk_root else 'uid=2000(shell)\n'
        elif args == ('shell', 'su', '-c', 'id'):
            stdout = 'uid=0(root) gid=0(root)\n' if self.magisk_root else 'uid=2000(shell)\n'
        elif args[:3] == ('shell', 'pm', 'path'):
            if args[3] == 'com.topjohnwu.magisk' and self.manager_installed:
                stdout = 'package:/data/app/magisk/base.apk\n'
            else:
                code = 1
        elif args == ('shell', 'getprop', 'ro.product.cpu.abi'):
            stdout = 'arm64-v8a\n'
        elif args[0] == 'pull':
            Path(args[2]).write_bytes(b'patched-private-ramdisk' * 4096)
        return subprocess.CompletedProcess(args, code, stdout, '')


class MagiskProvisionTests(unittest.TestCase):
    def test_magisk_only_provision_preserves_private_ramdisk_and_needs_no_gapps(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            project = base / 'project'
            (project / 'scripts').mkdir(parents=True)
            (project / 'third_party/Magisk').mkdir(parents=True)
            (project / 'third_party/Magisk/host_patch.sh').write_text('# pinned upstream patch source')
            cache = base / 'cache'
            cache.mkdir()
            archive = cache / 'Magisk.apk'
            with zipfile.ZipFile(archive, 'w') as apk:
                apk.writestr('lib/arm64-v8a/libbusybox.so', b'mock-busybox')
            (project / 'scripts/runtime-lock.json').write_text(json.dumps({'archives': [{
                'kind': 'magisk', 'relative_path': 'Magisk.apk',
                'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            }]}))
            root = base / 'runtime'
            root.mkdir()
            controller = FakeController(root)
            original = controller.sdk / 'system-images/android-36/default/arm64-v8a/ramdisk.img'
            original.parent.mkdir(parents=True)
            original.write_bytes(b'unchanged-sdk-ramdisk')
            with mock.patch.object(provision, 'PROJECT', project), mock.patch.object(
                    provision.subsystem, 'Controller', return_value=controller):
                report = provision.provision(cache, root)
            patched = root / 'images/16/default/ramdisk.magisk.img'
            descriptor = json.loads((patched.parent / 'ramdisk.json').read_text())
            self.assertEqual(controller.config['magisk_ramdisk'], str(patched))
            self.assertEqual(descriptor['image_tag'], 'default')
            self.assertEqual(descriptor['sha256'], hashlib.sha256(patched.read_bytes()).hexdigest())
            self.assertEqual(descriptor['source_ramdisk_sha256'], hashlib.sha256(original.read_bytes()).hexdigest())
            self.assertEqual(original.read_bytes(), b'unchanged-sdk-ramdisk')
            self.assertEqual(descriptor['magisk_apk_sha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(controller.boots, 2)
            self.assertEqual(report['packages'], {'com.topjohnwu.magisk': ['package:/data/app/magisk/base.apk']})
            self.assertNotIn('gapps_module', report)
            self.assertFalse(any('--install-module' in args for args in controller.calls))
            self.assertEqual(json.loads((root / 'provision-report.json').read_text()), report)

    def test_verification_accepts_guest_with_only_magisk_manager(self):
        controller = FakeController()
        report = provision.verify(controller)
        self.assertTrue(report['root'])
        package_requests = [args[3] for args in controller.calls if args[:3] == ('shell', 'pm', 'path')]
        self.assertEqual(package_requests, ['com.topjohnwu.magisk'])
        self.assertEqual(controller.calls[-1], ('unroot',))

    def test_root_check_uses_su_fallback(self):
        controller = FakeController()
        controller.su_applet = False
        self.assertTrue(provision.verify(controller)['root'])
        self.assertIn(('shell', 'su', '-c', 'id'), controller.calls)

    def test_missing_manager_restores_adb_unroot(self):
        controller = FakeController()
        controller.manager_installed = False
        with self.assertRaisesRegex(RuntimeError, 'Missing required package: com.topjohnwu.magisk'):
            provision.verify(controller)
        self.assertEqual(controller.calls[-1], ('unroot',))

    def test_non_root_magisk_is_rejected_and_restores_adb_unroot(self):
        controller = FakeController()
        controller.magisk_root = False
        with self.assertRaisesRegex(RuntimeError, 'Magisk su did not return uid=0'):
            provision.verify(controller)
        self.assertEqual(controller.calls[-1], ('unroot',))

    def test_production_guest_without_adb_root_is_rejected(self):
        controller = FakeController()
        controller.adb_root_allowed = False
        with self.assertRaisesRegex(RuntimeError, 'does not support adb root'):
            provision.adb_root(controller)


if __name__ == '__main__': unittest.main()

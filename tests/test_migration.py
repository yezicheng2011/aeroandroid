import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[1] / 'scripts/prepare-runtime-migration.py'
spec = importlib.util.spec_from_file_location('migration', MODULE)
migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)


class StoppedController:
    def running_emulator(self): return False
    def device(self): return False
    def unconfirmed_shutdown(self): return False


class MigrationTests(unittest.TestCase):
    def make_root(self, base, python=True):
        root = base / 'runtime-root'
        root.mkdir()
        config = {'android': 16, 'memory_mb': 6144, 'port': 5580, 'magisk_ramdisk': str(root / 'old.img')}
        (root / 'config.json').write_text(json.dumps(config))
        if python:
            path = root / 'runtime/python/bin/python3'
            path.parent.mkdir(parents=True)
            path.write_text('private-python-placeholder')
        userdata = root / 'avd/MacAndroid_16_arm64.avd/userdata-qemu.img'
        userdata.parent.mkdir(parents=True)
        userdata.write_bytes(b'old-userdata')
        return root

    def test_missing_private_python_does_not_quit_or_mutate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(Path(directory), python=False)
            before = (root / 'config.json').read_bytes()
            runner = mock.Mock()
            quit = mock.Mock()
            with self.assertRaisesRegex(RuntimeError, 'missing its private Python'):
                migration.prepare(root, runner=runner, quit=quit)
            runner.assert_not_called()
            quit.assert_not_called()
            self.assertEqual((root / 'config.json').read_bytes(), before)
            self.assertFalse((root / 'migration-backup').exists())

    def test_failed_old_backend_stop_preserves_config_and_userdata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(Path(directory))
            before = (root / 'config.json').read_bytes()
            runner = mock.Mock(return_value=subprocess.CompletedProcess([], 1, '{"ok":false,"error":"foreign emulator"}', ''))
            with mock.patch.object(migration, 'old_backend', return_value=Path('/existing/backend.py')):
                with self.assertRaisesRegex(RuntimeError, 'Old runtime shutdown failed'):
                    migration.prepare(root, runner=runner, quit=lambda _: None)
            self.assertEqual((root / 'config.json').read_bytes(), before)
            self.assertEqual((root / 'avd/MacAndroid_16_arm64.avd/userdata-qemu.img').read_bytes(), b'old-userdata')
            self.assertFalse((root / 'migration-backup').exists())

    def test_success_quits_then_stops_installed_old_backend_and_backs_up(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = self.make_root(base)
            home = base / 'home'
            old = home / 'Applications/Android Subsystem.app/Contents/Resources/backend/subsystem.py'
            old.parent.mkdir(parents=True)
            old.write_text('old-backend')
            before = (root / 'config.json').read_bytes()
            sequence = []
            def quit(_):
                sequence.append('quit')
            def runner(args, **kwargs):
                sequence.append('stop')
                self.assertEqual(args[1], str(old))
                self.assertEqual(args[2:], ['stop', '--root', str(root)])
                self.assertEqual((root / 'config.json').read_bytes(), before)
                return subprocess.CompletedProcess(args, 0, '{"ok":true,"data":{"state":"stopped"}}', '')
            def factory(_):
                sequence.append('verify-exit')
                return StoppedController()
            target = migration.prepare(root, home=home, runner=runner, quit=quit, factory=factory)
            self.assertEqual(sequence, ['quit', 'stop', 'verify-exit'])
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / 'config.json').read_bytes(), before)
            self.assertEqual((root / 'avd/MacAndroid_16_arm64.avd/userdata-qemu.img').read_bytes(), b'old-userdata')

    def test_failed_aosp_install_retry_uses_new_avd_aware_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(Path(directory))
            config = json.loads((root / 'config.json').read_text())
            config['image_tag'] = 'default'
            (root / 'config.json').write_text(json.dumps(config))
            runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, '{"ok":true,"data":{"state":"stopped"}}', ''))
            with mock.patch.object(migration, 'old_backend') as legacy:
                migration.prepare(root, runner=runner, quit=lambda _: None, factory=lambda _: StoppedController())
                legacy.assert_not_called()
            self.assertEqual(runner.call_args.args[0][1], str(migration.PROJECT / 'backend/subsystem.py'))
            self.assertEqual(json.loads((root / 'config.json').read_text())['memory_mb'], 6144)


if __name__ == '__main__': unittest.main()

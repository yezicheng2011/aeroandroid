import importlib.util
import json
import os
import plistlib
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1] / 'backend/subsystem.py'
spec = importlib.util.spec_from_file_location('subsystem', BACKEND)
subsystem = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subsystem)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sdk = self.root / 'sdk with spaces'
        self.fixture = Path(__file__).with_name('fake_runtime.py')
        for location in ['platform-tools/adb', 'emulator/emulator', 'cmdline-tools/latest/bin/avdmanager', 'cmdline-tools/latest/bin/sdkmanager', 'build-tools/36.0.0/aapt2']:
            tool = self.sdk / location; tool.parent.mkdir(parents=True, exist_ok=True)
            tool.write_bytes(self.fixture.read_bytes()); tool.chmod(0o755)
        image = self.sdk / 'system-images/android-36/default/arm64-v8a/system.img'
        image.parent.mkdir(parents=True); image.touch()
        scrcpy = self.root / 'scrcpy'; scrcpy.write_bytes(self.fixture.read_bytes()); scrcpy.chmod(0o755)
        self.environment = patch.dict(os.environ, {'ANDROID_SUBSYSTEM_SDK': str(self.sdk), 'TEST_RUNTIME_ROOT': str(self.root)})
        self.environment.start()
        self.mac = patch.object(subsystem.platform, 'system', return_value='Darwin'); self.mac.start()
        self.arm = patch.object(subsystem.platform, 'machine', return_value='arm64'); self.arm.start()
        # The fixture SDK only has the Android 16 image; the product default is Android 17.
        (self.root / 'state').mkdir()
        subsystem.atomic_json(self.root / 'state/config.json', {'android': 16, 'image_tag': 'default'})
        self.controller = subsystem.Controller(self.root / 'state')
        actual_tool = self.controller.tool
        self.controller.tool = lambda name: str(scrcpy) if name == 'scrcpy' else actual_tool(name)

    def tearDown(self):
        # Always terminate only fixture processes, even after an assertion failure.
        state_path = self.root / 'device.json'
        records = subsystem.read_json(self.controller.root / 'windows.json', {}).values()
        for record in records:
            if self.controller.process_matches(record): os.kill(record['pid'], signal.SIGTERM)
        if state_path.exists():
            state = json.loads(state_path.read_text())
            try: os.kill(state['pid'], signal.SIGTERM)
            except ProcessLookupError: pass
        self.mac.stop(); self.arm.stop(); self.environment.stop()
        # Reap fixture children created by subprocess.Popen.
        for p in list(subprocess._active):
            try: p.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
        self.temp.cleanup()

    def test_boot_two_windows_close_and_persistent_restart(self):
        self.assertEqual(self.controller.boot()['state'], 'running')
        self.assertEqual(len(self.controller.apps()['apps']), 2)
        first = self.controller.launch('com.example.first', 'First')
        second = self.controller.launch('com.example.second', 'Second')
        self.assertNotEqual(first['pid'], second['pid'])
        self.assertEqual(set(self.controller.status()['windows']), {'com.example.first', 'com.example.second'})
        self.assertTrue(self.controller.launch('com.example.first')['already_running'])
        commands = [json.loads(line) for line in (self.root / 'windows.jsonl').read_text().splitlines()]
        self.assertTrue(all('--new-display=1280x960/200' in command for command in commands))
        self.assertTrue(all('--flex-display' in command for command in commands))
        self.controller.close('com.example.first')
        self.assertEqual(set(self.controller.windows()), {'com.example.second'})
        self.controller.stop()
        self.assertEqual(self.controller.status()['state'], 'stopped')
        self.assertTrue(self.controller.configured())
        self.assertEqual(self.controller.boot()['state'], 'running')
        self.controller.stop()

    def test_install_app_builds_a_dock_ready_mac_app_with_the_android_icon(self):
        passthrough = subprocess.run
        self.controller.runner = lambda argv, **kw: (subprocess.CompletedProcess(argv, 0, '', '')
                                                    if argv[0].startswith('/usr/bin/') else passthrough(argv, **kw))
        app = self.root / 'Android Subsystem.app'
        (app / 'Contents/MacOS').mkdir(parents=True)
        (app / 'Contents/MacOS/AndroidSubsystem').write_bytes(b'binary')
        apk = self.root / 'fixture.apk'; apk.write_bytes(b'test')
        apps = self.root / 'Applications'
        result = self.controller.install_app([str(apk)], str(app), str(apps))
        self.assertEqual((result['package'], result['label']), ('com.example.fixture', 'Fixture App'))
        launcher = Path(result['launcher'])
        self.assertEqual(launcher, apps / 'Fixture App.app')
        info = plistlib.loads((launcher / 'Contents/Info.plist').read_bytes())
        self.assertEqual((info['AndroidPackage'], info['CFBundleIconFile']), ('com.example.fixture', 'AppIcon'))
        self.assertNotIn('LSUIElement', info)   # a normal app: it has a Dock icon of its own
        icns = (launcher / 'Contents/Resources/AppIcon.icns').read_bytes()
        self.assertEqual((icns[:4], int.from_bytes(icns[4:8], 'big'), icns[8:12]), (b'icns', len(icns), b'ic09'))
        self.assertEqual((launcher / 'Contents/MacOS/AndroidSubsystem').read_bytes(), b'binary')
        # Installing again (an update) refreshes the same app; a foreign folder is never overwritten.
        self.assertEqual(self.controller.install_app([str(apk)], str(app), str(apps))['launcher'], str(launcher))
        with self.assertRaisesRegex(subsystem.SubsystemError, 'already exists'):
            self.controller.export_launcher('com.example.other', 'Fixture App', str(app), str(apps), replace=True)
        with self.assertRaisesRegex(subsystem.SubsystemError, '512x512'):
            subsystem.icns_from_png(b'not a png')
        self.controller.stop()

    def test_quick_boot_is_opt_in_and_prime_clears_stale_snapshots(self):
        self.controller.boot()
        self.assertIn('-no-snapshot', json.loads((self.root / 'emulator-argv.json').read_text()))
        self.controller.stop()
        stale = self.controller.avd_home / f'{self.controller.avd}.avd/snapshots/default_boot/ram.bin'
        stale.parent.mkdir(parents=True); stale.write_bytes(b'old')
        self.assertEqual(self.controller.prime(), {'quick_boot': True})
        self.assertFalse(stale.exists())
        self.assertTrue((self.controller.root / 'quick-boot').is_file())
        self.assertNotIn('-no-snapshot', json.loads((self.root / 'emulator-argv.json').read_text()))
        self.assertEqual(self.controller.status()['state'], 'stopped')

    def test_apk_that_cannot_run_on_this_cpu_gets_a_plain_explanation(self):
        apk = self.root / 'game.apk'; apk.write_bytes(b'arm64 only')
        with self.assertRaisesRegex(subsystem.SubsystemError, r'x86_64,x86\). An Intel Mac needs ARM translation'):
            self.controller.install([str(apk)])
        self.controller.stop()

    def test_launchers_take_the_managers_version_and_follow_its_updates(self):
        passthrough = subprocess.run
        self.controller.runner = lambda argv, **kw: (subprocess.CompletedProcess(argv, 0, '', '')
                                                    if argv[0].startswith('/usr/bin/') else passthrough(argv, **kw))
        app = self.root / 'Android Subsystem.app'
        (app / 'Contents/MacOS').mkdir(parents=True)
        binary = app / 'Contents/MacOS/AndroidSubsystem'; binary.write_bytes(b'binary v1')
        def stamp(version):
            (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleShortVersionString': version,
                'CFBundleVersion': version, 'NSHumanReadableCopyright': 'Copyright test'}))
        stamp('0.3.0')
        apk = self.root / 'fixture.apk'; apk.write_bytes(b'test')
        apps = self.root / 'Applications'
        launcher = Path(self.controller.install_app([str(apk)], str(app), str(apps))['launcher'])
        info = plistlib.loads((launcher / 'Contents/Info.plist').read_bytes())
        self.assertEqual((info['CFBundleShortVersionString'], info['NSHumanReadableCopyright']), ('0.3.0', 'Copyright test'))
        self.assertEqual(self.controller.refresh_launchers(str(app), str(apps)), {'refreshed': []})   # already current
        # An unrelated app and a launcher made by a different manager are never touched.
        other = apps / 'Other.app/Contents'; other.mkdir(parents=True)
        (other / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'x'}))
        elsewhere = apps / 'Foreign.app/Contents/MacOS'; elsewhere.mkdir(parents=True)
        (elsewhere / 'AndroidSubsystem').write_bytes(b'foreign')
        (apps / 'Foreign.app/Contents/Info.plist').write_bytes(plistlib.dumps({
            'AndroidPackage': 'com.example.x', 'SubsystemAppPath': '/somewhere/else.app', 'CFBundleShortVersionString': '0.0.1'}))
        binary.write_bytes(b'binary v2'); stamp('0.4.0')
        self.assertEqual(self.controller.refresh_launchers(str(app), str(apps)), {'refreshed': [launcher.name]})
        self.assertEqual((launcher / 'Contents/MacOS/AndroidSubsystem').read_bytes(), b'binary v2')
        self.assertEqual(plistlib.loads((launcher / 'Contents/Info.plist').read_bytes())['CFBundleShortVersionString'], '0.4.0')
        self.assertEqual((elsewhere / 'AndroidSubsystem').read_bytes(), b'foreign')
        self.assertFalse((launcher / 'Contents/MacOS/.AndroidSubsystem.new').exists())
        self.assertEqual(self.controller.refresh_launchers(str(app), str(apps)), {'refreshed': []})
        self.controller.stop()

    def test_boot_wait_is_adjustable_and_longer_off_apple_silicon(self):
        controller = subsystem.Controller(self.root / 'state')
        self.assertEqual(controller.boot_timeout, 240 if controller.arch == 'arm64' else 480)
        with patch.dict(os.environ, {'ANDROID_SUBSYSTEM_BOOT_TIMEOUT': '90'}):
            self.assertEqual(subsystem.Controller(self.root / 'state').boot_timeout, 90)

    def test_a_process_that_dies_just_after_starting_is_reported(self):
        script = self.root / 'dies-soon'
        script.write_text('#!/bin/sh\nsleep 0.5\necho "bad option" >&2\nexit 3\n'); script.chmod(0o755)
        with self.assertRaisesRegex(subsystem.SubsystemError, r'Runtime exited \(3\)'):
            self.controller.spawn([str(script)], 'dies.log')

    def test_gpu_mode_is_configurable_and_validated_and_fps_reaches_60(self):
        self.controller.boot()
        args = json.loads((self.root / 'emulator-argv.json').read_text())
        self.assertEqual(args[args.index('-gpu') + 1], 'auto')
        self.controller.stop()
        self.controller.configure({'gpu': 'host', 'fps': 60})
        self.controller.boot()
        args = json.loads((self.root / 'emulator-argv.json').read_text())
        self.assertEqual(args[args.index('-gpu') + 1], 'host')
        bundle = self.root / 'bridge bundle'; (bundle / 'backend').mkdir(parents=True)
        (bundle / 'MacBridge.apk').write_bytes(b'bridge')
        with patch.object(subsystem, '__file__', str(bundle / 'backend/subsystem.py')):
            self.assertEqual(self.controller.native_session('com.example.first')['fps'], 60)
        self.controller.stop()
        with self.assertRaisesRegex(subsystem.SubsystemError, 'GPU mode'):
            self.controller.configure({'gpu': 'software'})

    def test_mac_camera_is_passed_through_only_when_one_is_connected(self):
        self.controller.boot()
        self.assertNotIn('-camera-back', json.loads((self.root / 'emulator-argv.json').read_text()))
        self.controller.stop()
        (self.root / 'webcam').touch()
        self.controller.boot()
        args = json.loads((self.root / 'emulator-argv.json').read_text())
        self.assertEqual(args[args.index('-camera-back') + 1], 'webcam0')
        self.assertEqual(args[args.index('-camera-front') + 1], 'webcam0')
        self.controller.stop()

    def bridge_bundle(self):
        """A fake app bundle holding MacBridge.apk, so the tests do not need a built guest APK."""
        bundle = self.root / 'bridge bundle'
        (bundle / 'backend').mkdir(parents=True, exist_ok=True)
        (bundle / 'MacBridge.apk').write_bytes(b'bridge')
        return patch.object(subsystem, '__file__', str(bundle / 'backend/subsystem.py'))

    def test_native_bridge_reuses_authenticated_service_and_cleans_forward(self):
        with self.bridge_bundle():
            self.check_native_bridge_reuse()

    def check_native_bridge_reuse(self):
        first = self.controller.native_session('com.example.first')
        second = self.controller.native_session('com.example.second')
        self.assertEqual(first['port'], second['port'])
        self.assertEqual(first['token'], second['token'])
        self.assertEqual(first['transport'], 'rgba-tcp-v1')
        self.assertEqual(len(first['token']), 64)
        self.assertEqual((self.controller.root / 'surface-token').stat().st_mode & 0o777, 0o600)
        self.assertEqual(first['fps'], 30)
        self.controller.stop()
        self.assertFalse((self.root / 'forward.txt').exists())
        self.assertFalse((self.controller.root / 'graphics.json').exists())

    def test_native_bridge_updates_apk_without_reusing_stale_service(self):
        import hashlib
        bundle = self.root / 'bridge bundle'
        (bundle / 'backend').mkdir(parents=True)
        apk = bundle / 'MacBridge.apk'
        apk.write_bytes(b'first bridge version')
        with patch.object(subsystem, '__file__', str(bundle / 'backend/subsystem.py')):
            first = self.controller.native_session('com.example.first')
            old = subsystem.read_json(self.controller.root / 'graphics.json', {})
            self.assertEqual(old['bridge_sha256'], hashlib.sha256(apk.read_bytes()).hexdigest())
            self.controller.native_session('com.example.second')
            reused = subsystem.read_json(self.controller.root / 'graphics.json', {})
            self.assertEqual(reused['pid'], old['pid'])

            apk.write_bytes(b'updated bridge version')
            real_adb = self.controller.adb
            with patch.object(self.controller, 'adb', wraps=real_adb) as adb:
                updated = self.controller.native_session('com.example.third')
            current = subsystem.read_json(self.controller.root / 'graphics.json', {})
            self.assertNotEqual(current['pid'], old['pid'])
            self.assertFalse(self.controller.process_matches(old))
            self.assertEqual(current['bridge_sha256'], hashlib.sha256(apk.read_bytes()).hexdigest())
            self.assertEqual(updated['token'], first['token'])
            self.assertEqual((self.controller.root / 'surface-token').stat().st_mode & 0o777, 0o600)
            adb.assert_any_call('forward', '--remove', f"tcp:{old['port']}", check=False)
            adb.assert_any_call('forward', 'tcp:0', 'tcp:7900')
            adb.assert_any_call('install', '-r', str(apk), timeout=120)
            self.assertEqual((self.root / 'forward.txt').read_text(),
                             f"{self.controller.serial} tcp:{current['port']} tcp:7900")
        self.controller.stop()

    def test_native_bridge_restarts_legacy_record_missing_apk_digest(self):
        with self.bridge_bundle():
            self.check_legacy_record_restart()

    def check_legacy_record_restart(self):
        first = self.controller.native_session('com.example.first')
        old = subsystem.read_json(self.controller.root / 'graphics.json', {})
        old.pop('bridge_sha256')
        subsystem.atomic_json(self.controller.root / 'graphics.json', old)
        upgraded = self.controller.native_session('com.example.second')
        current = subsystem.read_json(self.controller.root / 'graphics.json', {})
        self.assertNotEqual(current['pid'], old['pid'])
        self.assertFalse(self.controller.process_matches(old))
        self.assertRegex(current['bridge_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(upgraded['token'], first['token'])
        self.controller.stop()

    def test_private_magisk_ramdisk_is_used_and_tampering_is_rejected(self):
        import hashlib
        folder = self.controller.magisk_image_dir; folder.mkdir(parents=True)
        image = folder / 'ramdisk.magisk.img'; image.write_bytes(b'test private ramdisk')
        subsystem.atomic_json(folder / 'ramdisk.json', {'api': 36, 'image_tag': 'default', 'sha256': hashlib.sha256(image.read_bytes()).hexdigest()})
        self.controller.configure({'magisk_ramdisk': str(image)})
        self.controller.boot()
        args = json.loads((self.root / 'emulator-argv.json').read_text())
        self.assertIn('-ramdisk', args)
        self.assertEqual(args[args.index('-ramdisk')+1], str(image))
        self.assertIn('-SystemAsRoot', args)
        self.controller.stop()
        image.write_bytes(b'corrupted ramdisk')
        with self.assertRaisesRegex(subsystem.SubsystemError, 'digest does not match'):
            self.controller.boot()

    def test_foreign_emulator_is_never_stopped(self):
        (self.root / 'device.json').write_text(json.dumps({'avd': 'UserOwnedAVD', 'pid': 1, 'api': '36'}))
        with self.assertRaisesRegex(subsystem.SubsystemError, 'another emulator'):
            self.controller.stop()
        self.assertTrue((self.root / 'device.json').exists())
        (self.root / 'device.json').unlink()

    def test_apk_splits_file_exchange_and_notifications(self):
        apk = self.root / 'app with spaces.apk'; apk.write_bytes(b'test')
        split = self.root / 'split.apk'; split.write_bytes(b'test')
        self.assertEqual(len(self.controller.install([str(apk), str(split)])['installed']), 2)
        file = self.root / "hello $(must-not-run).txt"; file.write_text('input')
        remote = self.controller.push([str(file)])['imported'][0]
        self.assertNotIn('$', remote)
        shell = [json.loads(x) for x in (self.root / 'shell-commands.jsonl').read_text().splitlines()]
        self.assertIn(['test', '-e', remote], shell)
        output = self.root / 'export'; output.mkdir()
        self.controller.pull('/sdcard/Download/MacBridge/test.txt', str(output))
        self.assertEqual((output / 'test.txt').read_text(), 'android data')
        with self.assertRaisesRegex(subsystem.SubsystemError, 'overwrite'):
            self.controller.pull('/sdcard/Download/MacBridge/test.txt', str(output))
        self.assertEqual(self.controller.notifications()['notifications'][0]['body'], 'World')
        self.controller.uninstall('com.example.first')
        self.controller.stop()

    def test_version_switch_locked_while_running_and_no_downgrade(self):
        self.controller.boot()
        with self.assertRaisesRegex(subsystem.SubsystemError, 'Stop Android'):
            self.controller.configure({'android': 17})
        self.controller.stop()
        self.controller.configure({'android': 17})
        with self.assertRaisesRegex(subsystem.SubsystemError, 'Android 17 image missing'):
            self.controller.create()
        self.assertEqual(self.controller.config['android'], 17)

    def test_invalid_inputs_and_pid_reuse(self):
        for value in ['com.example;touch /tmp/x', '--help', '', 'com.example\n']:
            with self.assertRaises(subsystem.SubsystemError): subsystem.package_name(value)
        for value in ['/etc/passwd', '/sdcard/Download/MacBridge/../secret', '/sdcard/Download/MacBridge/$(id)']:
            with self.assertRaises(subsystem.SubsystemError): subsystem.shared_path(value)
        for config in [{'android': 15}, {'port': 5555}, {'memory_mb': True}, {'fps': 10000}, {'resolution': '9999x9999/999'}]:
            with self.assertRaises(subsystem.SubsystemError): subsystem.Controller.validate_config({**subsystem.DEFAULTS, **config})
        self.assertFalse(self.controller.process_matches({'pid': os.getpid(), 'birth': 'not the current process'}))
        with self.assertRaises(subsystem.SubsystemError): self.controller.install([str(self.root / 'missing.apk')])

    def test_wrong_android_api_rejected(self):
        self.controller.boot()
        path = self.root / 'device.json'; state = json.loads(path.read_text()); state['api'] = '35'; path.write_text(json.dumps(state))
        with self.assertRaisesRegex(subsystem.SubsystemError, 'Expected Android API 36'):
            self.controller.ready()
        self.controller.stop()

    def test_live_console_and_adb_port_conflicts_select_another_pair(self):
        for offset in (0, 1):
            port = next(p for p in range(5554, 5681, 2) if self.controller.ports_available(p))
            self.controller.configure({'port': port, 'memory_mb': 8192})
            with socket.socket() as occupied:
                occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                occupied.bind(('127.0.0.1', port + offset))
                occupied.listen(1)
                self.controller.boot()
                selected = self.controller.config['port']
                self.assertNotEqual(selected, port)
                self.assertEqual(subsystem.Controller(self.controller.root).config['port'], selected)
                args = json.loads((self.root / 'emulator-argv.json').read_text())
                self.assertEqual(args[args.index('-memory') + 1], '8192')
                self.assertEqual(args[args.index('-port') + 1], str(selected))
                # The unrelated listener remains open; no process is killed.
                self.assertEqual(occupied.getsockname()[1], port + offset)
                self.controller.stop()

    def test_port_pool_exhaustion_preserves_config_and_does_not_spawn(self):
        self.controller.configure({'memory_mb': 6144})
        before = (self.controller.root / 'config.json').read_bytes()
        with patch.object(self.controller, 'ports_available', return_value=False), \
                patch.object(self.controller, 'spawn') as spawn:
            with self.assertRaisesRegex(subsystem.SubsystemError, 'No free Android port pair') as caught:
                self.controller.boot()
            spawn.assert_not_called()
        self.assertEqual(caught.exception.code, 'no_free_port')    # the Mac app translates this code
        self.assertEqual((self.controller.root / 'config.json').read_bytes(), before)

    def test_occupied_port_with_untrusted_old_record_stays_locked(self):
        port = next(p for p in range(5554, 5681, 2) if self.controller.ports_available(p))
        self.controller.configure({'port': port})
        subsystem.atomic_json(self.controller.root / 'emulator.json', {'pid': 1, 'birth': 'unknown'})
        with socket.socket() as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupied.bind(('127.0.0.1', port)); occupied.listen(1)
            with patch.object(self.controller, 'spawn') as spawn:
                with self.assertRaisesRegex(subsystem.SubsystemError, 'has not confirmed it exited') as caught:
                    self.controller.boot()
                spawn.assert_not_called()
            self.assertEqual(caught.exception.code, 'shutdown_unconfirmed')
            with self.assertRaisesRegex(subsystem.SubsystemError, 'Stop Android'):
                self.controller.configure({'memory_mb': 8192})
        self.assertEqual(self.controller.config['memory_mb'], 4096)

    def test_stop_waits_for_adb_disconnect_and_then_unlocks_memory(self):
        self.controller.boot()
        with patch.object(self.controller, 'device', side_effect=[True, True, False]) as device, \
                patch.object(self.controller, 'running_emulator', return_value=False):
            self.controller.stop()
        self.assertEqual(device.call_count, 3)
        self.assertFalse((self.controller.root / 'emulator.json').exists())
        self.controller.configure({'memory_mb': 8192})
        self.controller.boot()
        args = json.loads((self.root / 'emulator-argv.json').read_text())
        self.assertEqual(args[args.index('-memory') + 1], '8192')
        self.controller.stop()

    def test_stop_failure_keeps_record_and_memory_locked(self):
        self.controller.boot()
        record = (self.controller.root / 'emulator.json').read_bytes()
        real_adb = self.controller.adb
        def failed_kill(*args, **kwargs):
            if args == ('emu', 'kill'):
                return subprocess.CompletedProcess(args, 1, '', 'not stopped')
            return real_adb(*args, **kwargs)
        with patch.object(self.controller, 'adb', side_effect=failed_kill), \
                patch.object(subsystem.time, 'monotonic', side_effect=[0, 16]):
            with self.assertRaisesRegex(subsystem.SubsystemError, 'settings remain locked'):
                self.controller.stop()
        self.assertEqual((self.controller.root / 'emulator.json').read_bytes(), record)
        with self.assertRaisesRegex(subsystem.SubsystemError, 'Stop Android'):
            self.controller.configure({'memory_mb': 8192})
        self.controller.stop()

    def test_waiting_request_reloads_selected_port_before_saving(self):
        waiting = subsystem.Controller(self.controller.root)
        port = next(p for p in range(5554, 5681, 2) if p != waiting.config['port'])
        self.controller.configure({'port': port})
        waiting.configure({'memory_mb': 8192})
        self.assertEqual(waiting.config['port'], port)
        self.assertEqual(subsystem.Controller(self.controller.root).config['port'], port)

    def test_legacy_google_configuration_isolated_from_new_aosp_data(self):
        legacy = self.controller.avd_home / 'MacAndroid_16_arm64.ini'
        legacy.write_text('path=preserved-old-data')
        subsystem.atomic_json(self.controller.root / 'config.json', {'android': 16, 'memory_mb': 6144,
                              'magisk_ramdisk': '/legacy/ramdisk.img'})
        controller = subsystem.Controller(self.controller.root)
        self.assertEqual(controller.image_tag, 'google_apis')
        self.assertEqual(controller.avd, 'MacAndroid_16_arm64')
        with self.assertRaisesRegex(subsystem.SubsystemError, 'Legacy Google'):
            controller.boot()
        controller.configure({'image_tag': 'default'})
        self.assertEqual(controller.avd, 'MacAndroid_16_AOSP_arm64')
        self.assertEqual(controller.config['memory_mb'], 6144)
        self.assertNotIn('magisk_ramdisk', controller.config)
        self.assertEqual(legacy.read_text(), 'path=preserved-old-data')


class PortProbeTests(unittest.TestCase):
    def test_time_wait_is_reusable_but_live_listener_is_not(self):
        port = next(p for p in range(5554, 5681, 2) if subsystem.Controller.ports_available(p))
        with socket.socket() as server, socket.socket() as client:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', port)); server.listen(1)
            self.assertFalse(subsystem.Controller.ports_available(port))
            client.connect(('127.0.0.1', port))
            peer, _ = server.accept()
            peer.close()  # The server actively closes, leaving local TIME_WAIT.
            self.assertEqual(client.recv(1), b'')
        with socket.socket() as old_probe:
            with self.assertRaises(OSError):
                old_probe.bind(('127.0.0.1', port))
        self.assertTrue(subsystem.Controller.ports_available(port))


if __name__ == '__main__': unittest.main()

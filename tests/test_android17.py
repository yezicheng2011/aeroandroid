import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


installer = load('installer', 'scripts/setup-offline-mac.py')
subsystem = load('subsystem', 'backend/subsystem.py')
HEX = re.compile(r'[0-9a-f]{64}\Z')


class Android17Tests(unittest.TestCase):
    def test_lock_pins_a_stable_android_17_image_and_a_new_enough_emulator(self):
        lock16 = json.loads((ROOT / 'scripts/runtime-lock.json').read_text())
        lock17 = json.loads((ROOT / 'scripts/runtime-lock-17.json').read_text())
        self.assertEqual((lock16['android'], lock17['android']), (16, 17))
        packages = {e.get('package'): e for e in lock17['archives'] if e.get('package')}
        self.assertIn('system-images;android-37.0;default;arm64-v8a', packages)
        self.assertNotIn('system-images;android-36;default;arm64-v8a', packages)
        self.assertNotEqual(packages['emulator']['name'], next(e for e in lock16['archives'] if e.get('package') == 'emulator')['name'])
        self.assertTrue(all(HEX.fullmatch(e['sha256']) for e in lock17['archives']))
        # Root and microG are provisioned on 17 too: Magisk v31.0 is the first release with Zygisk for API 37.
        magisk = next(e for e in lock17['archives'] if e.get('kind') == 'magisk')
        self.assertEqual(magisk['name'], 'Magisk-v31.0.apk')
        for kind in ('microg_services', 'microg_companion', 'vector'):
            self.assertEqual(next(e for e in lock17['archives'] if e.get('kind') == kind),
                             next(e for e in lock16['archives'] if e.get('kind') == kind))
        shared = [e for e in lock16['archives'] if e['relative_path'] in {x['relative_path'] for x in lock17['archives']}]
        self.assertTrue(all(e in lock17['archives'] for e in shared))   # reused archives are pinned identically

    def test_sdk_package_destinations_match_the_sdk_layout(self):
        sdk = Path('/sdk')
        for package, expected in {'platforms;android-36': 'platforms/android-36', 'build-tools;36.0.0': 'build-tools/36.0.0',
                                  'cmdline-tools;latest': 'cmdline-tools/latest', 'platform-tools': 'platform-tools',
                                  'emulator': 'emulator',
                                  'system-images;android-36;default;arm64-v8a': 'system-images/android-36/default/arm64-v8a',
                                  'system-images;android-37.0;default;arm64-v8a': 'system-images/android-37.0/default/arm64-v8a'}.items():
            self.assertEqual(installer.package_destination(sdk, package), sdk / expected)

    def test_provisioning_picks_the_lock_for_the_android_version_and_mac_architecture(self):
        core = load('magisk_provision', 'scripts/provision-mac.py')
        names = {(16, 'arm64'): 'runtime-lock.json', (17, 'arm64'): 'runtime-lock-17.json',
                 (16, 'x86_64'): 'runtime-lock-x86_64.json', (17, 'x86_64'): 'runtime-lock-17-x86_64.json'}
        for (android, arch), name in names.items():
            self.assertEqual(core.lock_file(android, arch).name, name)
            self.assertTrue(core.lock_file(android, arch).is_file())

    def test_intel_locks_pin_x86_64_builds_of_every_host_tool(self):
        for android, name in ((16, 'runtime-lock-x86_64.json'), (17, 'runtime-lock-17-x86_64.json')):
            lock = json.loads((ROOT / 'scripts' / name).read_text())
            arm = json.loads((ROOT / 'scripts' / ('runtime-lock.json' if android == 16 else 'runtime-lock-17.json')).read_text())
            self.assertEqual(lock['android'], android)
            by_kind = {e.get('kind') or e.get('package').split(';')[0]: e for e in lock['archives']}
            self.assertIn('x64', by_kind['emulator']['name'])
            self.assertTrue(by_kind['system-images']['package'].endswith(';x86_64'))
            self.assertIn('x64_mac', by_kind['jdk']['name'])
            self.assertIn('x86_64', by_kind['scrcpy']['name'])
            self.assertIn('x86_64-apple-darwin', by_kind['python']['name'])
            self.assertIn('x86_64', by_kind['cmdline-tools']['name'])
            self.assertTrue(all(HEX.fullmatch(e['sha256']) for e in lock['archives']))
            # Nothing architecture-neutral changed: same platform, build tools, root and microG pins.
            keep = ('platforms', 'build-tools', 'platform-tools', 'magisk', 'microg_services', 'microg_companion', 'vector')
            arm_by_kind = {e.get('kind') or e.get('package').split(';')[0]: e for e in arm['archives']}
            for kind in keep:
                self.assertEqual(by_kind[kind], arm_by_kind[kind])

    def test_host_architecture_treats_a_rosetta_shell_on_apple_silicon_as_arm64(self):
        from unittest import mock
        result = lambda out: mock.Mock(stdout=out)
        with mock.patch.object(subsystem.platform, 'machine', return_value='arm64'):
            self.assertEqual(subsystem.host_arch(), 'arm64')
        with mock.patch.object(subsystem.platform, 'machine', return_value='x86_64'):
            with mock.patch.object(subsystem.subprocess, 'run', return_value=result('1\n')):
                self.assertEqual(subsystem.host_arch(), 'arm64')
            with mock.patch.object(subsystem.subprocess, 'run', return_value=result('')):
                self.assertEqual(subsystem.host_arch(), 'x86_64')
            with mock.patch.object(subsystem.subprocess, 'run', side_effect=FileNotFoundError):
                self.assertEqual(subsystem.host_arch(), 'x86_64')

    def test_intel_mac_uses_the_x86_64_image_and_its_own_avd(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = subsystem.Controller(Path(folder))
            controller.config['android'] = 17
            controller.arch = 'arm64'
            self.assertEqual((controller.abi, controller.avd), ('arm64-v8a', 'MacAndroid_17_AOSP_arm64'))
            controller.arch = 'x86_64'
            self.assertEqual((controller.abi, controller.avd), ('x86_64', 'MacAndroid_17_AOSP_x86_64'))

    def test_new_installs_default_to_android_17(self):
        self.assertEqual(subsystem.DEFAULTS['android'], 17)

    def test_controller_looks_for_the_android_17_image_in_android_37_0(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = subsystem.Controller(Path(folder))
            controller.config['android'] = 16
            self.assertEqual(controller.image_api, '36')
            controller.config['android'] = 17
            self.assertEqual((controller.api, controller.image_api), (37, '37.0'))


if __name__ == '__main__':
    unittest.main()

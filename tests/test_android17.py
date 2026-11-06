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
        lock = json.loads((ROOT / 'scripts/runtime-lock.json').read_text())
        self.assertEqual(lock['android'], 17)
        packages = {e.get('package'): e for e in lock['archives'] if e.get('package')}
        self.assertIn('system-images;android-37.0;default;arm64-v8a', packages)
        self.assertEqual([p for p in packages if p.startswith('system-images;')], ['system-images;android-37.0;default;arm64-v8a'])
        self.assertTrue(packages['emulator']['relative_path'].startswith('android17-macos/'))
        self.assertTrue(all(HEX.fullmatch(e['sha256']) for e in lock['archives']))
        # Root and microG are provisioned too: Magisk v31.0 is the first release with Zygisk for API 37.
        magisk = next(e for e in lock['archives'] if e.get('kind') == 'magisk')
        self.assertEqual(magisk['name'], 'Magisk-v31.0.apk')
        for kind in ('microg_services', 'microg_companion', 'vector'):
            self.assertEqual(sum(e.get('kind') == kind for e in lock['archives']), 1)

    def test_android_16_has_been_removed(self):
        scripts = ROOT / 'scripts'
        self.assertEqual(sorted(p.name for p in scripts.glob('runtime-lock*.json')), ['runtime-lock-x86_64.json', 'runtime-lock.json'])
        for name in ('runtime-lock.json', 'runtime-lock-x86_64.json'):
            text = (scripts / name).read_text()
            self.assertNotIn('android-36;', text)           # no Android 16 system image (platform 36 is only the build target)
            self.assertNotIn('android16-macos', text)
            self.assertEqual(json.loads(text)['android'], 17)

    def test_sdk_package_destinations_match_the_sdk_layout(self):
        sdk = Path('/sdk')
        for package, expected in {'platforms;android-36': 'platforms/android-36', 'build-tools;36.0.0': 'build-tools/36.0.0',
                                  'cmdline-tools;latest': 'cmdline-tools/latest', 'platform-tools': 'platform-tools',
                                  'emulator': 'emulator',
                                  'system-images;android-37.0;default;arm64-v8a': 'system-images/android-37.0/default/arm64-v8a'}.items():
            self.assertEqual(installer.package_destination(sdk, package), sdk / expected)

    def test_provisioning_picks_the_lock_for_the_mac_architecture(self):
        core = load('magisk_provision', 'scripts/provision-mac.py')
        for arch, name in {'arm64': 'runtime-lock.json', 'x86_64': 'runtime-lock-x86_64.json'}.items():
            self.assertEqual(core.lock_file(arch).name, name)
            self.assertTrue(core.lock_file(arch).is_file())

    def test_intel_lock_pins_x86_64_builds_of_every_host_tool(self):
        lock = json.loads((ROOT / 'scripts/runtime-lock-x86_64.json').read_text())
        arm = json.loads((ROOT / 'scripts/runtime-lock.json').read_text())
        self.assertEqual(lock['android'], 17)
        by_kind = {e.get('kind') or e.get('package').split(';')[0]: e for e in lock['archives']}
        self.assertIn('x64', by_kind['emulator']['name'])
        self.assertTrue(by_kind['system-images']['package'].endswith(';x86_64'))
        self.assertIn('x64_mac', by_kind['jdk']['name'])
        self.assertIn('x86_64', by_kind['scrcpy']['name'])
        self.assertIn('x86_64-apple-darwin', by_kind['python']['name'])
        self.assertIn('x86_64', by_kind['cmdline-tools']['name'])
        translation = by_kind['arm_translation']      # Google's image, the source of the ARM translator
        self.assertIn('google_apis', translation['url'])
        self.assertTrue(translation['relative_path'].startswith('provision/'))   # only downloaded for the full edition
        self.assertEqual(lock['arch'], 'x86_64')
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
            self.assertEqual((controller.config['android'], controller.api, controller.image_api), (17, 37, '37.0'))
            self.assertEqual(subsystem.image_folder(16), '36')       # only used to recognise an old install

    def test_only_android_17_is_accepted_for_new_settings(self):
        subsystem.Controller.validate_config({**subsystem.DEFAULTS})
        subsystem.Controller.validate_config({**subsystem.DEFAULTS, 'android': 16})   # loads, so an old install can be upgraded
        for version in (15, 18, '17', None):
            with self.assertRaisesRegex(subsystem.SubsystemError, 'Only Android 17'):
                subsystem.Controller.validate_config({**subsystem.DEFAULTS, 'android': version})

if __name__ == '__main__':
    unittest.main()

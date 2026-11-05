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
        self.assertFalse([e for e in lock17['archives'] if e['relative_path'].startswith('provision/')])   # no Magisk/microG
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

    def test_controller_looks_for_the_android_17_image_in_android_37_0(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = subsystem.Controller(Path(folder))
            self.assertEqual(controller.image_api, '36')
            controller.config['android'] = 17
            self.assertEqual((controller.api, controller.image_api), (37, '37.0'))


if __name__ == '__main__':
    unittest.main()

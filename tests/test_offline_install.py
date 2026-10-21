import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
import json
import hashlib
from unittest.mock import patch
from xml.dom import minidom

MODULE = Path(__file__).resolve().parents[1] / 'scripts/setup-offline-mac.py'
spec = importlib.util.spec_from_file_location('installer', MODULE)
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)

class ArchiveTests(unittest.TestCase):
    def test_valid_package_layout_and_executable_bits(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); archive = root / 'tools.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                item = zipfile.ZipInfo('tools/bin/adb'); item.external_attr = 0o100755 << 16; z.writestr(item, 'executable')
            installer.extract_zip(archive, root / 'output')
            self.assertEqual((root / 'output/bin/adb').read_text(), 'executable')
            self.assertEqual((root / 'output/bin/adb').stat().st_mode & 0o777, 0o755)
    def test_zip_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as z: z.writestr('tools/../../outside', 'bad')
            with self.assertRaisesRegex(RuntimeError, 'Unsafe ZIP'): installer.extract_zip(archive, root / 'output')
            self.assertFalse((root / 'outside').exists())
    def test_unexpected_multiple_roots_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as z: z.writestr('one/file', 'one'); z.writestr('two/file', 'two')
            with self.assertRaisesRegex(RuntimeError, 'layout'): installer.extract_zip(archive, root / 'output')


class MetadataTests(unittest.TestCase):
    def test_pinned_stable_revision_and_namespaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); metadata = root / 'android16-macos'; metadata.mkdir()
            (metadata / 'repository2-3.xml').write_text('''<sdk:sdk-repository
                xmlns:sdk="http://schemas.android.com/sdk/android/repo/repository2/03"
                xmlns:generic="http://schemas.android.com/repository/android/generic/02"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                <license id="android-sdk-license" type="text">SDK terms</license>
                <remotePackage path="emulator"><type-details xsi:type="generic:genericDetailsType"/>
                  <revision><major>38</major></revision><archives><archive><complete><url>preview.zip</url><checksum>preview-sha</checksum></complete></archive></archives>
                </remotePackage>
                <remotePackage path="emulator"><type-details xsi:type="generic:genericDetailsType"/>
                  <revision><major>37</major><minor>2</minor><micro>12</micro></revision><display-name>Android Emulator</display-name>
                  <uses-license ref="android-sdk-license"/><archives><archive><complete><url>stable.zip</url><checksum>stable-sha</checksum></complete></archive></archives>
                </remotePackage></sdk:sdk-repository>''')
            lock = {'archives':[{'package':'emulator','name':'stable.zip','sha1':'stable-sha'}]}
            dest = root / 'sdk/emulator'; dest.mkdir(parents=True)
            installer.register_sdk_packages(installer.package_records(root, lock), {'emulator':dest})
            document = minidom.parse(str(dest / 'package.xml'))
            self.assertEqual(document.documentElement.namespaceURI, installer.COMMON_NAMESPACE)
            self.assertEqual(document.documentElement.getAttribute('xmlns:generic'), 'http://schemas.android.com/repository/android/generic/02')
            self.assertEqual(document.getElementsByTagName('major')[0].firstChild.data, '37')
            self.assertEqual(document.getElementsByTagName('localPackage')[0].getAttribute('path'), 'emulator')
            self.assertEqual(len(document.getElementsByTagName('archives')), 0)
    def test_existing_binaries_allow_metadata_only_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); lock={'archives':[]}
            (root/'sdk/emulator').mkdir(parents=True); (root/'runtime/bin').mkdir(parents=True)
            (root/'sdk/emulator/emulator').touch(); (root/'runtime/bin/scrcpy').touch()
            fingerprint=hashlib.sha256(json.dumps(lock,sort_keys=True).encode()).hexdigest()
            (root/'installed-runtime.json').write_text(json.dumps({'fingerprint':fingerprint}))
            self.assertTrue(installer.runtime_installed(root,lock))
            self.assertFalse((root/'sdk/emulator/package.xml').exists())
    def test_accepted_license_is_not_prompted_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); sdk=root/'sdk'
            installer.accept_sdk_licenses({'android-sdk-license':'Terms'},sdk,root,accept=True)
            with patch('builtins.input',side_effect=AssertionError('Already accepted license prompted again')):
                installer.accept_sdk_licenses({'android-sdk-license':'Terms'},sdk,root)
    def test_module_update_keeps_sdk_fingerprint_but_image_change_invalidates_it(self):
        lock = {'android': 16, 'image_tag': 'default', 'archives': [
            {'package': 'system-images;android-36;default;arm64-v8a', 'sha256': 'a'},
            {'kind': 'microg_services', 'sha256': 'b'}]}
        first = installer.runtime_fingerprint(lock)
        lock['archives'][1]['sha256'] = 'c'
        self.assertEqual(installer.runtime_fingerprint(lock), first)
        lock['archives'][0]['sha256'] = 'd'
        self.assertNotEqual(installer.runtime_fingerprint(lock), first)
    def test_legacy_image_cleanup_keeps_userdata_and_refuses_redirected_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'runtime'; root.mkdir()
            legacy = root / 'sdk/system-images/android-36/google_apis/arm64-v8a'
            legacy.mkdir(parents=True); (legacy / 'system.img').write_text('old image')
            userdata = root / 'avd/MacAndroid_16_arm64.avd/userdata-qemu.img'
            userdata.parent.mkdir(parents=True); userdata.write_text('user data')
            installer.retire_legacy_google_image(root)
            self.assertFalse(legacy.exists())
            self.assertEqual(userdata.read_text(), 'user data')
            outside = Path(directory) / 'outside'; outside.mkdir()
            (outside / 'important').write_text('keep')
            legacy.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, 'redirected'):
                installer.retire_legacy_google_image(root)
            self.assertEqual((outside / 'important').read_text(), 'keep')

if __name__ == '__main__': unittest.main()

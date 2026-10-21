import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zipfile

MODULE = Path(__file__).resolve().parents[1] / 'scripts/provision-microg.py'
spec = importlib.util.spec_from_file_location('microg', MODULE)
microg = importlib.util.module_from_spec(spec); spec.loader.exec_module(microg)

PM_PERMISSIONS = '''All Permissions:

+ group:android.permission-group.PHONE
  permission:android.permission.READ_PHONE_STATE
    package:android
    protectionLevel:dangerous
+ Permission not in a group:
  permission:android.permission.READ_PRIVILEGED_PHONE_STATE
    package:android
    protectionLevel:signature|privileged
  permission:android.permission.UPDATE_APP_OPS_STATS
    package:android
    protectionLevel:signature|privileged|development|appop
  permission:android.permission.MANAGE_USERS
    package:android
    protectionLevel:signature|privileged
  permission:android.permission.INTERNET
    package:android
    protectionLevel:normal
  permission:android.permission.FAKE_SIGNATURE_ONLY
    package:android
    protectionLevel:signature
'''


def good_probe():
    return {'ok': True, 'signature_checked': True, 'packages': [
        {'package': package, 'legacy_valid': True, 'modern_valid': True,
         'raw_certificate_valid': True, 'digest_certificate_valid': True,
         'wrong_certificate_rejected': True, 'legacy_sha256': ['google'], 'modern_sha256': ['google']}
        for package in microg.APK_KINDS.values()]}


class FakeController:
    image_tag = 'default'
    config = {'android': 16}

    def __init__(self, root):
        self.root = Path(root)
        self.sdk = self.root / 'sdk'
        self.calls = []
        self.packages = {}
        self.modules = set()
        self.boot_count = 0
        self.zygisk = 0
        self.module_status = 'enabled'
        self.scope = [{'APP_PACKAGE': 'system', 'USER_ID': 0}]
        self.enable_failed = []
        self.probe = good_probe()

    def boot(self):
        self.boot_count += 1
        if microg.MODULE_ID in self.modules:
            for package, directory in microg.APK_MODULE_DIRS.items():
                self.packages[package] = f'/system/priv-app/{directory}/{directory}.apk'

    def stop(self):
        self.calls.append(('stop',))

    def adb(self, *args, **kwargs):
        self.calls.append(args)
        output = ''
        code = 0
        if args[:3] == ('shell', 'pm', 'path'):
            if args[3] in self.packages:
                output = 'package:' + self.packages[args[3]] + '\n'
            else:
                code = 1
        elif args == ('shell', 'pm', 'list', 'permissions', '-f'):
            output = PM_PERMISSIONS
        elif args == ('shell', '/debug_ramdisk/magisk', '-v'):
            output = '30.7:MAGISK:R (30700)\n'
        elif args[0] == 'pull':
            Path(args[2]).write_bytes(b'mock-apk')
        elif args[0] == 'install':
            self.packages[microg.SPOOF_PACKAGE] = '/data/app/compat/base.apk'
        elif args[:2] == ('shell', 'cat'):
            name = args[2].split('/')[-2]
            if name in self.modules:
                output = 'id=' + name + '\n'
            else:
                code = 1
        elif args[:3] == ('shell', 'test', '-e'):
            code = 1
        elif len(args) > 2 and args[2] == '--sqlite':
            if args[3].startswith('INSERT'):
                self.zygisk = 1
            else:
                output = f'value={self.zygisk}\n'
        elif len(args) > 2 and args[2] == '--install-module':
            self.modules.add(microg.VECTOR_ID if args[3].endswith('vector.zip') else microg.MODULE_ID)
        elif args[:2] == ('shell', '/system/bin/app_process'):
            self.assert_classpath(args)
            if args[4].endswith('.SignatureProbe'):
                output = json.dumps(self.probe)
                code = 0 if self.probe['ok'] else 1
            else:
                command = args[6:]
                if command == ('modules', 'enable', microg.SPOOF_PACKAGE):
                    data = {'Enabled': [microg.SPOOF_PACKAGE], 'Failed': self.enable_failed}
                elif command == ('modules', 'ls'):
                    data = [{'PACKAGE': microg.SPOOF_PACKAGE, 'UID': 10123, 'STATUS': self.module_status}]
                elif command == ('scope', 'ls', microg.SPOOF_PACKAGE):
                    data = self.scope
                elif command == ('scope', 'set', microg.SPOOF_PACKAGE, 'system/0'):
                    data = 'Successfully overwrote scope for module (1 apps).'
                elif command == ('status',):
                    data = {'Framework Version': '2.2', 'Enabled Modules': 1}
                else:
                    raise AssertionError(command)
                output = json.dumps({'success': True, 'data': data})
        return subprocess.CompletedProcess(args, code, output, '')

    @staticmethod
    def assert_classpath(args):
        if not args[2].startswith('-Djava.class.path='):
            raise AssertionError('app_process must use an explicit classpath')


def make_assets(root):
    result = {}
    for package in (*microg.APK_MODULE_DIRS, microg.SPOOF_PACKAGE):
        path = root / (package + '.apk')
        path.write_bytes(package.encode())
        result[package] = {'path': path, 'sha256': microg.core.digest(path), 'info': {
            'app_package': package, 'signer_sha256': 'a' * 64, 'version_code': 123,
            'permissions': ['android.permission.UPDATE_APP_OPS_STATS', 'android.permission.INTERNET']}}
    return result


class PermissionTests(unittest.TestCase):
    def test_actual_aapt_formats_and_uses_permission_tags(self):
        body = "uses-permission: name='android.permission.INTERNET'\nuses-permission-sdk-23: name='android.permission.READ_PHONE_STATE'\n"
        for package in ["package: com.google.android.gms\n", "package: name='com.google.android.gms'\n"]:
            self.assertEqual(microg.parse_apk_permissions(package + body), ('com.google.android.gms', {
                'android.permission.INTERNET', 'android.permission.READ_PHONE_STATE'}))

    def test_guest_protection_levels_include_only_privileged(self):
        self.assertEqual(microg.parse_privileged_permissions(PM_PERMISSIONS), {
            'android.permission.READ_PRIVILEGED_PHONE_STATE',
            'android.permission.UPDATE_APP_OPS_STATS', 'android.permission.MANAGE_USERS'})

    def test_invalid_guest_permission_output_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'refusing to grant privileges'):
            microg.parse_privileged_permissions('Permission database unavailable')

    def test_module_grants_only_requested_platform_privileges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apks = make_assets(root)
            module = root / 'module.zip'
            allowed = microg.make_module(apks, microg.parse_privileged_permissions(PM_PERMISSIONS), module)
            self.assertEqual(set(allowed), set(microg.APK_MODULE_DIRS))
            with zipfile.ZipFile(module) as archive:
                permission_xml = ET.fromstring(archive.read('system/etc/permissions/privapp-permissions-mac-microg.xml'))
                self.assertEqual({node.attrib['package'] for node in permission_xml}, set(microg.APK_MODULE_DIRS))
                self.assertEqual({child.attrib['name'] for node in permission_xml for child in node},
                                 {'android.permission.UPDATE_APP_OPS_STATS'})
                self.assertEqual(len([name for name in archive.namelist() if name.endswith('.apk')]), 3)
                self.assertFalse(any('DroidGuard' in name for name in archive.namelist()))
                self.assertEqual(microg.parse_properties(archive.read('module.prop').decode())['id'], microg.MODULE_ID)


class ProvisionTests(unittest.TestCase):
    def test_rejects_google_image_before_loading_or_starting_guest(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = FakeController(directory)
            controller.image_tag = 'google_apis'
            with mock.patch.object(microg.subsystem, 'Controller', return_value=controller), mock.patch.object(
                    microg, 'load_assets') as load:
                with self.assertRaisesRegex(RuntimeError, 'pure AOSP'):
                    microg.provision(Path(directory), Path(directory))
                load.assert_not_called()
            self.assertEqual(controller.boot_count, 0)

    def test_vector_success_with_failed_packages_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = FakeController(directory)
            controller.enable_failed = [microg.SPOOF_PACKAGE]
            with self.assertRaisesRegex(RuntimeError, 'Vector rejected modules'):
                microg.vector_cli(controller, 'modules', 'enable', microg.SPOOF_PACKAGE)

    def test_disabled_or_wrong_scope_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = FakeController(directory)
            controller.modules = {microg.MODULE_ID, microg.VECTOR_ID}
            controller.module_status = 'disabled'
            with self.assertRaisesRegex(RuntimeError, 'not enabled'):
                microg.verify_vector(controller)
            controller.module_status = 'enabled'
            controller.scope = [{'APP_PACKAGE': 'system', 'USER_ID': 10}]
            with self.assertRaisesRegex(RuntimeError, 'expected only system/0'):
                microg.verify_vector(controller)

    def test_conflicting_proprietary_signer_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = FakeController(root)
            package = 'com.google.android.gms'
            controller.packages[package] = '/system/priv-app/PrebuiltGmsCore/base.apk'
            expected = make_assets(root)[package]
            with mock.patch.object(microg, 'apk_info', return_value={
                    'app_package': package, 'signer_sha256': 'b' * 64, 'version_code': 123}):
                with self.assertRaisesRegex(RuntimeError, 'proprietary Google packages cannot be mixed'):
                    microg.check_installed_apk(controller, package, expected, root)

    def test_signature_probe_requires_all_checks_and_both_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = FakeController(directory)
            controller.packages[microg.SPOOF_PACKAGE] = '/data/app/compat/base.apk'
            controller.probe['packages'][0]['wrong_certificate_rejected'] = False
            with self.assertRaisesRegex(RuntimeError, 'Actual Android signature compatibility checks failed'):
                microg.signature_probe(controller)
            controller.probe = good_probe()
            controller.probe['packages'].pop()
            with self.assertRaises(RuntimeError):
                microg.signature_probe(controller)
            controller.probe = good_probe()
            self.assertTrue(microg.signature_probe(controller)['signature_checked'])

    def test_full_flow_reboots_and_only_then_reports_real_signature_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = FakeController(root)
            apks = make_assets(root)
            vector = root / 'vector.zip'
            vector.write_bytes(b'mock-vector')
            def info(_, path):
                return apks[path.stem]['info']
            with mock.patch.object(microg.subsystem, 'Controller', return_value=controller), mock.patch.object(
                    microg, 'load_assets', return_value=(apks, vector)), mock.patch.object(
                    microg, 'apk_info', side_effect=info), mock.patch.object(
                    microg.core, 'verify', return_value={'magisk': '30.7'}), mock.patch.object(
                    microg.core, 'adb_root'), mock.patch.object(microg.core, 'wait_device'):
                report = microg.provision(root, root)
            self.assertEqual(controller.boot_count, 3)
            self.assertEqual(controller.zygisk, 1)
            self.assertTrue(report['signature_checked'])
            self.assertTrue(report['m5_self_check_required'])
            self.assertFalse(report['google_login_configured'])
            self.assertFalse(report['device_registration_enabled_by_installer'])
            self.assertFalse(report['push_enabled_by_installer'])
            self.assertEqual(set(report['installed']), {*microg.APK_MODULE_DIRS, microg.SPOOF_PACKAGE})
            self.assertEqual(json.loads((root / 'microg-report.json').read_text()), report)
            self.assertFalse(any(args[0] == 'shell' and ('rm' in args or 'pm' in args and 'uninstall' in args)
                                 for args in controller.calls if args))
            self.assertEqual(controller.calls[-1], ('unroot',))

    def test_failed_signature_probe_is_saved_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = FakeController(root)
            controller.modules = {microg.MODULE_ID, microg.VECTOR_ID}
            apks = make_assets(root)
            controller.packages = {package: '/data/app/mock/base.apk' for package in apks}
            controller.probe['packages'][0]['modern_valid'] = False
            with mock.patch.object(microg, 'apk_info', side_effect=lambda _, path: apks[path.stem]['info']), mock.patch.object(
                    microg.core, 'verify', return_value={'magisk': '30.7'}), mock.patch.object(
                    microg.core, 'adb_root'), mock.patch.object(microg.core, 'wait_device'):
                with self.assertRaisesRegex(RuntimeError, 'Actual Android signature compatibility'):
                    microg.verify(controller, apks)
            report = json.loads((root / 'microg-report.json').read_text())
            self.assertFalse(report['signature_checked'])
            self.assertEqual(report['signature_check']['status'], 'failed')
            self.assertEqual(controller.calls[-1], ('unroot',))

    def test_pinned_paths_cannot_escape_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'Unsafe pinned asset path'):
                microg.pinned_path(root, '../outside.apk')
            (root / 'link').symlink_to(root.parent)
            with self.assertRaisesRegex(RuntimeError, 'leaves its cache'):
                microg.pinned_path(root, 'link/outside.apk')


if __name__ == '__main__': unittest.main()

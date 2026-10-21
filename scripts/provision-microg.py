#!/usr/bin/env python3
"""Install pinned microG into this project's pure AOSP Android 16 AVD.

No Google proprietary payload, account login, device registration, or push opt-in
is performed. Package installation, framework configuration, and actual signature
hook checks are reported separately.
"""
from __future__ import annotations
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('magisk_provision', PROJECT / 'scripts/provision-mac.py')
core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)
subsystem = core.subsystem
MODULE_ID = 'mac_microg_api36'
SPOOF_PACKAGE = 'dev.dan.androidsubsystem.microgspoof'
VECTOR_ID = 'zygisk_vector'
VECTOR_DAEMON = f'/data/adb/modules/{VECTOR_ID}/daemon.apk'
VECTOR_CLI = 'org.matrix.vector.daemon.Cli'
APK_KINDS = {'microg_services': 'com.google.android.gms',
             'microg_companion': 'com.android.vending'}
LOCAL_APKS = {'GSFProxy.apk': 'com.google.android.gsf',
              'MicroGSignatureCompat.apk': SPOOF_PACKAGE}
APK_MODULE_DIRS = {'com.google.android.gms': 'MicroGServices',
                   'com.android.vending': 'MicroGCompanion',
                   'com.google.android.gsf': 'MicroGGSFProxy'}
PERMISSION = re.compile(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+\Z')
HEX256 = re.compile(r'[0-9a-fA-F]{64}\Z')


def require_aosp(controller):
    if controller.config['android'] != 16 or controller.image_tag != 'default':
        raise RuntimeError('microG requires the separate pure AOSP Android 16 default image; migrate first')


def parse_apk_permissions(output):
    package = re.search(r"^package:\s*(?:name=)?'?([A-Za-z][A-Za-z0-9_.]+)'?(?:\s|$)", output, re.MULTILINE)
    if not package or not subsystem.PACKAGE.fullmatch(package.group(1)):
        raise RuntimeError('aapt2 returned no valid APK package name')
    permissions = set(re.findall(r"^uses-permission(?:-sdk-\d+)?:\s+name='([^']+)'", output, re.MULTILINE))
    if any(not PERMISSION.fullmatch(permission) for permission in permissions):
        raise RuntimeError('aapt2 returned an invalid APK permission name')
    return package.group(1), permissions


def parse_privileged_permissions(output):
    """Use the running AOSP permission definitions, not a blanket allowlist."""
    definitions = {}
    name = None
    for line in output.splitlines():
        match = re.fullmatch(r'\s*permission:\s*([A-Za-z0-9_.]+)\s*', line)
        if match:
            name = match.group(1)
            if not PERMISSION.fullmatch(name):
                raise RuntimeError('Guest returned an invalid permission name')
        else:
            protection = re.fullmatch(r'\s*protectionLevel:\s*([^\s]+)\s*', line)
            if protection and name:
                definitions[name] = protection.group(1).split('|')
                name = None
    if 'android.permission.READ_PRIVILEGED_PHONE_STATE' not in definitions:
        raise RuntimeError('Could not read AOSP permission definitions; refusing to grant privileges')
    return {name for name, flags in definitions.items() if 'privileged' in flags}


def sdk_build_tool(controller, name):
    path = controller.sdk / 'build-tools/36.0.0' / name
    if not path.is_file():
        raise RuntimeError(f'Missing pinned Android build tool: {name}')
    return str(path)


def apk_info(controller, path):
    package, permissions = parse_apk_permissions(controller.run(
        [sdk_build_tool(controller, 'aapt2'), 'dump', 'permissions', str(path)], timeout=60).stdout)
    badging = controller.run([sdk_build_tool(controller, 'aapt2'), 'dump', 'badging', str(path)], timeout=60).stdout
    version = re.search(r"^package:.*?versionCode='(\d+)'", badging, re.MULTILINE)
    if not version:
        raise RuntimeError(f'No APK version code: {path.name}')
    certificates = controller.run([sdk_build_tool(controller, 'apksigner'), 'verify', '--print-certs', str(path)],
                                  timeout=60).stdout
    digests = re.findall(r'^Signer #\d+ certificate SHA-256 digest:\s*([0-9a-fA-F]{64})\s*$',
                         certificates, re.MULTILINE)
    if len(digests) != 1:
        raise RuntimeError(f'Expected one verified APK signer: {path.name}')
    return {'app_package': package, 'permissions': sorted(permissions),
            'signer_sha256': digests[0].lower(), 'version_code': int(version.group(1))}


def check_pin(path, entry):
    checksum = entry.get('sha256')
    if not isinstance(checksum, str) or not HEX256.fullmatch(checksum):
        raise RuntimeError(f'Missing locked SHA256: {path.name}')
    if not path.is_file() or core.digest(path) != checksum.lower():
        raise RuntimeError(f'Invalid pinned microG asset: {path.name}')


def pinned_path(base, relative):
    relative = PurePosixPath(relative)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise RuntimeError('Unsafe pinned asset path')
    path = base / str(relative)
    if not path.resolve().is_relative_to(base.resolve()):
        raise RuntimeError('Pinned asset leaves its cache directory')
    return path


def load_assets(cache, controller):
    lock = json.loads((PROJECT / 'scripts/runtime-lock.json').read_text())
    entries = {entry['kind']: entry for entry in lock['archives']
               if entry.get('kind') in {*APK_KINDS, 'vector'}}
    if set(entries) != {*APK_KINDS, 'vector'}:
        raise RuntimeError('Pinned microG Services, Companion, and Vector assets are required')
    apks = {}
    for kind, expected_package in APK_KINDS.items():
        entry = entries[kind]
        path = pinned_path(cache, entry['relative_path'])
        check_pin(path, entry)
        info = apk_info(controller, path)
        if entry.get('app_package') != expected_package or info['app_package'] != expected_package:
            raise RuntimeError(f'Unexpected APK package for {kind}')
        if info['signer_sha256'] != str(entry.get('signer_sha256', '')).lower():
            raise RuntimeError(f'Unexpected official microG signer: {path.name}')
        apks[expected_package] = {'path': path, 'info': info, 'sha256': entry['sha256'].lower()}
    local = json.loads((PROJECT / 'artifacts/microg-tools.json').read_text())
    for name, expected_package in LOCAL_APKS.items():
        matches = [entry for entry in local['artifacts'] if entry.get('name') == name]
        if len(matches) != 1:
            raise RuntimeError(f'Missing local artifact pin: {name}')
        entry = matches[0]
        path = PROJECT / 'artifacts' / name
        check_pin(path, entry)
        info = apk_info(controller, path)
        if entry.get('app_package') != expected_package or info['app_package'] != expected_package:
            raise RuntimeError(f'Unexpected local compatibility APK package: {name}')
        if info['signer_sha256'] != str(entry.get('signer_sha256', '')).lower():
            raise RuntimeError(f'Unexpected local artifact signer: {name}')
        apks[expected_package] = {'path': path, 'info': info, 'sha256': entry['sha256'].lower()}
    vector = pinned_path(cache, entries['vector']['relative_path'])
    check_pin(vector, entries['vector'])
    with zipfile.ZipFile(vector) as archive:
        props = parse_properties(archive.read('module.prop').decode())
        if props.get('id') != VECTOR_ID:
            raise RuntimeError('Pinned Vector archive has an unexpected module id')
    return apks, vector


def expected_signers():
    """Verification does not require keeping the downloaded APK archives."""
    lock = json.loads((PROJECT / 'scripts/runtime-lock.json').read_text())
    local = json.loads((PROJECT / 'artifacts/microg-tools.json').read_text())
    result = {}
    for kind, package in APK_KINDS.items():
        matches = [entry for entry in lock['archives'] if entry.get('kind') == kind and
                   entry.get('app_package') == package]
        if len(matches) != 1 or not HEX256.fullmatch(str(matches[0].get('signer_sha256', ''))):
            raise RuntimeError(f'Missing official signer pin: {package}')
        result[package] = {'info': {'signer_sha256': matches[0]['signer_sha256'].lower()}}
    for name, package in LOCAL_APKS.items():
        matches = [entry for entry in local['artifacts'] if entry.get('name') == name and
                   entry.get('app_package') == package]
        if len(matches) != 1 or not HEX256.fullmatch(str(matches[0].get('signer_sha256', ''))):
            raise RuntimeError(f'Missing local signer pin: {package}')
        result[package] = {'info': {'signer_sha256': matches[0]['signer_sha256'].lower()}}
    return result


def parse_properties(text):
    return dict(line.split('=', 1) for line in text.splitlines()
                if '=' in line and not line.lstrip().startswith('#'))


def make_module(apks, privileged, target):
    permissions = ET.Element('permissions')
    allowed = {}
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for package, directory in APK_MODULE_DIRS.items():
            asset = apks[package]
            grant = sorted(set(asset['info']['permissions']) & privileged)
            allowed[package] = grant
            element = ET.SubElement(permissions, 'privapp-permissions', {'package': package})
            for permission in grant:
                ET.SubElement(element, 'permission', {'name': permission})
            archive.write(asset['path'], f'system/priv-app/{directory}/{directory}.apk')
        archive.writestr('system/etc/permissions/privapp-permissions-mac-microg.xml',
                         ET.tostring(permissions, encoding='utf-8', xml_declaration=True))
        archive.writestr('module.prop', f'id={MODULE_ID}\nname=Mac Android 16 microG\nversion=0.1\n'
                         'versionCode=1\nauthor=Android Subsystem\n'
                         'description=Open-source microG Services, Companion, and GSFProxy for the private AOSP runtime\n')
        archive.writestr('customize.sh', 'SKIPUNZIP=0\nset_perm_recursive "$MODPATH/system" 0 0 0755 0644\n')
    return allowed


def package_paths(controller, package, required=False):
    result = controller.adb('shell', 'pm', 'path', package, check=False)
    paths = [line.removeprefix('package:') for line in result.stdout.splitlines() if line.startswith('package:')]
    if required and (result.returncode or not paths):
        raise RuntimeError(f'Missing installed package: {package}')
    if any(not path.startswith(('/system/', '/product/', '/system_ext/', '/data/app/')) or
           '\n' in path or '..' in PurePosixPath(path).parts for path in paths):
        raise RuntimeError(f'Unsafe installed APK path: {package}')
    return paths


def check_installed_apk(controller, package, expected, directory):
    paths = package_paths(controller, package)
    if not paths:
        return None
    if len(paths) != 1:
        raise RuntimeError(f'Refusing to replace a split APK package: {package}')
    pulled = directory / (package + '.apk')
    controller.adb('pull', paths[0], str(pulled), timeout=120)
    info = apk_info(controller, pulled)
    if info['app_package'] != package or info['signer_sha256'] != expected['info']['signer_sha256']:
        raise RuntimeError(f'Conflicting package {package}; proprietary Google packages cannot be mixed with microG')
    return {'paths': paths, 'signer_sha256': info['signer_sha256'], 'version_code': info['version_code']}


def configure_zygisk(controller, binary):
    # Magisk v30.7 native/src/core/sqlite.cpp and db.rs define this schema/key.
    controller.adb('shell', binary, '--sqlite',
                   "INSERT OR REPLACE INTO settings (key,value) VALUES('zygisk',1)")
    output = controller.adb('shell', binary, '--sqlite', "SELECT value FROM settings WHERE key='zygisk'").stdout
    if output.strip() != 'value=1':
        raise RuntimeError('Magisk did not persist Zygisk=1')


def vector_cli(controller, *args):
    result = controller.adb('shell', '/system/bin/app_process', f'-Djava.class.path={VECTOR_DAEMON}',
                            '/system/bin', VECTOR_CLI, '--json', *args, timeout=30, check=False)
    try:
        response = json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError(f'Vector CLI did not return JSON: {(result.stderr or result.stdout)[-1000:]}') from error
    if result.returncode or not isinstance(response, dict) or response.get('success') is not True:
        raise RuntimeError(f'Vector CLI failed: {response.get("error", response) if isinstance(response, dict) else response}')
    data = response.get('data')
    if isinstance(data, dict) and data.get('Failed'):
        raise RuntimeError(f'Vector rejected modules: {data["Failed"]}')
    return data


def wait_vector(controller, limit=90):
    deadline = time.monotonic() + limit
    last_error = None
    while time.monotonic() < deadline:
        try:
            return vector_cli(controller, 'status')
        except RuntimeError as error:
            last_error = error
            time.sleep(1)
    raise RuntimeError(f'Vector daemon did not become ready: {last_error}')


def module_enabled(controller, module):
    directory = f'/data/adb/modules/{module}'
    result = controller.adb('shell', 'cat', directory + '/module.prop', check=False)
    if result.returncode or parse_properties(result.stdout).get('id') != module:
        raise RuntimeError(f'Magisk module is missing after reboot: {module}')
    for marker in ('disable', 'remove'):
        if controller.adb('shell', 'test', '-e', directory + '/' + marker, check=False).returncode == 0:
            raise RuntimeError(f'Magisk module has a {marker} marker: {module}')
    return True


def verify_vector(controller):
    modules = vector_cli(controller, 'modules', 'ls')
    if not isinstance(modules, list):
        raise RuntimeError('Invalid Vector module list')
    matches = [row for row in modules if isinstance(row, dict) and row.get('PACKAGE') == SPOOF_PACKAGE]
    if len(matches) != 1 or matches[0].get('STATUS') != 'enabled':
        raise RuntimeError('Signature compatibility module is not enabled in Vector')
    scope = vector_cli(controller, 'scope', 'ls', SPOOF_PACKAGE)
    if not isinstance(scope, list) or len(scope) != 1 or scope[0] != {'APP_PACKAGE': 'system', 'USER_ID': 0}:
        raise RuntimeError(f'Unexpected signature compatibility scope: {scope}; expected only system/0')
    return {'magisk_microg': module_enabled(controller, MODULE_ID),
            'magisk_vector': module_enabled(controller, VECTOR_ID),
            'vector_module_enabled': True, 'vector_scope': scope}


def cold_boot(controller):
    root = controller.root
    controller.stop()
    fresh = subsystem.Controller(root)
    require_aosp(fresh)
    fresh.boot()
    core.adb_root(fresh)
    return fresh


def signature_probe(controller):
    paths = package_paths(controller, SPOOF_PACKAGE, required=True)
    if len(paths) != 1:
        raise RuntimeError('Signature compatibility probe requires its single installed APK')
    result = controller.adb('shell', '/system/bin/app_process', f'-Djava.class.path={paths[0]}',
                            '/system/bin', SPOOF_PACKAGE + '.SignatureProbe', timeout=60, check=False)
    try:
        report = json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError(f'Signature probe returned no JSON: {(result.stderr or result.stdout)[-1000:]}') from error
    if not isinstance(report, dict):
        raise RuntimeError('Signature probe returned an invalid report')
    expected = set(APK_KINDS.values())
    rows = report.get('packages')
    checks = ('legacy_valid', 'modern_valid', 'raw_certificate_valid',
              'digest_certificate_valid', 'wrong_certificate_rejected')
    if (result.returncode or report.get('ok') is not True or report.get('signature_checked') is not True or
            not isinstance(rows, list) or len(rows) != len(expected) or
            {row.get('package') for row in rows if isinstance(row, dict)} != expected or
            any(not isinstance(row, dict) or any(row.get(key) is not True for key in checks) for row in rows)):
        raise RuntimeError(f'Actual Android signature compatibility checks failed: {report}')
    return report


def verify(controller, apks=None):
    require_aosp(controller)
    apks = expected_signers() if apks is None else apks
    magisk_report = core.verify(controller)
    core.adb_root(controller)
    try:
        wait_vector(controller)
        modules = verify_vector(controller)
        packages = {}
        folder = controller.root / 'provision-work/microg-installed'
        folder.mkdir(parents=True, exist_ok=True)
        for package in (*APK_MODULE_DIRS, SPOOF_PACKAGE):
            installed = check_installed_apk(controller, package, apks[package], folder)
            if not installed:
                raise RuntimeError(f'Missing installed microG package: {package}')
            packages[package] = installed
        report = {'android': 16, 'api': 36, 'image_tag': controller.image_tag,
                  'magisk': magisk_report['magisk'], 'installed': packages,
                  'modules_verified': modules, 'signature_checked': False,
                  'signature_check': {'status': 'not_run'}, 'm5_self_check_required': True,
                  'google_login_configured': False, 'device_registration_enabled_by_installer': False,
                  'push_enabled_by_installer': False}
        try:
            report['signature_check'] = signature_probe(controller)
            report['signature_checked'] = True
        except RuntimeError as error:
            report['signature_check'] = {'status': 'failed', 'error': str(error)}
            subsystem.atomic_json(controller.root / 'microg-report.json', report)
            raise
        return report
    finally:
        controller.adb('unroot', check=False)
        core.wait_device(controller)


def provision(cache, root=None):
    controller = subsystem.Controller(root)
    require_aosp(controller)
    apks, vector = load_assets(cache.resolve(), controller)
    workspace = controller.root / 'provision-work'
    workspace.mkdir(exist_ok=True)
    controller.boot()
    core.verify(controller)
    core.adb_root(controller)
    try:
        for package, asset in apks.items():
            check_installed_apk(controller, package, asset, workspace)
        privileged = parse_privileged_permissions(controller.adb('shell', 'pm', 'list', 'permissions', '-f').stdout)
        module = workspace / 'MacMicroG16.zip'
        granted = make_module(apks, privileged, module)
        binary, _ = core.magisk_binary(controller)
        configure_zygisk(controller, binary)
        # Only our private runtime and these exact new temporary names are touched.
        for source, guest in [(vector, '/data/local/tmp/mac_subsystem_vector.zip'),
                              (module, '/data/local/tmp/mac_subsystem_microg.zip')]:
            controller.adb('push', str(source), guest, timeout=120)
            controller.adb('shell', binary, '--install-module', guest, timeout=240)
        controller.adb('install', '-r', str(apks[SPOOF_PACKAGE]['path']), timeout=120)
        controller = cold_boot(controller)
        wait_vector(controller)
        enabled = vector_cli(controller, 'modules', 'enable', SPOOF_PACKAGE)
        if not isinstance(enabled, dict) or enabled.get('Enabled') != [SPOOF_PACKAGE] or enabled.get('Failed') != []:
            raise RuntimeError(f'Vector did not confirm module activation: {enabled}')
        vector_cli(controller, 'scope', 'set', SPOOF_PACKAGE, 'system/0')
        verify_vector(controller)
        controller = cold_boot(controller)
        report = verify(controller, apks)
        report['privileged_permissions'] = granted
        subsystem.atomic_json(controller.root / 'microg-report.json', report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print('microG 安装、模块配置及 Android 签名兼容检查完成。microG 界面自检和应用运行仍需在 M5 上确认。')
        return report
    finally:
        controller.adb('unroot', check=False)
        core.wait_device(controller)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cache', type=Path, nargs='?')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    controller = subsystem.Controller(args.root)
    with (controller.root / 'provision.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.verify_only:
            controller.boot()
            apks = load_assets(args.cache.resolve(), controller)[0] if args.cache else None
            report = verify(controller, apks)
            subsystem.atomic_json(controller.root / 'microg-report.json', report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            if args.cache is None:
                parser.error('cache is required')
            provision(args.cache, args.root)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError, zipfile.BadZipFile, subsystem.SubsystemError) as error:
        print('microG 配置未完成：', error, file=sys.stderr)
        sys.exit(1)

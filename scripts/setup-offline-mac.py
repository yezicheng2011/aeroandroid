#!/usr/bin/env python3
"""Install locked runtime archives, without downloading software on the Mac."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
import xml.etree.ElementTree as ET
from xml.dom import minidom

PROJECT = Path(__file__).resolve().parents[1]
COMMON_NAMESPACE = 'http://schemas.android.com/repository/android/common/02'


def package_records(cache, lock):
    """Select the exact repository revision whose archive bytes are locked.

    A package path can appear more than once (stable and preview). Keeping the
    original DOM also preserves namespace prefixes used inside xsi:type values.
    """
    documents = {}
    records = []
    for entry in lock['archives']:
        if not entry.get('package'): continue
        catalog = 'images2-3.xml' if entry['package'].startswith('system-images;') else 'repository2-3.xml'
        if catalog not in documents:
            documents[catalog] = minidom.parse(str(cache / 'android16-macos' / catalog))
        document = documents[catalog]
        selected = None
        for package in document.getElementsByTagName('remotePackage'):
            if package.getAttribute('path') != entry['package']: continue
            for complete in package.getElementsByTagName('complete'):
                urls = complete.getElementsByTagName('url')
                checksums = complete.getElementsByTagName('checksum')
                url = ''.join(n.data for n in urls[0].childNodes if n.nodeType == n.TEXT_NODE).strip() if urls else ''
                checksum = ''.join(n.data for n in checksums[0].childNodes if n.nodeType == n.TEXT_NODE).strip() if checksums else ''
                if Path(url).name == entry['name'] and checksum == entry['sha1']:
                    selected = package; break
            if selected is not None: break
        if selected is None: raise RuntimeError('Locked SDK package is absent from offline metadata: ' + entry['name'])
        records.append((entry, document, selected))
    return records


def register_sdk_packages(records, destinations):
    """Raw Google ZIPs omit the local package.xml normally written by sdkmanager."""
    licenses = {}
    for entry, catalog, remote in records:
        document = minidom.Document()
        repository = document.createElementNS(COMMON_NAMESPACE, 'common:repository')
        document.appendChild(repository)
        for attribute in catalog.documentElement.attributes.values():
            if attribute.name == 'xmlns' or attribute.name.startswith('xmlns:'):
                repository.setAttribute(attribute.name, attribute.value)
        repository.setAttribute('xmlns:common', COMMON_NAMESPACE)
        local = document.createElement('localPackage')
        local.setAttribute('path', entry['package'])
        local.setAttribute('obsolete', 'false')
        for child in remote.childNodes:
            if child.nodeType == child.ELEMENT_NODE and child.tagName in ('type-details', 'revision', 'display-name', 'uses-license', 'dependencies'):
                local.appendChild(document.importNode(child, True))
        for reference in local.getElementsByTagName('uses-license'):
            license_id = reference.getAttribute('ref')
            node = next((n for n in catalog.getElementsByTagName('license') if n.getAttribute('id') == license_id), None)
            if node is None: raise RuntimeError('Missing SDK license in offline metadata: ' + license_id)
            repository.appendChild(document.importNode(node, True))
            text = ''.join(n.data for n in node.childNodes if n.nodeType in (n.TEXT_NODE, n.CDATA_SECTION_NODE)).strip()
            licenses[license_id] = text
        repository.appendChild(local)
        destination = destinations[entry['package']]
        if not destination.is_dir(): raise RuntimeError('SDK package directory is missing: ' + str(destination))
        pending = destination / 'package.xml.pending'
        pending.write_bytes(document.toxml(encoding='UTF-8'))
        pending.replace(destination / 'package.xml')
        print('登记 SDK 包：', entry['package'], flush=True)
    return licenses


def accept_sdk_licenses(licenses, sdk, root, accept=False):
    (sdk / 'licenses').mkdir(parents=True, exist_ok=True)
    for license_id, text in licenses.items():
        digest = hashlib.sha1(text.encode()).hexdigest()
        target = sdk / 'licenses' / license_id
        previous = target.read_text().splitlines() if target.exists() else []
        if digest in previous: continue
        saved = root / (license_id + '.txt')
        saved.write_text(text + '\n')
        if not accept:
            print('\nSDK 协议已保存到：', saved)
            print(text)
            if input('\n阅读后，是否接受该 SDK 协议？输入 YES 继续：').strip() != 'YES':
                raise RuntimeError('SDK license was not accepted; installation cancelled')
        target.write_text('\n'.join(previous + [digest]) + '\n')


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def extract_zip(source, destination):
    """SDK archives contain a top directory. Replace it with the package destination."""
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as z:
        tops = {Path(e.filename).parts[0] for e in z.infolist() if Path(e.filename).parts}
        if len(tops) != 1: raise RuntimeError(f'Unexpected SDK archive layout: {source.name}')
        for entry in z.infolist():
            parts = Path(entry.filename).parts[1:]
            if not parts: continue
            if '..' in parts or entry.filename.startswith('/'):
                raise RuntimeError('Unsafe ZIP path')
            target = destination.joinpath(*parts)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise RuntimeError('Unexpected symlink in SDK archive')
            if entry.is_dir(): target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(entry) as f, target.open('wb') as out: shutil.copyfileobj(f, out, 4 * 1024 * 1024)
                if mode: target.chmod(mode & 0o777)


def extract_tar(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source) as t: t.extractall(destination, filter='data')


def runtime_fingerprint(lock):
    core = {key: value for key, value in lock.items() if key != 'archives'}
    core['archives'] = [entry for entry in lock['archives'] if entry.get('package') or entry.get('kind') in ('python', 'jdk', 'scrcpy')]
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()


def runtime_installed(root, lock):
    marker = root / 'installed-runtime.json'
    previous = json.loads(marker.read_text()) if marker.exists() else {}
    fingerprint = runtime_fingerprint(lock)
    return (previous.get('fingerprint') == fingerprint and
            (root / 'sdk/emulator/emulator').exists() and (root / 'runtime/bin/scrcpy').exists())


def retire_legacy_google_image(root):
    """Remove only our obsolete Google SDK image after AOSP provisioning succeeds.

    The old AVD's application data remains available as an offline backup.
    Never follow a redirected SDK path outside this private installation.
    """
    root = root.resolve()
    legacy = root / 'sdk/system-images/android-36/google_apis/arm64-v8a'
    if not legacy.exists():
        return
    if legacy.is_symlink() or not legacy.resolve().is_relative_to(root):
        raise RuntimeError('Legacy SDK image path is redirected; refusing cleanup')
    shutil.rmtree(legacy)
    print('已移除旧 Google APIs 系统镜像；原安卓用户数据保留为离线备份。')


def install(cache, root, lock, accept_licenses=False, build=True, graphics_only=False):
    sdk = root / 'sdk'
    runtime = root / 'runtime'
    root.mkdir(parents=True, exist_ok=True)
    # Every path and digest is fixed in the shipped lockfile, not inferred from filenames.
    for entry in lock['archives']:
        archive = cache / entry['relative_path']
        if not archive.is_file(): raise RuntimeError(f'Missing runtime archive: {archive}')
        print('校验：', archive.name, flush=True)
        if sha256(archive) != entry['sha256']: raise RuntimeError(f'Checksum mismatch: {archive.name}')
    metadata = ET.parse(cache / 'android16-macos/repository2-3.xml').getroot()
    license_node = next(x for x in metadata.findall('license') if x.get('id') == 'android-sdk-license')
    license_text = license_node.text.strip()
    license_file = root / 'ANDROID-SDK-LICENSE.txt'
    license_file.write_text(license_text + '\n')
    accepted = sdk / 'licenses/android-sdk-license'
    license_digest = hashlib.sha1(license_text.encode()).hexdigest()
    previously_accepted = accepted.exists() and license_digest in accepted.read_text().splitlines()
    if not accept_licenses and not previously_accepted:
        print('\nAndroid SDK 协议已保存到：', license_file)
        print(license_text)
        if input('\n阅读后，是否接受该 SDK 协议？输入 YES 继续：').strip() != 'YES':
            raise RuntimeError('SDK license was not accepted; installation cancelled')
    (sdk / 'licenses').mkdir(parents=True, exist_ok=True)
    if not previously_accepted: accepted.write_text(license_digest + '\n')
    destinations = {
        'platforms;android-36': sdk / 'platforms/android-36',
        'build-tools;36.0.0': sdk / 'build-tools/36.0.0',
        'cmdline-tools;latest': sdk / 'cmdline-tools/latest',
        'platform-tools': sdk / 'platform-tools',
        'emulator': sdk / 'emulator',
        'system-images;android-36;default;arm64-v8a': sdk / 'system-images/android-36/default/arm64-v8a'
    }
    marker = root / 'installed-runtime.json'
    fingerprint = runtime_fingerprint(lock)
    already = runtime_installed(root, lock)
    if not already:
        # Do not overwrite a running VM's dependencies.
        controller = PROJECT / 'backend/subsystem.py'
        check = subprocess.run([sys.executable, str(controller), 'status', '--root', str(root)], capture_output=True, text=True)
        status = json.loads(check.stdout)
        if status.get('data', {}).get('state') in ['running', 'booting'] or status.get('data', {}).get('runtime_process_active'):
            raise RuntimeError('Stop the existing Android subsystem before installing runtime dependencies')
        for entry in lock['archives']:
            archive = cache / entry['relative_path']
            print('安装：', archive.name, flush=True)
            if entry.get('package'):
                extract_zip(archive, destinations[entry['package']])
            elif entry['kind'] == 'python':
                # Install.command has already bootstrapped this exact Python.
                if not (runtime / 'python/bin/python3').exists(): extract_tar(archive, runtime)
            elif entry['kind'] == 'jdk': extract_tar(archive, runtime / 'java')
            elif entry['kind'] == 'scrcpy': extract_tar(archive, runtime / 'scrcpy')
        (runtime / 'bin').mkdir(parents=True, exist_ok=True)
        scrcpy = next(p for p in (runtime / 'scrcpy').rglob('scrcpy') if p.is_file())
        link = runtime / 'bin/scrcpy'
        link.unlink(missing_ok=True); link.symlink_to(scrcpy)
    # Repair the installation record even when the previous binary-install marker
    # matches. Existing users keep their SDK files, AVDs, applications and userdata.
    licenses = register_sdk_packages(package_records(cache, lock), destinations)
    accept_sdk_licenses(licenses, sdk, root, accept_licenses)
    marker.write_text(json.dumps({'fingerprint': fingerprint}, indent=2))
    java_home = next((runtime / 'java').glob('*/Contents/Home'))
    config_path = root / 'config.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if config.get('image_tag') != 'default':
        config.pop('magisk_ramdisk', None)
    config.update({'android': 16, 'image_tag': 'default', 'sdk': str(sdk), 'java_home': str(java_home)})
    config_path.write_text(json.dumps(config, indent=2))
    config_path.chmod(0o600)
    env = {**os.environ, 'JAVA_HOME': str(java_home), 'ANDROID_SUBSYSTEM_SDK': str(sdk),
           'ANDROID_SUBSYSTEM_HOME': str(root), 'PYTHON': sys.executable,
           'PATH': str(runtime / 'python/bin') + ':' + str(runtime / 'bin') + ':' + str(java_home / 'bin') + ':' + os.environ.get('PATH', '')}
    subprocess.run([sys.executable, str(PROJECT / 'backend/subsystem.py'), 'create'], env=env, check=True)
    # Full provisioning adds persistent Magisk root to this private runtime.
    if build:
        subprocess.run(['/bin/bash', str(PROJECT / 'scripts/build-mac.sh')], env=env, check=True)
        if not graphics_only:
            subprocess.run([sys.executable, str(PROJECT / 'scripts/provision-mac.py'), str(cache)], env=env, check=True)
            subprocess.run([sys.executable, str(PROJECT / 'scripts/provision-microg.py'), str(cache)], env=env, check=True)
            retire_legacy_google_image(root)
        app_folder = Path.home() / 'Applications'
        app_folder.mkdir(exist_ok=True)
        built = PROJECT / 'dist/Android Subsystem.app'
        target = app_folder / built.name
        if target.exists():
            print('已有安装版本，更新前请退出管理应用。')
            backup = app_folder / 'Android Subsystem.previous.app'
            if backup.exists(): shutil.rmtree(backup)
            target.rename(backup)
        shutil.copytree(built, target, symlinks=True)
        subprocess.run(['/usr/bin/open', str(target)], check=True)
        print('安装完成：', target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cache', type=Path)
    parser.add_argument('--root', type=Path, default=Path.home() / 'Library/Application Support/AndroidSubsystem')
    parser.add_argument('--accept-sdk-license', action='store_true')
    parser.add_argument('--graphics-only', action='store_true', help='Install for graphics acceptance before Magisk root provisioning')
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64': raise RuntimeError('Requires an Apple Silicon Mac')
    lock = json.loads((PROJECT / 'scripts/runtime-lock.json').read_text())
    # A retry with existing dependencies needs space for compilation, not another
    # full SDK extraction. Full provisioning also needs room for Guest userdata.
    required_gb = (2 if args.graphics_only else 12) if runtime_installed(args.root, lock) else 20
    if shutil.disk_usage(args.root.parent if args.root.parent.exists() else Path.home()).free < required_gb * 1024**3:
        raise RuntimeError(f'At least {required_gb} GB free disk space is required for this installation stage')
    subprocess.run(['/usr/bin/xcrun', '--find', 'swift'], check=True, stdout=subprocess.DEVNULL)
    install(args.cache.resolve(), args.root.resolve(), lock, args.accept_sdk_license, graphics_only=args.graphics_only)


if __name__ == '__main__':
    try: main()
    except (RuntimeError, OSError, subprocess.CalledProcessError, StopIteration) as e:
        print('安装未完成：', e, file=sys.stderr); sys.exit(1)

#!/usr/bin/env python3
"""Provision this project's AVD with persistent Magisk.

The patched boot image is private to this runtime. Real API 36 ARM64 boot and
Magisk behavior must be accepted on the user's Mac.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('subsystem', PROJECT / 'backend/subsystem.py')
subsystem = importlib.util.module_from_spec(spec); spec.loader.exec_module(subsystem)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def wait_device(controller, limit=90):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        try:
            if controller.device(): return
        except subsystem.SubsystemError: pass
        time.sleep(1)
    raise RuntimeError('ADB did not reconnect')


def adb_root(controller):
    # Only the AVD identified and owned by this project is eligible.
    controller.ready()
    response = controller.adb('root')
    if 'cannot run as root' in response.stdout: raise RuntimeError('This image does not support adb root')
    wait_device(controller)
    if controller.adb('shell', 'id', '-u').stdout.strip() != '0': raise RuntimeError('Guest adb root failed')


def magisk_binary(controller):
    for path in ['/debug_ramdisk/magisk', '/sbin/magisk']:
        result = controller.adb('shell', path, '-v', check=False)
        if result.returncode == 0 and result.stdout.strip(): return path, result.stdout.strip()
    raise RuntimeError('Persistent Magisk was not active after cold boot; inspect emulator.log')


def verify(controller):
    controller.ready()
    adb_root(controller)
    try:
        binary, version = magisk_binary(controller)
        uid = controller.adb('shell', binary, 'su', '-c', 'id', check=False)
        # Magisk uses the same executable for applets; su is normally a symlink.
        if uid.returncode or 'uid=0' not in uid.stdout:
            uid = controller.adb('shell', 'su', '-c', 'id')
        if 'uid=0' not in uid.stdout: raise RuntimeError('Magisk su did not return uid=0')
        packages = {}
        for package in ['com.topjohnwu.magisk']:
            paths = controller.adb('shell', 'pm', 'path', package).stdout.strip()
            if not paths.startswith('package:'): raise RuntimeError(f'Missing required package: {package}')
            packages[package] = paths.splitlines()
        return {'api': controller.api, 'abi': controller.adb('shell', 'getprop', 'ro.product.cpu.abi').stdout.strip(),
                'magisk': version, 'root': True, 'packages': packages,
                'graphics_tested_on_m5': False}
    finally:
        controller.adb('unroot', check=False)
        wait_device(controller)


def provision(cache, root=None):
    c = subsystem.Controller(root)
    if c.config['android'] != 16: raise RuntimeError('This pinned Magisk profile supports Android 16 only')
    lock = json.loads((PROJECT / 'scripts/runtime-lock.json').read_text())
    assets = {}
    for entry in lock['archives']:
        if entry.get('kind') == 'magisk':
            path = cache / entry['relative_path']
            if not path.is_file() or digest(path) != entry['sha256']: raise RuntimeError(f'Invalid provision archive: {path.name}')
            assets[entry['kind']] = path
    if 'magisk' not in assets: raise RuntimeError('The pinned Magisk archive is required')
    workspace = c.root / 'provision-work'; workspace.mkdir(exist_ok=True)
    c.boot()
    adb_root(c)
    patch_script = PROJECT / 'third_party/Magisk/host_patch.sh'
    if not patch_script.exists(): raise RuntimeError('Missing pinned upstream Magisk patch source')
    ramdisk = c.sdk / f'system-images/android-36/{c.image_tag}/arm64-v8a/ramdisk.img'
    if not ramdisk.is_file(): raise RuntimeError('Android 16 ARM64 ramdisk is missing')
    with zipfile.ZipFile(assets['magisk']) as apk:
        busybox = workspace / 'busybox'; busybox.write_bytes(apk.read('lib/arm64-v8a/libbusybox.so'))
    print('修补私有 ramdisk：Magisk v30.7 / Android 16 ARM64', flush=True)
    c.adb('push', str(busybox), '/data/local/tmp/busybox')
    c.adb('push', str(assets['magisk']), '/data/local/tmp/magisk.apk', timeout=120)
    c.adb('push', str(patch_script), '/data/local/tmp/mac_magisk_patch.sh')
    c.adb('push', str(ramdisk), '/data/local/tmp/ramdisk.img', timeout=120)
    c.adb('shell', 'sh', '/data/local/tmp/mac_magisk_patch.sh', '/data/local/tmp/ramdisk.img', timeout=180)
    image_dir = c.magisk_image_dir; image_dir.mkdir(parents=True, exist_ok=True)
    patched = image_dir / 'ramdisk.magisk.img'
    c.adb('pull', '/data/local/tmp/ramdisk.img.magisk', str(patched), timeout=120)
    if patched.stat().st_size < 65536: raise RuntimeError('Patched ramdisk is unexpectedly small')
    c.adb('install', '-r', str(assets['magisk']), timeout=120)
    c.stop()
    descriptor = {'android': 16, 'api': 36, 'image_tag': c.image_tag,
                  'sha256': digest(patched), 'magisk_apk_sha256': digest(assets['magisk']),
                  'source_ramdisk_sha256': digest(ramdisk)}
    subsystem.atomic_json(image_dir / 'ramdisk.json', descriptor)
    c.configure({'magisk_ramdisk': str(patched)})
    c = subsystem.Controller(root)
    c.boot()
    adb_root(c)
    _, version = magisk_binary(c)
    print('冷启动后 Magisk：', version, flush=True)
    report = verify(c)
    subsystem.atomic_json(c.root / 'provision-report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('Magisk root / 管理器检查完成。M5 图形仍需实测。')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cache', type=Path, nargs='?')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--rollback-root', action='store_true')
    args = parser.parse_args()
    c = subsystem.Controller(args.root)
    if args.rollback_root:
        c.stop()
        config = dict(c.config); config.pop('magisk_ramdisk', None)
        subsystem.atomic_json(c.root / 'config.json', config)
        print('Magisk ramdisk override removed. The original SDK image was never changed.'); return
    if args.verify_only:
        c.boot(); print(json.dumps(verify(c), indent=2)); return
    if args.cache is None: parser.error('cache is required')
    with (c.root / 'provision.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        provision(args.cache.resolve(), args.root)


if __name__ == '__main__':
    try: main()
    except (OSError, RuntimeError, ValueError, KeyError, subsystem.SubsystemError, zipfile.BadZipFile) as e:
        print('Magisk root 配置未完成：', e, file=sys.stderr); sys.exit(1)

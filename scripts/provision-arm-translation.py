#!/usr/bin/env python3
"""Let an Intel Mac's Android run arm64-only apps.

The x86_64 Android image has no ARM translation, so most games and many apps cannot even be installed. This
builds a Magisk module from the translator inside Google's x86_64 "Google APIs" image (see arm_translation.py),
installs it through Magisk, cold boots, and then proves it by running a real arm64 program.

    provision-arm-translation.py CACHE            install and verify
    provision-arm-translation.py CACHE --verify-only

Set ARM_TRANSLATION_MODULE to a module zip made with scripts/arm_translation.py to skip the ~2 GB image.
Apple Silicon Macs run arm64 apps natively; there this does nothing.
"""
from __future__ import annotations
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'scripts'))
import arm_translation


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, PROJECT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load('magisk_provision', 'scripts/provision-mac.py')
subsystem = core.subsystem
PROBE_DIR = '/data/local/tmp/mac_arm64_probe'
PROBE = PROBE_DIR + '/busybox'   # BusyBox picks its tool from its own file name
GUEST_MODULE = '/data/local/tmp/mac_subsystem_arm_translation.zip'


def source_entry(controller):
    lock = json.loads(core.lock_file(controller.config['android'], controller.arch).read_text())
    return next((e for e in lock['archives'] if e.get('kind') == 'arm_translation'), None)


def build_module(cache, controller, workspace):
    """The module zip: a prebuilt one from ARM_TRANSLATION_MODULE, or built from the pinned Google image."""
    prebuilt = os.environ.get('ARM_TRANSLATION_MODULE')
    if prebuilt:
        return Path(prebuilt)
    entry = source_entry(controller)
    if entry is None:
        raise RuntimeError('This runtime lock has no ARM translation source')
    image = cache / entry['relative_path']
    if not image.is_file() or core.digest(image) != entry['sha256']:
        raise RuntimeError(f"Invalid pinned Google APIs image: {image.name}")
    module = workspace / 'MacArmTranslation.zip'
    report = arm_translation.build_from_zip(image, module)
    print(f"ARM 翻译模块：{report['files']} 个文件，{len(report['props'])} 个属性 / "
          f"translator module: {report['files']} files, {len(report['props'])} properties", flush=True)
    return module


def probe_binary(apk):
    """A static arm64 program that ships inside the Magisk APK (its busybox): a real arm64 ELF to translate."""
    with zipfile.ZipFile(apk) as archive:
        return archive.read('lib/arm64-v8a/libbusybox.so')


def verify(controller, apk, workspace):
    """Properties, the binfmt rules, and then an actual arm64 program run through the translator."""
    core.adb_root(controller)
    try:
        abis = controller.adb('shell', 'getprop', 'ro.product.cpu.abilist').stdout.strip()
        bridge = controller.adb('shell', 'getprop', 'ro.dalvik.vm.native.bridge').stdout.strip()
        if 'arm64-v8a' not in abis.split(','):
            raise RuntimeError(f'Android does not list arm64-v8a after reboot (CPU types: {abis or "none"})')
        if not bridge.endswith('libndk_translation.so'):
            raise RuntimeError(f'The native bridge is not libndk_translation (found: {bridge or "none"})')
        for rule in ('arm64_exe', 'arm64_dyn'):
            if controller.adb('shell', 'test', '-e', f'/proc/sys/fs/binfmt_misc/{rule}', check=False).returncode:
                raise RuntimeError(f'The arm64 execution rule {rule} is not registered')
        local = workspace / 'arm64_probe'
        local.write_bytes(probe_binary(apk))
        controller.adb('shell', 'mkdir', '-p', PROBE_DIR)
        controller.adb('push', str(local), PROBE, timeout=60)
        controller.adb('shell', 'chmod', '755', PROBE)
        ran = controller.adb('shell', PROBE, 'echo', 'arm64-ok', check=False)
        if ran.returncode or ran.stdout.strip() != 'arm64-ok':
            raise RuntimeError('An arm64 program could not run through the translator '
                               f'(exit {ran.returncode}: {(ran.stdout + ran.stderr).strip()[:300]})')
        return {'abilist': abis, 'native_bridge': bridge, 'arm64_program_ran': True}
    finally:
        controller.adb('shell', 'rm', '-rf', PROBE_DIR, check=False)
        controller.adb('unroot', check=False)
        core.wait_device(controller)


def cold_boot(controller):
    root = controller.root
    controller.stop()
    fresh = subsystem.Controller(root)
    fresh.boot()
    core.adb_root(fresh)
    return fresh


def provision(cache, root=None):
    controller = subsystem.Controller(root)
    if controller.arch == 'arm64':
        print('Apple Silicon runs arm64 apps natively; no translation needed.')
        return None
    if controller.config['android'] not in (16, 17):
        raise RuntimeError('ARM translation supports Android 16 and 17')
    workspace = controller.root / 'provision-work'
    workspace.mkdir(exist_ok=True)
    apk = core.magisk_apk(cache, controller)
    module = build_module(cache, controller, workspace)
    controller.boot()
    core.verify(controller)
    core.adb_root(controller)
    try:
        binary, _ = core.magisk_binary(controller)
        core.ensure_magisk_env(controller, apk)
        controller.adb('push', str(module), GUEST_MODULE, timeout=120)
        controller.adb('shell', binary, '--install-module', GUEST_MODULE, timeout=240)
        controller = cold_boot(controller)
        report = verify(controller, apk, workspace)
    finally:
        controller.adb('unroot', check=False)
        core.wait_device(controller)
    report['module_sha256'] = core.digest(module)
    subsystem.atomic_json(controller.root / 'arm-translation-report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('ARM 翻译已启用：现在可以安装只含 arm64 代码的应用。 / ARM translation is on: arm64-only apps can be installed.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('cache', type=Path)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    controller = subsystem.Controller(args.root)
    with (controller.root / 'provision.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.verify_only:
            controller.boot()
            workspace = controller.root / 'provision-work'
            workspace.mkdir(exist_ok=True)
            print(json.dumps(verify(controller, core.magisk_apk(args.cache.resolve(), controller), workspace), indent=2))
        else:
            provision(args.cache.resolve(), args.root)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, KeyError, ValueError, zipfile.BadZipFile, arm_translation.sysimg.ImageError,
            subsystem.SubsystemError) as error:
        print('ARM 翻译未完成 / ARM translation not installed:', error, file=sys.stderr)
        sys.exit(1)

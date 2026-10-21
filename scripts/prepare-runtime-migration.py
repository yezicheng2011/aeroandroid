#!/usr/bin/env python3
"""Stop the existing installation before installing a different Android image."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path.home() / 'Library/Application Support/AndroidSubsystem'
BUNDLE_ID = 'dev.dan.androidsubsystem'


def old_backend(home, project=PROJECT):
    candidates = [home / 'Applications/Android Subsystem.app/Contents/Resources/backend/subsystem.py',
                  Path('/Applications/Android Subsystem.app/Contents/Resources/backend/subsystem.py'),
                  home / 'Downloads/M5-Android16-0.1.0/AndroidSubsystem/backend/subsystem.py',
                  project / 'backend/subsystem.py']
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError('Cannot find the existing subsystem backend; the installation was not changed')


def quit_manager(runner=subprocess.run):
    # NSRunningApplication identifies our bundle directly. No System Events,
    # accessibility permission, force-kill, or launch of an absent app is needed.
    script = '''ObjC.import('AppKit');
var identifier = 'dev.dan.androidsubsystem';
var applications = $.NSRunningApplication.runningApplicationsWithBundleIdentifier(identifier);
for (var i = 0; i < applications.count; i++) {
    if (!applications.objectAtIndex(i).terminate) throw new Error('Cannot quit Android Subsystem');
}
var deadline = Date.now() + 10000;
while ($.NSRunningApplication.runningApplicationsWithBundleIdentifier(identifier).count > 0) {
    if (Date.now() >= deadline) throw new Error('Android Subsystem has not exited');
    $.NSThread.sleepForTimeInterval(0.1);
}'''
    runner(['/usr/bin/osascript', '-l', 'JavaScript', '-e', script],
           check=True, timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def controller_factory(root):
    spec = importlib.util.spec_from_file_location('migration_backend', PROJECT / 'backend/subsystem.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.Controller(root)


def prepare(root, home=None, runner=subprocess.run, factory=controller_factory, quit=quit_manager):
    root = root.resolve()
    home = Path.home() if home is None else Path(home)
    python = root / 'runtime/python/bin/python3'
    if not python.is_file():
        raise RuntimeError('Existing installation is missing its private Python. No configuration was changed; restore the original runtime before migrating')
    if not (root / 'config.json').is_file():
        raise RuntimeError('Existing runtime configuration is missing; migration was stopped before changing it')
    # Do not overwrite the app/backend or rewrite config before the old VM stops.
    # After a failed AOSP provision, config may already describe the new AVD while
    # the installed app still has its legacy backend. Use the matching backend
    # for that retry, rather than asking an old backend to control another AVD.
    config = json.loads((root / 'config.json').read_text())
    backend = PROJECT / 'backend/subsystem.py' if config.get('image_tag') == 'default' else old_backend(home)
    quit(runner)
    result = runner([str(python), str(backend), 'stop', '--root', str(root)],
                    check=False, timeout=60, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stopped = json.loads(result.stdout)
    except ValueError as error:
        raise RuntimeError(f'Old backend did not confirm shutdown: {(result.stderr or result.stdout)[-2000:]}') from error
    if result.returncode or stopped.get('ok') is not True or stopped.get('data', {}).get('state') != 'stopped':
        raise RuntimeError(f'Old runtime shutdown failed: {stopped}')
    controller = factory(root)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not controller.running_emulator() and not controller.device() and not controller.unconfirmed_shutdown():
            break
        time.sleep(0.2)
    else:
        raise RuntimeError('Old emulator has not fully exited; runtime configuration was not changed')
    backup = root / 'migration-backup'
    backup.mkdir(mode=0o700, exist_ok=True)
    filename = 'config-before-aosp-' + time.strftime('%Y%m%d-%H%M%S') + '.json'
    target = backup / filename
    # Config and memory settings are retained; old AVD userdata is kept separately.
    shutil.copyfile(root / 'config.json', target)
    target.chmod(0o600)
    print('旧子系统已停止，管理应用已退出。配置备份：', target)
    print('内存设置将保留；纯 AOSP 使用独立 AVD，旧安卓应用数据不会被擦除或直接混入新系统。')
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('Run this migration on your Apple Silicon Mac')
    prepare(args.root)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print('迁移准备未完成：', error, file=sys.stderr)
        sys.exit(1)

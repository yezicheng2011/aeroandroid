#!/usr/bin/env python3
"""Download and install the pinned Android runtime from inside the Mac app.

The app runs this script and reads progress lines from stderr:

    AERO_MIRROR\\tcn|global
    AERO_PROGRESS\\t<fraction 0-1>\\t<message>

stdout of `license` is the Android SDK license text. stdout of `status` is
JSON. The Android SDK archives are not stored in the app; they are downloaded
on the Mac that runs it.

Copyright 2026 daniel.ye — Apache-2.0
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mirror  # noqa: E402

GOOGLE_BASE = mirror.GOOGLE_BASE
CATALOGS = (
    ('repository2-3.xml', 'repository2-3.xml'),
    ('sys-img/android/sys-img2-3.xml', 'images2-3.xml'),
)


def scripts_dir():
    return Path(__file__).resolve().parent


def support_dir():
    return Path.home() / 'Library/Application Support/AndroidSubsystem'


def setup_module():
    path = scripts_dir() / 'setup-offline-mac.py'
    spec = importlib.util.spec_from_file_location('setup_offline_mac_bundle', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def host_arch():
    """Match scripts/host.sh: Apple Silicon, including a Rosetta shell, is arm64."""
    machine = platform.machine()
    if machine == 'arm64':
        return 'arm64'
    try:
        result = subprocess.run(['sysctl', '-in', 'hw.optional.arm64'], capture_output=True, text=True, timeout=5)
        if result.stdout.strip() == '1':
            return 'arm64'
    except (OSError, subprocess.TimeoutExpired):
        pass
    return machine


def lock_path():
    override = os.environ.get('ANDROID_SUBSYSTEM_LOCK')
    if override:
        return Path(override)
    name = 'runtime-lock.json' if host_arch() == 'arm64' else 'runtime-lock-%s.json' % host_arch()
    return scripts_dir() / name


def resolve_root(arg):
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get('ANDROID_SUBSYSTEM_HOME')
    if env:
        return Path(env).expanduser()
    return support_dir()


def resolve_cache(arg, root):
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get('ANDROID_SUBSYSTEM_CACHE')
    if env:
        return Path(env).expanduser()
    return root / 'download-cache'


def emit(fraction, message):
    fraction = max(0.0, min(1.0, float(fraction)))
    print('AERO_PROGRESS\t%.4f\t%s' % (fraction, message.replace('\t', ' ').replace('\n', ' ')),
          file=sys.stderr, flush=True)


def emit_mirror(selected):
    print('AERO_MIRROR\t%s' % selected, file=sys.stderr, flush=True)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def candidate_urls(url, selected):
    ordered = []
    for item in (mirror.rewrite(url, selected), url):
        if item not in ordered:
            ordered.append(item)
    return ordered


def download_file(url, dest, on_bytes, opener=None, timeout=60):
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent': 'aeroandroid'})
    open_url = opener or urllib.request.urlopen
    with open_url(request, timeout=timeout) as response:
        total_header = response.headers.get('Content-Length') if response.headers is not None else None
        total = int(total_header) if total_header and str(total_header).isdigit() else None
        done = 0
        with dest.open('wb') as out:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                on_bytes(done, total)


def fetch_loose(url, dest, selected, span, label, opener=None):
    part = dest.with_name(dest.name + '.part')
    errors = []
    for candidate in candidate_urls(url, selected):
        try:
            def on_bytes(done, total, candidate=candidate):
                if total:
                    fraction = span[0] + (span[1] - span[0]) * min(1.0, done / total)
                else:
                    fraction = span[0]
                emit(fraction, 'Downloading %s' % label)

            download_file(candidate, part, on_bytes, opener=opener)
            part.replace(dest)
            emit(span[1], 'Downloaded %s' % label)
            return
        except Exception as exc:
            part.unlink(missing_ok=True)
            errors.append('%s: %s' % (candidate, exc))
    raise RuntimeError('download failed: %s: %s' % (label, '; '.join(errors)))


def fetch_verified(url, dest, digest, selected, span, label, opener=None):
    if dest.is_file() and sha256(dest) == digest:
        emit(span[1], 'Already downloaded %s' % label)
        return
    part = dest.with_name(dest.name + '.part')
    errors = []
    for candidate in candidate_urls(url, selected):
        try:
            def on_bytes(done, total, candidate=candidate):
                if total:
                    fraction = span[0] + (span[1] - span[0]) * min(1.0, done / total)
                else:
                    fraction = span[0]
                emit(fraction, 'Downloading %s' % label)

            download_file(candidate, part, on_bytes, opener=opener)
            actual = sha256(part)
            if actual != digest:
                part.unlink(missing_ok=True)
                errors.append('SHA-256 mismatch from %s' % candidate)
                continue
            part.replace(dest)
            emit(span[1], 'Downloaded %s' % label)
            return
        except Exception as exc:
            part.unlink(missing_ok=True)
            errors.append('%s: %s' % (candidate, exc))
    raise RuntimeError('download failed: %s: %s' % (label, '; '.join(errors)))


def ensure_space(anchor, gigabytes=20):
    anchor.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(anchor).free
    if free < gigabytes * 1024 ** 3:
        raise RuntimeError('At least %s GB of free disk space is required' % gigabytes)


def download_steps(lock, cache, include_catalogs, graphics_only):
    steps = []
    if include_catalogs:
        for src, name in CATALOGS:
            steps.append(('catalog', GOOGLE_BASE + src, cache / 'sdk-macos' / name, None, name))
    for entry in setup_module().selected_archives(lock, graphics_only=graphics_only):
        steps.append(('archive', entry['url'], cache / entry['relative_path'], entry['sha256'], entry['name']))
    return steps


def download_runtime(lock, cache, selected, include_catalogs=True, graphics_only=True, opener=None):
    steps = download_steps(lock, cache, include_catalogs, graphics_only)
    if not steps:
        emit(0.90, 'Nothing to download')
        return
    start, end = 0.02, 0.90
    width = (end - start) / len(steps)
    for index, (kind, url, dest, digest, label) in enumerate(steps):
        span = (start + index * width, start + (index + 1) * width)
        if kind == 'catalog':
            fetch_loose(url, dest, selected, span, label, opener=opener)
        else:
            fetch_verified(url, dest, digest, selected, span, label, opener=opener)


def read_license(cache):
    path = cache / 'sdk-macos' / 'repository2-3.xml'
    root = ET.parse(path).getroot()
    node = next((item for item in root.findall('license') if item.get('id') == 'android-sdk-license'), None)
    if node is None or not (node.text and node.text.strip()):
        raise RuntimeError('Android SDK license was not found in the downloaded catalog')
    return node.text.strip()


def cmd_status(root, lock):
    installed = setup_module().runtime_installed(root, lock)
    sys.stdout.write(json.dumps({'installed': installed}) + '\n')
    sys.stdout.flush()


def cmd_license(cache, selected, opener=None):
    emit_mirror(selected)
    emit(0.01, 'Downloading the Android SDK license')
    fetch_loose(GOOGLE_BASE + 'repository2-3.xml', cache / 'sdk-macos' / 'repository2-3.xml',
                selected, (0.01, 0.05), 'repository2-3.xml', opener=opener)
    text = read_license(cache)
    sys.stdout.write(text + '\n')
    sys.stdout.flush()


def cmd_install(cache, root, lock_file):
    emit(0.90, 'Installing Android components')
    script = scripts_dir() / 'setup-offline-mac.py'
    env = os.environ.copy()
    env['ANDROID_SUBSYSTEM_LOCK'] = str(lock_file)
    proc = subprocess.Popen(
        [sys.executable, str(script), str(cache), '--root', str(root), '--runtime-only', '--accept-sdk-license'],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.append(line)
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('Installing:') or stripped.startswith('Checking:'):
            emit(0.93, stripped)
        elif 'Quick Boot' in stripped or stripped.startswith('Saving'):
            emit(0.97, stripped)
        else:
            print(stripped, file=sys.stderr, flush=True)
    code = proc.wait()
    if code != 0:
        tail = ''.join(lines)[-4000:].strip()
        raise RuntimeError(tail or 'setup exited %s' % code)
    emit(1.0, 'Android is installed')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Download and install the pinned Android runtime.')
    parser.add_argument('command', choices=('status', 'license', 'download', 'install'))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--mirror', choices=('auto', 'cn', 'global'),
                        default=os.environ.get('AEROANDROID_MIRROR', 'auto'))
    parser.add_argument('--accept-sdk-license', action='store_true')
    args = parser.parse_args(argv)
    try:
        try:
            sys.stderr.reconfigure(line_buffering=True)
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass
        root = resolve_root(args.root)
        cache = resolve_cache(args.cache, root)
        lock_file = lock_path()
        lock = json.loads(lock_file.read_text())
        if args.command == 'status':
            cmd_status(root, lock)
            return 0
        selected = mirror.choose_mirror(args.mirror)
        if args.command == 'license':
            cmd_license(cache, selected)
        elif args.command == 'download':
            emit_mirror(selected)
            ensure_space(cache)
            download_runtime(lock, cache, selected)
            emit(0.90, 'Downloads finished')
        else:
            if not args.accept_sdk_license:
                raise RuntimeError('Accept the Android SDK license before installing')
            emit_mirror(selected)
            ensure_space(root)
            cmd_install(cache, root, lock_file)
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Pre-install extra apps (Aurora Store, a browser, ...) into the subsystem.

Each app in scripts/preinstall.json is pinned by APK SHA-256 and by signing-certificate
SHA-256, the same trust model as runtime-lock.json: nothing unpinned is ever installed.

  preinstall-apps.py CACHE        download (if needed), verify and install the pinned apps
  preinstall-apps.py --pin URL    download one APK and print its manifest entry to review and paste
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT / 'scripts/preinstall.json'
spec = importlib.util.spec_from_file_location('microg_provision', PROJECT / 'scripts/provision-microg.py')
microg = importlib.util.module_from_spec(spec); spec.loader.exec_module(microg)
core, subsystem = microg.core, microg.subsystem


def download(url, destination):
    if not url.startswith('https://'):
        raise RuntimeError(f'Refusing a non-HTTPS download: {url}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + '.part')
    with urllib.request.urlopen(url, timeout=120) as response, partial.open('wb') as out:
        shutil.copyfileobj(response, out)
    partial.replace(destination)


def verified_apk(cache, entry, controller):
    """The pinned APK, downloaded when absent; both pins and the real package name must match."""
    path = cache / 'apps' / (entry['package'] + '.apk')
    if not path.is_file() or core.digest(path) != entry['sha256']:
        download(entry['url'], path)
    if core.digest(path) != entry['sha256']:
        path.unlink()
        raise RuntimeError(f"SHA-256 mismatch for {entry['package']}; the download was discarded")
    info = microg.apk_info(controller, path)
    if info['app_package'] != entry['package'] or info['signer_sha256'] != entry['signer_sha256']:
        raise RuntimeError(f"{entry['package']} has the wrong package name or signing certificate")
    return path


def install_pinned(cache, root):
    apps = json.loads(MANIFEST.read_text())['apps']
    if not apps:
        print('No extra apps are pinned in scripts/preinstall.json; skipping.')
        return []
    controller = subsystem.Controller(root)
    controller.boot()
    installed = []
    for entry in apps:
        path = verified_apk(cache, entry, controller)
        if microg.package_paths(controller, entry['package']):
            print(f"  ✓ {entry['name']} is already installed")
            continue
        controller.install([str(path)])
        installed.append(entry['package'])
        print(f"  ✓ installed {entry['name']}")
    return installed


def pin(url, root):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'app.apk'
        download(url, path)
        controller = subsystem.Controller(root)
        info = microg.apk_info(controller, path)
        label = controller.apk_info([path])['label']
        return {'name': label, 'package': info['app_package'], 'url': url,
                'sha256': core.digest(path), 'signer_sha256': info['signer_sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('cache', type=Path, nargs='?')
    parser.add_argument('--pin', metavar='URL')
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    if args.pin:
        print(json.dumps(pin(args.pin, args.root), indent=2, ensure_ascii=False))
    elif args.cache:
        install_pinned(args.cache.resolve(), args.root)
    else:
        parser.error('give a cache folder, or --pin URL')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, KeyError, ValueError, subsystem.SubsystemError) as error:
        print('预装应用未完成 / Pre-installed apps incomplete:', error, file=sys.stderr)
        sys.exit(1)

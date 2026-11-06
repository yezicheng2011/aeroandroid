#!/usr/bin/env python3
"""Pre-install extra apps (Aurora Store, a browser, ...) into the subsystem.

Each app in scripts/preinstall.json is pinned by APK SHA-256 and by signing-certificate
SHA-256, the same trust model as runtime-lock.json: nothing unpinned is ever installed.

  preinstall-apps.py CACHE        download (if needed), verify and install the pinned apps
  preinstall-apps.py --pin URL    download one APK and print its manifest entry to review and paste
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
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


OFFICIAL_REPO = 'https://f-droid.org/repo/'


def candidate_urls(url):
    """Mirrors first, then the pinned URL. FDROID_MIRROR holds space-separated F-Droid repo URLs
    (build.sh sets it for --mirror cn). The SHA-256 pin makes the choice of server irrelevant."""
    mirrors = [m if m.endswith('/') else m + '/' for m in os.environ.get('FDROID_MIRROR', '').split()]
    return ([m + url[len(OFFICIAL_REPO):] for m in mirrors] if url.startswith(OFFICIAL_REPO) else []) + [url]


def download(url, destination, sha256=None):
    """Fetch `url` (or a mirror of it). With `sha256`, a server whose file does not match is skipped, so a bad
    mirror falls back to the next server instead of ending the install."""
    if not url.startswith('https://'):
        raise RuntimeError(f'Refusing a non-HTTPS download: {url}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + '.part')
    failure = None
    for candidate in candidate_urls(url):
        try:
            with urllib.request.urlopen(candidate, timeout=60) as response, partial.open('wb') as out:
                shutil.copyfileobj(response, out)
            if sha256 and hashlib.sha256(partial.read_bytes()).hexdigest() != sha256:
                failure = RuntimeError(f'{candidate} served a file that does not match its SHA-256 pin')
                continue
            partial.replace(destination)
            return
        except OSError as error:
            failure = error
    raise RuntimeError(f'Could not download {url}: {failure}')


def verified_apk(cache, entry, controller):
    """The pinned APK, downloaded when absent; both pins and the real package name must match."""
    path = cache / 'apps' / f"{entry['package']}-{entry['sha256'][:8]}.apk"
    if not path.is_file() or core.digest(path) != entry['sha256']:
        download(entry['url'], path, entry['sha256'])
    if core.digest(path) != entry['sha256']:
        path.unlink()
        raise RuntimeError(f"SHA-256 mismatch for {entry['package']}; the download was discarded")
    info = microg.apk_info(controller, path)
    if info['app_package'] != entry['package'] or info['signer_sha256'] != entry['signer_sha256']:
        raise RuntimeError(f"{entry['package']} has the wrong package name or signing certificate")
    return path


def choose_builds(apps, abilist):
    """One build per package: those the system can run, preferring the earliest CPU type it lists (a native
    x86_64 build over an arm64 one that would need translation). An entry without `abi` runs anywhere."""
    best = {}
    for entry in apps:
        abi = entry.get('abi')
        if abi is not None and abi not in abilist:
            continue
        rank = abilist.index(abi) if abi is not None else 0
        if entry['package'] not in best or rank < best[entry['package']][0]:
            best[entry['package']] = (rank, entry)
    return [entry for _rank, entry in best.values()]


def install_pinned(cache, root):
    apps = json.loads(MANIFEST.read_text())['apps']
    if not apps:
        print('No extra apps are pinned in scripts/preinstall.json; skipping.')
        return []
    controller = subsystem.Controller(root)
    controller.boot()
    abilist = controller.adb('shell', 'getprop', 'ro.product.cpu.abilist').stdout.strip().split(',')
    installed = []
    for entry in choose_builds(apps, abilist):
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

#!/usr/bin/env python3
"""Cache official Android SDK archives directly on the requested cloud mount."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

BASE = 'https://dl.google.com/android/repository/'
REPO = BASE + 'repository2-3.xml'
IMAGES = BASE + 'sys-img/android/sys-img2-3.xml'


def get_metadata(url, destination):
    with urllib.request.urlopen(url, timeout=90) as response:
        data = response.read()
    destination.write_bytes(data)
    return ET.fromstring(data)


def choose(root, package, host):
    for p in root.findall('remotePackage'):
        if p.get('path') != package or p.find('obsolete') is not None:
            continue
        if p.find('channelRef') is not None and p.find('channelRef').get('ref') != 'channel-0':
            continue
        for a in p.findall('archives/archive'):
            os_name = a.findtext('host-os')
            arch = a.findtext('host-arch')
            if os_name not in (None, host) or arch not in (None, 'aarch64' if host == 'macosx' else 'x64'):
                continue
            complete = a.find('complete')
            return {'package': package, 'host': host, 'name': complete.findtext('url').split('/')[-1],
                    'url': urllib.request.urljoin(BASE, complete.findtext('url')),
                    'size': int(complete.findtext('size')), 'sha1': complete.findtext('checksum')}
    raise RuntimeError(f'No stable {host} archive for {package}')


def digest(path, algorithm):
    h = hashlib.new(algorithm)
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def download(entry, cache):
    target = cache / entry['name']
    if target.exists() and target.stat().st_size == entry['size'] and digest(target, 'sha1') == entry['sha1']:
        print('Cached:', target.name, flush=True)
    else:
        temporary = target.with_suffix(target.suffix + '.partial')
        print('Downloading:', target.name, entry['size'], flush=True)
        try:
            with urllib.request.urlopen(entry['url'], timeout=120) as response, temporary.open('wb') as out:
                while block := response.read(4 * 1024 * 1024): out.write(block)
            if temporary.stat().st_size != entry['size'] or digest(temporary, 'sha1') != entry['sha1']:
                raise RuntimeError(f'Checksum mismatch: {target.name}')
            temporary.replace(target)
        finally: temporary.unlink(missing_ok=True)
    entry['sha256'] = digest(target, 'sha256')
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cache', type=Path)
    parser.add_argument('--host', choices=['macosx', 'linux'], default='macosx')
    parser.add_argument('--android', type=int, choices=[16, 17], default=16)
    parser.add_argument('--guest-only', action='store_true')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    sdk = get_metadata(REPO, args.cache / 'repository2-3.xml')
    images = get_metadata(IMAGES, args.cache / 'images2-3.xml')
    packages = ['platforms;android-36', 'build-tools;36.0.0']
    if not args.guest_only: packages += ['cmdline-tools;latest', 'platform-tools', 'emulator']
    entries = [choose(sdk, p, args.host) for p in packages]
    if not args.guest_only:
        image = choose(images, f'system-images;android-{args.android+20};default;arm64-v8a', args.host)
        image['url'] = urllib.request.urljoin(BASE + 'sys-img/android/',
                                            next(p for p in images.findall('remotePackage') if p.get('path') == image['package']).findtext('archives/archive/complete/url'))
        entries.append(image)
    manifest = {'android': args.android, 'host': args.host, 'archives': []}
    # Save progress after every archive; interrupted downloads can safely resume on rerun.
    for entry in entries:
        manifest['archives'].append(download(entry, args.cache))
        (args.cache / f'manifest-{args.host}.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Cache ready:', args.cache, flush=True)


if __name__ == '__main__': main()

"""Build a Magisk module that lets an x86_64 Android run arm64 apps.

The stock x86_64 AOSP emulator image has no ARM translation, so apps and games that ship only arm64 native code
cannot be installed. Google's "Google APIs" x86_64 image does include AOSP's open-source binary translator
(libndk_translation, "berberis", Apache-2.0). This module copies just that translator, and the few system
properties that switch it on, out of that image, and nothing else: none of Google's own apps or services.

    python3 scripts/arm_translation.py google_apis-x86_64.zip mac_arm_translation.zip

Run on the user's own machine on an image they downloaded from Google; the project does not redistribute it.
"""
from __future__ import annotations
import argparse
import re
import stat
import sys
import tempfile
from pathlib import Path
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sysimg

MODULE_ID = 'mac_arm_translation'

# Everything the translator needs lives in the `system` partition. Matching by pattern keeps this working when
# Google adds a proxy library; REQUIRED guards against a layout change that would leave a half-working module.
TRANSLATOR_FILES = re.compile(
    r'^/system/(bin/arm64/|bin/ndk_translation_program_runner_binfmt_misc|etc/berberis/|etc/binfmt_misc/'
    r'|etc/ld\.config\.arm|lib64/arm64/|lib64/libberberis_exec_region\.so$|lib64/libndk_translation\.so$'
    r'|lib64/libproxy_arm64_to_x86_64_)')
REQUIRED = ('/system/lib64/libndk_translation.so', '/system/bin/ndk_translation_program_runner_binfmt_misc_arm64',
            '/system/bin/arm64/linker64', '/system/lib64/arm64/libc.so',
            '/system/etc/binfmt_misc/arm64_exe', '/system/etc/binfmt_misc/arm64_dyn')

# Properties copied from the Google image's own build.prop, so the values always match its translator build.
IMAGE_PROPS = re.compile(r'^(ro\.berberis\.|ro\.dalvik\.vm\.isa\.arm|ro\.dalvik\.vm\.native\.bridge$|ro\.enable\.native\.bridge)')
ABI_LIST = 'x86_64,arm64-v8a'
ABI_PROPS = ('ro.product.cpu.abilist', 'ro.product.cpu.abilist64', 'ro.system.product.cpu.abilist',
             'ro.system.product.cpu.abilist64', 'ro.vendor.product.cpu.abilist', 'ro.vendor.product.cpu.abilist64',
             'ro.odm.product.cpu.abilist', 'ro.odm.product.cpu.abilist64')

CUSTOMIZE = '''SKIPUNZIP=0
set_perm_recursive "$MODPATH/system" 0 0 0755 0644
set_perm_recursive "$MODPATH/system/bin" 0 2000 0755 0755
'''

# binfmt_misc lets Android run arm64 command-line programs. Registered late, from the module's own copy of the
# rules, so it does not depend on init having parsed a rc file that the module cannot add in time.
SERVICE = '''#!/system/bin/sh
MODDIR=${0%/*}
[ -d /proc/sys/fs/binfmt_misc ] || exit 0
[ -e /proc/sys/fs/binfmt_misc/register ] || mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
for rule in arm64_exe arm64_dyn; do
  [ -e "/proc/sys/fs/binfmt_misc/$rule" ] || cat "$MODDIR/system/etc/binfmt_misc/$rule" > /proc/sys/fs/binfmt_misc/register
done
'''


def parse_props(text):
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line and not line.lstrip().startswith('#'))


def open_system(image):
    """The `system` partition of an emulator system.img, as an Ext4."""
    super_offset = sysimg.gpt_partitions(image)['super'][0]
    return sysimg.Ext4(sysimg.lp_partition(image, super_offset, 'system'))


def translator_paths(system):
    """(path, inode, mode) of every translator file in the image; raises if the layout is not as expected."""
    found = [(path, inode, mode) for path, inode, mode in system.walk('/')
             if stat.S_ISREG(mode) and TRANSLATOR_FILES.match(path)]
    missing = [path for path in REQUIRED if path not in {p for p, _, _ in found}]
    if missing:
        raise sysimg.ImageError('This system image has no ARM translator (missing ' + ', '.join(missing) + ')')
    return found


def translation_props(system):
    props = parse_props(system.read(system.lookup('/system/build.prop')).decode())
    chosen = {key: value for key, value in props.items() if IMAGE_PROPS.match(key)}
    if chosen.get('ro.dalvik.vm.native.bridge') != 'libndk_translation.so':
        raise sysimg.ImageError('This system image does not enable libndk_translation')
    chosen.update({key: ABI_LIST for key in ABI_PROPS})
    return dict(sorted(chosen.items()))


def build_module(system, destination):
    """Write the Magisk module zip; returns {'files': n, 'props': {...}}."""
    files = translator_paths(system)
    props = translation_props(system)
    version = props.get('ro.berberis.version', 'unknown')
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        def add(name, data, mode=0o644):
            info = zipfile.ZipInfo(name, (2008, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
        add('module.prop', f'id={MODULE_ID}\nname=Mac ARM translation\nversion={version}\nversionCode=1\n'
                           'author=Android Subsystem\ndescription=AOSP ARM64-to-x86_64 binary translator (berberis) '
                           'from the Google APIs image, so arm64 apps run\n')
        add('customize.sh', CUSTOMIZE)
        add('system.prop', ''.join(f'{key}={value}\n' for key, value in props.items()))
        add('service.sh', SERVICE, 0o755)
        for path, inode, mode in sorted(files):
            add('system' + path[len('/system'):], system.read(inode), mode & 0o777)
    return {'files': len(files), 'props': props}


def build_from_zip(image_zip, destination, name='x86_64/system.img'):
    """Unpack system.img from Google's image zip to a temporary file, build the module, then discard the image."""
    with zipfile.ZipFile(image_zip) as archive, tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'system.img'
        with archive.open(name) as source, target.open('wb') as out:
            while chunk := source.read(1 << 24):
                out.write(chunk)
        with target.open('rb') as image:
            return build_module(open_system(image), destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('image_zip', type=Path, help='x86_64 Google APIs system image zip from Google')
    parser.add_argument('module', type=Path, help='Magisk module zip to write')
    args = parser.parse_args()
    report = build_from_zip(args.image_zip, args.module)
    print(f"Wrote {args.module}: {report['files']} translator files, {len(report['props'])} properties")


if __name__ == '__main__':
    try:
        main()
    except (OSError, sysimg.ImageError, KeyError, zipfile.BadZipFile) as error:
        print('ARM translation module not built:', error, file=sys.stderr)
        sys.exit(1)

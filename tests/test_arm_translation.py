import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'


import sys
sys.path.insert(0, str(SCRIPTS))
import arm_translation    # the same module objects the provisioning script imports, so exception classes match
import sysimg


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


provision = load('provision_arm', 'scripts/provision-arm-translation.py')


class FileSource:
    def __init__(self, f): self.f = f
    def read_at(self, position, count): self.f.seek(position); return self.f.read(count)


def make_ext4(tree, path):
    """A real ext4 image holding `tree` (mke2fs -d), or skip the test when e2fsprogs is missing."""
    if not shutil.which('mke2fs'):
        raise unittest.SkipTest('mke2fs is not installed')
    subprocess.run(['mke2fs', '-q', '-t', 'ext4', '-O', '^has_journal', '-d', str(tree), str(path), '8M'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def translator_tree(root, with_translator=True):
    files = {'system/build.prop': 'ro.dalvik.vm.native.bridge=libndk_translation.so\nro.dalvik.vm.isa.arm64=x86_64\n'
                                  'ro.dalvik.vm.isa.arm=x86\nro.enable.native.bridge.exec=1\nro.berberis.version=16.0.0\n'
                                  'ro.unrelated=1\n',
             'system/lib64/libc.so': 'native libc'}
    if with_translator:
        files.update({
            'system/lib64/libndk_translation.so': 'engine', 'system/lib64/libberberis_exec_region.so': 'region',
            'system/lib64/libproxy_arm64_to_x86_64_libc.so': 'proxy', 'system/lib64/arm64/libc.so': 'arm64 libc',
            'system/bin/arm64/linker64': 'linker', 'system/bin/arm64/app_process64': 'app',
            'system/bin/ndk_translation_program_runner_binfmt_misc_arm64': 'runner',
            'system/etc/binfmt_misc/arm64_exe': ':arm64_exe:M::x', 'system/etc/binfmt_misc/arm64_dyn': ':arm64_dyn:M::y',
            'system/etc/berberis/cpuinfo.arm64.txt': 'cpu', 'system/etc/ld.config.arm64.txt': 'ld',
            'system/etc/init/berberis_arm_or_arm64.rc': 'rc that must not be shipped'})
    for name, text in files.items():
        target = Path(root) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    for executable in ('system/bin/ndk_translation_program_runner_binfmt_misc_arm64', 'system/bin/arm64/linker64'):
        if (Path(root) / executable).exists(): (Path(root) / executable).chmod(0o755)
    if with_translator:
        os.symlink('libc.so', Path(root) / 'system/lib64/arm64/libm.so')


def make_disk(ext4_image, path):
    """A GPT disk whose `super` partition (Android dynamic partitions) holds one logical partition `system`."""
    data = ext4_image.read_bytes()
    super_offset = 1 << 20
    geometry = struct.pack('<II32sIII', 0x616C4467, 52, bytes(32), 4096, 1, 4096).ljust(52, b'\0')
    partition = struct.pack('<36sIIII', b'system', 0, 0, 1, 0)
    extent = struct.pack('<QIQI', len(data) // 512, 0, 4096 // 512 * 8 + 0, 0)
    first_data_sector = 64
    extent = struct.pack('<QIQI', len(data) // 512, 0, first_data_sector, 0)
    tables = partition + extent
    header = struct.pack('<IHHI32sI32s', 0x414C5030, 10, 0, 256, bytes(32), len(tables), bytes(32))
    header += struct.pack('<12I', 0, 1, 52, 52, 1, 24, 0, 0, 0, 0, 0, 0)
    header = header.ljust(256, b'\0')
    super_image = bytearray(first_data_sector * 512 + len(data))
    super_image[4096:4096 + 52] = geometry
    super_image[12288:12288 + 256] = header
    super_image[12288 + 256:12288 + 256 + len(tables)] = tables
    super_image[first_data_sector * 512:] = data
    entry = bytearray(128)
    entry[0:16] = b'\x01' * 16
    first = super_offset // 512
    entry[32:48] = struct.pack('<QQ', first, first + len(super_image) // 512 - 1)
    entry[56:56 + 10] = 'super'.encode('utf-16le')
    disk = bytearray(super_offset + len(super_image))
    disk[512:512 + 92] = struct.pack('<8sIIIIQQQQ16sQIII', b'EFI PART', 0x10000, 92, 0, 0, 1, 0, 0, 0, bytes(16), 2, 1, 128, 0)
    disk[1024:1024 + 128] = entry
    disk[super_offset:] = super_image
    path.write_bytes(disk)


class ImageReaderTests(unittest.TestCase):
    def test_ext4_reader_lists_reads_and_extracts_a_real_filesystem(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder); tree = folder / 'tree'; translator_tree(tree)
            image = folder / 'fs.img'; make_ext4(tree, image)
            with image.open('rb') as f:
                fs = sysimg.Ext4(FileSource(f))
                self.assertEqual(fs.read(fs.lookup('/system/lib64/libndk_translation.so')), b'engine')
                self.assertIn('arm64', fs.listdir(fs.lookup('/system/lib64')))
                self.assertEqual(fs.read(fs.lookup('/system/build.prop')).count(b'\n'), 6)
                out = folder / 'out'; fs.extract('/system/lib64/arm64', out)
                self.assertEqual((out / 'libc.so').read_text(), 'arm64 libc')
                self.assertTrue((out / 'libm.so').is_symlink() and os.readlink(out / 'libm.so') == 'libc.so')
                with self.assertRaises(sysimg.ImageError): fs.lookup('/system/nothing')

    def test_ext4_reader_handles_a_big_fragmentation_free_file_and_many_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder); tree = folder / 'tree'; (tree / 'many').mkdir(parents=True)
            for i in range(600): (tree / 'many' / f'file-{i:04d}.txt').write_text(str(i))
            (tree / 'big.bin').write_bytes(os.urandom(3_000_000))
            image = folder / 'fs.img'; make_ext4(tree, image)
            with image.open('rb') as f:
                fs = sysimg.Ext4(FileSource(f))
                self.assertEqual(len(fs.listdir(fs.lookup('/many'))), 600)
                self.assertEqual(fs.read(fs.lookup('/big.bin')), (tree / 'big.bin').read_bytes())

    def test_gpt_and_dynamic_partitions_are_found_and_read(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder); tree = folder / 'tree'; translator_tree(tree)
            fs_image = folder / 'fs.img'; make_ext4(tree, fs_image)
            disk = folder / 'system.img'; make_disk(fs_image, disk)
            with disk.open('rb') as f:
                offset, _size = sysimg.gpt_partitions(f)['super']
                self.assertEqual(offset, 1 << 20)
                self.assertEqual(list(sysimg.lp_partitions(f, offset)), ['system'])
                fs = sysimg.Ext4(sysimg.lp_partition(f, offset, 'system'))
                self.assertEqual(fs.read(fs.lookup('/system/lib64/libndk_translation.so')), b'engine')
                with self.assertRaises(sysimg.ImageError): sysimg.lp_partition(f, offset, 'vendor')
            (folder / 'not-gpt.img').write_bytes(bytes(4096))
            with (folder / 'not-gpt.img').open('rb') as f, self.assertRaises(sysimg.ImageError): sysimg.gpt_partitions(f)


class ModuleTests(unittest.TestCase):
    def build(self, folder, **kwargs):
        folder = Path(folder); tree = folder / 'tree'; translator_tree(tree, **kwargs)
        image = folder / 'fs.img'; make_ext4(tree, image)
        disk = folder / 'system.img'; make_disk(image, disk)
        module = folder / 'module.zip'
        with disk.open('rb') as f:
            report = arm_translation.build_module(arm_translation.open_system(f), module)
        return module, report

    def test_module_has_only_the_translator_the_switch_properties_and_correct_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            module, report = self.build(folder)
            archive = zipfile.ZipFile(module)
            names = set(archive.namelist())
            self.assertTrue({'module.prop', 'customize.sh', 'system.prop', 'service.sh'} <= names)
            self.assertIn('system/lib64/libndk_translation.so', names)
            self.assertIn('system/lib64/arm64/libc.so', names)
            self.assertIn('system/etc/binfmt_misc/arm64_exe', names)
            self.assertNotIn('system/lib64/libc.so', names)                         # the stock libraries stay untouched
            self.assertNotIn('system/build.prop', names)
            self.assertNotIn('system/etc/init/berberis_arm_or_arm64.rc', names)       # init has parsed rc files by then
            runner = archive.getinfo('system/bin/ndk_translation_program_runner_binfmt_misc_arm64')
            self.assertEqual((runner.external_attr >> 16) & 0o777, 0o755)
            self.assertEqual((archive.getinfo('system/lib64/arm64/libc.so').external_attr >> 16) & 0o777, 0o644)
            props = dict(line.split('=') for line in archive.read('system.prop').decode().splitlines())
            self.assertEqual(props['ro.dalvik.vm.native.bridge'], 'libndk_translation.so')
            self.assertEqual(props['ro.product.cpu.abilist'], 'x86_64,arm64-v8a')
            self.assertEqual(props['ro.product.cpu.abilist64'], 'x86_64,arm64-v8a')
            self.assertNotIn('ro.unrelated', props)
            self.assertIn(b'arm64_exe', archive.read('service.sh'))
            self.assertEqual(report['files'], len(names) - 4)

    def test_an_image_without_a_translator_is_refused(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(sysimg.ImageError, 'no ARM translator'):
            self.build(folder, with_translator=False)

    def test_an_image_that_does_not_enable_the_bridge_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder); tree = folder / 'tree'; translator_tree(tree)
            (tree / 'system/build.prop').write_text('ro.dalvik.vm.native.bridge=0\n')
            image = folder / 'fs.img'; make_ext4(tree, image)
            disk = folder / 'system.img'; make_disk(image, disk)
            with disk.open('rb') as f, self.assertRaisesRegex(sysimg.ImageError, 'does not enable'):
                arm_translation.build_module(arm_translation.open_system(f), folder / 'm.zip')


class FakeController:
    arch = 'x86_64'; abi = 'x86_64'; api = 37
    image_tag = 'default'

    def __init__(self, root, abilist='x86_64,arm64-v8a', probe_ok=True):
        self.root = Path(root); self.config = {'android': 17}
        self.calls = []; self.boots = 0; self.abilist = abilist; self.probe_ok = probe_ok
        (self.root).mkdir(exist_ok=True)

    def boot(self): self.boots += 1
    def stop(self): pass

    def adb(self, *args, **kwargs):
        self.calls.append(args)
        out, code = '', 0
        if args[:3] == ('shell', 'getprop', 'ro.product.cpu.abilist'): out = self.abilist + '\n'
        elif args[:3] == ('shell', 'getprop', 'ro.dalvik.vm.native.bridge'): out = 'libzygisk.solibndk_translation.so\n'
        elif args[:2] == ('shell', 'test'): code = 0
        elif args[:3] == ('shell', provision.PROBE, 'echo'):
            out, code = ('arm64-ok\n', 0) if self.probe_ok else ('', 139)
        return subprocess.CompletedProcess(args, code, out, '')


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.apk = self.root / 'Magisk.apk'
        with zipfile.ZipFile(self.apk, 'w') as z: z.writestr('lib/arm64-v8a/libbusybox.so', b'\x7fELF arm64 busybox')
        self.module = self.root / 'module.zip'; self.module.write_bytes(b'module')

    def tearDown(self): self.temp.cleanup()

    def run_provision(self, controller):
        with mock.patch.object(provision.subsystem, 'Controller', return_value=controller), \
                mock.patch.object(provision.core, 'magisk_apk', return_value=self.apk), \
                mock.patch.object(provision.core, 'verify'), mock.patch.object(provision.core, 'adb_root'), \
                mock.patch.object(provision.core, 'wait_device'), mock.patch.object(provision.core, 'ensure_magisk_env') as env, \
                mock.patch.object(provision.core, 'magisk_binary', return_value=('/debug_ramdisk/magisk', '31.0')), \
                mock.patch.object(provision, 'build_module', return_value=self.module):
            report = provision.provision(self.root, self.root)
        return report, env

    def test_installs_the_module_cold_boots_and_proves_it_with_an_arm64_program(self):
        controller = FakeController(self.root / 'state')
        report, env = self.run_provision(controller)
        env.assert_called_once()
        shell = [call for call in controller.calls if call[0] == 'shell']
        self.assertIn(('shell', '/debug_ramdisk/magisk', '--install-module', provision.GUEST_MODULE), shell)
        self.assertEqual(controller.boots, 2)           # once to install, once more cold
        self.assertTrue(report['arm64_program_ran'])
        self.assertEqual(json.loads((controller.root / 'arm-translation-report.json').read_text()), report)
        self.assertTrue(any(call[0] == 'shell' and 'rm' in call and provision.PROBE_DIR in call for call in controller.calls))

    def test_a_guest_that_does_not_list_arm64_fails_loudly(self):
        with self.assertRaisesRegex(RuntimeError, 'does not list arm64-v8a'):
            self.run_provision(FakeController(self.root / 'state', abilist='x86_64'))

    def test_an_arm64_program_that_crashes_is_reported_not_ignored(self):
        with self.assertRaisesRegex(RuntimeError, 'could not run through the translator'):
            self.run_provision(FakeController(self.root / 'state', probe_ok=False))

    def test_apple_silicon_does_nothing(self):
        controller = FakeController(self.root / 'state'); controller.arch = 'arm64'
        with mock.patch.object(provision.subsystem, 'Controller', return_value=controller):
            self.assertIsNone(provision.provision(self.root, self.root))
        self.assertEqual(controller.boots, 0)

    def test_a_prebuilt_module_skips_the_image(self):
        controller = FakeController(self.root / 'state')
        with mock.patch.dict(os.environ, {'ARM_TRANSLATION_MODULE': str(self.module)}):
            self.assertEqual(provision.build_module(self.root, controller, self.root), self.module)


if __name__ == '__main__':
    unittest.main()

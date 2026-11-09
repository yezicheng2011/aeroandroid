"""extract_tar must work on macOS's /usr/bin/python3 (3.9.6), which has no tarfile filters."""
import importlib.util
import io
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('setup_offline_tar', ROOT / 'scripts/setup-offline-mac.py')
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)


def make_tar(path, entries):
    with tarfile.open(path, 'w:gz') as t:
        for name, kind, extra in entries:
            info = tarfile.TarInfo(name)
            if kind == 'dir':
                info.type = tarfile.DIRTYPE; info.mode = 0o755; t.addfile(info)
            elif kind == 'file':
                data, mode = extra
                info.size = len(data); info.mode = mode; t.addfile(info, io.BytesIO(data))
            elif kind == 'sym':
                info.type = tarfile.SYMTYPE; info.linkname = extra; t.addfile(info)
            elif kind == 'hard':
                info.type = tarfile.LNKTYPE; info.linkname = extra; info.mode = 0o755; t.addfile(info)
            elif kind == 'fifo':
                info.type = tarfile.FIFOTYPE; t.addfile(info)


JDK = [('jdk/', 'dir', None), ('jdk/Contents/', 'dir', None), ('jdk/Contents/Home/', 'dir', None),
       ('jdk/Contents/Home/bin/', 'dir', None),
       ('jdk/Contents/Home/bin/java', 'file', (b'#!/bin/sh\n', 0o755)),
       ('jdk/Contents/Home/release', 'file', (b'JAVA_VERSION="17"\n', 0o4664)),
       ('jdk/Contents/Home/lib/', 'dir', None),
       ('jdk/Contents/Home/lib/libjli.dylib', 'file', (b'lib', 0o644)),
       ('jdk/Contents/MacOS/', 'dir', None),
       ('jdk/Contents/MacOS/libjli.dylib', 'sym', '../Home/lib/libjli.dylib'),
       ('jdk/Contents/Home/bin/java2', 'hard', 'jdk/Contents/Home/bin/java')]


class ExtractTarTests(unittest.TestCase):
    def run_both(self, check):
        """Run with the stdlib filter when present, and always with the 3.9.6 fallback."""
        modes = [False] + ([True] if hasattr(tarfile, 'data_filter') else [])
        for native in modes:
            with self.subTest(native_filter=native), tempfile.TemporaryDirectory() as tmp:
                patch = mock.patch.object(installer, 'tarfile', wraps=tarfile) if not native else None
                if patch:
                    with patch as fake:
                        del fake.data_filter   # behave like Python 3.9.6
                        self.assertFalse(hasattr(installer.tarfile, 'data_filter'))
                        check(Path(tmp))
                else:
                    check(Path(tmp))

    def test_jdk_layout_keeps_exec_bits_and_internal_symlinks(self):
        def check(tmp):
            archive = tmp / 'jdk.tar.gz'; make_tar(archive, JDK)
            dest = tmp / 'runtime/java'
            installer.extract_tar(archive, dest)
            java = dest / 'jdk/Contents/Home/bin/java'
            self.assertTrue(os.access(java, os.X_OK))
            self.assertFalse(stat.S_IMODE((dest / 'jdk/Contents/Home/release').stat().st_mode) & 0o7022)
            link = dest / 'jdk/Contents/MacOS/libjli.dylib'
            self.assertTrue(link.is_symlink()); self.assertEqual(os.readlink(link), '../Home/lib/libjli.dylib')
            self.assertEqual(link.read_bytes(), b'lib')
            self.assertEqual((dest / 'jdk/Contents/Home/bin/java2').read_bytes(), b'#!/bin/sh\n')
            # Retry over a previous (partial) extraction succeeds.
            installer.extract_tar(archive, dest)
            self.assertTrue(link.is_symlink())
            self.assertEqual(next((dest).glob('*/Contents/Home')), dest / 'jdk/Contents/Home')
        self.run_both(check)

    def test_unsafe_members_are_refused(self):
        bad = [[('/etc/evil', 'file', (b'x', 0o644))],
               [('jdk/../../evil', 'file', (b'x', 0o644))],
               [('jdk/', 'dir', None), ('jdk/out', 'sym', '../../outside')],
               [('jdk/', 'dir', None), ('jdk/abs', 'sym', '/etc/passwd')],
               [('jdk/', 'dir', None), ('jdk/up', 'sym', '..'), ('jdk/up/up2', 'sym', '..'), ('jdk/up/up2/evil', 'file', (b'x', 0o644))],
               [('jdk/', 'dir', None), ('jdk/h', 'hard', '../outside')],
               [('jdk/', 'dir', None), ('jdk/fifo', 'fifo', None)]]
        def check(tmp):
            fallback = not hasattr(installer.tarfile, 'data_filter')
            for index, entries in enumerate(bad):
                archive = tmp / f'bad{index}.tar.gz'; make_tar(archive, entries)
                dest = tmp / f'dest{index}'
                if fallback:
                    with self.assertRaises(RuntimeError, msg=str(entries)):
                        installer.extract_tar(archive, dest)
                else:
                    # The stdlib 'data' filter strips a leading '/' instead of refusing.
                    try: installer.extract_tar(archive, dest)
                    except Exception: pass
                self.assertFalse((tmp / 'evil').exists())
                self.assertFalse((tmp / 'outside').exists())
        self.run_both(check)


if __name__ == '__main__':
    unittest.main()

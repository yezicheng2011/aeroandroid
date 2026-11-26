"""Live shared-folder RPC tests: direct data access, confinement and revocation."""
import base64
import errno
import http.client
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'backend/storage_service.py'
spec = importlib.util.spec_from_file_location('storage_service', MODULE)
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


class StorageServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shared = self.root / 'Shared folder'
        self.shared.mkdir()
        self.share_id = 'a' * 32
        self.document = self.share_id + ':'
        self.token = 'b' * 64
        self.configure()
        self.server = storage.StorageServer(self.root, self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def configure(self, read_only=False, revoke=False):
        entries = [] if revoke else [{'id': self.share_id, 'name': 'Mac files', 'path': str(self.shared), 'read_only': read_only}]
        storage.atomic_json(self.root / 'storage-shares.json', {'shares': entries})

    def request(self, operation, token=None, **params):
        client = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            client.request('POST', '/rpc', json.dumps({'op': operation, **params}),
                           {'Authorization': 'Bearer ' + (self.token if token is None else token),
                            'Content-Type': 'application/json'})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def call(self, operation, **params):
        status, response = self.request(operation, **params)
        self.assertEqual(status, 200)
        self.assertTrue(response['ok'], response)
        return response['data']

    def error(self, operation, code=None, **params):
        status, response = self.request(operation, **params)
        self.assertEqual(status, 200)
        self.assertFalse(response['ok'], response)
        if code is not None:
            self.assertEqual(response['code'], code, response)
            self.assertEqual(response['errno'], errno.errorcode[code], response)
        return response

    def test_only_authenticated_loopback_requests_can_access_roots(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        self.assertEqual(self.request('roots', token='wrong')[0], 403)
        self.assertEqual(self.call('roots'), [{'id': self.share_id, 'name': 'Mac files', 'document': self.document, 'read_only': False}])
        response = self.request('roots', token='non-ascii-é')[1]
        self.assertFalse(response['ok'])

    def test_error_symbols_are_portable_between_mac_and_android(self):
        # errno integers differ across Darwin and Linux/Android; clients consume the symbol.
        status, denied = self.request('roots', token='wrong')
        self.assertEqual((status, denied['errno']), (403, 'EACCES'))
        stale = OSError(errno.ESTALE, 'Document changed on the Mac; reopen it')
        from unittest.mock import patch
        with patch.object(self.server.folders, 'invoke', side_effect=stale):
            response = self.request('stat', document=self.document)[1]
        self.assertEqual(response['errno'], 'ESTALE')
        self.assertEqual(response['code'], errno.ESTALE)
        (self.root / 'storage-shares.json').write_text('invalid configuration')
        invalid = self.request('roots')[1]
        self.assertEqual(invalid['errno'], 'EINVAL')

    def test_mac_changes_are_visible_to_android_without_import(self):
        folder = self.shared / 'Documents with spaces'
        folder.mkdir()
        file = folder / 'report résumé.txt'
        file.write_bytes(b'first revision')
        root_items = self.call('list', document=self.document)
        self.assertTrue(root_items[0]['directory'])
        document = self.document + 'Documents with spaces/report résumé.txt'
        metadata = self.call('stat', document=document)
        self.assertEqual(metadata['mime'], 'text/plain')
        self.assertEqual(metadata['size'], 14)
        self.assertEqual(base64.b64decode(self.call('read', document=document, offset=6, size=8)['data']), b'revision')
        file.write_bytes(b'updated by Finder')
        self.assertEqual(base64.b64decode(self.call('read', document=document, offset=0, size=100)['data']), b'updated by Finder')

    def test_listing_survives_a_file_deleted_on_the_mac_while_it_is_read(self):
        for name in ('a.txt', 'b.txt', 'c.txt'):
            (self.shared / name).write_bytes(b'data')
        folders = self.server.folders
        describe = folders.metadata

        def delete_the_rest(share, document, info, name):
            # Finder removes the other files after the folder was read but before they are examined.
            for other in self.shared.iterdir():
                if other.name != name: other.unlink()
            return describe(share, document, info, name)
        from unittest.mock import patch
        with patch.object(folders, 'metadata', side_effect=delete_the_rest):
            listed = self.call('list', document=self.document)
        self.assertEqual(len(listed), 1)   # the survivor, not ENOENT for the whole folder
        self.assertEqual([item['name'] for item in self.call('list', document=self.document)], [listed[0]['name']])

    def test_random_access_writes_truncation_and_fsync_change_the_mac_file(self):
        metadata = self.call('create', parent=self.document, name='notes.txt', mime='text/plain')
        document = metadata['document']
        payload = base64.b64encode(b'hello world').decode()
        self.assertEqual(self.call('write', document=document, offset=0, data=payload), {'written': 11})
        self.call('write', document=document, offset=6, data=base64.b64encode(b'Mac').decode())
        self.call('truncate', document=document, size=9)
        self.call('fsync', document=document)
        self.assertEqual((self.shared / 'notes.txt').read_bytes(), b'hello Mac')
        self.assertEqual(self.call('read', document=document, offset=100, size=100), {'data': ''})

    def test_append_writes_do_not_overwrite_when_offsets_are_stale(self):
        (self.shared / 'log.txt').write_bytes(b'initial')
        document = self.document + 'log.txt'
        for text in (b' one', b' two'):
            self.call('write', document=document, offset=0, append=True, data=base64.b64encode(text).decode())
        self.assertEqual((self.shared / 'log.txt').read_bytes(), b'initial one two')

    def test_create_rename_and_empty_directory_delete(self):
        directory = self.call('create', parent=self.document, name='New folder', mime=storage.DIRECTORY_MIME)
        child = self.call('create', parent=directory['document'], name='file.bin', mime='application/octet-stream')
        renamed = self.call('rename', document=child['document'], name='renamed.bin')
        self.assertEqual(renamed['document'], self.document + 'New folder/renamed.bin')
        self.assertTrue((self.shared / 'New folder/renamed.bin').exists())
        self.error('delete', document=directory['document'])
        self.call('delete', document=renamed['document'])
        self.call('delete', document=directory['document'])
        self.assertFalse((self.shared / 'New folder').exists())

    def test_create_and_rename_never_overwrite_existing_documents(self):
        (self.shared / 'one').write_bytes(b'one')
        (self.shared / 'two').write_bytes(b'two')
        self.error('create', errno.EEXIST, parent=self.document, name='one', mime='text/plain')
        self.error('rename', errno.EEXIST, document=self.document + 'one', name='two')
        self.assertEqual((self.shared / 'one').read_bytes(), b'one')
        self.assertEqual((self.shared / 'two').read_bytes(), b'two')
        self.call('rename', document=self.document + 'one', name='one')

    def test_read_only_configuration_blocks_every_mutation(self):
        (self.shared / 'one').write_bytes(b'one')
        self.configure(read_only=True)
        document = self.document + 'one'
        self.assertTrue(self.call('stat', document=document)['read_only'])
        for operation, params in [('write', {'offset': 0, 'data': 'b25l'}), ('truncate', {'size': 0}),
                                  ('fsync', {}), ('delete', {}), ('rename', {'name': 'new'})]:
            with self.subTest(operation=operation):
                self.error(operation, errno.EROFS, document=document, **params)
        self.error('create', errno.EROFS, parent=self.document, name='new', mime='text/plain')
        self.assertEqual((self.shared / 'one').read_bytes(), b'one')

    def test_revocation_takes_effect_on_the_next_request(self):
        (self.shared / 'one').write_bytes(b'one')
        self.call('stat', document=self.document + 'one')
        self.configure(revoke=True)
        self.assertEqual(self.call('roots'), [])
        self.error('read', errno.ENOENT, document=self.document + 'one', offset=0, size=1)
        self.error('write', errno.ENOENT, document=self.document + 'one', offset=0, data='eA==')

    def test_replacing_a_shared_root_ancestor_with_a_symlink_cannot_redirect_access(self):
        ancestor = self.root / 'selected-parent'
        ancestor.mkdir()
        selected = ancestor / 'shared'
        selected.mkdir()
        (selected / 'file').write_bytes(b'approved')
        storage.atomic_json(self.root / 'storage-shares.json', {'shares': [
            {'id': self.share_id, 'name': 'Selected', 'path': str(selected), 'read_only': False}]})
        document = self.document + 'file'
        self.assertEqual(base64.b64decode(self.call('read', document=document, offset=0, size=100)['data']), b'approved')
        private = self.root / 'private'
        (private / 'shared').mkdir(parents=True)
        (private / 'shared/file').write_bytes(b'not shared')
        ancestor.rename(self.root / 'old-parent')
        ancestor.symlink_to(private, target_is_directory=True)
        self.error('read', document=document, offset=0, size=100)
        self.error('write', document=document, offset=0, data='eA==')
        self.assertEqual((private / 'shared/file').read_bytes(), b'not shared')

    def test_traversal_and_root_mutations_are_rejected(self):
        for path in ('../secret', '/etc/passwd', 'folder/../../secret', 'folder//file', './file', 'file\0hidden'):
            with self.subTest(path=path):
                self.error('stat', document=self.document + path)
        for name in ('..', '.', '/', 'folder/file', '', 'file\0hidden'):
            self.error('create', parent=self.document, name=name, mime='text/plain')
        self.error('delete', errno.EACCES, document=self.document)
        self.error('rename', errno.EACCES, document=self.document, name='new')
        self.assertTrue(self.shared.exists())

    def test_symlinks_and_special_files_are_not_exposed(self):
        outside = self.root / 'private'; outside.mkdir()
        (outside / 'secret').write_bytes(b'private')
        (self.shared / 'link').symlink_to(outside, target_is_directory=True)
        (self.shared / 'direct-link').symlink_to(outside / 'secret')
        os.mkfifo(self.shared / 'pipe')
        self.assertEqual(self.call('list', document=self.document), [])
        for relative in ('link/secret', 'direct-link', 'pipe'):
            for operation, params in [('stat', {}), ('read', {'offset': 0, 'size': 10}),
                                      ('write', {'offset': 0, 'data': 'eA=='})]:
                with self.subTest(relative=relative, operation=operation):
                    self.error(operation, document=self.document + relative, **params)
        self.assertEqual((outside / 'secret').read_bytes(), b'private')

    def test_offsets_payload_limits_and_unknown_operations_are_checked(self):
        (self.shared / 'one').write_bytes(b'one')
        document = self.document + 'one'
        for offset in (-1, True, '0', 1 << 63):
            self.error('read', errno.EINVAL, document=document, offset=offset, size=1)
        self.error('read', errno.EINVAL, document=document, offset=0, size=storage.CHUNK_SIZE + 1)
        self.error('write', errno.EINVAL, document=document, offset=0, data='invalid!')
        self.error('write', errno.EINVAL, document=document, offset=0, data='eA==', append='yes')
        self.error('unknown', errno.EINVAL)
        self.assertEqual((self.shared / 'one').read_bytes(), b'one')

    def test_large_directory_is_paginated_without_losing_documents(self):
        for index in range(601):
            (self.shared / f'file-{index:04}.txt').touch()
        self.assertEqual(len(self.call('list', document=self.document)), 256)
        documents = []
        for offset, expected in ((0, 256), (256, 256), (512, 89)):
            page = self.call('list', document=self.document, offset=offset, limit=256)
            self.assertEqual(len(page), expected)
            documents.extend(item['document'] for item in page)
        self.assertEqual(len(set(documents)), 601)
        self.assertEqual(documents, sorted(documents))
        self.error('list', errno.EINVAL, document=self.document, offset=-1)
        self.error('list', errno.EINVAL, document=self.document, limit=257)
        self.error('list', errno.EINVAL, document=self.document, limit=0)

    def test_colon_named_directories_keep_unambiguous_document_paths(self):
        directory = self.call('create', parent=self.document, name='Folder:', mime=storage.DIRECTORY_MIME)
        document = self.call('create', parent=directory['document'], name='file.txt', mime='text/plain')
        self.assertEqual(document['document'], self.document + 'Folder:/file.txt')
        self.assertEqual(self.call('list', document=directory['document'])[0]['document'], document['document'])
        self.call('write', document=document['document'], offset=0, data='b25l')
        self.assertEqual((self.shared / 'Folder:/file.txt').read_bytes(), b'one')

    def test_open_document_identity_prevents_writing_a_replacement_file(self):
        file = self.shared / 'document.txt'; file.write_bytes(b'original')
        document = self.document + file.name
        identity = self.call('stat', document=document)['file_id']
        self.call('write', document=document, offset=0, data='T3JpZ2luYWw=', expected_file_id=identity)
        file.rename(self.shared / 'old-document.txt')
        file.write_bytes(b'replacement')
        for operation, params in [('stat', {}), ('read', {'offset': 0, 'size': 5}),
                                  ('write', {'offset': 0, 'data': 'eA=='}), ('truncate', {'size': 0}), ('fsync', {})]:
            with self.subTest(operation=operation):
                self.error(operation, errno.ESTALE, document=document, expected_file_id=identity, **params)
        self.assertEqual(file.read_bytes(), b'replacement')
        self.assertNotEqual(self.call('stat', document=document)['file_id'], identity)

    def test_watcher_exits_when_the_owned_emulator_stops(self):
        (self.root / 'storage-token').write_text(self.token)
        emulator = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        service = None
        try:
            birth = subprocess.run(['/bin/ps', '-p', str(emulator.pid), '-o', 'lstart='], capture_output=True, text=True, check=True).stdout.strip()
            expected = {'pid': emulator.pid, 'birth': birth}
            storage.atomic_json(self.root / 'emulator.json', expected)
            self.assertTrue(storage.emulator_alive(self.root, expected))
            self.assertFalse(storage.emulator_alive(self.root, {**expected, 'birth': 'reused pid'}))
            service = subprocess.Popen([sys.executable, str(MODULE), '--root', str(self.root), '--watch-emulator'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            record = self.root / 'storage-port.json'
            deadline = time.monotonic() + 5
            while not record.exists() and service.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(record.exists())
            emulator.terminate(); emulator.wait(timeout=5)
            service.communicate(timeout=5)
            self.assertEqual(service.returncode, 0)
            self.assertFalse(record.exists())
        finally:
            if emulator.poll() is None:
                emulator.terminate(); emulator.wait(timeout=5)
            if service is not None and service.poll() is None:
                service.terminate(); service.communicate(timeout=5)

    def test_cli_publishes_a_private_ephemeral_port_record(self):
        (self.root / 'storage-token').write_text(self.token)
        child = subprocess.Popen([sys.executable, str(MODULE), '--root', str(self.root)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            record = self.root / 'storage-port.json'
            deadline = time.monotonic() + 5
            while not record.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(record.exists(), child.stderr.read() if child.poll() is not None else 'service did not start')
            self.assertGreater(json.loads(record.read_text())['port'], 1024)
            self.assertEqual(record.stat().st_mode & 0o777, 0o600)
        finally:
            child.terminate()
            child.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()

"""Shared-folder lifecycle across controller, real local RPC and a fixture Android device."""
import base64
import http.client
import json
from pathlib import Path
import shutil
import stat
import unittest
from unittest.mock import patch

import test_controller

subsystem = test_controller.subsystem
SERVICE = Path(__file__).resolve().parents[1] / 'backend/storage_service.py'


class StorageControllerTests(unittest.TestCase):
    def setUp(self):
        test_controller.IntegrationTests.setUp(self)
        shutil.copy2(SERVICE, self.root / 'bridge-home/backend/storage_service.py')
        self.shared = self.root / 'Live shared folder'
        self.shared.mkdir()
        (self.shared / 'notes.txt').write_bytes(b'from Finder')

    def tearDown(self):
        try:
            self.controller.stop()
        finally:
            test_controller.IntegrationTests.tearDown(self)

    def rpc(self, **request):
        record = subsystem.read_json(self.controller.root / 'storage-service.json', {})
        token = (self.controller.root / 'storage-token').read_text()
        connection = http.client.HTTPConnection('127.0.0.1', record['port'], timeout=5)
        try:
            body = json.dumps(request).encode()
            connection.request('POST', '/rpc', body, {'Authorization': 'Bearer ' + token,
                                                     'Content-Type': 'application/json'})
            response = connection.getresponse()
            return json.loads(response.read())
        finally:
            connection.close()

    def test_share_configuration_works_without_starting_android(self):
        self.assertEqual(self.controller.storage_shares(), {'shares': [], 'running': False})
        first = self.controller.share_folder(str(self.shared))
        self.assertFalse(first['running'])
        share = first['shares'][0]
        self.assertEqual(share['path'], str(self.shared))
        updated = self.controller.share_folder(str(self.shared), read_only=True)
        self.assertEqual(len(updated['shares']), 1)
        self.assertEqual(updated['shares'][0]['id'], share['id'])
        self.assertTrue(updated['shares'][0]['read_only'])
        self.assertFalse((self.root / 'device.json').exists())
        for path, read_only in (('relative', False), (str(self.shared), 'yes')):
            with self.assertRaises(subsystem.SubsystemError):
                self.controller.share_folder(path, read_only)
        with self.assertRaises(subsystem.SubsystemError):
            self.controller.share_folder(str(self.shared / 'notes.txt'))

    def test_connect_reads_and_writes_the_original_file_and_reuses_service(self):
        share = self.controller.share_folder(str(self.shared))['shares'][0]
        started = self.controller.start_storage()
        self.assertTrue(started['running'])
        roles = subsystem.read_json(self.controller.root / 'communications.json', {})
        self.assertTrue(roles['phone']['selected'])
        self.assertTrue(roles['messages']['selected'])
        record = subsystem.read_json(self.controller.root / 'storage-service.json', {})
        document = share['id'] + ':notes.txt'
        data = self.rpc(op='read', document=document, offset=0, size=100)['data']['data']
        self.assertEqual(base64.b64decode(data), b'from Finder')
        self.rpc(op='write', document=document, offset=0, data=base64.b64encode(b'from Android').decode())
        self.assertEqual((self.shared / 'notes.txt').read_bytes(), b'from Android')
        self.controller.boot()
        self.assertEqual(subsystem.read_json(self.controller.root / 'storage-service.json', {})['pid'], record['pid'])
        commands = [json.loads(line) for line in (self.root / 'shell-commands.jsonl').read_text().splitlines()]
        self.assertTrue(any(command[:2] == ['content', 'call'] and 'storage-config' in command for command in commands))
        self.assertEqual(stat.S_IMODE((self.controller.root / 'storage-token').stat().st_mode), 0o600)
        self.controller.stop()
        self.assertFalse(self.controller.storage_shares()['running'])
        self.assertFalse(self.controller.process_matches(record))
        self.assertFalse((self.controller.root / 'storage-port.json').exists())
        self.assertTrue((self.shared / 'notes.txt').exists())
        self.controller.boot()  # exported Mac apps also call boot; sharing restores automatically
        self.assertTrue(self.controller.storage_shares()['running'])
        self.assertEqual(self.rpc(op='roots')['data'][0]['id'], share['id'])

    def test_revoke_one_folder_without_copying_or_deleting_data(self):
        first = self.controller.share_folder(str(self.shared))['shares'][0]
        other = self.root / 'Another folder'; other.mkdir()
        self.controller.share_folder(str(other), read_only=True)
        self.controller.start_storage()
        self.controller.unshare_folder(first['id'])
        self.assertTrue(self.controller.storage_shares()['running'])
        self.assertFalse(self.rpc(op='read', document=first['id'] + ':notes.txt', offset=0, size=10)['ok'])
        self.assertEqual((self.shared / 'notes.txt').read_bytes(), b'from Finder')
        remaining = self.controller.storage_shares()['shares'][0]
        self.assertTrue(remaining['read_only'])
        self.controller.unshare_folder(remaining['id'])
        self.assertEqual(self.controller.storage_shares(), {'shares': [], 'running': False})
        self.assertTrue(other.is_dir())
        self.assertTrue(self.controller.device())  # revocation does not shut down Android apps

    def test_failed_guest_setup_is_reported_and_cleans_local_service(self):
        self.controller.share_folder(str(self.shared))
        original = self.controller.adb
        def adb(*arguments, **kwargs):
            if arguments[:3] == ('shell', 'content', 'call'):
                return test_controller.subprocess.CompletedProcess(arguments, 0, 'provider unavailable', '')
            return original(*arguments, **kwargs)
        with patch.object(self.controller, 'adb', side_effect=adb):
            with self.assertRaisesRegex(subsystem.SubsystemError, 'did not accept'):
                self.controller.start_storage()
        self.assertFalse(self.controller.storage_shares()['running'])
        self.assertFalse((self.controller.root / 'storage-port.json').exists())


if __name__ == '__main__':
    unittest.main()

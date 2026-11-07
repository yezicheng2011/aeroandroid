"""Controller integration coverage for real guest-owned AppWidget instances."""
import base64
import json
import unittest
from unittest.mock import patch

import test_controller

subsystem = test_controller.subsystem
PROVIDER = 'com.example.first/com.example.first.ExampleWidget'


class WidgetTests(unittest.TestCase):
    setUp = test_controller.IntegrationTests.setUp

    def tearDown(self):
        try:
            self.controller.stop()
        finally:
            test_controller.IntegrationTests.tearDown(self)

    def call(self, action, **params):
        return subsystem.dispatch(self.controller, action, params)

    def create(self, provider=PROVIDER, width=320, height=180):
        return self.call('add-widget', provider=provider, width_dp=width, height_dp=height)['widget']

    def test_polling_stopped_android_never_starts_it_or_allocates_graphics(self):
        with patch.object(self.controller, 'native_session', side_effect=AssertionError('Background polling started Android')):
            self.assertEqual(self.call('widgets'), {'widgets': [], 'running': False})
        self.assertFalse((self.root / 'device.json').exists())
        self.assertFalse((self.controller.root / 'graphics.json').exists())
        self.assertFalse(self.controller.configured())

    def test_provider_picker_installs_live_bridge_and_lists_android_metadata(self):
        providers = self.call('widget-providers')['providers']
        self.assertEqual(len(providers), 2)
        self.assertEqual(providers[0]['provider'], PROVIDER)
        self.assertTrue(providers[0]['has_configuration'])
        self.assertEqual(providers[0]['min_width_dp'], 64)
        self.assertEqual(providers[1]['resize_mode'], 3)
        self.assertTrue((self.controller.root / 'graphics.json').is_file())
        self.assertEqual(self.call('widgets'), {'widgets': [], 'running': True})

    def test_multiple_instances_resize_and_delete_keep_independent_guest_state(self):
        first = self.create()
        second = self.create('com.example.first/.ExampleWidget', width=220, height=140)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(len(self.call('widgets')['widgets']), 2)
        resized = self.call('resize-widget', id=first['id'], width_dp=400, height_dp=240)['widget']
        self.assertEqual((resized['width_dp'], resized['height_dp']), (400, 240))
        by_id = {value['id']: value for value in self.call('widgets')['widgets']}
        self.assertEqual((by_id[second['id']]['width_dp'], by_id[second['id']]['height_dp']), (220, 140))
        self.assertEqual(self.call('delete-widget', id=first['id']), {'deleted': True, 'id': first['id']})
        self.assertEqual([value['id'] for value in self.call('widgets')['widgets']], [second['id']])
        with self.assertRaisesRegex(subsystem.SubsystemError, 'no longer exists'):
            self.call('widget-session', id=first['id'])

    def test_native_session_uses_widget_dp_and_setup_state_instead_of_app_resolution(self):
        self.controller.configure({'resolution': '1920x1080/320', 'fps': 15})
        widget = self.create(width=360, height=144)
        initial = self.call('widget-session', id=widget['id'])
        self.assertEqual((initial['width'], initial['height'], initial['dpi']), (360, 144, 160))
        self.assertEqual(initial['fps'], 15)
        self.assertEqual((initial['package'], initial['widget_id']), (subsystem.COMPANION, widget['id']))
        self.assertTrue(initial['widget_setup'])
        self.assertFalse(initial['widget_configure'])
        self.assertEqual(initial['transport'], 'rgba-tcp-v1')
        # Binding/configuration is completed by Android's standard consent UI,
        # not inferred from a successful desktop-window connection.
        state = json.loads((self.root / 'widget-state.json').read_text())
        state['widgets'][0].update(bound=True, configured=True, needs_permission=False)
        (self.root / 'widget-state.json').write_text(json.dumps(state))
        ready = self.call('widget-session', id=widget['id'])
        self.assertFalse(ready['widget_setup'])
        configure = self.call('configure-widget', id=widget['id'])
        self.assertTrue(configure['widget_configure'])
        self.assertTrue(configure['widget_setup'])
        self.assertEqual((configure['port'], configure['token']), (ready['port'], ready['token']))

    def test_cancelled_permission_can_remove_instance_and_restart_restores_remaining_ids(self):
        pending = self.create()
        kept = self.create('com.example.clock/.ClockWidget', width=128, height=128)
        self.assertTrue(pending['needs_permission'])
        self.assertFalse(pending['bound'])
        self.call('delete-widget', id=pending['id'])
        self.controller.stop()
        self.assertEqual(self.call('widgets'), {'widgets': [], 'running': False})
        self.assertFalse((self.root / 'device.json').exists())
        # Only an explicit open starts Android again; the persisted guest ID
        # still identifies the same instance after the VM restarts.
        resumed = self.call('widget-session', id=kept['id'])
        self.assertEqual(resumed['widget_id'], kept['id'])
        self.assertEqual([value['id'] for value in self.call('widgets')['widgets']], [kept['id']])

    def test_invalid_ids_dimensions_and_components_are_rejected_before_start(self):
        requests = []
        for identifier in (True, False, 0, -1, 2 ** 40, '1', 1.0, None):
            for action in ('widget-session', 'configure-widget', 'delete-widget'):
                requests.append((action, {'id': identifier}))
            requests.append(('resize-widget', {'id': identifier, 'width_dp': 320, 'height_dp': 180}))
        for size in (True, 63, 1281, 320.0, '320', None):
            requests.append(('add-widget', {'provider': PROVIDER, 'width_dp': size, 'height_dp': 180}))
            requests.append(('resize-widget', {'id': 1, 'width_dp': 320, 'height_dp': size}))
        for provider in ('', 'com.example', 'com.example/.Widget; touch /tmp/widget',
                         'com.example/$(whoami)', 'com.example/.Widget\n', None):
            requests.append(('add-widget', {'provider': provider, 'width_dp': 320, 'height_dp': 180}))
        with patch.object(self.controller, 'native_session', side_effect=AssertionError('Invalid input started Android')):
            for action, params in requests:
                with self.subTest(action=action, params=params):
                    with self.assertRaises(subsystem.SubsystemError):
                        subsystem.dispatch(self.controller, action, params)
        self.assertFalse((self.root / 'device.json').exists())
        self.assertFalse((self.root / 'widget-state.json').exists())

    def test_removed_provider_and_missing_instances_report_guest_errors(self):
        with self.assertRaisesRegex(subsystem.SubsystemError, 'no longer installed'):
            self.create('com.missing/.Widget')
        with self.assertRaisesRegex(subsystem.SubsystemError, 'no longer exists'):
            self.call('resize-widget', id=999, width_dp=320, height_dp=180)
        with self.assertRaisesRegex(subsystem.SubsystemError, 'no longer exists'):
            self.call('delete-widget', id=999)
        self.assertEqual(self.call('widgets')['widgets'], [])

    def test_polling_incompatible_bridge_reports_error_without_restarting_it(self):
        self.call('widget-providers')
        before = subsystem.read_json(self.controller.root / 'graphics.json', {})
        with patch.object(self.controller, 'native_session', side_effect=AssertionError('Polling restarted bridge')):
            with patch.object(self.controller, 'bridge', return_value={'notification_access': True}):
                with self.assertRaisesRegex(subsystem.SubsystemError, 'rebuild the guest bridge'):
                    self.call('widgets')
        after = subsystem.read_json(self.controller.root / 'graphics.json', {})
        self.assertEqual(before['pid'], after['pid'])

    def test_bridge_payload_reports_rejection_and_rejects_invalid_json(self):
        def encoded(value):
            return 'Result: Bundle[{payload=' + base64.b64encode(json.dumps(value).encode()).decode() + '}]'
        with self.assertRaisesRegex(subsystem.SubsystemError, 'Widget configuration was cancelled'):
            self.controller.bridge_payload(encoded({'error': 'Widget configuration was cancelled'}))
        for output in ('No result found', 'Row: 0 payload=e30===', encoded([]),
                       'Result: Bundle[{payload=' + base64.b64encode(b'broken json').decode() + '}]'):
            with self.subTest(output=output):
                with self.assertRaises(subsystem.SubsystemError):
                    self.controller.bridge_payload(output)


if __name__ == '__main__':
    unittest.main()

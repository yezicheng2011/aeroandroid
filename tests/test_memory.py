"""Adaptive allocation, legacy settings, and Quick Boot hardware compatibility."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_controller

subsystem = test_controller.subsystem


class MemoryBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.object(subsystem, 'host_arch', return_value='arm64'):
            self.controller = subsystem.Controller(Path(self.temp.name))

    def budget(self, total, available, **config):
        self.controller.config.update(config)
        with patch.object(subsystem, 'host_memory', return_value={'total_mb': total, 'available_mb': available}):
            return self.controller.memory_budget()

    def test_auto_is_default_and_reserves_ram_for_macos(self):
        self.assertEqual(self.controller.config['memory_mode'], 'auto')
        self.assertEqual(self.budget(8192, 7168)['selected_mb'], 4096)
        self.assertEqual(self.budget(16384, 10240)['selected_mb'], 6144)
        self.assertEqual(self.budget(32768, 30000)['selected_mb'], 8192)

    def test_pressure_floor_custom_ceiling_and_alignment(self):
        self.assertEqual(self.budget(8192, 1024)['selected_mb'], 2048)
        self.assertEqual(self.budget(16384, 9999)['selected_mb'], 5888)
        self.assertEqual(self.budget(32768, 30000, memory_max_mb=4096)['selected_mb'], 4096)
        self.assertEqual(self.budget(8192, 1024, memory_min_mb=3072)['selected_mb'], 3072)

    def test_unavailable_host_metrics_use_configured_floor(self):
        with patch.object(subsystem, 'host_memory', return_value=None):
            result = self.controller.memory_budget()
        self.assertEqual((result['selected_mb'], result['source']), (2048, 'fallback'))
        self.assertIsNone(result['host_available_mb'])

    def test_legacy_size_is_manual_until_auto_is_selected(self):
        config = self.controller.loaded_config({'memory_mb': 6144})
        self.assertEqual((config['memory_mode'], config['memory_mb']), ('manual', 6144))
        config = self.controller.loaded_config({'memory_mb': 6144, 'memory_mode': 'auto'})
        self.assertEqual(config['memory_mode'], 'auto')

    def test_manual_mode_uses_exact_size_without_host_probe(self):
        self.controller.config.update(memory_mode='manual', memory_mb=6144)
        with patch.object(subsystem, 'host_memory') as probe:
            self.assertEqual(self.controller.memory_budget()['selected_mb'], 6144)
        probe.assert_not_called()

    def test_invalid_memory_settings_are_rejected(self):
        for change in ({'memory_mode': 'elastic'}, {'memory_mode': True}, {'memory_min_mb': True},
                       {'memory_max_mb': '8192'}, {'memory_min_mb': 1024}, {'memory_max_mb': 32768},
                       {'memory_min_mb': 8192, 'memory_max_mb': 4096}, {'memory_min_mb': 2050}):
            with self.subTest(change=change), self.assertRaises(subsystem.SubsystemError):
                self.controller.validate_config({**subsystem.DEFAULTS, **change})

    def test_status_distinguishes_next_estimate_from_active_allocation(self):
        subsystem.atomic_json(self.controller.root / 'emulator.json', {'memory_mb': 6144})
        with patch.object(subsystem, 'host_memory', return_value=None):
            self.assertEqual(self.controller.memory_status(running=True)['active_mb'], 6144)
            status = self.controller.memory_status(running=False)
        self.assertIsNone(status['active_mb'])
        self.assertEqual(status['selected_mb'], 2048)


class HostMemoryTests(unittest.TestCase):
    def stats(self, page_size=16384):
        return (f'Mach Virtual Memory Statistics: (page size of {page_size} bytes)\n'
                'Pages free:                               65536.\n'
                'Pages inactive:                           131072.\n'
                'Pages speculative:                        32768.\n'
                'Pages purgeable:                          65536.\n')

    def probe(self, stats, total=8589934592):
        results = [subprocess.CompletedProcess([], 0, str(total), ''),
                   subprocess.CompletedProcess([], 0, stats, '')]
        with patch.object(subsystem.platform, 'system', return_value='Darwin'), \
                patch.object(subsystem.subprocess, 'run', side_effect=results) as run:
            result = subsystem.host_memory()
        self.assertEqual(run.call_args.kwargs['timeout'], 5)
        return result

    def test_reads_apple_silicon_and_intel_page_sizes_without_double_counting(self):
        self.assertEqual(self.probe(self.stats()), {'total_mb': 8192, 'available_mb': 3584})
        self.assertEqual(self.probe(self.stats(4096)), {'total_mb': 8192, 'available_mb': 896})

    def test_bad_or_incomplete_metrics_fall_back(self):
        for stats in ('unexpected output', self.stats().replace('Pages inactive:', 'Missing:'), self.stats(0)):
            self.assertIsNone(self.probe(stats))
        self.assertIsNone(self.probe(self.stats(), total='bad'))
        with patch.object(subsystem.platform, 'system', return_value='Darwin'), \
                patch.object(subsystem.subprocess, 'run', side_effect=subprocess.TimeoutExpired('vm_stat', 5)):
            self.assertIsNone(subsystem.host_memory())

    def test_reclaimable_estimate_cannot_exceed_physical_ram(self):
        self.assertEqual(self.probe(self.stats(), total=2 * 1024**3)['available_mb'], 2048)


class MemoryBootTests(unittest.TestCase):
    setUp = test_controller.IntegrationTests.setUp
    tearDown = test_controller.IntegrationTests.tearDown

    def test_boot_applies_one_budget_and_keeps_running_allocation_stable(self):
        with patch.object(subsystem, 'host_memory', return_value={'total_mb': 16384, 'available_mb': 10240}) as probe:
            self.controller.boot()
        probe.assert_called_once_with()
        args = json.loads((self.root / 'emulator-argv.json').read_text())
        self.assertEqual(args[args.index('-memory') + 1], '6144')
        avd = self.controller.avd_home / f'{self.controller.avd}.avd'
        self.assertIn('hw.ramSize=6144', (avd / 'config.ini').read_text())
        record = subsystem.read_json(self.controller.root / 'emulator.json', {})
        self.assertEqual((record['memory_mb'], record['memory_mode']), (6144, 'auto'))
        with patch.object(subsystem, 'host_memory', return_value=None):
            self.controller.boot()  # reopening an app must not resize a live guest
            status = self.controller.status()['memory']
        self.assertEqual((status['active_mb'], status['selected_mb']), (6144, 2048))
        self.assertEqual(json.loads((self.root / 'emulator-argv.json').read_text()), args)
        self.controller.stop()

    def test_size_only_configuration_remains_a_manual_request(self):
        self.controller.configure({'memory_mb': 8192})
        self.controller.boot()
        self.assertEqual(self.controller.status()['memory']['active_mb'], 8192)
        self.assertEqual(self.controller.config['memory_mode'], 'manual')
        self.controller.stop()
        self.controller.configure({'memory_mode': 'auto'})
        self.assertEqual(self.controller.config['memory_mode'], 'auto')

    def test_changed_or_unknown_snapshot_allocation_discards_only_snapshots(self):
        self.controller.create()
        avd = self.controller.avd_home / f'{self.controller.avd}.avd'
        user_data = avd / 'userdata-qemu.img'
        user_data.write_bytes(b'preserve apps and data')
        snapshots = avd / 'snapshots'
        snapshots.mkdir()
        (snapshots / 'old').write_text('unknown allocation')
        self.controller.prepare_memory(4096)
        self.assertFalse(snapshots.exists())
        snapshots.mkdir()
        (snapshots / 'compatible').write_text('keep')
        self.controller.prepare_memory(4096)
        self.assertTrue((snapshots / 'compatible').exists())
        self.controller.prepare_memory(6144)
        self.assertFalse(snapshots.exists())
        self.assertEqual(user_data.read_bytes(), b'preserve apps and data')
        self.assertIn('hw.ramSize=6144', (avd / 'config.ini').read_text())


if __name__ == '__main__':
    unittest.main()

import importlib.util
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('make_logo', ROOT / 'scripts/make-logo.py')
make_logo = importlib.util.module_from_spec(spec); spec.loader.exec_module(make_logo)


class LogoTests(unittest.TestCase):
    def test_committed_svgs_are_what_the_generator_writes(self):
        for name, look in make_logo.FILES.items():
            self.assertEqual((ROOT / 'assets' / name).read_text(), make_logo.svg(look), f'{name} is stale: run scripts/make-logo.py')

    def test_every_look_is_well_formed_svg(self):
        for look in ('light', 'dark', 'auto'):
            root = ET.fromstring(make_logo.svg(look))
            self.assertTrue(root.tag.endswith('svg'))
            self.assertEqual(root.get('viewBox'), '0 0 1024 1024')

    def test_the_auto_logo_turns_dark_with_the_viewers_theme_and_the_fixed_ones_do_not(self):
        auto, light, dark = (make_logo.svg(look) for look in ('auto', 'light', 'dark'))
        self.assertIn('@media (prefers-color-scheme: dark)', auto)
        self.assertNotIn('prefers-color-scheme', light + dark)
        dark_look = make_logo.LOOKS['dark']
        light_look = make_logo.LOOKS['light']
        for color in dark_look['tile'] + dark_look['ink']:
            self.assertIn(color, auto)                          # the dark colours are in the rule ...
            self.assertIn(color, dark)                          # ... and are exactly the fixed dark logo's
        for color in light_look['tile']:
            self.assertIn(f'stop-color="{color}"', auto)        # the default, outside the rule, is the light look
            self.assertNotIn(color, dark)
        self.assertEqual(re.findall(r'class="(\w+)"', auto).count('rim'), 1)

    def test_the_dark_look_has_contrast_against_its_own_tile_and_a_rim_to_stand_out_on_dark_pages(self):
        def luminance(color):
            channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
        look = make_logo.LOOKS['dark']
        for ink in look['ink']:
            for tile in look['tile']:
                lighter, darker = sorted((luminance(ink), luminance(tile)), reverse=True)
                self.assertGreaterEqual((lighter + 0.05) / (darker + 0.05), 4.5, (ink, tile))   # stricter than the 3:1 WCAG asks of graphics
        self.assertGreater(look['rim'], 0)
        self.assertEqual(make_logo.LOOKS['light']['rim'], 0)

    def test_the_swiftui_logo_draws_the_same_numbers_as_the_svg(self):
        swift = (ROOT / 'macos/Sources/AndroidSubsystem/Logo.swift').read_text()
        left, top, right, bottom, radius = make_logo.TILE
        self.assertIn(f'side * {radius} / {right - left}', swift)
        self.assertIn(f'let u = side / {right - left}', swift)
        for look in make_logo.LOOKS.values():
            for color in look['tile'] + look['ink']:
                if color != '#ffffff':
                    self.assertIn('0x' + color[1:], swift)                  # the colours, light and dark
        self.assertIn('0x' + make_logo.RIM_COLOR[1:], swift)
        self.assertIn(f'.opacity({make_logo.LOOKS["dark"]["rim"]})', swift)
        self.assertIn(f'dark ? {make_logo.LOOKS["dark"]["sheen"]} : {make_logo.LOOKS["light"]["sheen"]}', swift)
        cx, cy, ring_radius, ring_width = make_logo.RING
        self.assertIn(f'lineWidth: {ring_width} * u', swift)
        self.assertIn(f'.frame(width: {2 * ring_radius} * u, height: {2 * ring_radius} * u)', swift)
        self.assertIn(f'.position(x: {cx - left} * u, y: {cy - top} * u)', swift)
        stem_left, stem_top, stem_right, stem_bottom, _ = make_logo.STEM
        self.assertIn(f'bar(u, left: {stem_left - left}, top: {stem_top - top}, width: {stem_right - stem_left}, '
                      f'height: {stem_bottom - stem_top}, opacity: {make_logo.LETTER_OPACITY})', swift)
        for x, y, opacity in make_logo.LINES:
            self.assertIn(f'bar(u, left: {x - left}, top: {y - top}, width: {make_logo.LINE_RIGHT - x}, '
                          f'height: {make_logo.LINE_HEIGHT}, opacity: {opacity})', swift)

    def test_the_manager_window_shows_the_adaptive_logo(self):
        self.assertIn('LogoView()', (ROOT / 'macos/Sources/AndroidSubsystem/AndroidSubsystem.swift').read_text())

    def test_the_readme_picks_the_logo_by_theme(self):
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('<source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">', readme)
        self.assertIn('<img src="assets/logo.svg"', readme)     # where <picture> is not understood, the adaptive logo is used


if __name__ == '__main__':
    unittest.main()

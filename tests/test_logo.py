import importlib.util
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('make_logo', ROOT / 'scripts/make-logo.py')
make_logo = importlib.util.module_from_spec(spec); spec.loader.exec_module(make_logo)


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


class LogoFileTests(unittest.TestCase):
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
        dark_look, light_look = make_logo.LOOKS['dark'], make_logo.LOOKS['light']
        for color in dark_look['tile'] + dark_look['ink']:
            self.assertIn(color, auto)                          # the dark colours are in the rule or its gradients ...
            self.assertIn(color, dark)                          # ... and are exactly the fixed dark logo's
        for color in light_look['tile']:
            self.assertIn(f'stop-color="{color}"', auto)        # the default, outside the rule, is the light look
            self.assertIn(f'stop-color="{color}"', light)
            self.assertNotIn(color, dark)
        for part in ('aurora', 'id="rim"'):
            self.assertNotIn(part, light)                       # the lit rim and the glows belong to the dark look only
            self.assertIn(part, dark)

    def test_every_class_the_dark_rule_names_is_on_an_element(self):
        auto = make_logo.svg('auto')
        rule = re.search(r'<style>(.*?)</style>', auto, re.S).group(1)
        used = {name for value in re.findall(r'class="([^"]+)"', auto) for name in value.split()}
        named = set(re.findall(r'\.([a-z][\w-]*) \{', rule))
        self.assertTrue(named)
        self.assertLessEqual(named, used)                       # a typo here would leave the dark logo half light
        self.assertNotIn('class=', make_logo.svg('light') + make_logo.svg('dark'))

    def test_the_dark_look_has_contrast_against_its_own_tile_and_a_rim_to_stand_out_on_dark_pages(self):
        look = make_logo.LOOKS['dark']
        for ink in look['ink']:
            for tile in look['tile']:
                lighter, darker = sorted((luminance(ink), luminance(tile)), reverse=True)
                self.assertGreaterEqual((lighter + 0.05) / (darker + 0.05), 4.5, (ink, tile))   # stricter than the 3:1 asked of graphics
        self.assertGreater(look['rim'][2], 0)
        self.assertIsNone(make_logo.LOOKS['light']['rim'])

    def test_the_tile_is_a_squircle_that_a_rounded_square_matches_to_within_a_pixel_or_two(self):
        left, top, right, bottom = make_logo.TILE
        points = make_logo.squircle()
        self.assertLessEqual(max(abs(x - 512) for x, _ in points), (right - left) / 2 + 1e-6)
        self.assertEqual(sorted(round(x, 3) for x, _ in points), sorted(round(2 * 512 - x, 3) for x, _ in points))   # symmetric
        half = (right - left) / 2
        diagonal = max(x - 512 for x, y in points if abs((x - 512) - (y - 512)) < 1e-6)
        rounded_square = half - make_logo.CORNER * (1 - 2 ** -0.5)          # where a circular corner of that radius is
        self.assertLess(abs(diagonal - rounded_square), 2)

    def test_the_letter_is_flush_and_the_streaks_sit_left_of_it(self):
        cx, cy, radius, stroke = make_logo.RING
        stem_left, stem_top, stem_right, stem_bottom = make_logo.STEM
        self.assertEqual(stem_right, cx + radius + stroke // 2)             # no bump where the ring meets the stem
        self.assertEqual(stem_left, cx + radius - stroke // 2)              # and no flat spot in the ring's hole
        self.assertEqual(stem_right - stem_left, stroke)                    # the stem is the ring's stroke, carried up and down
        for left, top, opacity in make_logo.STREAKS:
            self.assertLess(make_logo.STREAK_RIGHT, cx - radius - stroke // 2)   # the streaks end before the letter begins
            self.assertTrue(0 < opacity <= 1)
            self.assertLess(left, make_logo.STREAK_RIGHT)
        centres = [top + make_logo.STREAK_HEIGHT / 2 for _, top, _ in make_logo.STREAKS]
        self.assertEqual(centres[1], cy)                                    # the middle streak is level with the ring's centre
        self.assertEqual(centres[1] - centres[0], centres[2] - centres[1])

    def test_the_readme_picks_the_logo_by_theme(self):
        readme = (ROOT / 'README.md').read_text()
        self.assertIn('<source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">', readme)
        self.assertIn('<img src="assets/logo.svg"', readme)     # where <picture> is not understood, the adaptive logo is used


class RasterLogoTests(unittest.TestCase):
    def test_the_app_icon_is_the_light_look_and_the_icns_wraps_it(self):
        try:
            import numpy  # noqa: F401
            from PIL import Image, ImageChops
        except ImportError:
            self.skipTest('Pillow and numpy are only needed to redraw the icon')
        drawn = make_logo.render()
        committed = Image.open(ROOT / 'assets/logo-1024.png').convert('RGBA')
        self.assertEqual(committed.size, (1024, 1024))
        largest = max(high for _, high in ImageChops.difference(drawn, committed).getextrema())
        self.assertLessEqual(largest, 8, 'assets/logo-1024.png is stale: run scripts/make-logo.py --raster')   # 8: another Pillow may round a little differently
        self.assertEqual(committed.getpixel((0, 0))[3], 0)                  # the corners outside the tile are transparent
        self.assertEqual(committed.getpixel((512, 512))[3], 255)

    def test_the_icns_is_a_valid_icon_family_with_every_size(self):
        data = (ROOT / 'assets/AppIcon.icns').read_bytes()
        self.assertEqual(data[:4], b'icns')
        self.assertEqual(int.from_bytes(data[4:8], 'big'), len(data))
        kinds, position = [], 8
        while position < len(data):
            kinds.append(data[position:position + 4])
            position += int.from_bytes(data[position + 4:position + 8], 'big')
        self.assertEqual(position, len(data))
        self.assertEqual(kinds, [b'icp4', b'icp5', b'icp6', b'ic07', b'ic08', b'ic09', b'ic10'])


class SwiftLogoTests(unittest.TestCase):
    def setUp(self):
        self.swift = (ROOT / 'macos/Sources/AndroidSubsystem/Logo.swift').read_text()

    def test_the_swiftui_logo_draws_the_same_numbers_as_the_svg(self):
        swift = self.swift
        left, top, right, bottom = make_logo.TILE
        size = right - left
        self.assertIn(f'side * {make_logo.CORNER} / {size}', swift)
        self.assertIn(f'let u = side / {size}', swift)
        self.assertIn('style: .continuous', swift)                          # the squircle
        for look in make_logo.LOOKS.values():
            for color in look['tile'] + look['ink'] + (look['lit'][0],):
                if color != '#ffffff':
                    self.assertIn('0x' + color[1:], swift)                  # the colours, light and dark
        light, dark = make_logo.LOOKS['light'], make_logo.LOOKS['dark']
        self.assertIn(f'dark ? {dark["lit"][1]} : {light["lit"][1]}', swift)
        self.assertIn(f'dark ? {dark["glass"]} : {light["glass"]}', swift)
        self.assertIn(f'location: {make_logo.MIDDLE}', swift)
        (gx1, gy1), (gx2, gy2) = make_logo.GRADIENT
        self.assertIn(f'startPoint: UnitPoint(x: {gx1}, y: {int(gy1)}), endPoint: UnitPoint(x: {gx2}, y: {int(gy2)})', swift)
        self.assertIn(f'center: UnitPoint(x: {make_logo.LIT[0]}, y: {make_logo.LIT[1]}), startRadius: 0, endRadius: side * {make_logo.LIT[2]}', swift)
        (ix1, iy1), (ix2, iy2) = make_logo.INK_LINE
        self.assertIn(f'UnitPoint(x: {ix1 - left} / {size}, y: {iy1 - top} / {size}), endPoint: UnitPoint(x: {ix2 - left} / {size}, y: {iy2 - top} / {size})', swift)
        self.assertIn(f'UnitPoint(x: 0.5, y: {make_logo.GLASS[0] - top} / {size}), endPoint: UnitPoint(x: 0.5, y: {make_logo.GLASS[1] - top} / {size})', swift)

    def test_the_swiftui_shadow_rim_and_glows_match_the_svg(self):
        swift = self.swift
        light, dark = make_logo.LOOKS['light'], make_logo.LOOKS['dark']
        for look, spec in (('light', light), ('dark', dark)):
            colour, opacity, drop, blur = spec['shadow']
            self.assertIn(f'Color(hex: 0x{colour[1:]}).opacity({opacity})', swift)
        self.assertIn(f'dark ? {dark["shadow"][2]} : {light["shadow"][2]}', swift)                # how far the shadow falls
        self.assertIn(f'dark ? {2 * dark["shadow"][3]} : {2 * light["shadow"][3]}', swift)         # SwiftUI's radius is twice the blur
        first, second, rim_opacity = dark['rim']
        self.assertIn(f'Color(hex: 0x{first[1:]}), Color(hex: 0x{second[1:]})', swift)
        self.assertIn(f'.opacity({rim_opacity})', swift)
        self.assertIn(f'inset(by: {make_logo.RIM_INSET - make_logo.RIM_WIDTH / 2} * u)', swift)
        self.assertIn(f'lineWidth: {make_logo.RIM_WIDTH} * u', swift)
        for color, opacity, x, y in dark['aurora']:
            self.assertIn(f'Color(hex: 0x{color[1:]}).opacity({opacity})', swift)
            self.assertIn(f'center: UnitPoint(x: {x}, y: {y})', swift)
        self.assertIn(f'endRadius: side * {make_logo.AURORA_RADIUS}', swift)

    def test_the_swiftui_letter_and_streaks_are_where_the_svg_puts_them(self):
        swift = self.swift
        left, top, right, bottom = make_logo.TILE
        cx, cy, radius, stroke = make_logo.RING
        self.assertIn(f'lineWidth: {stroke} * u', swift)
        self.assertIn(f'.frame(width: {2 * radius} * u, height: {2 * radius} * u)', swift)
        self.assertIn(f'.position(x: {cx - left} * u, y: {cy - top} * u)', swift)
        stem_left, stem_top, stem_right, stem_bottom = make_logo.STEM
        self.assertIn(f'bar(u, left: {stem_left - left}, top: {stem_top - top}, width: {stem_right - stem_left}, '
                      f'height: {stem_bottom - stem_top}, opacity: 1)', swift)
        for x, y, opacity in make_logo.STREAKS:
            self.assertIn(f'bar(u, left: {x - left}, top: {y - top}, width: {make_logo.STREAK_RIGHT - x}, '
                          f'height: {make_logo.STREAK_HEIGHT}, opacity: {opacity})', swift)
        size = right - left
        self.assertIn(f'UnitPoint(x: {make_logo.FADE[0] - left} / {size}, y: 0.5), endPoint: UnitPoint(x: {make_logo.FADE[1] - left} / {size}, y: 0.5)', swift)

    def test_the_manager_window_shows_the_adaptive_logo(self):
        self.assertIn('LogoView()', (ROOT / 'macos/Sources/AndroidSubsystem/AndroidSubsystem.swift').read_text())


if __name__ == '__main__':
    unittest.main()

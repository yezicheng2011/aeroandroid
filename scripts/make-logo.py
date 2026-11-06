#!/usr/bin/env python3
"""Draw the aeroandroid logo.

    python3 scripts/make-logo.py            assets/logo.svg, logo-light.svg, logo-dark.svg (standard library only)
    python3 scripts/make-logo.py --raster   also assets/logo-1024.png and assets/AppIcon.icns (needs Pillow and numpy)

Design-time tool, not part of the build: the files it writes are committed. A rounded tile holds a
letter "a" (ring plus stem) that is trailing three wind lines: aero.

The logo has a light look (white "a" on a sky-to-mint tile) and a dark look (a glowing "a" on a deep navy tile
with a thin rim, so it stands out on a dark page). assets/logo.svg switches between them by itself with a
prefers-color-scheme rule inside the file, which browsers apply even when the file is loaded as an image.
logo-light.svg and logo-dark.svg are the two fixed looks, for places that pick by theme themselves, such as the
README's <picture>. The Mac app draws the same logo in SwiftUI (macos/Sources/AndroidSubsystem/Logo.swift).
AppIcon.icns is one image, the light look: macOS does not switch a classic .icns between light and dark.
"""
import argparse
import struct
from io import BytesIO
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'assets'

# The drawing, in a 1024 x 1024 box.
TILE = (100, 100, 924, 924, 228)        # left, top, right, bottom, corner radius
RING = (520, 520, 148, 84)              # centre x, centre y, radius, stroke width
STEM = (624, 330, 710, 710, 43)         # left, top, right, bottom, corner radius
LINES = ((190, 410, 0.55), (150, 503, 0.8), (230, 596, 0.45))   # left, top, opacity; each ends at LINE_RIGHT
LINE_RIGHT, LINE_HEIGHT = 318, 34
LETTER_OPACITY = 0.97

LOOKS = {   # tile gradient (top left to bottom right), ink gradient, sheen at the top of the tile, rim opacity
    'light': {'tile': ('#2463eb', '#1ed6aa'), 'ink': ('#ffffff', '#ffffff'), 'sheen': 0.16, 'rim': 0},
    'dark': {'tile': ('#1a2744', '#0a111f'), 'ink': ('#7aa7ff', '#3de8c2'), 'sheen': 0.06, 'rim': 0.22},
}
RIM_COLOR = '#8fb4ff'
FILES = {'logo.svg': 'auto', 'logo-light.svg': 'light', 'logo-dark.svg': 'dark'}


def svg(look):
    """The logo as SVG text. look: 'light', 'dark', or 'auto' (light, turning dark with the viewer's theme)."""
    base = LOOKS['dark' if look == 'dark' else 'light']
    adaptive = look == 'auto'
    hook = lambda name: f' class="{name}"' if adaptive else ''   # the dark rule finds these
    left, top, right, bottom, radius = TILE
    width, height = right - left, bottom - top
    cx, cy, ring_radius, ring_width = RING
    stem_left, stem_top, stem_right, stem_bottom, stem_radius = STEM
    lines = ''.join(f'\n    <rect x="{x}" y="{y}" width="{LINE_RIGHT - x}" height="{LINE_HEIGHT}" '
                    f'rx="{LINE_HEIGHT // 2}" fill-opacity="{opacity}"/>' for x, y, opacity in LINES)
    style = ''
    if adaptive:
        dark = LOOKS['dark']
        style = ('\n  <style>@media (prefers-color-scheme: dark) { '
                 f'.ta {{ stop-color: {dark["tile"][0]} }} .tb {{ stop-color: {dark["tile"][1]} }} '
                 f'.ia {{ stop-color: {dark["ink"][0]} }} .ib {{ stop-color: {dark["ink"][1]} }} '
                 f'.sheen {{ stop-opacity: {dark["sheen"]} }} .rim {{ stroke-opacity: {dark["rim"]} }} }}</style>')
    rim = ''
    if adaptive or base['rim']:
        rim = (f'\n  <rect{hook("rim")} x="{left + 3}" y="{top + 3}" width="{width - 6}" height="{height - 6}" '
               f'rx="{radius - 3}" fill="none" stroke="{RIM_COLOR}" stroke-width="6" stroke-opacity="{base["rim"]}"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="aeroandroid">{style}
  <defs>
    <linearGradient id="sky" x1="0.2" y1="0" x2="0.8" y2="1">
      <stop{hook("ta")} offset="0" stop-color="{base["tile"][0]}"/><stop{hook("tb")} offset="1" stop-color="{base["tile"][1]}"/>
    </linearGradient>
    <linearGradient id="glow" x1="0" y1="0" x2="0" y2="1">
      <stop{hook("sheen")} offset="0" stop-color="#fff" stop-opacity="{base["sheen"]}"/><stop offset=".5" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="ink" gradientUnits="userSpaceOnUse" x1="150" y1="330" x2="710" y2="710">
      <stop{hook("ia")} offset="0" stop-color="{base["ink"][0]}"/><stop{hook("ib")} offset="1" stop-color="{base["ink"][1]}"/>
    </linearGradient>
  </defs>
  <rect x="{left}" y="{top}" width="{width}" height="{height}" rx="{radius}" fill="url(#sky)"/>
  <rect x="{left}" y="{top}" width="{width}" height="{height}" rx="{radius}" fill="url(#glow)"/>{rim}
  <g fill="url(#ink)">
    <circle cx="{cx}" cy="{cy}" r="{ring_radius}" fill="none" stroke="url(#ink)" stroke-width="{ring_width}" stroke-opacity="{LETTER_OPACITY}"/>
    <rect x="{stem_left}" y="{stem_top}" width="{stem_right - stem_left}" height="{stem_bottom - stem_top}" rx="{stem_radius}" fill-opacity="{LETTER_OPACITY}"/>{lines}
  </g>
</svg>
'''


def rounded_box(np, x, y, left, top, right, bottom, radius):
    """Signed distance to a rounded rectangle (negative inside)."""
    cx, cy = (left + right) / 2, (top + bottom) / 2
    dx = np.abs(x - cx) - ((right - left) / 2 - radius)
    dy = np.abs(y - cy) - ((bottom - top) / 2 - radius)
    return np.hypot(np.maximum(dx, 0), np.maximum(dy, 0)) + np.minimum(np.maximum(dx, dy), 0) - radius


def render():
    """The light look as a 1024 x 1024 RGBA image (the app icon)."""
    import numpy as np
    from PIL import Image
    scale, size = 2, 1024               # drawn at 2x, then averaged down for smooth edges
    rgb = lambda text: np.array([int(text[i:i + 2], 16) for i in (1, 3, 5)])
    top_color, bottom_color = (rgb(c) for c in LOOKS['light']['tile'])
    n = size * scale
    y, x = (np.mgrid[0:n, 0:n] + 0.5) / scale
    coverage = lambda sdf: np.clip(0.5 - sdf * scale, 0, 1)   # 1px anti-aliased edge
    left, top, right, bottom, radius = TILE

    tile = coverage(rounded_box(np, x, y, left, top, right, bottom, radius))
    t = np.clip((x * 0.35 + y * 0.65 - left) / (right - left), 0, 1)[..., None]
    color = top_color * (1 - t) + bottom_color * t
    color = color + (255 - color) * (np.clip(1 - (y - top) / 420, 0, 1) * LOOKS['light']['sheen'])[..., None]   # soft sky glow

    cx, cy, ring_radius, ring_width = RING
    ring = coverage(np.abs(np.hypot(x - cx, y - cy) - ring_radius) - ring_width / 2)
    stem = coverage(rounded_box(np, x, y, *STEM))
    letter = np.maximum(ring, stem)
    lines = np.maximum.reduce([coverage(rounded_box(np, x, y, line_left, line_top, LINE_RIGHT, line_top + LINE_HEIGHT, LINE_HEIGHT / 2)) * alpha
                               for line_left, line_top, alpha in LINES])

    white = np.maximum(letter * LETTER_OPACITY, lines)[..., None]
    pixels = color * (1 - white) + 255 * white
    rgba = np.dstack([pixels, tile * 255])
    big = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), 'RGBA')
    return big.resize((size, size), Image.LANCZOS)


def icns(image):
    from PIL import Image
    entries = b''
    for kind, size in ((b'icp4', 16), (b'icp5', 32), (b'icp6', 64), (b'ic07', 128),
                       (b'ic08', 256), (b'ic09', 512), (b'ic10', 1024)):
        png = BytesIO()
        image.resize((size, size), Image.LANCZOS).save(png, 'PNG', optimize=True)
        entries += kind + struct.pack('>I', len(png.getvalue()) + 8) + png.getvalue()
    return b'icns' + struct.pack('>I', len(entries) + 8) + entries


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--raster', action='store_true', help='also redraw logo-1024.png and AppIcon.icns (needs Pillow and numpy)')
    parser.add_argument('--out', type=Path, default=OUT, help='folder to write into (default: assets/)')
    args = parser.parse_args()
    for name, look in FILES.items():
        (args.out / name).write_text(svg(look))
        print('wrote', args.out / name)
    if args.raster:
        logo = render()
        logo.save(args.out / 'logo-1024.png', optimize=True)
        (args.out / 'AppIcon.icns').write_bytes(icns(logo))
        print('wrote', args.out / 'logo-1024.png', 'and', args.out / 'AppIcon.icns')


if __name__ == '__main__':
    main()

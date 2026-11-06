#!/usr/bin/env python3
"""Draw the aeroandroid logo.

    python3 scripts/make-logo.py            assets/logo.svg, logo-light.svg, logo-dark.svg (standard library only)
    python3 scripts/make-logo.py --raster   also assets/logo-1024.png and assets/AppIcon.icns (needs Pillow and numpy)

Design-time tool, not part of the build: the files it writes are committed.

A letter "a" (ring plus stem) trails three streaks of wind: aero. It sits on a squircle tile, the shape of a
macOS app icon, as frosted glass with a soft shadow; the streaks fade in from nothing like motion trails.

The logo has a light look (white glass on a blue-to-mint tile) and a dark look (a glowing azure-to-mint "a" on a
deep navy tile with an aurora glow and a thin lit rim). assets/logo.svg switches between them by itself with a
prefers-color-scheme rule inside the file, which browsers apply even when the file is loaded as an image.
logo-light.svg and logo-dark.svg are the two fixed looks, for places that pick by theme themselves, such as the
README's <picture>. The Mac app draws the same logo in SwiftUI (macos/Sources/AndroidSubsystem/Logo.swift).
AppIcon.icns is one image, the light look: macOS does not switch a classic .icns between light and dark.
"""
import argparse
import math
import struct
from io import BytesIO
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'assets'

# The drawing, in a 1024 x 1024 box.
TILE = (100, 100, 924, 924)          # left, top, right, bottom of the app-icon tile
EXPONENT = 5                         # of the superellipse: the squircle of Apple's icons, no hard corner radius
CORNER = 185                         # a rounded square with this radius is the same tile (SwiftUI uses it)
RING = (520, 520, 148, 80)           # centre x, centre y, radius, stroke width
STEM = (628, 330, 708, 710)          # left, top, right, bottom: one stroke wide, from the edge of the ring's hole to its outer edge
STREAKS = ((150, 410, 0.75), (112, 503, 0.95), (196, 596, 0.6))   # left, top, opacity; each ends at STREAK_RIGHT
STREAK_RIGHT, STREAK_HEIGHT = 318, 34
FADE = (110, 300)                    # streaks fade in from nothing at x = 110 to full strength at x = 300
GLASS = (330, 710)                   # the glyph's glass fade runs from the top of the stem to its bottom
INK_LINE = ((140, 300), (730, 730))  # the line the ink's two colours run along
GRADIENT = ((0.12, 0.0), (0.88, 1.0))   # tile gradient: from, to, in tile units
LIT = (0.24, 0.06, 0.9)              # soft light on the tile: centre x, centre y, radius, in tile units
AURORA_RADIUS = 0.75                 # of the tile, for the coloured glows of the dark look
RIM_INSET, RIM_WIDTH = 6, 5

LOOKS = {
    'light': {
        'tile': ('#3b6bff', '#18b4f2', '#25e3b4'),           # top left, middle (at 55%), bottom right
        'lit': ('#ffffff', 0.26),
        'aurora': (),                                        # glows in the tile corners: colour, opacity, x, y
        'rim': None,                                         # lit edge: from colour, to colour, opacity
        'ink': ('#ffffff', '#ffffff'), 'glass': 0.84,        # glass: the whole glyph fades to this towards the bottom
        'shadow': ('#04206b', 0.30, 14, 16),                 # colour, opacity, offset down, blur
    },
    'dark': {
        'tile': ('#18223d', '#0f1730', '#070c19'),
        'lit': ('#9db8ff', 0.16),
        'aurora': (('#2f6bff', 0.42, 0.12, 1.0), ('#1be0b4', 0.22, 0.95, 0.0)),
        'rim': ('#5b8cff', '#3de8c2', 0.55),
        'ink': ('#8fb4ff', '#43e8c4'), 'glass': 1.0,
        'shadow': ('#4da3ff', 0.55, 6, 20),                  # a glow rather than a shadow
    },
}
FILES = {'logo.svg': 'auto', 'logo-light.svg': 'light', 'logo-dark.svg': 'dark'}
MIDDLE = 0.55


def grey(level):
    """The grey whose brightness is `level`: a mask shows its source through that strongly."""
    return '#' + f'{round(level * 255):02x}' * 3


def squircle(inset=0, steps=160):
    """Points on the tile's outline: a superellipse, so the sides curve into the corners like an app icon's."""
    left, top, right, bottom = (value + sign * inset for value, sign in zip(TILE, (1, 1, -1, -1)))
    cx, cy, rx, ry = (left + right) / 2, (top + bottom) / 2, (right - left) / 2, (bottom - top) / 2
    points = []
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        c, s = math.cos(angle), math.sin(angle)
        points.append((cx + rx * math.copysign(abs(c) ** (2 / EXPONENT), c), cy + ry * math.copysign(abs(s) ** (2 / EXPONENT), s)))
    return points


def outline(inset=0):
    return 'M' + ' L'.join(f'{x:.1f} {y:.1f}' for x, y in squircle(inset)) + 'Z'


def svg(look):
    """The logo as SVG text. look: 'light', 'dark', or 'auto' (light, turning dark with the viewer's theme)."""
    adaptive = look == 'auto'
    light, dark = LOOKS['light'], LOOKS['dark']
    base = dark if look == 'dark' else light
    hook = lambda name: f' class="{name}"' if adaptive else ''        # the dark rule finds these
    ink_id = lambda name: f'ink-{name}' if adaptive else 'ink'
    left, top, right, bottom = TILE
    width, height = right - left, bottom - top

    def ink(name, spec):
        (x1, y1), (x2, y2) = INK_LINE
        return (f'\n    <linearGradient id="{ink_id(name)}" gradientUnits="userSpaceOnUse" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
                f'<stop offset="0" stop-color="{spec["ink"][0]}"/><stop offset="1" stop-color="{spec["ink"][1]}"/></linearGradient>')

    def shadow(name, spec):
        color, opacity, dy, blur = spec['shadow']
        return (f'\n    <filter id="{name}" x="-25%" y="-25%" width="150%" height="165%">'
                f'<feDropShadow dx="0" dy="{dy}" stdDeviation="{blur}" flood-color="{color}" flood-opacity="{opacity}"/></filter>')

    style = ''
    if adaptive:
        d = dark
        style = ('\n  <style>@media (prefers-color-scheme: dark) { '
                 f'.s0 {{ stop-color: {d["tile"][0]} }} .s1 {{ stop-color: {d["tile"][1]} }} .s2 {{ stop-color: {d["tile"][2]} }} '
                 f'.lit {{ stop-color: {d["lit"][0]} }} .lit0 {{ stop-opacity: {d["lit"][1]} }} '
                 '.au { opacity: 1 } ' f'.rim {{ stroke-opacity: {d["rim"][2]} }} '
                 f'.ink-fill {{ fill: url(#{ink_id("dark")}) }} .ink-stroke {{ stroke: url(#{ink_id("dark")}) }} '
                 f'.glass {{ stop-color: {grey(d["glass"])} }} .glyph {{ filter: url(#glow) }} }}</style>')

    defs = [f'\n    <linearGradient id="sky" x1="{GRADIENT[0][0]}" y1="{GRADIENT[0][1]}" x2="{GRADIENT[1][0]}" y2="{GRADIENT[1][1]}">'
            f'<stop{hook("s0")} offset="0" stop-color="{base["tile"][0]}"/><stop{hook("s1")} offset="{MIDDLE}" stop-color="{base["tile"][1]}"/>'
            f'<stop{hook("s2")} offset="1" stop-color="{base["tile"][2]}"/></linearGradient>',
            f'\n    <radialGradient id="lit" cx="{LIT[0]}" cy="{LIT[1]}" r="{LIT[2]}">'
            f'<stop{hook("lit lit0")} offset="0" stop-color="{base["lit"][0]}" stop-opacity="{base["lit"][1]}"/>'
            f'<stop{hook("lit")} offset="1" stop-color="{base["lit"][0]}" stop-opacity="0"/></radialGradient>']
    glows = dark['aurora'] if adaptive or look == 'dark' else ()
    for i, (color, opacity, cx, cy) in enumerate(glows):
        defs.append(f'\n    <radialGradient id="aurora{i}" cx="{cx}" cy="{cy}" r="{AURORA_RADIUS}">'
                    f'<stop offset="0" stop-color="{color}" stop-opacity="{opacity}"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>')
    if adaptive or look == 'dark':
        a, b, _ = dark['rim']
        defs.append(f'\n    <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient>')
    if adaptive:
        defs.append(ink('light', light) + ink('dark', dark))
    else:
        defs.append(ink('', base))
    defs.append(f'\n    <linearGradient id="fade" gradientUnits="userSpaceOnUse" x1="{FADE[0]}" y1="0" x2="{FADE[1]}" y2="0">'
                '<stop offset="0" stop-color="#000"/><stop offset="1" stop-color="#fff"/></linearGradient>'
                '\n    <mask id="trail" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024"><rect width="1024" height="1024" fill="url(#fade)"/></mask>')
    defs.append(f'\n    <linearGradient id="glassfade" gradientUnits="userSpaceOnUse" x1="0" y1="{GLASS[0]}" x2="0" y2="{GLASS[1]}">'
                f'<stop offset="0" stop-color="#fff"/><stop{hook("glass")} offset="1" stop-color="{grey(base["glass"])}"/></linearGradient>'
                '\n    <mask id="glass" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024"><rect width="1024" height="1024" fill="url(#glassfade)"/></mask>')
    defs.append(f'\n    <clipPath id="tile"><path d="{outline()}"/></clipPath>')
    defs.append(shadow('lift', light) + shadow('glow', dark) if adaptive else shadow('lift', base))

    paint = f'url(#{ink_id("light" if adaptive else "")})'
    tile_layers = [f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="url(#sky)"/>']
    for i in range(len(glows)):
        tile_layers.append(f'<rect{hook("au")} x="{left}" y="{top}" width="{width}" height="{height}" fill="url(#aurora{i})"'
                           + (' opacity="0"' if adaptive else '') + '/>')
    tile_layers.append(f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="url(#lit)"/>')
    rim = ''
    if adaptive or base['rim']:
        rim = (f'\n  <path{hook("rim")} d="{outline(RIM_INSET)}" fill="none" stroke="url(#rim)" stroke-width="{RIM_WIDTH}" '
               f'stroke-opacity="{0 if adaptive else base["rim"][2]}"/>')
    cx, cy, radius, stroke = RING
    stem_left, stem_top, stem_right, stem_bottom = STEM
    streaks = ''.join(f'\n        <rect{hook("ink-fill")} x="{x}" y="{y}" width="{STREAK_RIGHT - x}" height="{STREAK_HEIGHT}" '
                      f'rx="{STREAK_HEIGHT // 2}" fill="{paint}" fill-opacity="{opacity}"/>' for x, y, opacity in STREAKS)
    layers = '\n    '.join(tile_layers)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="aeroandroid">{style}
  <defs>{''.join(defs)}
  </defs>
  <g clip-path="url(#tile)">
    {layers}
  </g>{rim}
  <g{hook("glyph")} filter="url(#lift)">
    <g mask="url(#glass)">
      <circle{hook("ink-stroke")} cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{paint}" stroke-width="{stroke}"/>
      <rect{hook("ink-fill")} x="{stem_left}" y="{stem_top}" width="{stem_right - stem_left}" height="{stem_bottom - stem_top}" rx="{(stem_right - stem_left) // 2}" fill="{paint}"/>
      <g mask="url(#trail)">{streaks}
      </g>
    </g>
  </g>
</svg>
'''


def render():
    """The light look as a 1024 x 1024 RGBA image (the app icon), drawn to match logo-light.svg."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    size, over = 1024, 4                # shapes are drawn 4x larger and averaged down for smooth edges
    look = LOOKS['light']
    rgb = lambda text: np.array([int(text[i:i + 2], 16) for i in (1, 3, 5)], dtype=float)

    def shape(draw_on):
        image = Image.new('L', (size * over, size * over), 0)
        draw_on(ImageDraw.Draw(image), over)
        return np.asarray(image.resize((size, size), Image.LANCZOS), dtype=float) / 255

    left, top, right, bottom = TILE
    tile = shape(lambda d, k: d.polygon([(x * k, y * k) for x, y in squircle(steps=720)], fill=255))
    y, x = (np.mgrid[0:size, 0:size] + 0.5)
    u, v = (x - left) / (right - left), (y - top) / (bottom - top)           # tile units

    (fx, fy), (tx, ty) = GRADIENT
    t = np.clip(((u - fx) * (tx - fx) + (v - fy) * (ty - fy)) / ((tx - fx) ** 2 + (ty - fy) ** 2), 0, 1)
    stops = [rgb(c) for c in look['tile']]
    low = t < MIDDLE
    color = np.empty((size, size, 3))
    for channel in range(3):
        color[..., channel] = np.where(low, stops[0][channel] + (stops[1][channel] - stops[0][channel]) * t / MIDDLE,
                                       stops[1][channel] + (stops[2][channel] - stops[1][channel]) * (t - MIDDLE) / (1 - MIDDLE))
    lit_color, lit_alpha = rgb(look['lit'][0]), look['lit'][1]
    lit = lit_alpha * np.clip(1 - np.hypot(u - LIT[0], v - LIT[1]) / LIT[2], 0, 1)
    color = color * (1 - lit[..., None]) + lit_color * lit[..., None]

    cx, cy, radius, stroke = RING
    ring = shape(lambda d, k: (d.ellipse([(cx - radius - stroke / 2) * k, (cy - radius - stroke / 2) * k,
                                          (cx + radius + stroke / 2) * k, (cy + radius + stroke / 2) * k], fill=255),
                               d.ellipse([(cx - radius + stroke / 2) * k, (cy - radius + stroke / 2) * k,
                                          (cx + radius - stroke / 2) * k, (cy + radius - stroke / 2) * k], fill=0)))
    stem_left, stem_top, stem_right, stem_bottom = STEM
    stem = shape(lambda d, k: d.rounded_rectangle([stem_left * k, stem_top * k, stem_right * k, stem_bottom * k],
                                                  radius=(stem_right - stem_left) / 2 * k, fill=255))
    ramp = np.clip((x - FADE[0]) / (FADE[1] - FADE[0]), 0, 1)
    trail = np.zeros((size, size))
    for streak_left, streak_top, opacity in STREAKS:
        bar = shape(lambda d, k: d.rounded_rectangle([streak_left * k, streak_top * k, STREAK_RIGHT * k, (streak_top + STREAK_HEIGHT) * k],
                                                     radius=STREAK_HEIGHT / 2 * k, fill=255))
        trail = np.maximum(trail, bar * opacity * ramp)
    glass = 1 + (look['glass'] - 1) * np.clip((y - GLASS[0]) / (GLASS[1] - GLASS[0]), 0, 1)
    glyph = np.maximum(np.maximum(ring, stem), trail) * glass

    shadow_color, shadow_opacity, shadow_dy, shadow_blur = look['shadow']
    blurred = Image.fromarray(np.clip(glyph * 255, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(shadow_blur))
    soft = np.roll(np.asarray(blurred, dtype=float) / 255, shadow_dy, axis=0) * shadow_opacity
    color = color * (1 - soft[..., None]) + rgb(shadow_color) * soft[..., None]
    color = color * (1 - glyph[..., None]) + rgb(look['ink'][0]) * glyph[..., None]

    rgba = np.dstack([color, tile * 255])
    return Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), 'RGBA')


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

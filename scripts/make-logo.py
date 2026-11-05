#!/usr/bin/env python3
"""Render the aeroandroid logo (assets/logo-1024.png, assets/AppIcon.icns).

Design-time tool, not part of the build: needs Pillow and numpy, and the PNG and ICNS it
writes are committed. A rounded sky-to-mint tile holds a white "a" (ring plus stem) that is
trailing three wind lines: aero. assets/logo.svg is the same drawing as vector.
"""
import struct
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / 'assets'
SCALE, SIZE = 2, 1024          # drawn at 2x, then averaged down for smooth edges
TOP, BOTTOM = np.array([36, 99, 235]), np.array([30, 214, 170])   # azure -> mint


def rounded_box(x, y, left, top, right, bottom, radius):
    """Signed distance to a rounded rectangle (negative inside)."""
    cx, cy = (left + right) / 2, (top + bottom) / 2
    dx = np.abs(x - cx) - ((right - left) / 2 - radius)
    dy = np.abs(y - cy) - ((bottom - top) / 2 - radius)
    return np.hypot(np.maximum(dx, 0), np.maximum(dy, 0)) + np.minimum(np.maximum(dx, dy), 0) - radius


def render():
    n = SIZE * SCALE
    y, x = (np.mgrid[0:n, 0:n] + 0.5) / SCALE
    coverage = lambda sdf: np.clip(0.5 - sdf * SCALE, 0, 1)   # 1px anti-aliased edge

    tile = coverage(rounded_box(x, y, 100, 100, 924, 924, 228))
    t = np.clip((x * 0.35 + y * 0.65 - 100) / 824, 0, 1)[..., None]
    color = TOP * (1 - t) + BOTTOM * t
    color = color + (255 - color) * (np.clip(1 - (y - 100) / 420, 0, 1) * 0.16)[..., None]   # soft sky glow

    ring = coverage(np.abs(np.hypot(x - 520, y - 520) - 148) - 42)
    stem = coverage(rounded_box(x, y, 624, 330, 710, 710, 43))
    letter = np.maximum(ring, stem)
    lines = np.maximum.reduce([coverage(rounded_box(x, y, left, top, 318, top + 34, 17)) * alpha
                               for left, top, alpha in ((190, 410, 0.55), (150, 503, 0.8), (230, 596, 0.45))])

    white = np.maximum(letter * 0.97, lines)[..., None]
    rgb = color * (1 - white) + 255 * white
    rgba = np.dstack([rgb, tile * 255])
    big = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), 'RGBA')
    return big.resize((SIZE, SIZE), Image.LANCZOS)


def icns(image):
    entries = b''
    for kind, size in ((b'icp4', 16), (b'icp5', 32), (b'icp6', 64), (b'ic07', 128),
                       (b'ic08', 256), (b'ic09', 512), (b'ic10', 1024)):
        png = BytesIO()
        image.resize((size, size), Image.LANCZOS).save(png, 'PNG', optimize=True)
        entries += kind + struct.pack('>I', len(png.getvalue()) + 8) + png.getvalue()
    return b'icns' + struct.pack('>I', len(entries) + 8) + entries


if __name__ == '__main__':
    logo = render()
    logo.save(OUT / 'logo-1024.png', optimize=True)
    (OUT / 'AppIcon.icns').write_bytes(icns(logo))
    print('wrote', OUT / 'logo-1024.png', 'and', OUT / 'AppIcon.icns')

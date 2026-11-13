#!/usr/bin/env python3
"""
Favicons and app icons for the public website, from the official OKURMEN Kids
badge: gold ring, violet glasses and «KIDS», gold «ОКУРМЭН». The background is
TRANSPARENT (alpha channel), with no white backing, shadow or other additions.

Source: brand/okurmen-kids-logo-512.png. It is the academy's vector badge
(frontend/pwa/logo.svg) rendered at 512×512 on white. The art has exactly two
colors, gold #F5B52B and violet #291078, and every other pixel is an
anti-aliased edge mixed with white. So each pixel is solved as
    pixel = alpha · brand color + (1 − alpha) · white
for the closer brand color. The result:
  • solid gold and violet stay 100% opaque, in their exact colors;
  • all white (outside and inside the ring) becomes fully transparent;
  • edges keep their anti-aliasing as partial alpha, with no white halo.
Design and proportions are unchanged: same art, same framing as before.

Not part of `npm run build`: the PNG/ICO files in public/ are committed.
Re-run only when the brand art changes:

    python3 scripts/generate-favicons.py      (needs Pillow)

  public/favicon.ico            16, 32, 48   32-bit RGBA (transparent) — browsers, Google Search
  public/favicon-48x48.png      48           Google Search favicon (multiple of 48)
  public/favicon-96x96.png      96           Google Search / high-DPI tabs
  public/apple-touch-icon.png   180          iOS home screen
  public/icon-192.png           192          web manifest (Android)
  public/icon-512.png           512          web manifest; Organization logo in JSON-LD

Small icons (≤ 96 px and the ICO) are cropped to the ring, so the badge fills
92% and stays legible at 16–48 px. 180/192/512 keep the master's framing
(ring 78% of the square).
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
RING = 0.78  # ring diameter / master width (see frontend/pwa/generate-icons.mjs)
BRAND_COLORS = [(0xF5, 0xB5, 0x2B), (0x29, 0x10, 0x78)]  # gold, violet


def unmix_white(image):
    """RGB on white → RGBA on transparent: exact inverse of compositing a brand color over white."""
    rgb = image.convert('RGB')
    out = Image.new('RGBA', rgb.size)
    src, dst = rgb.load(), out.load()
    for y in range(rgb.height):
        for x in range(rgb.width):
            pixel = src[x, y]
            best = None
            for color in BRAND_COLORS:
                # least-squares alpha for pixel = a·color + (1 − a)·255, per channel
                num = sum((255 - p) * (255 - c) for p, c in zip(pixel, color))
                den = sum((255 - c) ** 2 for c in color)
                alpha = min(max(num / den, 0.0), 1.0)
                error = sum((p - (alpha * c + (1 - alpha) * 255)) ** 2 for p, c in zip(pixel, color))
                if best is None or error < best[0]:
                    best = (error, alpha, color)
            _, alpha, color = best
            a = round(alpha * 255)
            dst[x, y] = (*color, a) if a else (0, 0, 0, 0)
    return out


MASTER = unmix_white(Image.open(ROOT / 'brand/okurmen-kids-logo-512.png'))


def tight(fill=0.92):
    """The master cropped around its centre so the ring fills `fill` of the square."""
    side = round(MASTER.width * RING / fill)
    offset = (MASTER.width - side) // 2
    return MASTER.crop((offset, offset, offset + side, offset + side))


def resized(image, size):
    """Resize with premultiplied alpha, so transparent pixels never bleed dark or white into the edges."""
    if image.width == size:
        return image.copy()
    return image.convert('RGBa').resize((size, size), Image.LANCZOS).convert('RGBA')


def save(image, size, name):
    resized(image, size).save(PUBLIC / name, optimize=True)
    print(f'wrote public/{name} ({size}x{size}, RGBA)')


small = tight()
save(small, 48, 'favicon-48x48.png')
save(small, 96, 'favicon-96x96.png')
save(MASTER, 180, 'apple-touch-icon.png')
save(MASTER, 192, 'icon-192.png')
save(MASTER, 512, 'icon-512.png')
# Each ICO frame is resized separately from the master (not from 48 px) and stored as 32-bit RGBA.
frames = [resized(small, s) for s in (48, 32, 16)]
frames[0].save(PUBLIC / 'favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)], append_images=frames[1:])
print('wrote public/favicon.ico (16, 32, 48, RGBA)')

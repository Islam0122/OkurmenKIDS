#!/usr/bin/env python3
"""
Favicons and app icons for the public website: the original OKURMEN Kids
round logo (white circle, gold ring, violet glasses and «KIDS», gold
«ОКУРМЭН») with a TRANSPARENT background OUTSIDE the ring. The white square
around the round logo is removed; the logo itself (including its own white
circle) is not redrawn or recoloured.

Source: brand/okurmen-kids-logo-512.png, the academy's official badge
(frontend/pwa/logo.svg) at 512×512 on white. The ring is centred at
(255.5, 255.5), outer radius 200 px, stroke 13 px.
  • Up to the middle of the ring stroke (r ≤ 193.5 px) every pixel is the
    original pixel, fully opaque, so the logo and its white circle stay
    unchanged.
  • Outside it, only white and the anti-aliased outer edge of the gold ring
    are present. Each pixel is solved as alpha·gold + (1 − alpha)·white, so
    the square corners become alpha 0 and the ring's outer edge stays smooth
    with no white fringe.
Proportions are unchanged, and nothing is cut: the whole ring is inside every
icon, with a margin.

Not part of `npm run build`: the PNG/ICO files in public/ are committed.
Re-run only when the brand art changes:

    python3 scripts/generate-favicons.py      (needs Pillow)

  public/favicon.ico            16, 32, 48   32-bit RGBA, transparent corners
  public/favicon-48x48.png      48           Google Search favicon (multiple of 48)
  public/favicon-96x96.png      96           Google Search / high-DPI tabs
  public/icon-192.png           192          web manifest (Android)
  public/icon-512.png           512          web manifest; Organization logo in JSON-LD
  public/apple-touch-icon.png   180          iOS home screen: OPAQUE on purpose
                                             (iOS fills transparency with black)

Small icons (≤ 96 px and the ICO) are framed tighter, so the round logo fills
87.5% (≥ 1 px clear margin even at 16 px) and stays legible. 192/512 keep the master's framing (78%).
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
RING = 0.78  # ring diameter / master width (see frontend/pwa/generate-icons.mjs)
CENTRE = 255.5  # ring centre (x = y) in the 512 px master
CUT = 193.5  # middle of the ring stroke (outer 200 px, stroke 13 px): opaque original inside
GOLD = (0xF5, 0xB5, 0x2B)


def cut_outside_ring(image):
    """Original logo inside the ring; outside the ring, the white square becomes transparent."""
    rgb = image.convert('RGB')
    out = Image.new('RGBA', rgb.size)
    src, dst = rgb.load(), out.load()
    den = sum((255 - c) ** 2 for c in GOLD)
    for y in range(rgb.height):
        for x in range(rgb.width):
            pixel = src[x, y]
            if (x - CENTRE) ** 2 + (y - CENTRE) ** 2 <= CUT ** 2:
                dst[x, y] = (*pixel, 255)
                continue
            # outside: pixel = alpha·gold + (1 − alpha)·white (the ring's outer anti-aliasing)
            num = sum((255 - p) * (255 - c) for p, c in zip(pixel, GOLD))
            a = round(min(max(num / den, 0.0), 1.0) * 255)
            dst[x, y] = (*GOLD, a) if a else (0, 0, 0, 0)
    return out


ORIGINAL = Image.open(ROOT / 'brand/okurmen-kids-logo-512.png').convert('RGB')
MASTER = cut_outside_ring(ORIGINAL)


def tight(fill=0.875):
    """The master cropped around its centre so the ring fills `fill` of the square."""
    side = round(MASTER.width * RING / fill)
    offset = (MASTER.width - side) // 2
    return MASTER.crop((offset, offset, offset + side, offset + side))


def resized(image, size):
    """Resize with premultiplied alpha, so transparent pixels never bleed dark or white into the edges."""
    if image.width == size:
        return image.copy()
    # 16/32 px: area averaging (BOX) — no filter spill past the ring onto the canvas edge.
    method = Image.LANCZOS if size >= 48 else Image.BOX
    return image.convert('RGBa').resize((size, size), method).convert('RGBA')


def save(image, size, name):
    resized(image, size).save(PUBLIC / name, optimize=True)
    print(f'wrote public/{name} ({size}x{size}, RGBA)')


small = tight()
save(small, 48, 'favicon-48x48.png')
save(small, 96, 'favicon-96x96.png')
ORIGINAL.resize((180, 180), Image.LANCZOS).save(PUBLIC / 'apple-touch-icon.png', optimize=True)  # opaque: iOS paints transparency black
print('wrote public/apple-touch-icon.png (180x180, opaque)')
save(MASTER, 192, 'icon-192.png')
save(MASTER, 512, 'icon-512.png')
# Each ICO frame is resized separately from the master (not from 48 px) and stored as 32-bit RGBA.
frames = [resized(small, s) for s in (48, 32, 16)]
frames[0].save(PUBLIC / 'favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)], append_images=frames[1:])
print('wrote public/favicon.ico (16, 32, 48, RGBA)')

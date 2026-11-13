#!/usr/bin/env python3
"""
Favicons and app icons for the public website, from the official OKURMEN Kids
badge: white background, gold ring, violet glasses and «KIDS», gold «ОКУРМЭН».

Source: brand/okurmen-kids-logo-512.png. It is the academy's vector badge
(frontend/pwa/logo.svg) rendered at 512×512 on opaque white, the same art the
LMS app icons use. Not part of `npm run build`: the PNG/ICO files in public/
are committed. Re-run only when the brand art changes:

    python3 scripts/generate-favicons.py      (needs Pillow)

  public/favicon.ico            16, 32, 48   browsers, Google Search (URL unchanged)
  public/favicon-48x48.png      48           Google Search favicon (multiple of 48)
  public/favicon-96x96.png      96           Google Search / high-DPI tabs
  public/apple-touch-icon.png   180          iOS home screen
  public/icon-192.png           192          web manifest (Android)
  public/icon-512.png           512          web manifest; Organization logo in JSON-LD

Small icons (≤ 96 px and the ICO) crop to the ring, so the badge fills 92% and
stays legible at 16–48 px. 180/192/512 keep the master's 78% ring, which is
inside the maskable safe zone.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MASTER = Image.open(ROOT / 'brand/okurmen-kids-logo-512.png').convert('RGB')
PUBLIC = ROOT / 'public'
RING = 0.78  # ring diameter / master width (see frontend/pwa/generate-icons.mjs)


def tight(fill=0.92):
    """The master cropped around its centre so the ring fills `fill` of the square."""
    side = round(MASTER.width * RING / fill)
    offset = (MASTER.width - side) // 2
    return MASTER.crop((offset, offset, offset + side, offset + side))


def save(image, size, name):
    out = image.resize((size, size), Image.LANCZOS)
    out.save(PUBLIC / name, optimize=True)
    print(f'wrote public/{name} ({size}x{size})')


small = tight()
save(small, 48, 'favicon-48x48.png')
save(small, 96, 'favicon-96x96.png')
save(MASTER, 180, 'apple-touch-icon.png')
save(MASTER, 192, 'icon-192.png')
save(MASTER, 512, 'icon-512.png')
small.resize((256, 256), Image.LANCZOS).save(PUBLIC / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)])
print('wrote public/favicon.ico (16, 32, 48)')

"""Locate Chrome's own install dialog on a real screenshot.

The dialog is browser UI, so the page cannot report where it is. Chrome draws
the primary «Установить» button as a light-blue pill; the dialog around it is
a pure-white box on the dimmed page. Prints JSON {"install": rect, "dialog": rect}.
"""
import json
import sys

import numpy as np
from PIL import Image

img = np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(int)
h, w, _ = img.shape
top = img[60:520]

# The dialog's button pair: focused «Отмена» (dark blue #0b57d0) and, right
# next to it on the same row, «Установить» (light-blue pill #d3e3fd).
dark = (np.abs(top - np.array([11, 87, 208])).sum(axis=2) < 45)
light = (np.abs(top - np.array([211, 227, 253])).sum(axis=2) < 30)
best = None
for y in np.unique(np.nonzero(dark)[0]):
    dxs = np.nonzero(dark[y])[0]
    if len(dxs) < 20:
        continue
    right = dxs.max()
    lxs = np.nonzero(light[y, right:right + 160])[0]
    if len(lxs) >= 20:
        best = (y, right)
        break
if best is None:
    sys.exit('install dialog not found')
row_y, cancel_right = best
band = light[max(0, row_y - 30):row_y + 30, cancel_right:cancel_right + 200]
ys, xs = np.nonzero(band)
bx0, bx1 = xs.min() + cancel_right, xs.max() + cancel_right
by0, by1 = ys.min() + max(0, row_y - 30) + 60, ys.max() + max(0, row_y - 30) + 60
install = {'x': int(bx0), 'y': int(by0), 'w': int(bx1 - bx0 + 1), 'h': int(by1 - by0 + 1)}

white = (img == 255).all(axis=2)
row = by1 + 14  # below the button row: pure dialog white
x0 = bx0
while x0 > 0 and white[row, x0 - 1]:
    x0 -= 1
x1 = bx1
while x1 < w - 1 and white[row, x1 + 1]:
    x1 += 1
col = x0 + 4
y0 = row
while y0 > 0 and white[y0 - 1, col]:
    y0 -= 1
y1 = row
while y1 < h - 1 and white[y1 + 1, col]:
    y1 += 1
dialog = {'x': int(x0), 'y': int(y0), 'w': int(x1 - x0 + 1), 'h': int(y1 - y0 + 1)}
print(json.dumps({'install': install, 'dialog': dialog}))

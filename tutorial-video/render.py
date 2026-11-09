"""Okurmen Kids Digital — «Как установить приложение» tutorial renderer.

    python render.py            # → out/okurmen-kids-install.mp4 + .srt

Inputs:
  script.json                 scenes, narration lines (text = subtitles, say = pronunciation for TTS)
  build/chrome.mp4 + events   real screen recording (capture_chrome.mjs)
  recordings/<scene>.mp4      optional real recordings for macOS / Windows / Android / iPhone
  recordings/<scene>.json     optional highlights for them: [{"t": 3.2, "x": .., "y": .., "w": .., "h": .., "label": ".."}]
                              (seconds from the clip start, pixels of the clip)
  assets/logo.png             the Okurmen Kids logo

Nothing in the frame imitates a browser or OS: real recordings are shown as
recorded; scenes without a recording show the brand card with the steps.
"""
from __future__ import annotations

import json
import math
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
BUILD = ROOT / 'build'
OUT = ROOT / 'out'
W, H, FPS = 1920, 1080, 30
WHITE = (255, 255, 255)
GOLD = (245, 181, 43)  # #F5B52B
PURPLE = (41, 16, 120)  # #291078
INK = (33, 26, 64)
MUTED = (118, 112, 140)
LINE = (233, 230, 242)
CARD = (192, 112, 1536, 864)  # x, y, w, h of the recording area
SAMPLE_RATE = 24000

script = json.loads((ROOT / 'script.json').read_text())


# ----------------------------------------------------------------- text
class Fonts:
    """Manrope (brand font): separate Latin / Cyrillic files, variable weight."""

    def __init__(self):
        self.cache: dict = {}

    def get(self, subset: str, size: int, weight: int):
        key = (subset, size, weight)
        if key not in self.cache:
            font = ImageFont.truetype(str(BUILD / f'manrope-{subset}.ttf'), size)
            font.set_variation_by_axes([weight])
            self.cache[key] = font
        return self.cache[key]


FONTS = Fonts()


def runs(text: str):
    """Split text into runs by script (Cyrillic vs everything else)."""
    out, cur, kind = [], '', None
    for ch in text:
        # The Cyrillic subset has letters only; digits and all punctuation
        # (« » — „ “ ! ,) come from the Latin subset. Spaces follow the run.
        k = 'cyrillic' if 'Ѐ' <= ch <= 'ӿ' else 'latin'
        if ch == ' ' and kind:
            k = kind
        if k != kind and cur:
            out.append((kind, cur))
            cur = ''
        kind = k
        cur += ch
    if cur:
        out.append((kind, cur))
    return out


def text_width(text: str, size: int, weight: int) -> float:
    return sum(FONTS.get(k, size, weight).getlength(t) for k, t in runs(text))


def draw_text(draw: ImageDraw.ImageDraw, xy, text: str, size: int, weight: int, fill, anchor='ls'):
    """Draw mixed-script text. anchor: 'ls' left-baseline, 'ms' centre-baseline."""
    x, y = xy
    if anchor == 'ms':
        x -= text_width(text, size, weight) / 2
    for kind, chunk in runs(text):
        font = FONTS.get(kind, size, weight)
        draw.text((x, y), chunk, font=font, fill=fill, anchor='ls')
        x += font.getlength(chunk)


def wrap(text: str, size: int, weight: int, max_w: float) -> list[str]:
    lines, cur = [], ''
    for word in text.split(' '):
        trial = f'{cur} {word}'.strip()
        if text_width(trial, size, weight) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# ----------------------------------------------------------------- easing
def ease(k: float) -> float:
    k = min(1.0, max(0.0, k))
    return 4 * k ** 3 if k < 0.5 else 1 - (-2 * k + 2) ** 3 / 2


def ease_out(k: float) -> float:
    k = min(1.0, max(0.0, k))
    return 1 - (1 - k) ** 3


# ----------------------------------------------------------------- narration
def synthesize(scene_id: str, idx: int, text: str) -> tuple[Path, float]:
    path = BUILD / 'audio' / f'{scene_id}_{idx}.wav'
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = path.with_suffix('.txt')
    stamp = f"{script['voice']}|{text}"
    if not path.exists() or not meta.exists() or meta.read_text() != stamp:
        raw = path.with_suffix('.raw.wav')
        subprocess.run(['RHVoice-test', '-p', script['voice'], '-o', str(raw)], input=text.encode(), check=True)
        # Normalise to mono 24 kHz, trim edge silence.
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(raw), '-ac', '1', '-ar', str(SAMPLE_RATE),
                        '-af', 'silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse',
                        str(path)], check=True)
        raw.unlink()
        meta.write_text(stamp)
    with wave.open(str(path)) as w:
        return path, w.getnframes() / w.getframerate()


@dataclass
class Line:
    text: str
    audio: Path
    start: float  # seconds within the scene
    dur: float

    @property
    def end(self):
        return self.start + self.dur


@dataclass
class Scene:
    data: dict
    lines: list[Line] = field(default_factory=list)
    duration: float = 0.0
    start: float = 0.0  # absolute
    events: list = field(default_factory=list)


def find_event(events, spec: str):
    kind, _, label = spec.partition(':') if ':' in spec else ('focus', '', spec)
    for e in events:
        if e['type'] == kind and e.get('label') == label:
            return e
    raise KeyError(spec)


def plan() -> list[Scene]:
    scenes = []
    for data in script['scenes']:
        sc = Scene(data)
        if data['kind'] == 'recording':
            sc.events = json.loads((ROOT / data['events']).read_text())
        cursor = 0.9 if data['kind'] != 'recording' else 0.3
        for i, ln in enumerate(data['lines']):
            audio, dur = synthesize(data['id'], i, ln.get('say', ln['text']))
            start = cursor
            if 'at_event' in ln:
                start = max(find_event(sc.events, ln['at_event'])['t'] - data['from'] - 0.2, cursor)
            sc.lines.append(Line(ln['text'], audio, start, dur))
            cursor = start + dur + 0.45
        tail = {'title': 0.8, 'final': 3.0, 'slot': 1.0, 'recording': 1.0}[data['kind']]
        sc.duration = cursor - 0.45 + tail
        if data['kind'] == 'recording':
            sc.duration = max(sc.duration, data['to'] - data['from'] + 0.4)
        if data['kind'] == 'slot':
            clip = ROOT / 'recordings' / f"{data['id']}.mp4"
            if clip.exists():
                sc.duration = max(sc.duration, probe_duration(clip) + 0.5)
        scenes.append(sc)
    t = 0.0
    for sc in scenes:
        sc.start = t
        t += sc.duration
    return scenes


def probe_duration(path: Path) -> float:
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


# ----------------------------------------------------------------- video sources
class Reader:
    """Sequential frame reader with freeze-at-end (monotonic time only)."""

    def __init__(self, path: Path, start: float, size=(W, H)):
        self.size = size
        self.proc = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-ss', f'{start:.3f}', '-i', str(path), '-f', 'rawvideo',
                                      '-pix_fmt', 'rgb24', '-vf', f'scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease,'
                                      f'pad={size[0]}:{size[1]}:(ow-iw)/2:(oh-ih)/2:white,fps={FPS}', '-'],
                                     stdout=subprocess.PIPE)
        self.index = -1
        self.frame = Image.new('RGB', size, WHITE)

    def get(self, index: int) -> Image.Image:
        nbytes = self.size[0] * self.size[1] * 3
        while self.index < index:
            buf = self.proc.stdout.read(nbytes)
            if len(buf) < nbytes:
                break  # freeze on the last frame
            self.frame = Image.frombuffer('RGB', self.size, buf)
            self.index += 1
        return self.frame

    def close(self):
        self.proc.kill()


# ----------------------------------------------------------------- static layers
LOGO = Image.open(ROOT / 'assets' / 'logo.png').convert('RGBA')


def logo(size: int) -> Image.Image:
    return LOGO.resize((size, size), Image.LANCZOS)


def card_shadow():
    x, y, w, h = CARD
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((x, y + 10, x + w, y + h + 10), 22, fill=(41, 16, 120, 34))
    return layer.filter(ImageFilter.GaussianBlur(22))


SHADOW = card_shadow()
CARD_MASK = Image.new('L', CARD[2:], 0)
ImageDraw.Draw(CARD_MASK).rounded_rectangle((0, 0, CARD[2] - 1, CARD[3] - 1), 18, fill=255)


def header(scene: Scene) -> Image.Image:
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    img.alpha_composite(logo(64), (CARD[0], 26))
    draw_text(d, (CARD[0] + 80, 66), 'OKURMEN KIDS DIGITAL', 22, 800, PURPLE)
    tag = f"{scene.data['chapter']:02d}"
    tw = text_width(scene.data['chapter_title'], 26, 700)
    right = CARD[0] + CARD[2]
    d.rounded_rectangle((right - tw - 92, 32, right, 84), 26, fill=(250, 247, 238), outline=(245, 181, 43, 110))
    d.ellipse((right - tw - 84, 38, right - tw - 44, 78), fill=GOLD)
    draw_text(d, (right - tw - 64, 66), tag, 18, 800, WHITE, anchor='ms')
    draw_text(d, (right - tw - 28, 67), scene.data['chapter_title'], 26, 700, PURPLE)
    return img


# ----------------------------------------------------------------- overlays on recordings
def zoom_keys(scene: Scene):
    """(t, cx, cy, z) keyframes in source pixels, scene time."""
    f0 = scene.data['from']
    ev = scene.events
    keys = [(0.0, W / 2, H / 2, 1.0)]
    sid = scene.data['id']
    if sid == 'portal':
        bar = find_event(ev, 'Адресная строка')
        keys += [(bar['t'] - f0 - 0.6, W / 2, H / 2, 1.0), (bar['t'] - f0 + 0.3, 560, 170, 1.9)]
        loaded = next(e for e in ev if e.get('label') == 'portal-loaded')
        keys += [(loaded['t'] - f0 - 0.4, 560, 170, 1.9), (loaded['t'] - f0 + 0.5, W / 2, H / 2, 1.0)]
        btn = find_event(ev, 'Установить приложение')
        bx, by = btn['rect']['x'] + btn['rect']['w'] / 2, btn['rect']['y'] + btn['rect']['h'] / 2
        keys += [(btn['t'] - f0 - 0.1, W / 2, H / 2, 1.0), (btn['t'] - f0 + 0.8, bx, by + 120, 1.75)]
        dlg = find_event(ev, 'dialog:Окно установки Chrome')['rect']
        click = next(e for e in ev if e['type'] == 'click' and e['label'] == 'Установить приложение')
        dx, dy = dlg['x'] + dlg['w'] / 2, dlg['y'] + dlg['h'] / 2
        keys += [(click['t'] - f0 + 0.9, bx, by + 120, 1.75), (click['t'] - f0 + 1.8, dx, dy + 60, 1.9)]
    if sid == 'launch':
        dlg = find_event(ev, 'dialog:Окно установки Chrome')['rect']
        dx, dy = dlg['x'] + dlg['w'] / 2, dlg['y'] + dlg['h'] / 2
        app = next(e for e in ev if e.get('label') == 'app-window')
        keys = [(0.0, dx, dy + 60, 1.9), (app['t'] - f0 + 0.2, dx, dy + 60, 1.9), (app['t'] - f0 + 1.3, W / 2, H / 2, 1.0),
                (app['t'] - f0 + 3.2, W / 2, H / 2, 1.0), (app['t'] - f0 + 4.4, 662, 372, 1.45)]
    return keys


def zoom_at(keys, t):
    prev = keys[0]
    for k in keys[1:]:
        if t < k[0]:
            span = max(k[0] - prev[0], 1e-6)
            e = ease((t - prev[0]) / span)
            return tuple(prev[i] + (k[i] - prev[i]) * e for i in (1, 2, 3))
        prev = k
    return prev[1:]


def crop_box(cx, cy, z):
    cw, ch = W / z, H / z
    x0 = min(max(cx - cw / 2, 0), W - cw)
    y0 = min(max(cy - ch / 2, 0), H - ch)
    return x0, y0, cw, ch


def pointer_path(scene: Scene):
    """Real pointer moves (xdotool, easeInOutCubic over 0.9 s) reconstructed from the log."""
    pts = [(0.0, W / 2, H / 2)]
    pos = (W / 2, H / 2)
    for e in scene.events:
        if e['type'] == 'focus':
            r = e['rect']
            target = (r['x'] + r['w'] / 2, r['y'] + r['h'] / 2)
            pts.append((e['t'], *pos))
            pts.append((e['t'] + 0.9, *target))
            pos = target
    return pts


def pointer_at(pts, t):
    prev = pts[0]
    for p in pts[1:]:
        if t < p[0]:
            e = ease((t - prev[0]) / max(p[0] - prev[0], 1e-6))
            return prev[1] + (p[1] - prev[1]) * e, prev[2] + (p[2] - prev[2]) * e
        prev = p
    return prev[1], prev[2]


def highlights(scene: Scene):
    """Buttons to press: (show_from, click_t, rect, label), source time."""
    out = []
    for e in scene.events:
        if e['type'] == 'focus':
            click = next(c for c in scene.events if c['type'] == 'click' and c['label'] == e['label'] and c['t'] >= e['t'])
            out.append((e['t'] - 0.15, click['t'], e['rect'], e['label'], (click['x'], click['y'])))
        if e['type'] == 'window':
            # The installed app's own title bar (Chrome draws it for the app window).
            out.append((e['t'] + 1.8, None, {'x': 6, 'y': 11, 'w': 520, 'h': 22}, 'Отдельное окно приложения', None))
    return out


def draw_overlays(card_img: Image.Image, scene: Scene, src_t: float, box, scale):
    x0, y0, _, _ = box
    o = Image.new('RGBA', card_img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(o)

    def to_card(x, y):
        return (x - x0) * scale, (y - y0) * scale

    for start, click_t, r, label, click_xy in highlights(scene):
        if label == 'Адресная строка':
            r = {'x': 60, 'y': 46, 'w': 1220, 'h': 34}
        end = click_t + 0.5 if click_t is not None else 1e9
        if not (start <= src_t <= end):
            continue
        appear = ease_out((src_t - start) / 0.35)
        # gone right after the click: the next screen (e.g. Chrome's dialog) takes over
        fade = 1 - ease((src_t - click_t - 0.2) / 0.3) if click_t is not None and src_t > click_t + 0.2 else 1
        a = appear * fade
        pad = 8 + (1 - appear) * 10
        ax, ay = to_card(r['x'] - pad, r['y'] - pad)
        bx, by = to_card(r['x'] + r['w'] + pad, r['y'] + r['h'] + pad)
        glow = Image.new('RGBA', card_img.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle((ax, ay, bx, by), 14, outline=GOLD + (int(150 * a),), width=10)
        o.alpha_composite(glow.filter(ImageFilter.GaussianBlur(7)))
        d.rounded_rectangle((ax, ay, bx, by), 12, outline=GOLD + (int(255 * a),), width=4)
        # label chip under the target
        tw = text_width(label, 24, 700)
        lx = min(max((ax + bx) / 2 - tw / 2 - 18, 10), card_img.width - tw - 46)
        ly = by + 14
        d.rounded_rectangle((lx, ly, lx + tw + 36, ly + 44), 22, fill=PURPLE + (int(240 * a),))
        layer = Image.new('RGBA', card_img.size, (0, 0, 0, 0))
        draw_text(ImageDraw.Draw(layer), (lx + 18, ly + 30), label, 24, 700, WHITE + (int(255 * a),))
        o.alpha_composite(layer)
        # click ripple
        if click_t is not None and click_t <= src_t <= click_t + 0.7:
            k = (src_t - click_t) / 0.7
            px, py = to_card(*click_xy)
            rad = 14 + 46 * ease_out(k)
            d.ellipse((px - rad, py - rad, px + rad, py + rad), outline=GOLD + (int(255 * (1 - k)),), width=5)

    # soft halo around the real cursor
    px, py = to_card(*pointer_at(pointer_path(scene), src_t))
    halo = Image.new('RGBA', card_img.size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((px - 26, py - 26, px + 26, py + 26), fill=GOLD + (70,))
    o.alpha_composite(halo.filter(ImageFilter.GaussianBlur(4)))
    card_img.alpha_composite(o)


# ----------------------------------------------------------------- scene renderers
def compose_card(frame: Image.Image, card: Image.Image, t_in: float):
    frame.alpha_composite(SHADOW)
    frame.paste(card.convert('RGB'), CARD[:2], CARD_MASK)
    d = ImageDraw.Draw(frame)
    x, y, w, h = CARD
    d.rounded_rectangle((x, y, x + w - 1, y + h - 1), 18, outline=LINE, width=2)


def render_recording(scene: Scene, t: float, reader: Reader, hdr: Image.Image) -> Image.Image:
    src_t = scene.data['from'] + min(t, scene.data['to'] - scene.data['from'])
    src = reader.get(int(round(min(t, scene.data['to'] - scene.data['from']) * FPS)))
    cx, cy, z = zoom_at(zoom_keys(scene), t)
    box = crop_box(cx, cy, z)
    x0, y0, cw, ch = box
    card = src.resize(CARD[2:], Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch)).convert('RGBA')
    draw_overlays(card, scene, src_t, box, CARD[2] / cw)
    frame = Image.new('RGBA', (W, H), WHITE + (255,))
    frame.alpha_composite(hdr)
    compose_card(frame, card, t)
    return frame


def render_title(scene: Scene, t: float) -> Image.Image:
    frame = Image.new('RGBA', (W, H), WHITE + (255,))
    k = ease_out(t / 1.1)
    size = int(300 + 40 * (1 - k))
    lg = logo(size)
    lg.putalpha(lg.getchannel('A').point(lambda v: int(v * k)))
    frame.alpha_composite(lg, (W // 2 - size // 2, 190 - int(20 * (1 - k))))
    d = ImageDraw.Draw(frame)
    k2 = ease_out((t - 0.5) / 0.8)
    if k2 > 0:
        layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        draw_text(ld, (W / 2, 620 + 20 * (1 - k2)), 'Как установить приложение', 66, 800, PURPLE + (int(255 * k2),), 'ms')
        draw_text(ld, (W / 2, 704 + 20 * (1 - k2)), 'Okurmen Kids Digital', 66, 800, PURPLE + (int(255 * k2),), 'ms')
        frame.alpha_composite(layer)
    k3 = ease_out((t - 1.0) / 0.8)
    if k3 > 0:
        bw = 120 * k3
        d.rounded_rectangle((W / 2 - bw / 2, 748, W / 2 + bw / 2, 754), 3, fill=GOLD)
        layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        draw_text(ImageDraw.Draw(layer), (W / 2, 812), 'Инструкция для сотрудников академии', 32, 600, (190, 130, 10, int(255 * k3)), 'ms')
        frame.alpha_composite(layer)
    return frame


def render_slot(scene: Scene, t: float, hdr: Image.Image, reader: Reader | None) -> Image.Image:
    frame = Image.new('RGBA', (W, H), WHITE + (255,))
    frame.alpha_composite(hdr)
    if reader is not None:  # the user's real recording
        clip = reader.get(int(t * FPS)).convert('RGBA')
        hl_path = ROOT / 'recordings' / f"{scene.data['id']}.json"
        if hl_path.exists():
            draw_clip_highlights(clip, json.loads(hl_path.read_text()), t, scene)
        compose_card(frame, clip, t)
        return frame

    card = Image.new('RGBA', CARD[2:], WHITE + (255,))
    d = ImageDraw.Draw(card)
    steps = scene.data['steps']
    # Left: platform
    draw_text(d, (90, 300), scene.data['platform'], 76, 800, PURPLE)
    d.rounded_rectangle((92, 334, 92 + 90, 340), 3, fill=GOLD)
    for i, ln in enumerate(wrap('Повторите эти шаги на своём устройстве.', 30, 500, 520)):
        draw_text(d, (90, 400 + i * 42), ln, 30, 500, MUTED)
    if scene.data.get('note'):
        tw = text_width(scene.data['note'], 24, 700)
        d.rounded_rectangle((88, 506, 88 + tw + 40, 554), 24, fill=(250, 247, 238), outline=GOLD)
        draw_text(d, (108, 538), scene.data['note'], 24, 700, PURPLE)
    d.rounded_rectangle((88, 690, 88 + text_width('Запись экрана будет добавлена', 20, 600) + 36, 728), 19, outline=LINE, width=2)
    draw_text(d, (106, 716), 'Запись экрана будет добавлена', 20, 600, MUTED)
    # Right: numbered steps, revealed with the narration
    total = scene.duration
    for i, step in enumerate(steps):
        appear = ease_out((t - 0.6 - i * (total - 2.2) / len(steps)) / 0.5)
        if appear <= 0:
            continue
        y = 190 + i * 140 + 16 * (1 - appear)
        layer = Image.new('RGBA', CARD[2:], (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        a = int(255 * appear)
        ld.rounded_rectangle((780, y - 6, 1450, y + 104), 20, fill=(250, 248, 253, a), outline=LINE + (a,), width=2)
        ld.ellipse((806, y + 22, 862, y + 78), fill=GOLD + (a,))
        draw_text(ld, (834, y + 61), str(i + 1), 28, 800, WHITE + (a,), 'ms')
        draw_rich(ld, (890, y + 60), step, 30, a)
        card.alpha_composite(layer)
    compose_card(frame, card, t)
    return frame


def draw_rich(d, xy, text: str, size: int, alpha: int):
    """Plain text in ink, «button names» in purple bold."""
    x, y = xy
    parts = []
    buf, inside = '', False
    for ch in text:
        if ch == '«':
            parts.append((buf, False))
            buf, inside = '«', True
        elif ch == '»' and inside:
            parts.append((buf + '»', True))
            buf, inside = '', False
        else:
            buf += ch
    parts.append((buf, inside))
    for chunk, bold in parts:
        if not chunk:
            continue
        weight = 800 if bold else 500
        draw_text(d, (x, y), chunk, size, weight, (PURPLE if bold else INK) + (alpha,))
        x += text_width(chunk, size, weight)


def draw_clip_highlights(clip, items, t, scene):
    sx = CARD[2] / scene.clip_size[0] if hasattr(scene, 'clip_size') else 1
    d = ImageDraw.Draw(clip)
    for h in items:
        if h['t'] - 0.3 <= t <= h['t'] + 1.2:
            d.rounded_rectangle((h['x'] * sx - 8, h['y'] * sx - 8, (h['x'] + h['w']) * sx + 8, (h['y'] + h['h']) * sx + 8), 12, outline=GOLD, width=5)


def render_final(scene: Scene, t: float) -> Image.Image:
    frame = Image.new('RGBA', (W, H), WHITE + (255,))
    k = ease_out(t / 1.0)
    lg = logo(260)
    lg.putalpha(lg.getchannel('A').point(lambda v: int(v * k)))
    frame.alpha_composite(lg, (W // 2 - 130, 200))
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    k2 = ease_out((t - 0.4) / 0.8)
    draw_text(d, (W / 2, 600), 'Okurmen Kids Digital', 72, 800, PURPLE + (int(255 * k2),), 'ms')
    draw_text(d, (W / 2, 660), 'Обучение, расписание и результаты — в одном приложении', 32, 500, MUTED + (int(255 * k2),), 'ms')
    k3 = ease_out((t - 1.0) / 0.8)
    url = script['portal_url']
    uw = text_width(url, 30, 700)
    d.rounded_rectangle((W / 2 - uw / 2 - 30, 712, W / 2 + uw / 2 + 30, 772), 30, fill=PURPLE + (int(255 * k3),))
    draw_text(d, (W / 2, 752), url, 30, 700, WHITE + (int(255 * k3),), 'ms')
    k4 = ease_out((t - 1.8) / 0.8)
    draw_text(d, (W / 2, 860), 'Спасибо за внимание!', 34, 700, (190, 130, 10, int(255 * k4)), 'ms')
    frame.alpha_composite(layer)
    return frame


# ----------------------------------------------------------------- subtitles + progress
def subtitle_cues(scenes):
    cues = []
    for sc in scenes:
        for ln in sc.lines:
            lines = wrap(ln.text, 36, 600, 1380)
            groups = [lines[i:i + 2] for i in range(0, len(lines), 2)]
            total = sum(len(' '.join(g)) for g in groups)
            t = sc.start + ln.start
            for g in groups:
                dur = ln.dur * len(' '.join(g)) / total
                cues.append((t, t + dur, g))
                t += dur
    return cues


SUB_CACHE: dict = {}


def subtitle_layer(lines: list[str]) -> Image.Image:
    key = tuple(lines)
    if key in SUB_CACHE:
        return SUB_CACHE[key]
    width = max(text_width(l, 36, 600) for l in lines) + 64
    height = 22 + 50 * len(lines)
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    x0 = (W - width) / 2
    y1 = H - 26
    y0 = y1 - height
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + 4, x0 + width, y1 + 4), 18, fill=(41, 16, 120, 40))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((x0, y0, x0 + width, y1), 18, fill=(255, 255, 255, 246), outline=LINE, width=2)
    for i, l in enumerate(lines):
        draw_text(d, (W / 2, y0 + 50 + i * 50), l, 36, 600, INK, 'ms')
    SUB_CACHE[key] = img
    return img


def progress(frame: Image.Image, t: float, total: float, scenes):
    d = ImageDraw.Draw(frame)
    d.rectangle((0, H - 6, W, H), fill=(240, 237, 247))
    d.rectangle((0, H - 6, W * t / total, H), fill=GOLD)
    for sc in scenes[1:]:
        x = W * sc.start / total
        d.rectangle((x - 1, H - 6, x + 1, H), fill=WHITE)


def srt_time(s: float) -> str:
    ms = int(round(s * 1000))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


# ----------------------------------------------------------------- main
def main():
    OUT.mkdir(exist_ok=True)
    scenes = plan()
    total = scenes[-1].start + scenes[-1].duration
    print(f'duration {total:.1f}s', [f"{s.data['id']}:{s.duration:.1f}" for s in scenes])

    # narration track
    audio = np.zeros(int((total + 1) * SAMPLE_RATE), dtype=np.float32)
    for sc in scenes:
        for ln in sc.lines:
            with wave.open(str(ln.audio)) as w:
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
            i = int((sc.start + ln.start) * SAMPLE_RATE)
            audio[i:i + len(pcm)] += pcm
    pcm16 = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(BUILD / 'narration.wav'), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16.tobytes())

    cues = subtitle_cues(scenes)
    with open(OUT / 'okurmen-kids-install.srt', 'w') as f:
        for i, (a, b, lines) in enumerate(cues, 1):
            f.write(f'{i}\n{srt_time(a)} --> {srt_time(b)}\n' + '\n'.join(lines) + '\n\n')

    video_path = BUILD / 'video.mp4'
    enc = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
                            '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', str(video_path)],
                           stdin=subprocess.PIPE)
    prev_last = None
    n_total = int(round(total * FPS))
    frame_no = 0
    for sc in scenes:
        kind = sc.data['kind']
        hdr = header(sc)
        reader = None
        if kind == 'recording':
            reader = Reader(ROOT / sc.data['source'], sc.data['from'])
        elif kind == 'slot' and (ROOT / 'recordings' / f"{sc.data['id']}.mp4").exists():
            reader = Reader(ROOT / 'recordings' / f"{sc.data['id']}.mp4", 0, size=CARD[2:])
        n = int(round((sc.start + sc.duration) * FPS)) - frame_no
        last = None
        for i in range(n):
            t = i / FPS
            if kind == 'title':
                frame = render_title(sc, t)
            elif kind == 'final':
                frame = render_final(sc, t)
            elif kind == 'recording':
                frame = render_recording(sc, t, reader, hdr)
            else:
                frame = render_slot(sc, t, hdr, reader)
            # smooth zoom transition: previous scene fades out while this one settles in
            if prev_last is not None and t < 0.6:
                k = ease(t / 0.6)
                z = 1.03 - 0.03 * k
                cur = frame.resize((int(W * z), int(H * z)), Image.BILINEAR).crop(
                    (int((W * z - W) / 2), int((H * z - H) / 2), int((W * z - W) / 2) + W, int((H * z - H) / 2) + H))
                frame = Image.blend(prev_last.convert('RGBA'), cur, k)
            gt = sc.start + t
            for a, b, lines in cues:
                if a <= gt < b:
                    frame.alpha_composite(subtitle_layer(lines))
                    break
            progress(frame, gt, total, scenes)
            rgb = frame.convert('RGB')
            enc.stdin.write(rgb.tobytes())
            last = rgb
            frame_no += 1
            if frame_no % 150 == 0:
                print(f'  {frame_no}/{n_total} frames')
        prev_last = last
        if reader:
            reader.close()
    enc.stdin.close()
    enc.wait()

    final = OUT / 'okurmen-kids-install.mp4'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(video_path), '-i', str(BUILD / 'narration.wav'),
                    '-i', str(OUT / 'okurmen-kids-install.srt'),
                    '-map', '0:v', '-map', '1:a', '-map', '2:s', '-c:v', 'copy',
                    '-af', 'highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000',
                    '-c:s', 'mov_text', '-metadata:s:s:0', 'language=rus', '-metadata:s:a:0', 'language=rus',
                    '-metadata', f"title={script['title']}",
                    # the video decides the length (not the subtitle track, which ends with the last line)
                    '-t', f'{n_total / FPS:.3f}', '-movflags', '+faststart', str(final)], check=True)
    print('wrote', final)


if __name__ == '__main__':
    main()

"""Монтаж итогового ролика.

Собирает кадры 1920×1080, 30 к/с:
  * слайды (card) рисуются Pillow, пункты появляются вместе с репликами;
  * экранные сцены (screen) берут кадры CDP-скринкаста (2× разрешение) по
    времени записи, с плавными приближениями из events.json;
  * поверх — плашка раздела, поясняющие подписи и субтитры;
  * переходы — перекрёстное растворение между сценами, затемнение в начале и конце.
Кадры кодируются в H.264 параллельно по частям, затем склеиваются, и к ним
добавляются озвучка (с нормализацией громкости) и дорожка субтитров.

Запуск: python marketing_video/compose.py [--preview СЕКУНДЫ ...] [--jobs N]
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from scenes import SCENES, TITLE

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
REC = BUILD / "rec"
OUT = ROOT / "marketing_tutorial.mp4"
W, H, FPS = 1920, 1080, 30
XFADE = 0.5          # растворение между сценами, с
FADE_IN, FADE_OUT = 0.6, 1.2
ZOOM_EASE = 0.6      # время наезда и отъезда, с
CHIP_TIME = 5.0      # сколько секунд видна плашка раздела

BRAND = (47, 143, 91)
BRAND_DARK = (31, 102, 64)
BRAND_SOFT = (231, 243, 236)
INK = (20, 24, 31)
INK_2 = (88, 96, 108)
WARN = (194, 124, 14)
WARN_SOFT = (253, 243, 224)
SLATE = (96, 110, 130)
SLATE_SOFT = (236, 240, 245)
BG = (246, 248, 247)

FONT_DIR = Path("/usr/share/fonts/opentype/inter")


@lru_cache(None)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / f"Inter-{weight}.otf"), size)


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def wrap(text: str, fnt, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if fnt.getlength(test) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def shadowed_round_rect(size, radius, fill, shadow=18, alpha=46) -> Image.Image:
    w, h = size
    pad = shadow * 2
    sh = Image.new("L", (w + pad * 2, h + pad * 2), 0)
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 8, pad + w, pad + h + 8), radius, fill=alpha)
    img = Image.new("RGBA", sh.size, (16, 40, 28, 255))
    img.putalpha(sh.filter(ImageFilter.GaussianBlur(shadow)))
    ImageDraw.Draw(img).rounded_rectangle((pad, pad, pad + w, pad + h), radius, fill=fill)
    return img, pad


# ---------------------------------------------------------------------------
# Слайды
# ---------------------------------------------------------------------------
PANEL_TOP, PANEL_H = 262, 610
TONES = {"brand": (BRAND, BRAND_SOFT), "warn": (WARN, WARN_SOFT), "neutral": (SLATE, SLATE_SOFT)}


@lru_cache(None)
def logo() -> Image.Image:
    return Image.open(ROOT.parent / "frontend/src/assets/logo.png").convert("RGBA")


def card_base(scene) -> Image.Image:
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)
    # мягкие фигуры фирменного цвета
    deco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    dd.ellipse((W - 520, -300, W + 300, 520), fill=BRAND_SOFT + (255,))
    dd.ellipse((-260, H - 220, 260, H + 300), fill=(238, 244, 240, 255))
    img.alpha_composite(deco)
    lg = logo().copy()
    lg.thumbnail((64, 64))
    img.alpha_composite(lg, (96, 56))
    d.text((176, 70), "OkurmenKIDS · Маркетинг", font=font("SemiBold", 26), fill=INK_2)
    section = scene.get("section", "")
    idx = [s["section"] for s in SCENES]
    sections = list(dict.fromkeys(idx))
    num = sections.index(section) + 1
    d.text((W - 96, 74), f"{num:02d} · {section}", font=font("Medium", 24), fill=INK_2, anchor="ra")
    return img


def render_intro(scene, local, lines):
    c = scene["card"]
    img = card_base(scene)
    d = ImageDraw.Draw(img)
    k = ease(local / 0.9)
    y_off = int((1 - k) * 24)
    alpha = int(255 * k)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((120, 300 + y_off, 430, 352 + y_off), 26, fill=BRAND + (255,))
    ld.text((275, 326 + y_off), c["eyebrow"].upper(), font=font("SemiBold", 24), fill="white", anchor="mm")
    ld.text((116, 390 + y_off), c["title"], font=font("Bold", 120), fill=INK)
    sub = wrap(c["subtitle"], font("Medium", 44), 1180)
    for i, line in enumerate(sub):
        ld.text((120, 560 + y_off + i * 60), line, font=font("Medium", 44), fill=INK_2)
    ld.text((120, 590 + len(sub) * 60 + y_off), c["foot"], font=font("Regular", 32), fill=BRAND_DARK)
    lg = logo().copy()
    lg.thumbnail((300, 300))
    layer.alpha_composite(lg, (W - 420, 300 + y_off))
    a = layer.getchannel("A").point(lambda v: v * alpha // 255)
    layer.putalpha(a)
    img.alpha_composite(layer)
    return img


@lru_cache(None)
def card_static(scene_id: str) -> Image.Image:
    scene = next(s for s in SCENES if s["id"] == scene_id)
    c = scene["card"]
    img = card_base(scene)
    d = ImageDraw.Draw(img)
    d.text((96, 140), c["title"], font=font("Bold", 76), fill=INK)
    cols = c["columns"]
    gap, top = 48, PANEL_TOP
    cw = (W - 192 - gap * (len(cols) - 1)) // len(cols)
    for i, col in enumerate(cols):
        x = 96 + i * (cw + gap)
        panel, pad = shadowed_round_rect((cw, PANEL_H), 32, (255, 255, 255, 255))
        img.alpha_composite(panel, (x - pad, top - pad))
        color, soft = TONES[col["tone"]]
        d.rounded_rectangle((x + 40, top + 44, x + 56, top + 60), 4, fill=color)
        d.text((x + 76, top + 52), col["heading"], font=font("SemiBold", 36), fill=INK, anchor="lm")
        d.line((x + 40, top + 104, x + cw - 40, top + 104), fill=(230, 234, 238), width=2)
    return img


def card_item_layer(scene_id: str, ci: int, ii: int) -> tuple[Image.Image, tuple[int, int]]:
    return _card_item(scene_id, ci, ii)


@lru_cache(None)
def _card_item(scene_id: str, ci: int, ii: int):
    scene = next(s for s in SCENES if s["id"] == scene_id)
    cols = scene["card"]["columns"]
    col = cols[ci]
    gap, top = 48, PANEL_TOP
    cw = (W - 192 - gap * (len(cols) - 1)) // len(cols)
    x = 96 + ci * (cw + gap)
    n = len(col["items"])
    row_h = min(104, (PANEL_H - 150) // n)
    y = top + 136 + ii * row_h
    label, desc, _ = col["items"][ii]
    color, soft = TONES[col["tone"]]
    layer = Image.new("RGBA", (cw - 60, row_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((0, 4, 44, 48), fill=soft)
    if col["tone"] == "warn":
        d.text((22, 26), "!", font=font("Bold", 28), fill=color, anchor="mm")
    elif col["tone"] == "brand":
        d.line([(12, 27), (19, 34), (32, 19)], fill=color, width=5, joint="curve")
    else:
        d.ellipse((16, 20, 28, 32), fill=color)
    d.text((64, 2), label, font=font("SemiBold", 34), fill=INK)
    d.text((64, 46), desc, font=font("Regular", 27), fill=INK_2)
    return layer, (x + 40, y)


def render_card(scene, local, lines):
    if scene["id"] == "intro":
        return render_intro(scene, local, lines)
    img = card_static(scene["id"]).copy()
    for ci, col in enumerate(scene["card"]["columns"]):
        for ii, (_, _, at) in enumerate(col["items"]):
            appear = lines[min(at, len(lines) - 1)]["start"] + ii * 0.18 - 0.1
            k = ease((local - appear) / 0.45)
            if k <= 0:
                continue
            layer, (x, y) = card_item_layer(scene["id"], ci, ii)
            if k < 1:
                layer = layer.copy()
                layer.putalpha(layer.getchannel("A").point(lambda v, k=k: int(v * k)))
            img.alpha_composite(layer, (x, y + int((1 - k) * 18)))
    return img


# ---------------------------------------------------------------------------
# Экранные сцены
# ---------------------------------------------------------------------------
class Recording:
    def __init__(self):
        data = json.loads((REC / "events.json").read_text())
        self.dpr = data["dpr"]
        self.view = data["viewport"]
        self.offset = data["clockOffset"]
        self.frames = data["frames"]
        self.ts = [f["ts"] for f in self.frames]
        self.scenes = {e["id"]: e for e in data["events"] if e["type"] == "scene"}
        self.zooms = [e for e in data["events"] if e["type"] == "zoom"]
        self.notes = [e for e in data["events"] if e["type"] == "note"]
        self._img_idx, self._img = None, None

    def frame_at(self, wall: float) -> int:
        i = bisect.bisect_right(self.ts, wall - self.offset) - 1
        return max(0, i)

    def image(self, idx: int) -> Image.Image:
        if idx != self._img_idx:
            self._img = Image.open(REC / "frames" / self.frames[idx]["file"]).convert("RGB")
            self._img_idx = idx
        return self._img

    def zoom_rect(self, wall: float, fw: int, fh: int):
        full = (0.0, 0.0, float(fw), float(fh))
        best, k_best = None, 0.0
        for z in self.zooms:
            if z["t"] <= wall <= z["t"] + z["dur"] + ZOOM_EASE:
                k = min(ease((wall - z["t"]) / ZOOM_EASE), ease((z["t"] + z["dur"] + ZOOM_EASE - wall) / ZOOM_EASE))
                if k > k_best:
                    best, k_best = z, k
        if not best:
            return full
        s = fw / self.view["width"]
        b = best["box"]
        bx, by, bw, bh = b["x"] * s, b["y"] * s, b["width"] * s, b["height"] * s
        # прямоугольник 16:9 вокруг области, не ближе max-кратного увеличения
        w = max(bw, bh * fw / fh, fw / best["max"])
        w = min(w, fw)
        h = w * fh / fw
        cx, cy = bx + bw / 2, by + bh / 2
        x0 = min(max(cx - w / 2, 0), fw - w)
        y0 = min(max(cy - h / 2, 0), fh - h)
        target = (x0, y0, x0 + w, y0 + h)
        return tuple(f + (t - f) * k_best for f, t in zip(full, target))


REC_DATA: Recording | None = None


def render_screen(scene, local):
    rec = REC_DATA
    ev = rec.scenes[scene["id"]]
    wall = ev["t"] + min(local, ev["dur"] - 1 / FPS)
    idx = rec.frame_at(wall)
    src = rec.image(idx)
    rect = rec.zoom_rect(wall, *src.size)
    return src.resize((W, H), Image.Resampling.BICUBIC, box=rect), wall


# ---------------------------------------------------------------------------
# Наложения
# ---------------------------------------------------------------------------
@lru_cache(None)
def chip(text: str) -> Image.Image:
    f = font("SemiBold", 28)
    w = int(f.getlength(text)) + 76
    img, pad = shadowed_round_rect((w, 56), 28, BRAND + (255,), shadow=10, alpha=70)
    d = ImageDraw.Draw(img)
    d.ellipse((pad + 22, pad + 22, pad + 34, pad + 34), fill=(255, 255, 255, 230))
    d.text((pad + 46, pad + 28), text, font=f, fill="white", anchor="lm")
    return img


@lru_cache(None)
def note_img(text: str) -> Image.Image:
    f = font("SemiBold", 32)
    lines = wrap(text, f, 1240)
    w = max(int(f.getlength(line)) for line in lines) + 90
    h = 44 * len(lines) + 40
    img, pad = shadowed_round_rect((w, h), 18, (255, 255, 255, 250), shadow=14, alpha=70)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, pad + 12, pad + h), 6, fill=BRAND)
    for i, line in enumerate(lines):
        d.text((pad + 44, pad + 20 + i * 44), line, font=f, fill=INK)
    return img


@lru_cache(None)
def subtitle_img(text: str) -> Image.Image:
    f = font("Medium", 40)
    lines = wrap(text, f, 1560)
    w = max(int(f.getlength(line)) for line in lines) + 64
    h = 54 * len(lines) + 30
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w, h), 14, fill=(12, 16, 20, 228))
    for i, line in enumerate(lines):
        d.text((w // 2, 15 + i * 54 + 27), line, font=f, fill=(255, 255, 255, 255), anchor="mm")
    return img


def paste_alpha(base: Image.Image, over: Image.Image, xy, alpha: float):
    if alpha <= 0:
        return
    if alpha < 1:
        over = over.copy()
        over.putalpha(over.getchannel("A").point(lambda v: int(v * alpha)))
    base.paste(over, xy, over)


def overlays(img: Image.Image, scene, local, lines, wall):
    if scene["kind"] == "screen":
        c = chip(scene["caption"])
        # плашка раздела — в первые секунды сцены, чтобы не закрывать приближения
        a = ease((local - 0.3) / 0.4) * ease((CHIP_TIME - local) / 0.4)
        paste_alpha(img, c, ((W - c.width) // 2, 2), a)
        for n in REC_DATA.notes:
            if n["t"] <= wall <= n["t"] + n["dur"] and REC_DATA.scenes[scene["id"]]["t"] <= n["t"]:
                k = min(ease((wall - n["t"]) / 0.35), ease((n["t"] + n["dur"] - wall) / 0.35))
                ni = note_img(n["text"])
                paste_alpha(img, ni, (60, H - 250 - ni.height + 60), k)
    for line in lines:
        if line["start"] - 0.05 <= local <= line["start"] + line["duration"] + 0.25:
            s = subtitle_img(line["text"])
            k = min(ease((local - line["start"] + 0.05) / 0.15), ease((line["start"] + line["duration"] + 0.25 - local) / 0.15))
            paste_alpha(img, s, ((W - s.width) // 2, H - 48 - s.height), k)
            break


# ---------------------------------------------------------------------------
# Таймлайн
# ---------------------------------------------------------------------------
TIMING = json.loads((BUILD / "timing.json").read_text())
SCENE_BY_ID = {s["id"]: s for s in SCENES}
TL = TIMING["scenes"]
STARTS = [s["start"] for s in TL]


def scene_duration(scene) -> float:
    return next(s["duration"] for s in TL if s["id"] == scene["id"])


def base_frame(i: int, local: float):
    entry = TL[i]
    scene = SCENE_BY_ID[entry["id"]]
    if scene["kind"] == "card":
        return render_card(scene, local, entry["lines"]).convert("RGB"), None
    return render_screen(scene, local)


def frame(t: float) -> Image.Image:
    i = max(0, bisect.bisect_right(STARTS, t) - 1)
    entry = TL[i]
    scene = SCENE_BY_ID[entry["id"]]
    local = t - entry["start"]
    img, wall = base_frame(i, local)
    if i > 0 and local < XFADE:
        prev, _ = base_frame(i - 1, TL[i - 1]["duration"] - 1 / FPS)
        img = Image.blend(prev, img, ease(local / XFADE))
    overlays(img, scene, local, entry["lines"], wall)
    total = TIMING["total"]
    k = min(ease(t / FADE_IN), ease((total - t) / FADE_OUT))
    if k < 1:
        img = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), img, k)
    return img


def encode_part(args):
    part, f0, f1 = args
    global REC_DATA
    REC_DATA = Recording()
    # MPEG-TS: части склеиваются протоколом concat без потери кадров
    # (concat-демуксер по MP4 терял кадры на стыках).
    out = BUILD / "parts" / f"part{part:02d}.ts"
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-tune", "stillimage", "-g", str(FPS * 4), "-f", "mpegts", str(out)],
                          stdin=subprocess.PIPE)
    for n in range(f0, f1):
        ff.stdin.write(frame(n / FPS).tobytes())
        if (n - f0) % (FPS * 20) == 0:
            print(f"  часть {part}: {n - f0}/{f1 - f0}", flush=True)
    ff.stdin.close()
    ff.wait()
    return str(out)


def main():
    global REC_DATA
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=float, nargs="*", help="сохранить кадры на этих секундах в build/preview")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--mux-only", action="store_true", help="только склеить готовые части и добавить звук")
    args = ap.parse_args()

    if args.preview is not None:
        REC_DATA = Recording()
        (BUILD / "preview").mkdir(exist_ok=True)
        for t in args.preview:
            frame(t).save(BUILD / "preview" / f"t{t:07.2f}.png")
        print("Превью сохранены в", BUILD / "preview")
        return

    total_frames = int(math.ceil(TIMING["total"] * FPS))
    (BUILD / "parts").mkdir(exist_ok=True)
    if args.mux_only:
        parts = sorted(str(p) for p in (BUILD / "parts").glob("part*.ts"))
    else:
        for old in (BUILD / "parts").glob("part*"):
            old.unlink()
        jobs = max(1, args.jobs)
        bounds = [round(total_frames * k / jobs) for k in range(jobs + 1)]
        with Pool(jobs) as pool:
            parts = pool.map(encode_part, [(k, bounds[k], bounds[k + 1]) for k in range(jobs)])
    srt = ROOT / "subtitles.srt"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", "concat:" + "|".join(parts),
           "-i", str(BUILD / "narration.wav")]
    if srt.exists():
        cmd += ["-i", str(srt)]
    cmd += ["-map", "0:v", "-map", "1:a"]
    if srt.exists():
        cmd += ["-map", "2:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=rus",
                "-metadata:s:s:0", "title=Русские субтитры", "-disposition:s:0", "0"]
    cmd += ["-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
            "-metadata", f"title={TITLE}", "-metadata:s:a:0", "language=rus", "-movflags", "+faststart",
            str(OUT)]
    subprocess.run(cmd, check=True)
    print("Готово:", OUT)


if __name__ == "__main__":
    sys.exit(main())

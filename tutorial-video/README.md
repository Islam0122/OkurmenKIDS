# «Как установить приложение Okurmen Kids Digital» — tutorial video

A 16:9 1920×1080, 30 fps training video in Russian: narration, burned-in subtitles
plus a separate `.srt`, white Okurmen Kids branding (gold `#F5B52B`, violet
`#291078`), eight chapters.

**Output:** `out/okurmen-kids-install.mp4`, with a Russian subtitle track inside,
and `out/okurmen-kids-install.srt`.

## What is real in the video

| Chapter | Content |
| --- | --- |
| 1 Введение | Brand title card |
| 2 Откройте портал | **Real screen recording** of Chrome: address typed in the address bar, the portal, the «Установить приложение» button, **Chrome's own install dialog** («Отмена» / «Установить») |
| 3 macOS · 4 Windows · 5 Android · 6 iPhone | **Your recordings** (see below). Until a recording is added, a brand card with the exact steps and the note «Запись экрана будет добавлена» |
| 7 Запуск приложения | **Real recording**: after «Установить», Chrome opens the installed Okurmen Kids app in its own window (title bar, no address bar) at `/portal` |
| 8 Final | Brand card with the portal address |

Nothing imitates a browser or an operating system. Zooms, gold frames around the
buttons to press, click ripples and the cursor halo are drawn **on top of** the
real recordings, at positions logged during the capture.

How chapter 2 and 7 were recorded (`capture_chrome.mjs`): a virtual 1920×1080
display, headed Chromium with Russian UI and a normal profile, real keyboard and
mouse input (`xdotool`), and ffmpeg screen capture. The recording sandbox cannot
reach Vercel, so the production host name was served locally from this
repository's build of the same app, over real HTTPS with a certificate trusted
only inside the recording profile. That is why the address bar shows
`okurmen-kids-drab.vercel.app/portal`. API calls answered «signed out».

## Adding the macOS / Windows / Android / iPhone recordings

Put the files in `recordings/` and rebuild. Names:

| File | Record this (screen recording, any resolution; 16:9 or phone portrait both work) |
| --- | --- |
| `recordings/macos.mp4` | Chrome or Edge on a Mac: open the portal → click «Установить приложение» → in Chrome's dialog click «Установить» → the app window opens → show the icon in the Dock / Launchpad. Optional: Safari 17+ → «Файл» → «Добавить в Dock». |
| `recordings/windows.mp4` | Chrome or Edge on Windows: the same steps → show the app in the Start menu / on the desktop. |
| `recordings/android.mp4` | Android, Chrome: open the portal → «Установить приложение» → confirm «Установить» → show the icon on the home screen. |
| `recordings/iphone.mp4` | iPhone, Safari: open the portal → «Поделиться» → «На экран „Домой“» → «Добавить» → show the icon. |

Tips: macOS: Shift-Cmd-5 → «Записать весь экран». Windows: Win+Alt+R (Xbox Game Bar)
or Win+Shift+R (Snipping Tool). Android and iPhone: the built-in screen recorder in
the control panel. Keep each clip about 10–20 s, signed out, with no personal data
on screen.

Optional highlights for a clip go in `recordings/<name>.json`: the moments and
buttons to frame in gold (seconds from the clip start, pixel coordinates of the
clip):

```json
[{ "t": 3.2, "x": 840, "y": 96, "w": 220, "h": 40, "label": "Установить приложение" }]
```

The chapter grows to the clip's length automatically. Narration and subtitles for
these chapters are in `script.json`; edit them if your recording shows a
different order.

## Rebuild

```bash
# once: system tools (Ubuntu)
apt-get install -y rhvoice rhvoice-russian xdotool xvfb ffmpeg imagemagick libnss3-tools
pip install pillow numpy fonttools brotli
python - <<'PY'   # brand font → build/manrope-{latin,cyrillic}.ttf
from fontTools.ttLib import TTFont
for s in ('latin', 'cyrillic'):
    f = TTFont(f'../frontend/node_modules/@fontsource-variable/manrope/files/manrope-{s}-wght-normal.woff2')
    f.flavor = None; f.save(f'build/manrope-{s}.ttf')
PY

(cd ../frontend && npm run build)  # the app that gets recorded
node capture_chrome.mjs            # re-record chapters 2 and 7 (≈ 30 s)
python render.py                   # → out/okurmen-kids-install.mp4 + .srt (a few minutes)
```

`render.py` caches narration per line and only re-synthesises lines whose text
changed.

## Voice

The narration uses **RHVoice** (offline, voice `tatiana`; set `"voice"` in
`script.json`, e.g. `anna`, `arina`, `elena`, `irina`, `victoria`). It is clear
but synthetic: natural cloud voices were not reachable from the build machine.
To swap in a better voice later, replace the files in `build/audio/` (one WAV per
line, names `<scene>_<n>.wav`) or record them yourself. `say` in `script.json`
is the pronunciation text (e.g. «Окурмэн Кидс», «Хром»); `text` is the subtitle.

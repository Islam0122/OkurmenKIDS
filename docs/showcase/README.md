# OkurmenKIDS — YouTube showcase video

Deliverables for the 6:17 showcase video (1920×1080, 30 fps, H.264 + AAC, −15 LUFS).
The MP4 itself (`okurmenkids-showcase.mp4`, ~84 MB) is not committed; it is delivered separately.

| File | What |
|---|---|
| `narration-script-en.md` | English narration script, by scene |
| `okurmenkids-showcase.en.srt` | English subtitles (upload to YouTube as captions) |
| `okurmenkids-showcase.ru.srt` | Russian subtitles |
| `youtube-description.txt` | YouTube description with chapters and all five production URLs |
| `okurmenkids-youtube-thumbnail.png` | 1280×720 thumbnail |
| `screenshots/` | Production screenshots (Nov 2026). Student names are blurred. `12-…LOCAL…` is a local dev instance with an empty database |
| `tooling/` | Scripts that produced the video (see below) |

## How it was verified

- All five URLs were opened in headless Chromium on 2026-11-24: `okurmenkids.com` (307 → www, 200), `lms.okurmenkids.com` (200),
  `api.okurmenkids.com/admin/` (302 → login, 200), `api.okurmenkids.com` (404 at `/` by design; `/api/v1/` → `{"status": "ok"}`),
  `training.okurmenkids.com` (200, API calls succeed).
- API figures come from the live schema `https://api.okurmenkids.com/api/schema/`: 724 paths, 966 operations. 28 apps in `backend/apps/`.
- Infrastructure claims come from `backend/Dockerfile`, `backend/deployment/`, `backend/config/settings/`, `backend/config/celery.py`
  and `OKURMEN_PRODUCTION_AUDIT.md`. Redis is described as an *optional* Celery broker because the repository does not show whether
  production sets `CELERY_BROKER_URL`.
- Nothing was logged into in production, nothing was submitted. LMS cabinets and the production admin are not shown. The admin
  dashboard in the video is a local `runserver` on an empty SQLite database and is labelled as such on screen.

## Tooling

1. `rec/scenes.js` — records the live sites with a Chrome DevTools screencast (`node scenes.js website lms admin api training`).
2. `tts.py` — narration with Kokoro TTS (`KOKORO_DIR` must contain `kokoro-v1.0.onnx` and `voices-v1.0.bin`); text in `script.py`.
3. `gfx/gfx.html` + `gfx/render.js` — motion graphics rendered frame by frame.
4. `music/music.py` — original synthesized background track.
5. `compose.py` — timeline, browser frames, crossfades, ducked music mix, EN/RU subtitles, final MP4.

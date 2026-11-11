# Okurmen Kids LMS — видеодемонстрация

Продуктовое демо платформы длительностью **2:46** (1920×1080, 30 fps, H.264 + AAC).
Каждый экран в ролике — настоящая страница работающего приложения
(Django + DRF + PostgreSQL + React/TypeScript), запущенного локально на
демо-данных, которые создали штатные seed-команды проекта. Макетов и
фальшивых интерфейсов нет: монтаж добавляет только движение камеры, подсветку
блоков, подписи и титры.

## Результат

| Файл | Что это |
|---|---|
| [`media/okurmen-kids-lms-demo.mp4`](media/okurmen-kids-lms-demo.mp4) | Готовое видео, 2:46, Full HD |
| [`media/cover-1920x1080.png`](media/cover-1920x1080.png), [`media/cover-1280x720.jpg`](media/cover-1280x720.jpg) | Обложка (YouTube-превью — 1280×720) |
| [`VOICEOVER.md`](VOICEOVER.md) | Текст диктора с таймкодами |
| [`YOUTUBE.md`](YOUTUBE.md) | Название, описание, главы и теги для YouTube |
| [`ANALYSIS.md`](ANALYSIS.md) | Анализ проекта: модули, автоматизация, стек |
| [`SCENARIO.md`](SCENARIO.md) | Сценарий, список экранов, план монтажа с таймкодами |
| [`MANUAL_RECORDING.md`](MANUAL_RECORDING.md) | Как переснять ролик вручную (OBS) на своём стенде или в production |
| [`pipeline/`](pipeline) | Скрипты, которыми собран ролик (стенд → съёмка → озвучка → рендер) |

## Персональные данные

Все люди в ролике вымышленные. Данные созданы командами `generate_mock_data`,
`seed_accounting_demo`, `seed_billing_demo`, после чего
`pipeline/prepare_stand.py` заменил тестовые метки (`[MOCK]`, `DEMO`) на
нейтральные вымышленные имена. Телефоны — `+996 000 …`. Реальная база
production в съёмке не участвовала. В кадре постоянно видна подпись
«Демонстрационные данные · все имена вымышленные».

## Как пересобрать ролик

Нужны: PostgreSQL, Node 22, Python 3.12+, Chromium + Playwright, `ffmpeg`,
`faketime`, `rhvoice` + `rhvoice-russian` (офлайн-TTS).

```bash
# 1. Стенд: отдельная локальная база + штатные демо-данные
export DJANGO_SETTINGS_MODULE=demo_settings PYTHONPATH=docs/demo-video/pipeline \
       EMAIL_HOST_USER=demo@example.invalid EMAIL_HOST_PASSWORD=x DEMO_PASSWORD='<локальный пароль>'
cd backend && python manage.py migrate
FT='faketime -f @2026-11-12 04:20:00'           # «сегодня» = четверг, 10:20 по Бишкеку
$FT python manage.py generate_mock_data --start-date 2026-08-03 --end-date 2026-11-11
$FT python manage.py seed_accounting_demo
$FT python manage.py seed_billing_demo
$FT python manage.py shell < ../docs/demo-video/pipeline/prepare_stand.py
$FT python manage.py runserver 8000 &           # API
cd ../frontend && npm ci && npx vite --port 5173 &

# 2. Съёмка реальных экранов (3840×2160, DPR 2) + живая QR-отметка на телефоне
node docs/demo-video/pipeline/capture.js <out>/img
#   отметку прихода снимали с бэкендом под faketime 08:56, чтобы она была без опоздания:
#   NOW='2026-11-12T08:56:50+06:00' node capture.js <out>/img m_

# 3. Озвучка (RHVoice, голос aleksandr-hq) по pipeline/script.json
python3 docs/demo-video/pipeline/tts.py <workdir> aleksandr-hq 100

# 4. Рендер: pipeline/stage/index.html + timeline.js (рядом положить img/ и шрифт Manrope
#    из frontend/node_modules/@fontsource-variable/manrope/files) → кадры → ffmpeg
node renderall.js <frames> 30 3
ffmpeg -framerate 30 -i <frames>/f%05d.jpg -i mix.wav -c:v libx264 -crf 17 -pix_fmt yuv420p \
       -c:a aac -b:a 192k -movflags +faststart okurmen-kids-lms-demo.mp4
```

Идентификаторы занятий, группы и студента в `capture.js` (`/app/lessons/108`,
`/app/groups/2` и т. д.) относятся к базе, собранной этими командами; на
другой базе их нужно подставить свои.

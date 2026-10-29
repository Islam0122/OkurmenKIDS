#!/usr/bin/env bash
# Полная пересборка обучающего видео «Кабинет маркетинга».
#
#   ./marketing_video/build.sh          — всё: демо-среда → озвучка → запись → монтаж → проверка
#   SKIP_RECORD=1 ./marketing_video/build.sh — только перемонтаж по готовой записи
#
# Использует ОТДЕЛЬНУЮ демо-базу SQLite ($MARKETING_DEMO_DB), production не трогает.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
PY="${PYTHON:-python3}"
export MARKETING_DEMO_DB="${MARKETING_DEMO_DB:-/tmp/okurmen_marketing_demo.sqlite3}"
export PYTHONPATH="$REPO/backend:$HERE/demo"
export DJANGO_SETTINGS_MODULE=video_settings

cd "$HERE"
mkdir -p build

started=()
cleanup() { for pid in "${started[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT

wait_url() {
  for _ in $(seq 1 60); do curl -s -o /dev/null "$1" && return 0; sleep 1; done
  echo "Не дождался $1" >&2; return 1
}

echo "== 1. Озвучка (RHVoice)"
"$PY" tts.py
"$PY" docs.py

if [ -z "${SKIP_RECORD:-}" ]; then
  echo "== 2. Демо-база и данные"
  "$PY" "$REPO/backend/manage.py" migrate -v0
  "$PY" demo/seed_demo.py

  echo "== 3. Backend и frontend"
  if ! curl -s -o /dev/null http://127.0.0.1:8000/api/v1/; then
    "$PY" "$REPO/backend/manage.py" runserver 127.0.0.1:8000 --noreload > build/backend.log 2>&1 &
    started+=($!)
  fi
  if ! curl -s -o /dev/null http://127.0.0.1:5173/; then
    (cd "$REPO/frontend" && npx vite --host 127.0.0.1 --port 5173 > "$HERE/build/vite.log" 2>&1) &
    started+=($!)
  fi
  wait_url http://127.0.0.1:8000/api/v1/
  wait_url http://127.0.0.1:5173/

  echo "== 4. Запись экрана (Playwright)"
  node record.cjs
fi

echo "== 5. Монтаж"
"$PY" compose.py --jobs "${JOBS:-4}"

echo "== 6. Проверка"
"$PY" verify.py

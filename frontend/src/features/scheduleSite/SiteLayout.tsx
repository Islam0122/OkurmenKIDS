import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'

import logo from '@/assets/logo.png'

/** «OkurmenKIDS Schedule» — the public schedule site: no login, no LMS
 * navigation; it reads only the public schedule API. */
export function SiteLayout() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000)
    return () => window.clearInterval(id)
  }, [])
  useEffect(() => {
    const previous = document.title
    document.title = 'OkurmenKIDS Schedule — расписание занятий'
    return () => {
      document.title = previous
    }
  }, [])

  return (
    <div className="min-h-dvh bg-surface-muted">
      <header className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5">
          <a href="/schedule" className="flex items-center gap-2.5">
            <img src={logo} alt="" className="size-8 object-contain" />
            <span className="text-base font-semibold text-ink">
              OkurmenKIDS <span className="text-brand-700">Schedule</span>
            </span>
          </a>
          <span className="text-sm text-ink-secondary first-letter:uppercase" aria-label="Текущая дата">
            {now.toLocaleString('ru-RU', { timeZone: 'Asia/Bishkek', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-[1800px] px-3 py-4 sm:px-4">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-[1800px] px-4 pb-6 text-xs text-ink-muted">
        Расписание академии OkurmenKIDS. Обновляется автоматически; изменения и отмены появляются здесь сразу после внесения в систему.
      </footer>
    </div>
  )
}

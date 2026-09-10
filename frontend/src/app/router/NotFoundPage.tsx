import { CompassIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-surface-muted px-4 text-center">
      <span className="flex size-14 items-center justify-center rounded-full bg-surface-hover text-ink-muted">
        <CompassIcon className="size-6" aria-hidden />
      </span>
      <div>
        <h1 className="text-lg font-semibold text-ink">Страница не найдена</h1>
        <p className="mt-1 text-sm text-ink-secondary">Похоже, такого раздела не существует.</p>
      </div>
      <Link
        to="/app/dashboard"
        className="inline-flex h-10 items-center justify-center rounded-lg bg-brand-500 px-4 text-sm font-medium text-white hover:bg-brand-600"
      >
        На главную
      </Link>
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, KeyRound, LogOut, Maximize2, Minimize2, RefreshCw, Tv, X } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { monthlyPerformanceApi, type PerformanceDay, type TrendKey } from '@/api/monthlyPerformance'
import logo from '@/assets/logo.png'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { useAuth } from '@/hooks/useAuth'
import { extractErrorMessage, isForbidden, isUnauthorized } from '@/lib/apiError'
import { cn } from '@/utils/cn'

import { dashboardKeyStorage } from './dashboardKey'
import { MONTHS, formatDateTime } from './format'
import { CorrectionModal, DailyTable, KpiCard, METRICS } from './parts'
import { PerformanceChart } from './PerformanceChart'

export const MONTHLY_PERFORMANCE_PATH = '/monthly-performance'
export const REFRESH_INTERVAL_MS = 5 * 60 * 1000
const PROJECT_TZ = 'Asia/Bishkek'

const CHARTS: { key: TrendKey; title: string; kind: 'percent' | 'count' }[] = [
  { key: 'attendance', title: 'График посещаемости', kind: 'percent' },
  { key: 'homework', title: 'Выполнение домашних заданий', kind: 'percent' },
  { key: 'students', title: 'Динамика количества студентов', kind: 'count' },
  { key: 'groups', title: 'Динамика количества групп', kind: 'count' },
]

function nowInProject(): { year: number; month: number } {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: PROJECT_TZ, year: 'numeric', month: 'numeric' }).formatToParts(new Date())
  return {
    year: Number(parts.find((p) => p.type === 'year')?.value),
    month: Number(parts.find((p) => p.type === 'month')?.value),
  }
}

function useClock(intervalMs = 1000): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), intervalMs)
    return () => window.clearInterval(timer)
  }, [intervalMs])
  return now
}

function useFullscreen() {
  const [active, setActive] = useState(() => Boolean(document.fullscreenElement))
  useEffect(() => {
    const onChange = () => setActive(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])
  const enter = () => document.documentElement.requestFullscreen?.().catch(() => undefined)
  const exit = () => {
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => undefined)
  }
  return { active, enter, exit }
}

/**
 * «OkurmenKIDS — Общая статистика» — отдельный сайт (не страница кабинета LMS):
 * свой адрес /monthly-performance, своя шапка, без меню LMS. Доступ — только
 * для своих: вход сотрудника (тот же, что в LMS) или ключ «только чтение» для
 * телевизора в офисе (`?key=…` — запоминается в браузере и убирается из адреса).
 * Все цифры считает backend (apps.performance); здесь только отображение.
 */
export function MonthlyPerformanceSite() {
  const { status } = useAuth()
  const [params, setParams] = useSearchParams()
  const [dashboardKey, setDashboardKey] = useState<string | null>(() => params.get('key') || dashboardKeyStorage.get())

  useEffect(() => {
    const previous = document.title
    document.title = 'OkurmenKIDS — Общая статистика'
    return () => {
      document.title = previous
    }
  }, [])

  // Ключ из ссылки — запомнить и убрать из адресной строки.
  useEffect(() => {
    const fromUrl = params.get('key')
    if (!fromUrl) return
    dashboardKeyStorage.set(fromUrl)
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('key')
      return next
    }, { replace: true })
  }, [params, setParams])

  const applyKey = useCallback((value: string | null) => {
    if (value) dashboardKeyStorage.set(value)
    else dashboardKeyStorage.clear()
    setDashboardKey(value)
  }, [])

  if (!dashboardKey && status === 'loading') return <LoadingState label="Проверяем доступ…" fullScreen />
  if (!dashboardKey && status !== 'authenticated') return <AccessScreen onKey={applyKey} />
  return <Dashboard dashboardKey={dashboardKey} onKey={applyKey} />
}

// ---------------------------------------------------------------------------
// Экран доступа
// ---------------------------------------------------------------------------

function AccessScreen({ onKey, error }: { onKey: (key: string | null) => void; error?: string }) {
  const { login } = useAuth()
  const [key, setKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [loggingIn, setLoggingIn] = useState(false)

  const submitKey = (event: FormEvent) => {
    event.preventDefault()
    if (key.trim()) onKey(key.trim())
  }
  const submitLogin = async (event: FormEvent) => {
    event.preventDefault()
    setLoginError(null)
    setLoggingIn(true)
    try {
      await login(username.trim(), password)
      onKey(null) // вошёл сотрудник — ключ (возможно, неверный) больше не нужен
    } catch (err) {
      setLoginError(extractErrorMessage(err, 'Неверный логин или пароль.'))
    } finally {
      setLoggingIn(false)
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-surface-muted px-4 py-10">
      <div className="card w-full max-w-md p-6 sm:p-8">
        <div className="flex items-center gap-3">
          <img src={logo} alt="" className="size-12 object-contain" />
          <div>
            <p className="text-sm font-bold tracking-[0.2em] text-brand-700">OKURMENKIDS</p>
            <h1 className="text-xl font-semibold text-ink">Общая статистика академии</h1>
          </div>
        </div>
        <p className="mt-4 text-sm text-ink-secondary">Доступ только для сотрудников академии.</p>
        {error ? <p className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{error}</p> : null}

        <form className="mt-5 space-y-2" onSubmit={submitKey}>
          <label className="flex flex-col gap-1 text-sm font-medium text-ink">
            Ключ доступа
            <Input value={key} onChange={(e) => setKey(e.target.value)} placeholder="okd_…" autoComplete="off" />
          </label>
          <Button type="submit" className="w-full" leftIcon={<KeyRound className="size-4" aria-hidden />} disabled={!key.trim()}>
            Открыть по ключу
          </Button>
        </form>

        <div className="my-5 flex items-center gap-3 text-xs text-ink-muted">
          <span className="h-px flex-1 bg-border" />или войдите как сотрудник<span className="h-px flex-1 bg-border" />
        </div>

        <form className="space-y-3" onSubmit={submitLogin}>
          <label className="flex flex-col gap-1 text-sm font-medium text-ink">
            Логин
            <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium text-ink">
            Пароль
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </label>
          {loginError ? <p className="text-sm text-danger" role="alert">{loginError}</p> : null}
          <Button type="submit" variant="secondary" className="w-full" isLoading={loggingIn} disabled={!username || !password}>
            Войти
          </Button>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Панель
// ---------------------------------------------------------------------------

function Dashboard({ dashboardKey, onKey }: { dashboardKey: string | null; onKey: (key: string | null) => void }) {
  const [params, setParams] = useSearchParams()
  const tv = params.get('tv') === '1'
  const current = nowInProject()
  const year = Number(params.get('year')) || current.year
  const month = Number(params.get('month')) || current.month
  const [pickerOpen, setPickerOpen] = useState(false)
  const [editDay, setEditDay] = useState<PerformanceDay | null>(null)
  const fullscreen = useFullscreen()
  const now = useClock()

  const query = useQuery({
    queryKey: ['monthly-performance', year, month, dashboardKey ?? 'user'],
    queryFn: () => monthlyPerformanceApi.month({ year, month }, dashboardKey),
    refetchInterval: REFRESH_INTERVAL_MS,
    refetchIntervalInBackground: true,
    placeholderData: (previous) => previous,
    retry: (count, error) => !isUnauthorized(error) && !isForbidden(error) && count < 2,
  })
  const { data, isLoading, isError, error, refetch, isFetching, dataUpdatedAt } = query

  const update = useCallback(
    (changes: Record<string, string | null>) => {
      setParams((prev) => {
        const next = new URLSearchParams(prev)
        for (const [key, value] of Object.entries(changes)) {
          if (value === null) next.delete(key)
          else next.set(key, value)
        }
        return next
      }, { replace: true })
    },
    [setParams],
  )

  const enterTv = () => {
    update({ tv: '1' })
    fullscreen.enter()
  }
  const exitTv = useCallback(() => {
    update({ tv: null })
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => undefined)
  }, [update])

  useEffect(() => {
    if (!tv) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') exitTv()
    }
    // Браузер сам выходит из полноэкранного режима по Esc — выходим и из режима телевизора.
    let wasFullscreen = Boolean(document.fullscreenElement)
    const onFullscreen = () => {
      if (wasFullscreen && !document.fullscreenElement) exitTv()
      wasFullscreen = Boolean(document.fullscreenElement)
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('fullscreenchange', onFullscreen)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('fullscreenchange', onFullscreen)
    }
  }, [tv, exitTv])

  // Ключ отключён или неверен — вернуть на экран доступа.
  if (isError && (isUnauthorized(error) || isForbidden(error))) {
    if (dashboardKey) {
      return <AccessScreen onKey={onKey} error="Ключ доступа недействителен или отключён. Укажите другой ключ или войдите как сотрудник." />
    }
    return <AccessScreen onKey={onKey} error="Нет доступа к статистике." />
  }

  const { date, time } = formatDateTime(now, PROJECT_TZ)
  const updated = dataUpdatedAt ? formatDateTime(new Date(dataUpdatedAt), PROJECT_TZ).time : '—'
  const years = data?.available_years ?? [current.year]
  const isCurrent = year === current.year && month === current.month
  const monthOptions = MONTHS.map((label, index) => ({ value: String(index + 1), label }))
    .filter((option) => year < current.year || Number(option.value) <= current.month)

  return (
    <div className={cn('min-h-dvh bg-surface', tv && 'fixed inset-0 z-40 overflow-auto')} data-testid={tv ? 'tv-mode' : undefined}>
      {/* Шапка сайта */}
      <header className={cn('border-b border-border bg-surface', !tv && 'sticky top-0 z-30')}>
        <div className={cn('mx-auto flex w-full flex-wrap items-center justify-between gap-x-6 gap-y-3', tv ? 'px-8 py-4' : 'max-w-[1600px] px-4 py-3 sm:px-6')}>
          <div className="flex min-w-0 items-center gap-3">
            <img src={logo} alt="" className={cn('shrink-0 object-contain', tv ? 'size-16' : 'size-11')} />
            <div className="min-w-0">
              <p className={cn('font-extrabold tracking-[0.2em] text-brand-700', tv ? 'text-xl' : 'text-xs')}>OKURMENKIDS</p>
              <h1 className={cn('font-bold leading-tight text-ink', tv ? 'text-5xl' : 'text-xl sm:text-2xl')}>Общая статистика академии</h1>
              <p className={cn('text-ink-secondary', tv ? 'text-2xl' : 'text-sm')}>{MONTHS[month - 1]} {year}</p>
            </div>
          </div>
          <div className={cn('flex items-center', tv ? 'gap-6' : 'gap-4')}>
            <div className="text-right">
              <p className={cn('font-bold tabular-nums text-ink', tv ? 'text-6xl' : 'text-2xl')} data-testid="clock">{time}</p>
              <p className={cn('text-ink-secondary', tv ? 'text-xl' : 'text-xs sm:text-sm')}>{date}</p>
            </div>
            {tv ? (
              <button
                type="button"
                onClick={exitTv}
                className="flex size-12 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover hover:text-ink"
                aria-label="Выйти из режима телевизора (Esc)"
                title="Выйти (Esc)"
              >
                <X className="size-7" aria-hidden />
              </button>
            ) : null}
          </div>
        </div>
        {!tv ? (
          <div className="mx-auto flex w-full max-w-[1600px] flex-wrap items-center gap-2 px-4 pb-3 sm:px-6">
            <Button variant="secondary" leftIcon={<CalendarDays className="size-4" aria-hidden />} aria-expanded={pickerOpen} onClick={() => setPickerOpen((v) => !v)}>
              Выбрать месяц
            </Button>
            <Button variant="secondary" leftIcon={<RefreshCw className={cn('size-4', isFetching && 'animate-spin')} aria-hidden />} onClick={() => void refetch()} disabled={isFetching}>
              Обновить данные
            </Button>
            <Button
              variant="secondary"
              leftIcon={fullscreen.active ? <Minimize2 className="size-4" aria-hidden /> : <Maximize2 className="size-4" aria-hidden />}
              onClick={fullscreen.active ? fullscreen.exit : fullscreen.enter}
            >
              {fullscreen.active ? 'Выйти из полноэкранного режима' : 'Полноэкранный режим'}
            </Button>
            <Button leftIcon={<Tv className="size-4" aria-hidden />} onClick={enterTv}>
              Режим телевизора
            </Button>
            <span className="ml-auto flex items-center gap-3 text-xs text-ink-muted">
              <span>Последнее обновление: {updated}</span>
              {data ? (
                <span>
                  {data.access.mode === 'key' ? `Доступ по ключу: ${data.access.name}` : data.access.name}
                </span>
              ) : null}
              {dashboardKey ? (
                <button type="button" className="inline-flex items-center gap-1 font-medium text-ink-secondary hover:text-danger" onClick={() => onKey(null)}>
                  <LogOut className="size-3.5" aria-hidden />
                  Забыть ключ
                </button>
              ) : null}
            </span>
          </div>
        ) : null}
        {!tv && pickerOpen ? (
          <div className="mx-auto flex w-full max-w-[1600px] flex-wrap items-end gap-2 border-t border-border px-4 py-3 sm:px-6">
            <label className="flex flex-col gap-1 text-xs font-medium text-ink-secondary">
              Месяц
              <Select aria-label="Месяц" className="w-40" value={String(month)} options={monthOptions}
                onChange={(event) => update({ year: String(year), month: event.target.value })} />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-ink-secondary">
              Год
              <Select aria-label="Год" className="w-28" value={String(year)} options={years.map((y) => ({ value: String(y), label: String(y) }))}
                onChange={(event) => {
                  const nextYear = Number(event.target.value)
                  update({ year: String(nextYear), month: String(nextYear === current.year ? Math.min(month, current.month) : month) })
                }} />
            </label>
            <Button variant="ghost" onClick={() => update({ year: null, month: null })} disabled={isCurrent}>
              Текущий месяц
            </Button>
          </div>
        ) : null}
      </header>

      <main className={cn('mx-auto w-full', tv ? 'flex flex-col gap-5 px-8 py-5' : 'max-w-[1600px] space-y-6 px-4 py-6 sm:px-6')}>
        {isLoading ? (
          <LoadingState label="Загружаем статистику…" />
        ) : isError || !data ? (
          <ErrorState onRetry={() => void refetch()} />
        ) : (
          <>
            <div className={cn('grid', tv ? 'grid-cols-4 gap-5' : 'grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4')}>
              {METRICS.map((metric) => (
                <KpiCard key={metric.key} metric={metric} card={data.summary[metric.key]} tv={tv} />
              ))}
            </div>
            <DailyTable data={data} tv={tv} onEdit={data.can_edit && !tv ? setEditDay : undefined} />
            <div className={cn('grid', tv ? 'grid-cols-4 gap-5' : 'grid-cols-1 gap-4 lg:grid-cols-2')}>
              {CHARTS.map((chart) => (
                <PerformanceChart
                  key={chart.key}
                  title={chart.title}
                  kind={chart.kind}
                  points={data.trends[chart.key].points}
                  average={data.trends[chart.key].average}
                  daysInMonth={data.days.length}
                  tv={tv}
                />
              ))}
            </div>
            {tv ? (
              <p className="text-right text-lg text-ink-muted">
                Последнее обновление: {updated} · обновляется каждые 5 минут · выход — Esc
              </p>
            ) : (
              <p className="text-xs text-ink-muted">
                Только итоговые показатели академии — без персональных данных студентов. Данные обновляются автоматически каждые 5 минут.
              </p>
            )}
          </>
        )}
      </main>

      {editDay ? <CorrectionModal day={editDay} onClose={() => setEditDay(null)} /> : null}
    </div>
  )
}

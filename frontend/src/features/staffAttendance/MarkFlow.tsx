import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { AlertTriangle, CheckCircle2, LoaderCircle, LogOut, MapPin, RefreshCw } from 'lucide-react'

import { staffAttendanceApi } from '@/api/staffAttendance'
import { Button } from '@/components/ui/Button'
import { useRefreshMyAttendance } from '@/hooks/useStaffAttendance'
import type { MarkErrorBody, MarkKind, MarkResult, OfficeInfo } from '@/types/staffAttendance'

import { formatDay, formatDistance, formatDuration, formatLate, formatTime, DEFAULT_TZ } from './format'
import { getFreshPosition, GeolocationFailure, type FreshPosition } from './geolocation'
import { QrScanner } from './QrScanner'
import { newIdempotencyKey, parseOfficeQr } from './scanUrl'

type Step =
  | { kind: 'scan'; hint?: string }
  | { kind: 'busy'; label: string }
  | { kind: 'success'; result: MarkResult }
  | { kind: 'error'; message: string; retry: 'scan' | 'locate' }

function serverError(error: unknown): { message: string; body?: MarkErrorBody; noResponse: boolean } {
  if (isAxiosError(error)) {
    const body = error.response?.data as MarkErrorBody | undefined
    if (!error.response) return { message: 'Нет связи с сервером. Проверьте интернет и повторите попытку.', noResponse: true }
    if (error.response.status === 429) return { message: 'Слишком много попыток. Подождите немного и повторите.', noResponse: false }
    if (body?.detail) return { message: body.detail, body, noResponse: false }
    return { message: `Сервер не принял отметку (ошибка ${error.response.status}). Повторите попытку.`, noResponse: error.response.status >= 500 }
  }
  return { message: 'Что-то пошло не так. Повторите попытку.', noResponse: false }
}

export interface MarkFlowProps {
  /** Что отметить: приход или уход (по текущему статусу с сервера). */
  action: MarkKind
  /** Код офиса, если страница открыта по ссылке из QR (камера не нужна). */
  presetCode?: string
  onDone: () => void
}

/** Сканирование QR → проверка офиса → свежая геолокация → отметка на
 * сервере → экран подтверждения. Успех показывается только после ответа
 * backend. */
export function MarkFlow({ action, presetCode, onDone }: MarkFlowProps) {
  const refresh = useRefreshMyAttendance()
  const [step, setStep] = useState<Step>(presetCode ? { kind: 'busy', label: 'Проверяем QR-код офиса…' } : { kind: 'scan' })
  const officeRef = useRef<OfficeInfo | null>(null)
  // Один ключ на попытку: при обрыве связи повтор уходит с тем же ключом
  // и не создаёт вторую отметку; после ответа сервера ключ меняется.
  const keyRef = useRef<string>(newIdempotencyKey())
  const busyRef = useRef(false)

  const submit = useCallback(async () => {
    const office = officeRef.current
    if (!office) return
    setStep({ kind: 'busy', label: 'Определяем ваше местоположение…' })
    let position: FreshPosition
    try {
      position = await getFreshPosition()
    } catch (error) {
      const message = error instanceof GeolocationFailure ? error.message : 'Не удалось получить геолокацию.'
      setStep({ kind: 'error', message, retry: 'locate' })
      return
    }
    setStep({ kind: 'busy', label: action === 'check_in' ? 'Регистрируем приход…' : 'Регистрируем уход…' })
    const payload = { location_code: office.code, ...position, idempotency_key: keyRef.current }
    try {
      const result = action === 'check_in' ? await staffAttendanceApi.checkIn(payload) : await staffAttendanceApi.checkOut(payload)
      keyRef.current = newIdempotencyKey()
      refresh()
      setStep({ kind: 'success', result })
    } catch (error) {
      const { message, body, noResponse } = serverError(error)
      if (!noResponse) keyRef.current = newIdempotencyKey()
      if (body?.code === 'already_checked_in' || body?.code === 'not_checked_in' || body?.code === 'stale_session') refresh()
      const retry = body?.code === 'location_not_found' || body?.code === 'location_inactive' ? 'scan' : 'locate'
      setStep({ kind: 'error', message, retry })
    }
  }, [action, refresh])

  const startWithCode = useCallback(
    async (code: string) => {
      if (busyRef.current) return
      busyRef.current = true
      setStep({ kind: 'busy', label: 'Проверяем QR-код офиса…' })
      try {
        officeRef.current = await staffAttendanceApi.verifyOffice(code)
      } catch (error) {
        setStep({ kind: 'error', message: serverError(error).message, retry: 'scan' })
        busyRef.current = false
        return
      }
      await submit()
      busyRef.current = false
    },
    [submit],
  )

  useEffect(() => {
    if (presetCode) void startWithCode(presetCode)
    // Только при открытии: повтор — кнопкой.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onScan = useCallback(
    (text: string) => {
      const parsed = parseOfficeQr(text)
      if ('reason' in parsed) {
        setStep({ kind: 'scan', hint: parsed.reason })
        return
      }
      void startWithCode(parsed.code)
    },
    [startWithCode],
  )

  const retry = () => {
    if (step.kind !== 'error') return
    if (step.retry === 'locate' && officeRef.current) {
      busyRef.current = true
      void submit().finally(() => {
        busyRef.current = false
      })
    } else {
      officeRef.current = null
      setStep({ kind: 'scan' })
    }
  }

  if (step.kind === 'success') return <SuccessScreen result={step.result} onDone={onDone} />

  return (
    <div className="space-y-4">
      {step.kind === 'scan' ? (
        <>
          <QrScanner onResult={onScan} />
          {step.hint ? (
            <p className="flex items-start gap-2 rounded-xl bg-warning-soft px-3 py-2 text-sm text-warning" role="alert">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {step.hint}
            </p>
          ) : (
            <p className="text-center text-sm text-ink-secondary">
              {action === 'check_in' ? 'После сканирования отметим приход.' : 'После сканирования отметим уход.'} Понадобится доступ к геолокации.
            </p>
          )}
        </>
      ) : null}

      {step.kind === 'busy' ? (
        <div className="flex flex-col items-center gap-3 py-12 text-center" role="status">
          <LoaderCircle className="size-10 animate-spin text-brand-500" aria-hidden />
          <p className="font-medium text-ink">{step.label}</p>
          {officeRef.current ? <p className="text-sm text-ink-secondary">Офис: {officeRef.current.name}</p> : null}
        </div>
      ) : null}

      {step.kind === 'error' ? (
        <div className="flex flex-col items-center gap-4 py-8 text-center">
          <span className="flex size-16 items-center justify-center rounded-full bg-danger-soft text-danger">
            <AlertTriangle className="size-8" aria-hidden />
          </span>
          <div>
            <p className="text-lg font-semibold text-ink">Отметка не выполнена</p>
            <p className="mt-1 max-w-sm text-sm text-ink-secondary" role="alert">{step.message}</p>
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            <Button leftIcon={<RefreshCw className="size-4" aria-hidden />} onClick={retry}>
              {step.retry === 'scan' ? 'Сканировать снова' : 'Повторить попытку'}
            </Button>
            <Button variant="secondary" onClick={onDone}>Вернуться в кабинет</Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function SuccessScreen({ result, onDone }: { result: MarkResult; onDone: () => void }) {
  const tz = result.timezone || DEFAULT_TZ
  const isIn = result.event === 'check_in'
  const rows: [string, string][] = isIn
    ? [
        ['Сотрудник', result.employee.full_name],
        ['Дата', formatDay(result.session.work_date)],
        ['Время', formatTime(result.occurred_at, tz)],
        ['Офис', result.location.name ?? '—'],
        ['Расстояние до центра', formatDistance(result.distance_m)],
      ]
    : [
        ['Сотрудник', result.employee.full_name],
        ['Время ухода', formatTime(result.occurred_at, tz)],
        ['Начало рабочего дня', formatTime(result.session.checked_in_at, tz)],
        ['Продолжительность сессии', formatDuration(result.session.duration_seconds)],
        ['Офис', result.location.name ?? '—'],
      ]
  return (
    <div className="flex flex-col items-center gap-5 py-4 text-center">
      <span className={isIn ? 'flex size-20 items-center justify-center rounded-full bg-brand-50 text-brand-600' : 'flex size-20 items-center justify-center rounded-full bg-info-soft text-info'}>
        {isIn ? <CheckCircle2 className="size-12" aria-hidden /> : <LogOut className="size-11" aria-hidden />}
      </span>
      <div>
        <h3 className="text-xl font-semibold text-ink">{isIn ? 'Приход успешно зарегистрирован' : 'Уход успешно зарегистрирован'}</h3>
        {result.replayed ? <p className="mt-1 text-sm text-ink-secondary">Эта отметка уже была сохранена ранее.</p> : null}
        {isIn && result.session.late_minutes > 0 ? (
          <p className="mt-1 text-sm font-medium text-warning">Опоздание: {formatLate(result.session.late_minutes)}</p>
        ) : null}
        {result.closed_stale_session ? (
          <p className="mt-1 text-sm text-warning">
            Уход за {formatDay(result.closed_stale_session.work_date, false)} не был отмечен — запись помечена «Нет ухода».
          </p>
        ) : null}
      </div>
      <dl className="w-full max-w-sm divide-y divide-border rounded-2xl border border-border text-left">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3 px-4 py-2.5">
            <dt className="text-sm text-ink-secondary">{label}</dt>
            <dd className="text-sm font-semibold text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="flex items-center gap-1 text-xs text-ink-muted">
        <MapPin className="size-3.5" aria-hidden /> Время — по часовому поясу офиса ({tz})
      </p>
      <Button size="lg" className="w-full max-w-sm" onClick={onDone}>
        Вернуться в кабинет
      </Button>
    </div>
  )
}

import { useState, type FormEvent } from 'react'
import { CalendarCog, Plus, Trash2 } from 'lucide-react'
import { Navigate } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useToast } from '@/components/ui/Toast'
import {
  useAttendanceMeta,
  useAttendanceRecords,
  useAttendanceSettings,
  useDeleteWorkSchedule,
  useSaveWorkSchedule,
  useUpdateAttendanceSettings,
  useWorkSchedules,
} from '@/hooks/useStaffAttendance'
import { extractErrorMessage } from '@/lib/apiError'
import { ROLE_LABEL } from '@/lib/roles'
import type { UserRole } from '@/types/auth'
import type { AttendanceSettings, WorkSchedule } from '@/types/staffAttendance'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const ALL_ROLES = Object.keys(ROLE_LABEL) as UserRole[]

const hhmm = (value: string) => value.slice(0, 5)

function WeekdayPicker({ value, onChange, idPrefix }: { value: number[]; onChange: (days: number[]) => void; idPrefix: string }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Рабочие дни">
      {WEEKDAYS.map((label, day) => {
        const checked = value.includes(day)
        return (
          <label key={label} htmlFor={`${idPrefix}-${day}`} className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm font-medium ${checked ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-border text-ink-secondary'}`}>
            <input
              id={`${idPrefix}-${day}`}
              type="checkbox"
              className="sr-only"
              checked={checked}
              onChange={() => onChange(checked ? value.filter((d) => d !== day) : [...value, day].sort((a, b) => a - b))}
            />
            {label}
          </label>
        )
      })}
    </div>
  )
}

/** /admin/attendance/settings — общее расписание, точность GPS, роли,
 * офисная сеть и личные расписания сотрудников. */
export function SettingsPage() {
  const meta = useAttendanceMeta()
  if (meta.isPending) return <LoadingState label="Проверяем доступ…" />
  if (meta.isError || !meta.data.access.can_manage) return <Navigate to="/attendance" replace />
  return (
    <div className="space-y-5">
      <PageHeader title="Настройки посещаемости" description="Рабочее расписание, опоздания, геолокация и проверка сети" />
      <GeneralSettings />
      <PersonalSchedules today={meta.data.today} />
    </div>
  )
}

function GeneralSettings() {
  const settings = useAttendanceSettings()
  if (settings.isPending) return <LoadingState />
  if (settings.isError) return <ErrorState message={extractErrorMessage(settings.error)} onRetry={() => void settings.refetch()} />
  return <SettingsForm key={settings.data.updated_at} initial={settings.data} />
}

function SettingsForm({ initial }: { initial: AttendanceSettings }) {
  const { showToast } = useToast()
  const update = useUpdateAttendanceSettings()
  const [form, setForm] = useState({ ...initial, work_start: hhmm(initial.work_start), work_end: hhmm(initial.work_end) })
  const [error, setError] = useState<string | null>(null)
  const patch = (values: Partial<typeof form>) => setForm((f) => ({ ...f, ...values }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      await update.mutateAsync({
        timezone: form.timezone,
        max_gps_accuracy_m: Number(form.max_gps_accuracy_m),
        work_start: form.work_start,
        work_end: form.work_end,
        work_days: form.work_days,
        late_grace_minutes: Number(form.late_grace_minutes),
        tracked_roles: form.tracked_roles,
        teacher_schedule_from_lessons: form.teacher_schedule_from_lessons,
        teacher_arrival_before_lesson_minutes: Number(form.teacher_arrival_before_lesson_minutes),
        tracking_started_on: form.tracking_started_on,
        network_check_enabled: form.network_check_enabled,
        office_networks: form.office_networks,
      })
      showToast('Настройки сохранены', 'success')
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  return (
    <Card title="Общие настройки" description={initial.updated_by_name ? `Последнее изменение: ${initial.updated_by_name}` : undefined}>
      <form onSubmit={submit} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label htmlFor="set-start" className="mb-1.5 block field-label">Начало рабочего дня</label>
            <Input id="set-start" type="time" value={form.work_start} onChange={(e) => patch({ work_start: e.target.value })} required />
          </div>
          <div>
            <label htmlFor="set-end" className="mb-1.5 block field-label">Окончание рабочего дня</label>
            <Input id="set-end" type="time" value={form.work_end} onChange={(e) => patch({ work_end: e.target.value })} required />
          </div>
          <div>
            <label htmlFor="set-grace" className="mb-1.5 block field-label">Льготное время опоздания, мин</label>
            <Input id="set-grace" type="number" min={0} max={240} value={form.late_grace_minutes} onChange={(e) => patch({ late_grace_minutes: Number(e.target.value) })} />
          </div>
          <div>
            <label htmlFor="set-tz" className="mb-1.5 block field-label">Часовой пояс офиса</label>
            <Input id="set-tz" value={form.timezone} onChange={(e) => patch({ timezone: e.target.value })} placeholder="Asia/Bishkek" required />
          </div>
          <div>
            <label htmlFor="set-since" className="mb-1.5 block field-label">Учёт ведётся с</label>
            <Input id="set-since" type="date" value={form.tracking_started_on} onChange={(e) => patch({ tracking_started_on: e.target.value })} required />
            <p className="mt-1 text-xs text-ink-muted">Раньше этой даты (и до регистрации сотрудника) дни не считаются пропусками.</p>
          </div>
        </div>
        <div>
          <p className="mb-1.5 field-label">Рабочие дни недели</p>
          <WeekdayPicker idPrefix="set-day" value={form.work_days} onChange={(work_days) => patch({ work_days })} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="set-acc" className="mb-1.5 block field-label">Максимальная погрешность GPS, м</label>
            <Input id="set-acc" type="number" min={5} max={1000} value={form.max_gps_accuracy_m} onChange={(e) => patch({ max_gps_accuracy_m: Number(e.target.value) })} />
            <p className="mt-1 text-xs text-ink-muted">Отметка отклоняется, если браузер сообщает погрешность больше.</p>
          </div>
          <div>
            <p className="mb-1.5 field-label">Кто отмечает приход и уход</p>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {ALL_ROLES.map((role) => (
                <label key={role} className="flex items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={form.tracked_roles.includes(role)}
                    onChange={(e) => patch({ tracked_roles: e.target.checked ? [...form.tracked_roles, role] : form.tracked_roles.filter((r) => r !== role) })}
                  />
                  {ROLE_LABEL[role]}
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-border p-4">
          <label className="flex items-start gap-2 text-sm text-ink">
            <input type="checkbox" className="mt-0.5" checked={form.teacher_schedule_from_lessons} onChange={(e) => patch({ teacher_schedule_from_lessons: e.target.checked })} />
            <span>
              Тренеры: начало рабочего дня — по первому занятию в расписании LMS
              <span className="block text-xs text-ink-muted">В день без занятий опоздание и «нет прихода» для тренера не считаются. Личное расписание сотрудника важнее.</span>
            </span>
          </label>
          {form.teacher_schedule_from_lessons ? (
            <div className="mt-3 max-w-xs">
              <label htmlFor="set-before" className="mb-1.5 block field-label">Прийти до первого занятия за, мин</label>
              <Input id="set-before" type="number" min={0} max={240} value={form.teacher_arrival_before_lesson_minutes} onChange={(e) => patch({ teacher_arrival_before_lesson_minutes: Number(e.target.value) })} />
            </div>
          ) : null}
        </div>
        <div className="rounded-xl border border-border p-4">
          <label className="flex items-start gap-2 text-sm text-ink">
            <input type="checkbox" className="mt-0.5" checked={form.network_check_enabled} onChange={(e) => patch({ network_check_enabled: e.target.checked })} />
            <span>
              Принимать отметки только из офисной сети
              <span className="block text-xs text-ink-muted">Нужен статический внешний IP офиса; за прокси сервер должен видеть настоящий IP (ATTENDANCE_TRUST_X_FORWARDED_FOR).</span>
            </span>
          </label>
          {form.network_check_enabled ? (
            <div className="mt-3">
              <label htmlFor="set-nets" className="mb-1.5 block field-label">Сети (CIDR, по одной в строке)</label>
              <Textarea id="set-nets" rows={3} value={form.office_networks} onChange={(e) => patch({ office_networks: e.target.value })} placeholder="203.0.113.0/24" />
            </div>
          ) : null}
        </div>
        <p className="text-xs text-ink-muted">Учёт посещаемости не подключается к расчёту зарплаты: продолжительность сессии не считается оплачиваемыми часами без утверждённых правил.</p>
        {error ? <p className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{error}</p> : null}
        <div className="flex justify-end">
          <Button type="submit" isLoading={update.isPending}>Сохранить настройки</Button>
        </div>
      </form>
    </Card>
  )
}

function PersonalSchedules({ today }: { today: string }) {
  const schedules = useWorkSchedules()
  const remove = useDeleteWorkSchedule()
  const { showToast } = useToast()
  const [editing, setEditing] = useState<WorkSchedule | 'new' | null>(null)

  return (
    <Card
      title="Личные расписания"
      description="Для сотрудников, у которых рабочее время отличается от общего"
      actions={<Button size="sm" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing('new')}>Добавить</Button>}
    >
      {schedules.isPending ? (
        <LoadingState />
      ) : schedules.isError ? (
        <ErrorState message={extractErrorMessage(schedules.error)} onRetry={() => void schedules.refetch()} />
      ) : schedules.data.length === 0 ? (
        <p className="text-sm text-ink-secondary">Все сотрудники работают по общему расписанию.</p>
      ) : (
        <ul className="divide-y divide-border">
          {schedules.data.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
              <div>
                <p className="font-medium text-ink">{s.employee.full_name} <span className="text-sm font-normal text-ink-secondary">· {s.employee.role_label}</span></p>
                <p className="text-sm text-ink-secondary">
                  {hhmm(s.work_start)}–{hhmm(s.work_end)} · {s.work_days.map((d) => WEEKDAYS[d]).join(', ') || 'нет рабочих дней'}
                  {s.late_grace_minutes !== null ? ` · льгота ${s.late_grace_minutes} мин` : ''}
                  {s.is_active ? '' : ' · выключено'}
                  {s.note ? ` · ${s.note}` : ''}
                </p>
              </div>
              <div className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => setEditing(s)}>Изменить</Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label="Удалить расписание"
                  onClick={() =>
                    remove.mutate(s.user, {
                      onSuccess: () => showToast('Личное расписание удалено', 'success'),
                      onError: (err) => showToast(extractErrorMessage(err), 'error'),
                    })
                  }
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <Modal isOpen={editing !== null} onClose={() => setEditing(null)} title="Личное расписание" icon={<CalendarCog className="size-5 text-brand-600" aria-hidden />}>
        {editing !== null ? <ScheduleForm schedule={editing === 'new' ? null : editing} today={today} onClose={() => setEditing(null)} /> : null}
      </Modal>
    </Card>
  )
}

function ScheduleForm({ schedule, today, onClose }: { schedule: WorkSchedule | null; today: string; onClose: () => void }) {
  const { showToast } = useToast()
  const save = useSaveWorkSchedule()
  // Список сотрудников — из той же выборки, что и таблица учёта.
  const employees = useAttendanceRecords({ date: today, page_size: 100, ordering: 'name' })
  const [userId, setUserId] = useState(schedule ? String(schedule.user) : '')
  const [start, setStart] = useState(schedule ? hhmm(schedule.work_start) : '09:00')
  const [end, setEnd] = useState(schedule ? hhmm(schedule.work_end) : '18:00')
  const [days, setDays] = useState<number[]>(schedule?.work_days ?? [0, 1, 2, 3, 4])
  const [grace, setGrace] = useState(schedule?.late_grace_minutes != null ? String(schedule.late_grace_minutes) : '')
  const [active, setActive] = useState(schedule?.is_active ?? true)
  const [note, setNote] = useState(schedule?.note ?? '')
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!userId) {
      setError('Выберите сотрудника.')
      return
    }
    try {
      await save.mutateAsync({
        userId: Number(userId),
        payload: { work_start: start, work_end: end, work_days: days, late_grace_minutes: grace === '' ? null : Number(grace), is_active: active, note },
      })
      showToast('Личное расписание сохранено', 'success')
      onClose()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  const options = schedule
    ? [{ value: String(schedule.user), label: schedule.employee.full_name }]
    : (employees.data?.results ?? []).map((row) => ({ value: String(row.employee.id), label: `${row.employee.full_name} — ${row.employee.role_label}` }))

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label htmlFor="sch-user" className="mb-1.5 block field-label">Сотрудник *</label>
        <Select id="sch-user" value={userId} onChange={(e) => setUserId(e.target.value)} disabled={schedule !== null} placeholder={employees.isPending && !schedule ? 'Загрузка…' : 'Выберите сотрудника'} options={options} />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor="sch-start" className="mb-1.5 block field-label">Начало</label>
          <Input id="sch-start" type="time" value={start} onChange={(e) => setStart(e.target.value)} required />
        </div>
        <div>
          <label htmlFor="sch-end" className="mb-1.5 block field-label">Окончание</label>
          <Input id="sch-end" type="time" value={end} onChange={(e) => setEnd(e.target.value)} required />
        </div>
        <div>
          <label htmlFor="sch-grace" className="mb-1.5 block field-label">Льгота, мин</label>
          <Input id="sch-grace" type="number" min={0} max={240} placeholder="Как в общих" value={grace} onChange={(e) => setGrace(e.target.value)} />
        </div>
      </div>
      <div>
        <p className="mb-1.5 field-label">Рабочие дни</p>
        <WeekdayPicker idPrefix="sch-day" value={days} onChange={setDays} />
      </div>
      <div>
        <label htmlFor="sch-note" className="mb-1.5 block field-label">Комментарий</label>
        <Input id="sch-note" value={note} maxLength={255} onChange={(e) => setNote(e.target.value)} />
      </div>
      <label className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Действует
      </label>
      {error ? <p className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>Отмена</Button>
        <Button type="submit" isLoading={save.isPending}>Сохранить</Button>
      </div>
    </form>
  )
}

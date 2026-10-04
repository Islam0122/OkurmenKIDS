import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { useNavigate } from 'react-router-dom'

import { groupsApi } from '@/api/groups'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useCreateExamSession, useSessionTests } from '@/hooks/useExams'
import { extractErrorMessage } from '@/lib/apiError'
import { fetchAllPages } from '@/lib/fetchAllPages'

const FIELD_LABELS = { test: 1, group: 1, date: 1, start_time: 1, end_time: 1, __all__: 1 } as const

function today(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

/** «Создать сессию» — a test session for a group (Admin / Team Lead). The
 * backend applies the same rules as the admin's session form and gives the
 * session to the group's active students (its roster). */
export function CreateSessionModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const mutation = useCreateExamSession()
  const tests = useSessionTests(isOpen)
  const groups = useQuery({
    queryKey: ['groups', 'all-active'],
    queryFn: () => fetchAllPages((page) => groupsApi.list({ status: 'active', ordering: 'name', page })),
    enabled: isOpen,
    staleTime: 60_000,
  })

  const [test, setTest] = useState('')
  const [group, setGroup] = useState('')
  const [date, setDate] = useState(today)
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  const subject = useMemo(() => tests.data?.find((t) => t.id === test)?.subject_name ?? '—', [tests.data, test])
  // The group's trainer comes from its existing Group → Trainer link (the
  // program for the test's subject) — the backend sets the same on create.
  const groupDetail = useQuery({
    queryKey: ['groups', 'detail', Number(group)],
    queryFn: () => groupsApi.get(Number(group)),
    enabled: isOpen && group !== '',
  })
  const trainer = useMemo(() => {
    const programs = (groupDetail.data?.teachers ?? []).filter((p) => p.is_active)
    const name = (p: (typeof programs)[number]) => `${p.teacher_detail.user.first_name} ${p.teacher_detail.user.last_name}`.trim()
    const match = programs.find((p) => p.subject_detail?.name === subject)
    if (match) return name(match)
    const names = [...new Set(programs.map(name))]
    return names.length === 1 ? names[0] : null
  }, [groupDetail.data, subject])

  async function handleSubmit() {
    const missing: Record<string, string> = {}
    if (!test) missing.test = 'Выберите тест.'
    if (!group) missing.group = 'Выберите группу.'
    if (!date) missing.date = 'Укажите дату.'
    if (!startTime) missing.start_time = 'Укажите время начала.'
    setErrors(missing)
    if (Object.keys(missing).length) return
    try {
      const session = await mutation.mutateAsync({
        test,
        group: Number(group),
        date,
        start_time: startTime,
        end_time: endTime || undefined,
      })
      showToast('Сессия создана', 'success')
      onClose()
      navigate(`/app/exams/${session.id}`)
    } catch (error) {
      // Field errors from the backend's session form go under their fields.
      const body = error instanceof AxiosError ? error.response?.data : undefined
      if (body && typeof body === 'object' && !Array.isArray(body)) {
        const fieldErrors: Record<string, string> = {}
        for (const [field, value] of Object.entries(body as Record<string, unknown>)) {
          if (field in FIELD_LABELS) fieldErrors[field] = Array.isArray(value) ? value.join(' ') : String(value)
        }
        setErrors(fieldErrors)
      }
      showToast(extractErrorMessage(error, 'Не удалось создать сессию'), 'error')
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Создать сессию">
      <div className="space-y-4">
        <Field label="Тест *" error={errors.test} htmlFor="session-test">
          <Select
            id="session-test"
            value={test}
            onChange={(event) => setTest(event.target.value)}
            placeholder={tests.isPending ? 'Загружаем тесты…' : '— Выберите тест —'}
            options={(tests.data ?? []).map((t) => ({
              value: t.id,
              label: `${t.title}${t.question_count !== null ? ` · ${t.question_count} вопр.` : ''}`,
            }))}
          />
        </Field>
        <Field label="Предмет">
          <p className="text-sm text-ink" data-testid="session-subject">
            {subject}
          </p>
        </Field>
        <Field label="Группа *" error={errors.group} htmlFor="session-group">
          <Select
            id="session-group"
            value={group}
            onChange={(event) => setGroup(event.target.value)}
            placeholder={groups.isPending ? 'Загружаем группы…' : '— Выберите группу —'}
            options={(groups.data ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
          />
        </Field>
        {group ? (
          <Field label="Тренер">
            <p className="text-sm text-ink" data-testid="session-trainer">
              {groupDetail.isPending ? 'Загружаем…' : trainer ? `👨‍🏫 ${trainer}` : 'Не назначен — назначьте в карточке группы'}
            </p>
          </Field>
        ) : null}
        <Field label="Дата *" error={errors.date} htmlFor="session-date">
          <Input id="session-date" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </Field>
        {errors.__all__ ? <p className="text-sm text-danger">{errors.__all__}</p> : null}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Время начала *" error={errors.start_time} htmlFor="session-start">
            <Input id="session-start" type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
          </Field>
          <Field label="Время окончания" error={errors.end_time} htmlFor="session-end" hint="Пусто — по времени теста">
            <Input id="session-end" type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
          </Field>
        </div>
      </div>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>
          Отмена
        </Button>
        <Button onClick={() => void handleSubmit()} isLoading={mutation.isPending}>
          Создать сессию
        </Button>
      </div>
    </Modal>
  )
}

function Field({
  label,
  error,
  hint,
  htmlFor,
  children,
}: {
  label: string
  error?: string
  hint?: string
  htmlFor?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1.5 block field-label">
        {label}
      </label>
      {children}
      {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
    </div>
  )
}

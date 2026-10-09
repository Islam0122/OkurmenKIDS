import { useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, ClipboardList, FileDown, ListTodo, Plus, RefreshCw, Save, Trash2 } from 'lucide-react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { lessonsApi } from '@/api/lessons'
import { worklogApi } from '@/api/worklog'
import { PageHeader } from '@/components/layout/PageHeader'
import { BackLink } from '@/components/ui/BackLink'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { DatePicker } from '@/components/ui/DatePicker'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import {
  useDeleteReport,
  useRecalculateReport,
  useSaveReport,
  useWorklogOptions,
  useWorklogReport,
} from '@/hooks/useWorklog'
import { extractErrorMessage } from '@/lib/apiError'
import type {
  ReportData,
  ReportKind,
  ReportKindSchema,
  ReportLink,
  TeamLeadReport,
  TeamLeadReportInput,
  WorkLogEntry,
  WorklogOptions,
} from '@/types/worklog'
import { formatDate } from '@/utils/format'

import { EntryCard } from './EntryCard'
import { EntryModal } from './EntryModal'
import { Field, fieldErrors, idOrNull, shiftDate, today } from './formUi'
import { ReportFieldInput, ReportFieldValue, cleanData } from './ReportFields'
import { ReportMetrics } from './ReportMetrics'

const BACK = '/app/worklog?tab=reports'

function defaultPeriod(kind: ReportKind): [string, string] {
  const now = today()
  switch (kind) {
    case 'weekly':
      return [shiftDate(now, -6), now]
    case 'internship':
      return [now, shiftDate(now, 2)]
    case 'probation':
      return [shiftDate(now, -29), now]
    default:
      return [`${now.slice(0, 8)}01`, now]
  }
}

/** A Team Lead report: new (`/app/worklog/reports/new?kind=…`), edited by
 * its author, or read by anyone else with access (Admin, other Team Leads). */
export function ReportPage() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const isNew = id === 'new'
  const options = useWorklogOptions()
  const report = useWorklogReport(isNew ? undefined : Number(id))

  if (options.isPending || (!isNew && report.isPending)) return <LoadingState label="Загружаем отчёт…" />
  if (options.isError || !options.data) return <ErrorState onRetry={() => void options.refetch()} />
  if (!isNew && (report.isError || !report.data)) return <ErrorState onRetry={() => void report.refetch()} />

  const kind = (report.data?.kind ?? params.get('kind')) as ReportKind
  const schema = options.data.report_kinds.find((k) => k.kind === kind)
  if (!schema) {
    return <EmptyState icon={ClipboardList} title="Неизвестный вид отчёта" description="Выберите вид отчёта в рабочем журнале." />
  }

  return (
    <ReportEditor
      key={report.data ? report.data.id : `new-${kind}`}
      schema={schema}
      options={options.data}
      report={report.data}
    />
  )
}

function linkLabel(link: ReportLink): string {
  return { group: 'Группа', teacher: 'Тренер', student: 'Студент', lesson: 'Занятие' }[link]
}

function LessonPicker({ group, value, onChange, error }: { group: string; value: string; onChange: (v: string) => void; error?: string }) {
  const lessons = useQuery({
    queryKey: ['lessons', 'list', { group: Number(group), ordering: '-date', worklog: true }],
    queryFn: () => lessonsApi.list({ group: Number(group), ordering: '-date' }),
    enabled: Boolean(group),
  })
  return (
    <Field label="Занятие" htmlFor="report-lesson" error={error} help={group ? 'Дата, время, тренер, предмет и кабинет возьмутся из занятия.' : 'Сначала выберите группу.'}>
      <Select
        id="report-lesson"
        value={value}
        disabled={!group}
        onChange={(e) => onChange(e.target.value)}
        placeholder={lessons.isFetching ? 'Загрузка…' : 'Не выбрано'}
        options={(lessons.data?.results ?? []).map((l) => ({
          value: String(l.id),
          label: `${formatDate(l.date)}, ${l.start_time.slice(0, 5)}, №${l.lesson_number}${l.subject_name ? `, ${l.subject_name}` : ''}${l.topic ? ` — ${l.topic}` : ''}`,
        }))}
      />
    </Field>
  )
}

function ReportEditor({ schema, options, report }: { schema: ReportKindSchema; options: WorklogOptions; report?: TeamLeadReport }) {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const editable = !report || report.can_edit
  const [start, end] = defaultPeriod(schema.kind)
  const text = (v: number | string | null | undefined) => (v == null ? '' : String(v))
  const [date, setDate] = useState(report?.date ?? today())
  const [periodStart, setPeriodStart] = useState(report?.period_start ?? start)
  const [periodEnd, setPeriodEnd] = useState(report?.period_end ?? end)
  const [links, setLinks] = useState<Record<ReportLink, string>>({
    group: text(report?.group),
    teacher: text(report?.teacher),
    student: text(report?.student),
    lesson: text(report?.lesson),
  })
  const [data, setData] = useState<ReportData>(report?.data ?? {})
  const [status, setStatus] = useState(report?.status ?? schema.statuses[0].value)
  const [modal, setModal] = useState<{ kind: 'log' | 'task'; entry?: WorkLogEntry } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [downloading, setDownloading] = useState(false)

  // The PDF is the saved report (the same data as this page after «Сохранить»).
  const downloadPdf = async () => {
    if (!report) return
    setDownloading(true)
    try {
      await worklogApi.downloadReportPdf(report.id)
    } catch (error) {
      showToast(`Не удалось сформировать PDF: ${extractErrorMessage(error)}`, 'error')
    } finally {
      setDownloading(false)
    }
  }

  const save = useSaveReport()
  const recalc = useRecalculateReport()
  const remove = useDeleteReport()
  const errors = fieldErrors(save.error)

  const setLink = (link: ReportLink, value: string) =>
    setLinks((prev) => ({ ...prev, [link]: value, ...(link === 'group' ? { lesson: '' } : {}) }))

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const payload: TeamLeadReportInput = { status, data: cleanData(data) }
    if (!report) payload.kind = schema.kind
    if (schema.period === 'range') {
      payload.period_start = periodStart || null
      payload.period_end = periodEnd || null
      payload.date = periodEnd || today()
    } else if (!(schema.links.includes('lesson') && links.lesson)) {
      payload.date = date
    }
    for (const link of schema.links) payload[link] = idOrNull(links[link])
    save.mutate(
      { id: report?.id, payload },
      {
        onSuccess: (saved) => {
          showToast('Отчёт сохранён', 'success')
          if (!report) navigate(`/app/worklog/reports/${saved.id}`, { replace: true })
        },
      },
    )
  }

  const students = options.students.filter((s) => !links.group || s.group === Number(links.group))
  const linkOptions: Record<Exclude<ReportLink, 'lesson'>, { value: string; label: string }[]> = {
    group: options.groups.map((g) => ({ value: String(g.id), label: g.name })),
    teacher: options.teachers.map((t) => ({ value: String(t.id), label: t.name })),
    student: students.map((s) => ({ value: String(s.id), label: s.name })),
  }
  const shownErrors = new Set(['date', 'period_start', 'period_end', 'status', ...schema.links, ...schema.fields.map((f) => `data.${f.key}`)])
  const generalError = save.error && !Object.keys(errors).some((k) => shownErrors.has(k)) ? extractErrorMessage(save.error) : null
  const hasDataErrors = Object.keys(errors).some((k) => k.startsWith('data.'))

  return (
    <div>
      <BackLink to={BACK}>Рабочий журнал</BackLink>
      <PageHeader
        title={report ? report.title : schema.label}
        description={schema.description}
        badge={report ? <Badge tone={report.status === 'draft' ? 'muted' : 'success'}>{report.status_label}</Badge> : null}
        actions={
          report ? (
            <>
              <Button
                variant="secondary"
                leftIcon={<FileDown className="size-4" aria-hidden />}
                onClick={() => void downloadPdf()}
                isLoading={downloading}
                disabled={downloading || save.isPending}
                title="PDF сохранённой версии отчёта"
              >
                {downloading ? 'Формируем PDF…' : 'Скачать PDF'}
              </Button>
              {report.can_edit ? (
                <Button variant="ghost" leftIcon={<Trash2 className="size-4" aria-hidden />} onClick={() => setConfirmDelete(true)}>
                  Удалить
                </Button>
              ) : null}
            </>
          ) : null
        }
      />

      <div className="space-y-6">
        {editable ? (
          <form onSubmit={handleSubmit} noValidate className="space-y-6">
            <Card title="Отчёт">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {schema.period === 'range' ? (
                  <>
                    <Field label="Начало периода" htmlFor="report-start" error={errors.period_start} required>
                      <DatePicker id="report-start" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
                    </Field>
                    <Field label="Конец периода" htmlFor="report-end" error={errors.period_end} required>
                      <DatePicker id="report-end" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
                    </Field>
                  </>
                ) : !(schema.links.includes('lesson') && links.lesson) ? (
                  <Field label="Дата" htmlFor="report-date" error={errors.date} required>
                    <DatePicker id="report-date" value={date} onChange={(e) => setDate(e.target.value)} />
                  </Field>
                ) : null}
                {schema.links.map((link) =>
                  link === 'lesson' ? (
                    <LessonPicker key={link} group={links.group} value={links.lesson} onChange={(v) => setLink('lesson', v)} error={errors.lesson} />
                  ) : (
                    <Field key={link} label={linkLabel(link)} htmlFor={`report-${link}`} error={errors[link]} required={schema.required_links.includes(link)}>
                      <Select
                        id={`report-${link}`}
                        value={links[link]}
                        onChange={(e) => setLink(link, e.target.value)}
                        placeholder={link === 'teacher' && schema.links.includes('lesson') ? 'Из занятия' : 'Не выбрано'}
                        options={linkOptions[link]}
                      />
                    </Field>
                  ),
                )}
                <Field label="Статус" htmlFor="report-status" error={errors.status}>
                  <Select id="report-status" value={status} onChange={(e) => setStatus(e.target.value)} options={schema.statuses} />
                </Field>
              </div>
              {schema.kind !== 'problem_student' ? (
                <p className="mt-3 text-xs text-ink-muted">Черновик можно сохранить неполным; для сдачи нужны все обязательные поля.</p>
              ) : null}
            </Card>

            <Card title="Содержание">
              <div className="space-y-4">
                {schema.fields.map((field) => (
                  <ReportFieldInput
                    key={field.key}
                    field={field}
                    value={data[field.key]}
                    error={errors[`data.${field.key}`]}
                    onChange={(value) => setData((prev) => ({ ...prev, [field.key]: value }))}
                  />
                ))}
              </div>
            </Card>

            {generalError || hasDataErrors ? (
              <p role="alert" className="text-sm text-danger">
                {generalError ?? 'Заполните отмеченные поля.'}
              </p>
            ) : null}
            <div className="flex justify-end">
              <Button type="submit" isLoading={save.isPending} leftIcon={<Save className="size-4" aria-hidden />}>
                Сохранить
              </Button>
            </div>
          </form>
        ) : report ? (
          <Card title="Содержание" description={`Автор: ${report.author.name}`}>
            <dl className="space-y-3">
              {schema.fields.map((field) => (
                <ReportFieldValue key={field.key} field={field} value={report.data[field.key]} />
              ))}
            </dl>
          </Card>
        ) : null}

        {report?.day_entries ? (
          <Card
            title="Выполнено"
            description="Записи рабочего журнала за этот день"
            actions={
              editable ? (
                <Button variant="secondary" size="sm" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setModal({ kind: 'log' })}>
                  Запись
                </Button>
              ) : null
            }
          >
            {report.day_entries.length === 0 ? (
              <p className="text-sm text-ink-muted">За этот день записей нет.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Время</th>
                      <th>Задача</th>
                      <th>Группа / тренер</th>
                      <th>Результат</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.day_entries.map((entry) => (
                      <tr key={entry.id}>
                        <td className="whitespace-nowrap">
                          {entry.time_from ? `${entry.time_from.slice(0, 5)}${entry.time_to ? `–${entry.time_to.slice(0, 5)}` : ''}` : '—'}
                        </td>
                        <td>{entry.description || entry.work_type_label}</td>
                        <td>{[entry.group_detail?.name, entry.teacher_detail?.name, entry.student_detail?.name, entry.with_whom].filter(Boolean).join(', ') || '—'}</td>
                        <td>{entry.result || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        ) : null}

        {report && schema.kind === 'meeting' ? (
          <Card
            title="Решения"
            description="Каждое решение — задача с ответственным, сроком и статусом"
            actions={
              editable ? (
                <Button variant="secondary" size="sm" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setModal({ kind: 'task' })}>
                  Добавить решение
                </Button>
              ) : null
            }
          >
            {report.tasks?.length ? (
              <div className="space-y-3">
                {report.tasks.map((task) => (
                  <EntryCard key={task.id} entry={task} onEdit={(entry) => setModal({ kind: 'task', entry })} />
                ))}
              </div>
            ) : (
              <EmptyState icon={ListTodo} title="Решений пока нет" />
            )}
          </Card>
        ) : null}

        {report ? (
          <Card
            title={
              <span className="flex items-center gap-2">
                <BarChart3 className="size-5 text-ink-muted" aria-hidden />
                Данные LMS
              </span>
            }
            description={
              report.metrics_calculated_at
                ? `Рассчитано ${new Date(report.metrics_calculated_at).toLocaleString('ru-RU')}`
                : 'Ещё не рассчитано'
            }
            actions={
              report.can_edit ? (
                <Button
                  variant="secondary"
                  size="sm"
                  isLoading={recalc.isPending}
                  leftIcon={<RefreshCw className="size-4" aria-hidden />}
                  onClick={() =>
                    recalc.mutate(report.id, {
                      onSuccess: () => showToast('Данные пересчитаны', 'success'),
                      onError: (error) => showToast(extractErrorMessage(error), 'error'),
                    })
                  }
                >
                  Пересчитать
                </Button>
              ) : null
            }
          >
            {Object.keys(report.metrics).length ? (
              <ReportMetrics metrics={report.metrics} />
            ) : (
              <p className="text-sm text-ink-muted">Для этого отчёта LMS ничего не считает — выберите тренера, студента или занятие.</p>
            )}
          </Card>
        ) : null}
      </div>

      {modal && report ? (
        <EntryModal
          key={modal.entry?.id ?? `new-${modal.kind}`}
          isOpen
          onClose={() => setModal(null)}
          options={options}
          kind={modal.kind}
          entry={modal.entry}
          title={modal.kind === 'task' && !modal.entry ? 'Новое решение' : undefined}
          defaults={
            modal.kind === 'task'
              ? { report: report.id, work_type: 'meeting', date: report.date }
              : { date: report.date }
          }
        />
      ) : null}

      <ConfirmDialog
        isOpen={confirmDelete}
        title="Удалить отчёт?"
        message="Отчёт и связанные с ним решения будут удалены. Это действие нельзя отменить."
        confirmLabel="Удалить"
        tone="danger"
        isLoading={remove.isPending}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() =>
          report &&
          remove.mutate(report.id, {
            onSuccess: () => {
              showToast('Отчёт удалён', 'success')
              navigate(BACK, { replace: true })
            },
            onError: (error) => showToast(extractErrorMessage(error), 'error'),
          })
        }
      />
    </div>
  )
}

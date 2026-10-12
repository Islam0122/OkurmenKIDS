import { useState } from 'react'
import { AxiosError } from 'axios'
import { CalendarClock, Check, Pencil, X } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ErrorState } from '@/components/ui/ErrorState'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { SearchInput } from '@/components/ui/SearchInput'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useGroups, useSaveSubjectStartDate, useSubjectStartDates, type SubjectStartSource } from '@/hooks/useGroups'
import { extractErrorMessage } from '@/lib/apiError'
import type { SubjectStartRow, SubjectStartStatus } from '@/types/academy'
import { formatDateShort } from '@/utils/format'

const STATUS_TONE: Record<SubjectStartStatus, BadgeTone> = {
  not_started: 'info',
  in_progress: 'success',
  completed: 'muted',
}

function errorMessages(error: unknown): string {
  const body = error instanceof AxiosError ? error.response?.data : undefined
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const messages = Object.values(body as Record<string, unknown>).flatMap((value) =>
      Array.isArray(value) ? value.map(String) : [String(value)],
    )
    if (messages.length) return messages.join(' ')
  }
  return extractErrorMessage(error, 'Не удалось сохранить дату старта')
}

/**
 * «Даты старта предметов»: every subject of a group with its own start date
 * and status; each date is changed on its own row, never the group's dates
 * or another subject (backend: services.subject_start, which also moves that
 * subject's not-yet-given lessons). Without `groupId` the group is picked
 * inside the dialog.
 */
export function SubjectStartDatesModal({
  isOpen,
  onClose,
  groupId,
  source = 'lms',
}: {
  isOpen: boolean
  onClose: () => void
  groupId?: number
  source?: SubjectStartSource
}) {
  const [picked, setPicked] = useState<number | undefined>(undefined)
  const currentGroup = groupId ?? picked

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      title="Даты старта предметов"
      icon={<CalendarClock className="size-5 text-ink-muted" aria-hidden />}
    >
      <div className="space-y-4">
        {groupId === undefined ? <GroupPicker value={picked} onChange={setPicked} /> : null}
        {currentGroup !== undefined ? (
          <SubjectStartTable key={currentGroup} groupId={currentGroup} source={source} />
        ) : (
          <p className="text-sm text-ink-secondary">Выберите группу, чтобы увидеть даты старта её предметов.</p>
        )}
      </div>
    </Modal>
  )
}

function GroupPicker({ value, onChange }: { value: number | undefined; onChange: (id: number | undefined) => void }) {
  const [search, setSearch] = useState('')
  const { data, isPending } = useGroups({ search: search || undefined, ordering: 'name' })
  const options = (data?.results ?? []).map((group) => ({ value: String(group.id), label: `${group.name} · ${group.course_name}` }))
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <SearchInput value={search} onChange={setSearch} placeholder="Поиск группы…" />
      <Select
        aria-label="Группа"
        placeholder={isPending ? 'Загружаем группы…' : 'Выберите группу'}
        value={value ? String(value) : ''}
        onChange={(event) => onChange(event.target.value ? Number(event.target.value) : undefined)}
        options={options}
      />
    </div>
  )
}

export function SubjectStartTable({ groupId, source = 'lms' }: { groupId: number; source?: SubjectStartSource }) {
  const { data, isPending, isError, refetch } = useSubjectStartDates(groupId, source)
  const [editing, setEditing] = useState<number | null>(null)

  if (isPending) return <LoadingState label="Загружаем предметы…" />
  if (isError || !data) return <ErrorState onRetry={() => void refetch()} />

  return (
    <div className="space-y-2">
      <p className="text-xs text-ink-muted">
        Группа «{data.group.name}» · начало группы {formatDateShort(data.group.start_date)}
        {data.group.end_date ? ` · окончание ${formatDateShort(data.group.end_date)}` : ''}. Дата каждого предмета меняется отдельно.
      </p>
      {data.subjects.length === 0 ? (
        <p className="text-sm text-ink-secondary">В курсе группы нет предметов.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="data-table" aria-label="Даты старта предметов">
            <thead>
              <tr>
                <th scope="col">Предмет</th>
                <th scope="col">Дата старта</th>
                <th scope="col">Статус</th>
                <th scope="col" className="text-right">
                  Действие
                </th>
              </tr>
            </thead>
            <tbody>
              {data.subjects.map((row) => (
                <SubjectRow
                  key={row.subject.id}
                  row={row}
                  groupId={groupId}
                  source={source}
                  minDate={data.group.start_date}
                  maxDate={data.group.end_date}
                  isEditing={editing === row.subject.id}
                  canEdit={editing === null}
                  onEdit={() => setEditing(row.subject.id)}
                  onDone={() => setEditing(null)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SubjectRow({
  row,
  groupId,
  source,
  minDate,
  maxDate,
  isEditing,
  canEdit,
  onEdit,
  onDone,
}: {
  row: SubjectStartRow
  groupId: number
  source: SubjectStartSource
  minDate: string
  maxDate: string | null
  isEditing: boolean
  canEdit: boolean
  onEdit: () => void
  onDone: () => void
}) {
  const { showToast } = useToast()
  const mutation = useSaveSubjectStartDate(groupId, source)
  const [value, setValue] = useState(row.start_date)
  const [error, setError] = useState<string | null>(null)

  async function save() {
    if (!value) return setError('Укажите дату.')
    if (value === row.start_date && row.is_custom) return onDone()
    setError(null)
    try {
      const result = await mutation.mutateAsync({ subjectId: row.subject.id, startDate: value })
      const moved = result.saved?.moved ?? 0
      showToast(
        `«${row.subject.name}»: старт ${formatDateShort(value)}${moved ? ` · перенесено занятий: ${moved}` : ''}`,
        'success',
      )
      onDone()
    } catch (err) {
      const message = errorMessages(err)
      setError(message)
      showToast(message, 'error')
    }
  }

  return (
    <tr data-testid="subject-start-row">
      <td className="font-medium text-ink">{row.subject.name}</td>
      <td>
        {isEditing ? (
          <div className="space-y-1">
            <Input
              type="date"
              aria-label={`Дата старта: ${row.subject.name}`}
              value={value}
              min={minDate}
              max={maxDate ?? undefined}
              onChange={(event) => setValue(event.target.value)}
              className="h-8 max-w-[11rem] py-1 text-sm"
            />
            {error ? (
              <p role="alert" className="max-w-xs text-xs text-danger">
                {error}
              </p>
            ) : null}
          </div>
        ) : (
          <span>
            {formatDateShort(row.start_date)}
            {row.is_custom ? null : <span className="ml-1 text-xs text-ink-muted">(с группой)</span>}
          </span>
        )}
      </td>
      <td>
        <Badge tone={STATUS_TONE[row.status]}>{row.status_display}</Badge>
      </td>
      <td className="text-right">
        {isEditing ? (
          <div className="inline-flex gap-1">
            <Button size="sm" aria-label="Сохранить" onClick={() => void save()} isLoading={mutation.isPending}>
              <Check className="size-4" aria-hidden />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              aria-label="Отмена"
              disabled={mutation.isPending}
              onClick={() => {
                setValue(row.start_date)
                setError(null)
                onDone()
              }}
            >
              <X className="size-4" aria-hidden />
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Pencil className="size-4" aria-hidden />}
            onClick={onEdit}
            disabled={!canEdit}
            aria-label={`Изменить дату старта: ${row.subject.name}`}
          >
            Изменить
          </Button>
        )}
      </td>
    </tr>
  )
}

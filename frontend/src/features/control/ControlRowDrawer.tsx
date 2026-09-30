import { useState } from 'react'
import { ChevronDown, Clock3 } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Drawer } from '@/components/ui/Drawer'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import type { ControlDetailParams } from '@/api/control'
import { useControlDetail } from '@/hooks/useControl'
import type { ControlLesson, ControlRow } from '@/types/control'
import { cn } from '@/utils/cn'
import { formatDateShort } from '@/utils/format'

import { ControlLessonCheck } from './ControlLessonCheck'
import { ComponentCell, CONTROL_STATUS_TONE, LevelIcon } from './controlDisplay'
import { formatDateTime } from './format'

export interface ControlRowDrawerProps {
  row: ControlRow | null
  params: Omit<ControlDetailParams, 'group' | 'teacher'>
  periodLabel: string
  onClose: () => void
}

function LessonSummaryLine({ lesson }: { lesson: ControlLesson }) {
  if (lesson.state === 'upcoming') {
    return (
      <p className="flex items-center gap-1.5 text-sm text-info">
        <Clock3 className="size-4" aria-hidden /> Предстоящий
      </p>
    )
  }
  if (lesson.state === 'cancelled') {
    return <p className="text-sm text-ink-muted">Занятие отменено</p>
  }
  if (lesson.problems.length === 0) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-brand-600">
        <LevelIcon level="ok" /> Всё заполнено
      </p>
    )
  }
  return (
    <ul className="space-y-0.5">
      {lesson.problems.map((problem) => (
        <li key={problem} className="flex items-center gap-1.5 text-sm text-danger">
          <LevelIcon level="danger" /> {problem}
        </li>
      ))}
    </ul>
  )
}

/** Detail of one trainer×group row: the backend's numbers plus every lesson behind them. */
export function ControlRowDrawer({ row, params, periodLabel, onClose }: ControlRowDrawerProps) {
  const [openLessonId, setOpenLessonId] = useState<number | null>(null)
  const { data, isPending, isError, refetch } = useControlDetail(
    row ? { ...params, group: row.group.id, teacher: row.teacher?.id ?? 'none' } : null,
  )
  const current = data?.row ?? row

  return (
    <Drawer
      isOpen={row !== null}
      onClose={onClose}
      title={row ? `${row.teacher?.name ?? 'Тренер не назначен'} · ${row.group.name}` : ''}
      side="right"
      size="lg"
    >
      {current ? (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-xs text-ink-muted">Период</p>
              <p className="text-ink">{periodLabel}</p>
            </div>
            <div>
              <p className="text-xs text-ink-muted">Статус</p>
              <Badge tone={CONTROL_STATUS_TONE[current.status]}>{current.status_label}</Badge>
            </div>
            <div>
              <p className="text-xs text-ink-muted">Ответственный</p>
              <p className="text-ink">
                {current.teacher?.name ?? 'Не назначен'}
                {current.teacher && !current.teacher.is_active ? ' (неактивен)' : ''}
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-muted">Последнее изменение данных</p>
              <p className="text-ink">{formatDateTime(current.last_activity_at)}</p>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-3 rounded-lg border border-border p-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-ink-muted">Уроки закрыты</dt>
              <dd><ComponentCell component={current.lessons} /></dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">Посещаемость</dt>
              <dd><ComponentCell component={current.attendance} /></dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">ДЗ проверено</dt>
              <dd><ComponentCell component={current.homework} /></dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">Баллы</dt>
              <dd><ComponentCell component={current.grades} /></dd>
            </div>
          </dl>

          {current.lessons.upcoming > 0 || current.lessons.cancelled > 0 ? (
            <p className="text-xs text-ink-muted">
              {current.lessons.upcoming > 0 ? `Предстоящих: ${current.lessons.upcoming}. ` : ''}
              {current.lessons.cancelled > 0 ? `Отменено: ${current.lessons.cancelled}.` : ''}
            </p>
          ) : null}

          {current.issues.length > 0 ? (
            <section>
              <h3 className="mb-2 text-sm font-semibold text-ink">Что осталось заполнить</h3>
              <ul className="space-y-1 text-sm text-ink">
                {current.issues.map((issue) => (
                  <li key={issue} className="flex items-center gap-1.5">
                    <LevelIcon level="danger" /> {issue}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section>
            <h3 className="mb-2 text-sm font-semibold text-ink">Занятия</h3>
            {isPending ? <LoadingState label="Загружаем занятия…" /> : null}
            {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
            <ul className="space-y-2">
              {(data?.lessons ?? []).map((lesson) => {
                const isOpen = openLessonId === lesson.id
                return (
                  <li key={lesson.id} className="rounded-lg border border-border">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      onClick={() => setOpenLessonId(isOpen ? null : lesson.id)}
                      className="flex w-full items-start justify-between gap-3 p-3 text-left hover:bg-surface-hover"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink">
                          {formatDateShort(lesson.date)}
                          {lesson.subject ? <span className="text-ink-secondary"> · {lesson.subject.name}</span> : null}
                        </p>
                        <div className="mt-1">
                          <LessonSummaryLine lesson={lesson} />
                        </div>
                      </div>
                      <ChevronDown
                        className={cn('mt-0.5 size-4 shrink-0 text-ink-muted transition-transform', isOpen && 'rotate-180')}
                        aria-hidden
                      />
                    </button>
                    {isOpen ? (
                      <div className="border-t border-border p-3">
                        <ControlLessonCheck lesson={lesson} />
                      </div>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          </section>
        </div>
      ) : null}
    </Drawer>
  )
}

import { useState } from 'react'
import { ClipboardCheck } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { useExamList } from '@/hooks/useExams'
import type { ExamListFilter } from '@/types/exams'

import { ExamCard } from './ExamCard'

const FILTERS: { value: ExamListFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'live', label: 'Сейчас проходят' },
  { value: 'scheduled', label: 'Запланированные' },
  { value: 'finished', label: 'Завершённые' },
]

const EMPTY_TEXT: Record<ExamListFilter, string> = {
  all: 'Для ваших групп пока не назначено ни одного экзамена.',
  live: 'Сейчас ни одна из ваших групп не проходит экзамен.',
  scheduled: 'Запланированных экзаменов нет.',
  finished: 'Завершённых экзаменов пока нет.',
}

/** Exam sessions of the teacher's own groups — the backend scopes the list. */
export function ExamsListPage() {
  const [filter, setFilter] = useState<ExamListFilter>('all')
  const [page, setPage] = useState(1)
  const { data, isPending, isError, refetch } = useExamList({ status: filter, page })

  return (
    <div>
      <PageHeader title="Экзамены" description="Тестовые сессии ваших групп: кто начал, кто проходит, кто завершил." />

      <SegmentedControl
        aria-label="Фильтр экзаменов"
        className="mb-5"
        options={FILTERS}
        value={filter}
        onChange={(value) => {
          setFilter(value)
          setPage(1)
        }}
      />

      {isPending ? <LoadingState label="Загружаем экзамены…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}

      {data && data.results.length === 0 ? (
        <EmptyState icon={ClipboardCheck} title="Экзаменов нет" description={EMPTY_TEXT[filter]} />
      ) : null}

      {data && data.results.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {data.results.map((session) => (
              <ExamCard key={session.id} session={session} />
            ))}
          </div>
          <div className="mt-6">
            <Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} />
          </div>
        </>
      ) : null}
    </div>
  )
}

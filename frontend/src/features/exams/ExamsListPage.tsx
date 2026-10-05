import { useState } from 'react'
import { ClipboardCheck, Plus } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Pagination } from '@/components/ui/Pagination'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { useAuth } from '@/hooks/useAuth'
import { useExamList } from '@/hooks/useExams'
import { seesWholeAcademy } from '@/lib/roles'
import type { ExamListFilter } from '@/types/exams'

import { CreateSessionModal } from './CreateSessionModal'
import { ExamCard } from './ExamCard'
import { MyResults } from './MyResults'

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

/** Exam sessions — a Trainer's own sessions only (backend-scoped: the
 * session's trainer, never every session of a group they teach in); Admin and Team
 * Lead see every session of the academy and may create one («Сессии»). */
export function ExamsListPage() {
  const { user } = useAuth()
  const academyView = seesWholeAcademy(user?.role)
  const [filter, setFilter] = useState<ExamListFilter>('all')
  const [page, setPage] = useState(1)
  const [isCreateOpen, setCreateOpen] = useState(false)
  const { data, isPending, isError, refetch } = useExamList({ status: filter, page })

  return (
    <div>
      {academyView ? (
        <PageHeader
          title="Сессии"
          description="Тестовые сессии всей академии: группа, тест, кто начал, кто завершил, результаты."
          actions={
            <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setCreateOpen(true)}>
              Создать сессию
            </Button>
          }
        />
      ) : (
        <PageHeader title="Экзамены" description="Ваши тестовые сессии: кто начал, кто проходит, кто завершил." />
      )}

      {academyView ? (
        <div className="mb-6">
          <MyResults />
        </div>
      ) : null}

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
        <EmptyState
          icon={ClipboardCheck}
          title={academyView ? 'Сессий нет' : 'Экзаменов нет'}
          description={academyView && filter === 'all' ? 'Создайте первую тестовую сессию для группы.' : EMPTY_TEXT[filter]}
        />
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

      {academyView ? <CreateSessionModal isOpen={isCreateOpen} onClose={() => setCreateOpen(false)} /> : null}
    </div>
  )
}

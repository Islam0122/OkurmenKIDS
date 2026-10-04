import { useState } from 'react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Tabs } from '@/components/ui/Tabs'
import { useAuth } from '@/hooks/useAuth'
import { MONITORING_REFRESH_MS } from '@/hooks/useMonitoring'
import { seesWholeAcademy } from '@/lib/roles'
import type { MonitoringFilters } from '@/types/monitoring'

import { AttemptsTab } from './AttemptsTab'
import { GroupsTab, TeachersTab, TrainersTab } from './TeamTabs'

type TabKey = 'attempts' | 'groups' | 'trainers' | 'teachers'

/**
 * Monitoring of exams and trainers: live attempts, results, violations and
 * analytics. What a user sees is decided by the backend (a Trainer — their
 * own groups; Team Lead / Admin — the academy); the tabs here only mirror it.
 * Polled every 15 s while the page is visible.
 */
export function MonitoringPage() {
  const { user } = useAuth()
  const team = seesWholeAcademy(user?.role)
  const [tab, setTab] = useState<TabKey>('attempts')
  const [filters, setFilters] = useState<MonitoringFilters>({ page: 1 })

  const tabs = [
    { key: 'attempts' as const, label: 'Попытки' },
    { key: 'groups' as const, label: 'Группы' },
    { key: 'trainers' as const, label: 'Тренажёры и экзамены' },
    ...(team ? [{ key: 'teachers' as const, label: 'Тренеры' }] : []),
  ]

  return (
    <div>
      <PageHeader
        title="Мониторинг"
        description={`Экзамены и тренажёры${team ? ' всей академии' : ' ваших групп и публичные тренажёры ваших предметов'}: кто проходит сейчас, результаты и нарушения. Обновляется каждые ${MONITORING_REFRESH_MS / 1000} с.`}
      />
      <Tabs items={tabs} value={tab} onChange={setTab} aria-label="Разделы мониторинга" />
      {tab === 'attempts' ? <AttemptsTab filters={filters} setFilters={setFilters} /> : null}
      {tab === 'groups' ? <GroupsTab filters={filters} /> : null}
      {tab === 'trainers' ? <TrainersTab filters={filters} /> : null}
      {tab === 'teachers' && team ? <TeachersTab filters={filters} /> : null}
    </div>
  )
}

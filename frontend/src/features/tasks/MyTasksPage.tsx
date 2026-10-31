import { useState } from 'react'
import { Plus } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Tabs } from '@/components/ui/Tabs'
import { useMyTasks } from '@/hooks/useOperations'
import type { MyTaskSection } from '@/types/operations'

import { QueryView, Section } from '../operations/shared'
import { TaskFormModal } from './TaskForm'
import { TaskList } from './TaskList'

const SECTIONS: { key: MyTaskSection; label: string; empty: string }[] = [
  { key: 'today', label: 'Сегодня', empty: 'На сегодня задач нет' },
  { key: 'overdue', label: 'Просрочено', empty: 'Просроченных задач нет' },
  { key: 'in_progress', label: 'В работе', empty: 'Нет задач в работе' },
  { key: 'upcoming', label: 'Предстоящие', empty: 'Предстоящих задач нет' },
  { key: 'review', label: 'На проверке', empty: 'Ничего не ждёт проверки' },
  { key: 'completed', label: 'Выполнено', empty: 'Выполненных задач пока нет' },
  { key: 'to_review', label: 'Проверить мне', empty: 'Нет задач на вашу проверку' },
]

/** /tasks — личный To-Do каждого сотрудника: сегодня, просрочено, в работе,
 * предстоящие, на проверке, выполнено и задачи, которые ждут его проверки. */
export function MyTasksPage() {
  const query = useMyTasks()
  const [section, setSection] = useState<MyTaskSection>('today')
  const [creating, setCreating] = useState(false)
  return (
    <div className="space-y-4">
      <PageHeader title="Мои задачи" description="Личный список дел с дедлайнами, проверкой и историей"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>Задача</Button>} />
      <QueryView query={query}>
        {(data) => (
          <div className="space-y-3">
            <Tabs aria-label="Разделы задач" value={section} onChange={setSection}
              items={SECTIONS.map((s) => ({ key: s.key, label: `${s.label}${data[s.key].length ? ` · ${s.key === 'to_review' ? data.counts.to_review : data[s.key].length}` : ''}` }))} />
            {SECTIONS.filter((s) => s.key === section).map((s) => (
              <Section key={s.key} title={s.label} padding={false}><TaskList tasks={data[s.key]} empty={s.empty} showAssignee={s.key === 'to_review'} /></Section>
            ))}
          </div>
        )}
      </QueryView>
      {creating ? <TaskFormModal onClose={() => setCreating(false)} /> : null}
    </div>
  )
}

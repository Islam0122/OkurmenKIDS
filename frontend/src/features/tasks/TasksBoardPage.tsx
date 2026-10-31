import { useState } from 'react'
import { Plus, Square } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useRecurrences, useTaskMutations, useTasks, useTasksMeta } from '@/hooks/useOperations'
import type { TasksParams } from '@/types/operations'

import { QueryView, Section, Table, shortDate } from '../operations/shared'
import { TaskFormModal } from './TaskForm'
import { TaskList } from './TaskList'

const STATUS_TABS = [
  { value: 'open', label: 'Открытые' },
  { value: 'overdue', label: 'Просроченные' },
  { value: 'review', label: 'На проверке' },
  { value: 'completed', label: 'Выполненные' },
  { value: 'all', label: 'Все' },
]
const PAGE_SIZE = 25

/** /operations/tasks — все задачи компании: фильтры по отделу, исполнителю,
 * приоритету, категории и сроку, повторяющиеся задачи. */
export function TasksBoardPage() {
  const meta = useTasksMeta()
  const [search, setSearch] = useSearchParams()
  const [creating, setCreating] = useState(false)
  const [tab, setTab] = useState<'tasks' | 'recurring'>('tasks')
  const get = (key: string) => search.get(key) ?? ''
  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(search)
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)))
    if (!('page' in patch)) next.delete('page')
    setSearch(next, { replace: true })
  }
  const status = get('status') || 'open'
  const params: TasksParams = {
    status: status === 'all' ? undefined : status,
    department: get('department') || undefined,
    assignee: get('assignee') || undefined,
    priority: get('priority') || undefined,
    category: get('category') || undefined,
    search: get('q') || undefined,
    deadline_from: get('deadline_from') || undefined,
    deadline_to: get('deadline_to') || undefined,
    recurrence: get('recurrence') || undefined,
    page: Number(get('page') || 1),
    page_size: PAGE_SIZE,
  }
  const tasks = useTasks(params)
  const recurrences = useRecurrences()
  const { stopRecurrence } = useTaskMutations()
  return (
    <div className="space-y-4">
      <PageHeader title="Задачи" description="Задачи всех отделов: постановка, контроль сроков, проверка и история"
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setCreating(true)}>Новая задача</Button>} />
      <SegmentedControl aria-label="Раздел" value={tab} onChange={setTab} options={[{ value: 'tasks', label: 'Задачи' }, { value: 'recurring', label: 'Повторяющиеся' }]} />
      {tab === 'tasks' ? (
        <>
          <SegmentedControl aria-label="Статус" value={status} onChange={(v) => set({ status: v })} options={STATUS_TABS} />
          <div className="grid grid-cols-2 gap-2 md:flex md:flex-wrap">
            <div className="col-span-2 md:w-60"><SearchInput value={get('q')} onChange={(v) => set({ q: v })} placeholder="Поиск задач" /></div>
            <div className="md:w-44"><Select aria-label="Отдел" placeholder="Все отделы" value={get('department')} options={meta.data?.departments ?? []} onChange={(e) => set({ department: e.target.value })} /></div>
            <div className="md:w-56"><Select aria-label="Исполнитель" placeholder="Все исполнители" value={get('assignee')} options={[{ value: 'none', label: 'Без исполнителя' }, ...(meta.data?.assignees ?? []).map((p) => ({ value: String(p.id), label: p.full_name }))]} onChange={(e) => set({ assignee: e.target.value })} /></div>
            <div className="md:w-40"><Select aria-label="Приоритет" placeholder="Приоритет" value={get('priority')} options={meta.data?.priorities ?? []} onChange={(e) => set({ priority: e.target.value })} /></div>
            <div className="md:w-48"><Select aria-label="Категория" placeholder="Категория" value={get('category')} options={meta.data?.categories ?? []} onChange={(e) => set({ category: e.target.value })} /></div>
            <input type="date" aria-label="Дедлайн с" className="form-control md:w-40" value={get('deadline_from')} onChange={(e) => set({ deadline_from: e.target.value })} />
            <input type="date" aria-label="Дедлайн по" className="form-control md:w-40" value={get('deadline_to')} onChange={(e) => set({ deadline_to: e.target.value })} />
          </div>
          <QueryView query={tasks}>
            {(data) => (
              <div className="space-y-3">
                <Section title={`Найдено: ${data.count}`} padding={false}><TaskList tasks={data.results} /></Section>
                <Pagination page={params.page ?? 1} pageSize={PAGE_SIZE} totalCount={data.count} onPageChange={(page) => set({ page: String(page) })} />
              </div>
            )}
          </QueryView>
        </>
      ) : (
        <QueryView query={recurrences}>
          {(data) => (
            <Section title="Шаблоны повторяющихся задач" padding={false}>
              <Table empty={!data.results.length} headers={['Задача', 'Исполнитель', 'Периодичность', 'С', 'Создано повторений', 'Статус', '']}>
                {data.results.map((r) => (
                  <tr key={r.id}>
                    <td className="font-medium">{r.title}</td>
                    <td className="text-sm">{r.assignee_info.full_name}</td>
                    <td className="text-sm">{r.frequency_label}{r.frequency === 'weekly' ? ` (${r.weekdays.map((d) => ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'][d]).join(', ')})` : r.frequency === 'monthly' ? ` (${r.month_day}-го)` : ''}</td>
                    <td>{shortDate(r.starts_on)}</td>
                    <td><button type="button" className="text-brand-700 hover:underline" onClick={() => { setTab('tasks'); set({ status: 'all', recurrence: String(r.id) }) }}>{r.occurrences_count} — история по датам</button></td>
                    <td>{r.is_active ? 'Активен' : 'Остановлен'}</td>
                    <td>{r.is_active ? <Button size="sm" variant="ghost" leftIcon={<Square className="size-3.5" aria-hidden />} onClick={() => stopRecurrence.mutate(r.id)}>Остановить</Button> : null}</td>
                  </tr>
                ))}
              </Table>
            </Section>
          )}
        </QueryView>
      )}
      {creating ? <TaskFormModal onClose={() => setCreating(false)} /> : null}
    </div>
  )
}

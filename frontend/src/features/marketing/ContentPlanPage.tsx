import { useMemo, useState } from 'react'
import { addDays, addMonths, endOfMonth, endOfWeek, format, isSameMonth, parseISO, startOfMonth, startOfWeek } from 'date-fns'
import { ru } from 'date-fns/locale'
import { CalendarRange, ChevronLeft, ChevronRight, Lightbulb, Plus } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { useContentItems, useMarketingMeta } from '@/hooks/useMarketing'
import { extractErrorMessage } from '@/lib/apiError'
import type { Channel, ContentItem, ContentParams, MarketingMeta } from '@/types/marketing'
import { cn } from '@/utils/cn'

import { ContentDialog, type ContentDraft } from './Dialogs'
import { ContentRow } from './Rows'
import { CHANNEL_SHORT, CONTENT_BORDER, isoDate, monthLabel } from './shared'

type View = 'calendar' | 'list'
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const CELL_LIMIT = 3
const LIST_PAGE = 30

/** `Среда, 28 октября` — заглавная только первая буква. */
function weekdayDate(day: Date): string {
  const text = format(day, 'EEEE, d MMMM', { locale: ru })
  return text.charAt(0).toUpperCase() + text.slice(1)
}

interface Filters {
  channel: string
  status: string
  responsible: string
}

function filterParams(filters: Filters): ContentParams {
  return {
    channel: (filters.channel || undefined) as Channel | undefined,
    status: filters.status || undefined,
    responsible: filters.responsible ? Number(filters.responsible) : undefined,
  }
}

/** /marketing/content — контент-план: календарь месяца (на телефоне —
 * компактная лента по дням) и список со всеми публикациями, включая идеи без
 * даты. Создавать и править может любой сотрудник маркетинга; удалить —
 * автор или администратор (проверяет сервер). */
export function MarketingContentPlanPage() {
  const meta = useMarketingMeta()
  const [view, setView] = useState<View>('calendar')
  const [filters, setFilters] = useState<Filters>({ channel: '', status: '', responsible: '' })
  const [draft, setDraft] = useState<ContentDraft | null>(null)

  if (meta.isPending) return <LoadingState label="Загружаем контент-план…" />
  if (meta.isError) return <ErrorState message={extractErrorMessage(meta.error)} onRetry={() => void meta.refetch()} />

  return (
    <div className="space-y-4">
      <PageHeader
        title="Контент-план"
        description="Публикации по каналам: от идеи до выхода"
        actions={<Button className="max-sm:h-11 max-sm:w-full" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setDraft({})}>Новая публикация</Button>}
      />

      <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
        <SegmentedControl
          className="shrink-0"
          aria-label="Вид контент-плана"
          value={view}
          onChange={setView}
          options={[{ value: 'calendar', label: 'Календарь' }, { value: 'list', label: 'Список' }]}
        />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:ml-auto xl:flex">
          <FilterSelect label="Канал" value={filters.channel} options={meta.data.channels} all="Все каналы" onChange={(channel) => setFilters((f) => ({ ...f, channel }))} />
          <FilterSelect label="Статус" value={filters.status} options={meta.data.content_statuses} all="Все статусы" onChange={(status) => setFilters((f) => ({ ...f, status }))} />
          <FilterSelect
            label="Ответственный"
            className="col-span-2 sm:col-span-1"
            value={filters.responsible}
            options={meta.data.team.map((m) => ({ value: String(m.id), label: m.full_name }))}
            all="Вся команда"
            onChange={(responsible) => setFilters((f) => ({ ...f, responsible }))}
          />
        </div>
      </div>

      {view === 'calendar' ? (
        <CalendarView meta={meta.data} filters={filters} onOpen={setDraft} onShowIdeas={() => { setFilters((f) => ({ ...f, status: 'idea' })); setView('list') }} />
      ) : (
        <ListView filters={filters} onOpen={setDraft} />
      )}

      <ContentDialog draft={draft} onClose={() => setDraft(null)} />
    </div>
  )
}

function FilterSelect({ label, value, options, all, onChange, className }: { label: string; value: string; options: { value: string; label: string }[]; all: string; onChange: (value: string) => void; className?: string }) {
  return (
    <div className={cn('min-w-0 xl:w-44', className)}>
      <Select aria-label={label} className="max-sm:h-11 max-sm:text-base" value={value} placeholder={all} options={options} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Календарь
// ---------------------------------------------------------------------------

function CalendarView({ meta, filters, onOpen, onShowIdeas }: { meta: MarketingMeta; filters: Filters; onOpen: (draft: ContentDraft) => void; onShowIdeas: () => void }) {
  const [month, setMonth] = useState(() => startOfMonth(parseISO(meta.today)))
  const [dayOpen, setDayOpen] = useState<string | null>(null)
  const gridStart = startOfWeek(month, { weekStartsOn: 1 })
  const gridEnd = endOfWeek(endOfMonth(month), { weekStartsOn: 1 })
  const items = useContentItems({ ...filterParams(filters), date_from: isoDate(gridStart), date_to: isoDate(gridEnd), page_size: 200 })
  const ideas = useContentItems({ no_date: '1', page_size: 1 })

  const byDay = useMemo(() => {
    const map = new Map<string, ContentItem[]>()
    for (const item of items.data?.results ?? []) {
      if (!item.publish_date) continue
      map.set(item.publish_date, [...(map.get(item.publish_date) ?? []), item])
    }
    return map
  }, [items.data])

  const days: Date[] = []
  for (let d = gridStart; d <= gridEnd; d = addDays(d, 1)) days.push(d)
  const monthDays = days.filter((d) => isSameMonth(d, month))
  const agendaDays = monthDays.filter((d) => byDay.has(isoDate(d)))
  const undated = ideas.data?.count ?? 0

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center">
          <Button variant="ghost" size="sm" className="size-10 px-0" aria-label="Предыдущий месяц" onClick={() => setMonth((m) => addMonths(m, -1))}>
            <ChevronLeft className="size-5" aria-hidden />
          </Button>
          <h2 className="min-w-32 text-center text-base font-semibold text-ink">{monthLabel(isoDate(month))}</h2>
          <Button variant="ghost" size="sm" className="size-10 px-0" aria-label="Следующий месяц" onClick={() => setMonth((m) => addMonths(m, 1))}>
            <ChevronRight className="size-5" aria-hidden />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          {items.isFetching ? <span className="text-xs text-ink-muted">Обновляем…</span> : null}
          <Button variant="secondary" size="sm" onClick={() => setMonth(startOfMonth(parseISO(meta.today)))}>Сегодня</Button>
        </div>
      </div>

      {items.isError ? (
        <ErrorState message={extractErrorMessage(items.error)} onRetry={() => void items.refetch()} />
      ) : items.isPending ? (
        <LoadingState />
      ) : (
        <>
          {/* Ноутбук и планшет: сетка месяца. */}
          <div className="card hidden overflow-hidden md:block">
            <div className="grid grid-cols-7 border-b border-border bg-surface-muted text-xs font-medium text-ink-secondary">
              {WEEKDAYS.map((day) => <div key={day} className="px-2 py-2">{day}</div>)}
            </div>
            <div className="grid grid-cols-7">
              {days.map((day) => {
                const key = isoDate(day)
                const list = byDay.get(key) ?? []
                const inMonth = isSameMonth(day, month)
                const isToday = key === meta.today
                return (
                  <div key={key} className={cn('group relative min-h-28 min-w-0 border-b border-r border-border p-1.5 [&:nth-child(7n)]:border-r-0', !inMonth && 'bg-surface-muted/60')}>
                    <div className="mb-1 flex items-center justify-between">
                      <span className={cn('flex size-6 items-center justify-center rounded-full text-xs tabular-nums', isToday ? 'bg-brand-500 font-semibold text-white' : inMonth ? 'text-ink' : 'text-ink-muted')}>
                        {day.getDate()}
                      </span>
                      <button
                        type="button"
                        aria-label={`Добавить публикацию на ${format(day, 'd MMMM', { locale: ru })}`}
                        onClick={() => onOpen({ date: key })}
                        className="flex size-6 items-center justify-center rounded-md text-ink-muted opacity-0 transition-opacity hover:bg-brand-50 hover:text-brand-700 focus-visible:opacity-100 group-hover:opacity-100"
                      >
                        <Plus className="size-4" aria-hidden />
                      </button>
                    </div>
                    <ul className="space-y-1">
                      {list.slice(0, CELL_LIMIT).map((item) => (
                        <li key={item.id}>
                          <button
                            type="button"
                            onClick={() => onOpen({ item })}
                            title={`${item.title} · ${item.channel_label} · ${item.status_label}`}
                            className={cn('block w-full truncate rounded-md border-l-[3px] bg-surface-muted px-1.5 py-1 text-left text-xs text-ink transition-colors hover:bg-brand-50', CONTENT_BORDER[item.status], item.status === 'published' && 'text-ink-secondary')}
                          >
                            <span className="font-medium text-ink-secondary">{CHANNEL_SHORT[item.channel]}</span> {item.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                    {list.length > CELL_LIMIT ? (
                      <button type="button" onClick={() => setDayOpen(key)} className="mt-1 text-xs font-medium text-brand-700 hover:underline">
                        Ещё {list.length - CELL_LIMIT}
                      </button>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Телефон: только дни с публикациями, крупные карточки. */}
          <div className="md:hidden">
            {agendaDays.length === 0 ? (
              <EmptyState icon={CalendarRange} title="В этом месяце публикаций нет" description="Добавьте публикацию — она появится в календаре." />
            ) : (
              <div className="space-y-3">
                {agendaDays.map((day) => {
                  const key = isoDate(day)
                  return (
                    <section key={key} aria-label={format(day, 'd MMMM', { locale: ru })} className="card overflow-hidden">
                      <h3 className={cn('flex items-center gap-2 border-b border-border px-4 py-2 text-sm font-semibold', key === meta.today ? 'bg-brand-50 text-brand-700' : 'text-ink')}>
                        <span>{weekdayDate(day)}</span>
                        {key === meta.today ? <span className="text-xs font-medium">· сегодня</span> : null}
                      </h3>
                      <ul className="divide-y divide-border">
                        {(byDay.get(key) ?? []).map((item) => <ContentRow key={item.id} item={item} onOpen={(i) => onOpen({ item: i })} />)}
                      </ul>
                    </section>
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}

      {undated > 0 ? (
        <button type="button" onClick={onShowIdeas} className="card card-interactive flex w-full items-center gap-3 px-4 py-3 text-left">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-info-soft text-info"><Lightbulb className="size-5" aria-hidden /></span>
          <span className="min-w-0 flex-1 text-sm text-ink">Без даты: {undated} — идеи и материалы, которым ещё не назначен день</span>
          <ChevronRight className="size-4 shrink-0 text-ink-muted" aria-hidden />
        </button>
      ) : null}

      <Modal isOpen={dayOpen !== null} onClose={() => setDayOpen(null)} title={dayOpen ? weekdayDate(parseISO(dayOpen)) : ''}>
        <ul className="-mx-4 divide-y divide-border sm:-mx-6">
          {(dayOpen ? byDay.get(dayOpen) ?? [] : []).map((item) => (
            <ContentRow key={item.id} item={item} onOpen={(i) => { setDayOpen(null); onOpen({ item: i }) }} />
          ))}
        </ul>
      </Modal>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Список
// ---------------------------------------------------------------------------

function ListView({ filters, onOpen }: { filters: Filters; onOpen: (draft: ContentDraft) => void }) {
  const [search, setSearch] = useState('')
  // Новые фильтры или поиск — снова первая страница.
  const scope = JSON.stringify([filters, search])
  const [paging, setPaging] = useState({ scope, page: 1 })
  const page = paging.scope === scope ? paging.page : 1
  const setPage = (next: number) => setPaging({ scope, page: next })
  const params = { ...filterParams(filters), search: search || undefined, page, page_size: LIST_PAGE }
  const items = useContentItems(params)

  return (
    <div className="space-y-3">
      <SearchInput value={search} onChange={setSearch} placeholder="Поиск по теме и заметкам" />
      <Card padding="none">
        {items.isPending ? (
          <LoadingState />
        ) : items.isError ? (
          <ErrorState message={extractErrorMessage(items.error)} onRetry={() => void items.refetch()} />
        ) : items.data.results.length === 0 ? (
          <EmptyState icon={CalendarRange} title="Публикаций не найдено" description="Измените фильтры или добавьте новую публикацию." />
        ) : (
          <>
            <ul className="divide-y divide-border">
              {items.data.results.map((item) => <ContentRow key={item.id} item={item} onOpen={(i) => onOpen({ item: i })} />)}
            </ul>
            {items.data.count > LIST_PAGE ? (
              <div className="px-4 pb-4 sm:px-5">
                <Pagination page={page} pageSize={LIST_PAGE} totalCount={items.data.count} onPageChange={setPage} />
              </div>
            ) : null}
          </>
        )}
      </Card>
      <p className="text-xs text-ink-muted">Сначала — ближайшие даты; публикации без даты — в конце списка.</p>
    </div>
  )
}

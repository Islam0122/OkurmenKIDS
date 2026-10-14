import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowDownWideNarrow, ArrowUpNarrowWide, CalendarRange, Clock, Search, Users, X } from 'lucide-react'

import { useGroupBoard, useLeaderboardMeta, useStudentBoard } from '@/hooks/usePublicLeaderboard'
import type { LeaderboardMeta, LeaderboardPeriod } from '@/types/leaderboard'

import { formatDateTime, formatNumber, periodRange, periodTitle, plural } from './format'
import { GroupList, MemberStack } from './GroupList'
import { PeriodSwitcher } from './PeriodSwitcher'
import { Podium } from './Podium'
import type { PodiumEntry } from './Podium'
import { GroupMethodCard, RulesCard, TopGroupsCard, TopStudentsCard } from './SideCards'
import { StudentTable } from './StudentTable'
import { EmptyState, ErrorState, LoadMoreButton, Panel, PodiumSkeleton, RowsSkeleton, Skeleton } from './ui'
import { usePeriodParams } from './usePeriodParams'

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(id)
  }, [value, delay])
  return debounced
}

const controlClass =
  'h-9 w-full min-w-0 rounded-lg border border-lb-line bg-white px-3 text-sm text-ink placeholder:text-ink-muted ' +
  'hover:border-lb-purple-100 focus-visible:border-lb-purple focus-visible:outline-lb-purple'

function SearchBox({ value, onChange, label }: { value: string; onChange: (value: string) => void; label: string }) {
  return (
    <div className="relative min-w-0 flex-1 sm:max-w-xs">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={label}
        aria-label={label}
        maxLength={100}
        className={`${controlClass} pl-9 pr-8 [&::-webkit-search-cancel-button]:hidden`}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange('')}
          aria-label="Очистить поиск"
          className="absolute right-2 top-1/2 inline-flex size-5 -translate-y-1/2 items-center justify-center rounded-full text-ink-muted hover:bg-lb-bg"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      ) : null}
    </div>
  )
}

function FilterSelect({ label, value, onChange, options }: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} className={`${controlClass} sm:w-auto sm:max-w-[14rem]`}>
      <option value="">{label}: все</option>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

function OrderToggle({ order, onChange }: { order: 'desc' | 'asc'; onChange: (order: 'desc' | 'asc') => void }) {
  const desc = order === 'desc'
  const Icon = desc ? ArrowDownWideNarrow : ArrowUpNarrowWide
  return (
    <button
      type="button"
      onClick={() => onChange(desc ? 'asc' : 'desc')}
      aria-label={desc ? 'Сортировка: больше XP сначала' : 'Сортировка: меньше XP сначала'}
      title={desc ? 'Больше XP сначала' : 'Меньше XP сначала'}
      className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-lb-line bg-white px-3 text-sm font-medium text-ink-secondary transition-colors hover:border-lb-purple-100 hover:text-lb-purple focus-visible:outline-lb-purple"
    >
      <Icon className="size-4" aria-hidden />
      XP
    </button>
  )
}

function Stat({ icon, label, value, loading }: { icon: ReactNode; label: string; value: ReactNode; loading?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-xl bg-white/10 px-3 py-2.5 ring-1 ring-white/15">
      <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/15 text-lb-gold">{icon}</span>
      <span className="min-w-0">
        <span className="block text-xs text-white/70">{label}</span>
        {loading ? <Skeleton className="mt-1 h-4 w-24 bg-white/25" /> : <span className="block truncate text-sm font-semibold text-white">{value}</span>}
      </span>
    </div>
  )
}

/** The page head: title, what is ranked, participants, period, freshness. */
function Hero({ title, description, participants, participantsLabel, period, meta, generatedAt }: {
  title: string
  description: string
  participants: number | undefined
  participantsLabel: [string, string, string]
  period: LeaderboardPeriod | undefined
  meta: LeaderboardMeta | undefined
  generatedAt: string | undefined
}) {
  return (
    <section className="relative overflow-hidden rounded-2xl bg-lb-deep px-5 py-6 text-white sm:px-8 sm:py-8">
      <div aria-hidden className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-lb-purple/70 blur-2xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-24 right-24 size-48 rounded-full bg-lb-gold/20 blur-3xl" />
      <div className="relative">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-lb-gold">OkurmenKIDS · Leaderboard</p>
        <h1 className="mt-2 text-2xl font-extrabold tracking-tight sm:text-3xl">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm text-white/80">{description}</p>
        <div className="mt-5 grid gap-2 sm:grid-cols-3">
          <Stat
            icon={<Users className="size-4" aria-hidden />}
            label="Участников в рейтинге"
            loading={participants === undefined}
            value={participants === undefined ? '' : `${formatNumber(participants)} ${plural(participants, participantsLabel)}`}
          />
          <Stat
            icon={<CalendarRange className="size-4" aria-hidden />}
            label={period ? periodTitle(period) : 'Период'}
            loading={!period}
            value={period ? periodRange(period) : ''}
          />
          <Stat
            icon={<Clock className="size-4" aria-hidden />}
            label="Данные обновлены"
            loading={!meta && !generatedAt}
            value={formatDateTime(meta?.last_activity ?? generatedAt)}
          />
        </div>
      </div>
    </section>
  )
}

function SectionHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-lb-line px-4 py-3 sm:px-5">
      <h2 className="text-base font-bold text-lb-deep">{title}</h2>
      {children}
    </div>
  )
}

function useLeaderboardPeriod() {
  const meta = useLeaderboardMeta()
  const period = usePeriodParams(meta.data)
  return { meta, ...period }
}

function PeriodBar({ state }: { state: ReturnType<typeof useLeaderboardPeriod> }) {
  return (
    <PeriodSwitcher
      meta={state.meta.data}
      params={state.params}
      onType={state.setPeriodType}
      onChange={state.update}
      onShiftWeek={state.shiftWeek}
    />
  )
}

function periodNote(period: LeaderboardPeriod | undefined): string | null {
  if (!period) return null
  return period.is_current ? 'Период ещё идёт — рейтинг обновляется по мере новых результатов.' : null
}

// ---------------------------------------------------------------------------
// Топ студентов
// ---------------------------------------------------------------------------

export function StudentsLeaderboardPage() {
  const state = useLeaderboardPeriod()
  const [q, setQ] = useState('')
  const [group, setGroup] = useState('')
  const [course, setCourse] = useState('')
  const [order, setOrder] = useState<'desc' | 'asc'>('desc')
  const search = useDebounced(q.trim())
  const filtered = Boolean(search || group || course || order === 'asc')

  const board = useStudentBoard({ ...state.params, q: search, group, course, order }, state.ready)
  const first = board.data?.pages[0]
  const rows = board.data?.pages.flatMap((page) => page.results) ?? []
  const meta = state.meta.data
  const groups = (meta?.groups ?? []).filter((g) => !course || g.course === course)

  const podium: PodiumEntry[] = (first?.podium ?? []).map((row) => ({
    key: row.key, rank: row.rank, title: row.name, subtitle: row.group?.name, detail: row.course?.name,
    value: `${formatNumber(row.xp)} XP`, initials: row.initials, hidden: row.hidden,
    valueHint: `Посещаемость ${row.breakdown.attendance} · ДЗ ${row.breakdown.homework} · Тесты ${row.breakdown.tests}`,
  }))
  const loading = !state.ready || board.isPending

  return (
    <div className="space-y-5">
      <Hero
        title="Топ студентов"
        description="Лучшие ученики академии за выбранный период. XP начисляются за посещение занятий, сданные домашние задания и результаты тестов — по одинаковым правилам для всех."
        participants={first?.participants}
        participantsLabel={['студент', 'студента', 'студентов']}
        period={first?.period}
        meta={meta}
        generatedAt={first?.generated_at}
      />
      <PeriodBar state={state} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-5">
          <Panel aria-label="Пьедестал">
            <SectionHead title={first ? `Топ-3 · ${periodTitle(first.period)}` : 'Топ-3'} />
            <div className="px-3 pb-0 pt-8 sm:px-8">
              {loading ? <PodiumSkeleton /> : board.isError && !first ? null : podium.length ? (
                <Podium entries={podium} label="Три лучших студента" />
              ) : (
                <EmptyState title="Пока нет результатов" description="За этот период ещё нет начисленных XP. Выберите другой период или загляните позже." />
              )}
            </div>
          </Panel>

          <Panel aria-label="Рейтинг студентов">
            <SectionHead title="Рейтинг">
              {first && filtered ? (
                <span className="text-xs text-ink-secondary">Найдено: {formatNumber(first.count)}</span>
              ) : null}
            </SectionHead>
            <div className="flex flex-col gap-2 border-b border-lb-line px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:px-5">
              <SearchBox value={q} onChange={setQ} label="Поиск студента" />
              <FilterSelect label="Направление" value={course} onChange={(v) => { setCourse(v); setGroup('') }}
                options={(meta?.courses ?? []).map((c) => ({ value: c.key, label: c.name }))} />
              <FilterSelect label="Группа" value={group} onChange={setGroup}
                options={groups.map((g) => ({ value: g.key, label: g.name }))} />
              <OrderToggle order={order} onChange={setOrder} />
            </div>
            {periodNote(first?.period) ? <p className="px-4 pt-3 text-xs text-ink-muted sm:px-5">{periodNote(first?.period)}</p> : null}
            <div aria-live="polite" aria-busy={board.isFetching}>
              {loading ? <RowsSkeleton /> : board.isError && !first ? (
                <ErrorState onRetry={() => void board.refetch()} />
              ) : rows.length === 0 ? (
                filtered ? (
                  <EmptyState title="Никого не нашли" description="Попробуйте изменить поиск или сбросить фильтры." />
                ) : (
                  <EmptyState title="Рейтинг пуст" description="За этот период ещё нет начисленных XP." />
                )
              ) : (
                <>
                  <StudentTable rows={rows} caption={`Рейтинг студентов: ${first ? periodTitle(first.period) : ''}`} />
                  {board.hasNextPage ? (
                    <LoadMoreButton onClick={() => void board.fetchNextPage()} loading={board.isFetchingNextPage} shown={rows.length} total={first?.count ?? rows.length} />
                  ) : null}
                </>
              )}
            </div>
          </Panel>
        </div>

        <aside className="min-w-0 space-y-5" aria-label="Дополнительно">
          {state.ready ? <TopGroupsCard period={state.params} /> : null}
          <RulesCard rules={meta?.rules} />
        </aside>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Топ групп
// ---------------------------------------------------------------------------

export function GroupsLeaderboardPage() {
  const state = useLeaderboardPeriod()
  const [q, setQ] = useState('')
  const [course, setCourse] = useState('')
  const [order, setOrder] = useState<'desc' | 'asc'>('desc')
  const search = useDebounced(q.trim())
  const filtered = Boolean(search || course || order === 'asc')

  const board = useGroupBoard({ ...state.params, q: search, course, order }, state.ready)
  const first = board.data?.pages[0]
  const rows = board.data?.pages.flatMap((page) => page.results) ?? []
  const meta = state.meta.data
  const loading = !state.ready || board.isPending

  const podium: PodiumEntry[] = (first?.podium ?? []).map((group) => ({
    key: group.key, rank: group.rank, title: group.name, subtitle: group.course?.name,
    detail: `${group.members} ${plural(group.members, ['студент', 'студента', 'студентов'])} · Σ ${formatNumber(group.total_xp)} XP`,
    value: `${formatNumber(group.average_xp)} XP/чел.`, valueHint: 'Средний XP на студента', initials: '',
    avatar: (
      <span className="flex min-h-14 items-center justify-center sm:min-h-20">
        <MemberStack members={group.top_members} groupKey={group.key} size="md" max={3} />
      </span>
    ),
  }))

  return (
    <div className="space-y-5">
      <Hero
        title="Топ групп"
        description="Рейтинг учебных групп за выбранный период. Группы сравниваются по среднему XP на одного студента, чтобы маленькие и большие группы были в равных условиях."
        participants={first?.participants}
        participantsLabel={['группа', 'группы', 'групп']}
        period={first?.period}
        meta={meta}
        generatedAt={first?.generated_at}
      />
      <PeriodBar state={state} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-5">
          <Panel aria-label="Пьедестал групп">
            <SectionHead title={first ? `Топ-3 групп · ${periodTitle(first.period)}` : 'Топ-3 групп'} />
            <div className="px-3 pb-0 pt-8 sm:px-8">
              {loading ? <PodiumSkeleton /> : board.isError && !first ? null : podium.length ? (
                <Podium entries={podium} label="Три лучшие группы" />
              ) : (
                <EmptyState title="Пока нет результатов" description="За этот период у групп ещё нет начисленных XP." />
              )}
            </div>
          </Panel>

          <Panel aria-label="Рейтинг групп">
            <SectionHead title="Все группы">
              {first && filtered ? <span className="text-xs text-ink-secondary">Найдено: {formatNumber(first.count)}</span> : null}
            </SectionHead>
            <div className="flex flex-col gap-2 border-b border-lb-line px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:px-5">
              <SearchBox value={q} onChange={setQ} label="Поиск группы" />
              <FilterSelect label="Направление" value={course} onChange={setCourse}
                options={(meta?.courses ?? []).map((c) => ({ value: c.key, label: c.name }))} />
              <OrderToggle order={order} onChange={setOrder} />
            </div>
            <p className="px-4 pt-3 text-xs text-ink-muted sm:px-5">Нажмите на группу, чтобы увидеть её студентов за этот период.</p>
            <div aria-live="polite" aria-busy={board.isFetching} className="pt-1">
              {loading ? <RowsSkeleton /> : board.isError && !first ? (
                <ErrorState onRetry={() => void board.refetch()} />
              ) : rows.length === 0 ? (
                filtered ? (
                  <EmptyState title="Ничего не нашли" description="Попробуйте изменить поиск или фильтр." />
                ) : (
                  <EmptyState title="Рейтинг пуст" description="За этот период ещё нет начисленных XP." />
                )
              ) : (
                <>
                  <GroupList rows={rows} period={state.params} caption="Рейтинг групп" />
                  {board.hasNextPage ? (
                    <LoadMoreButton onClick={() => void board.fetchNextPage()} loading={board.isFetchingNextPage} shown={rows.length} total={first?.count ?? rows.length} />
                  ) : null}
                </>
              )}
            </div>
          </Panel>
        </div>

        <aside className="min-w-0 space-y-5" aria-label="Дополнительно">
          <GroupMethodCard />
          {state.ready ? <TopStudentsCard period={state.params} /> : null}
          <RulesCard rules={meta?.rules} />
        </aside>
      </div>
    </div>
  )
}

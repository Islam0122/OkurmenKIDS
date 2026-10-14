import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowDownWideNarrow, ArrowUpNarrowWide, Crown, ListOrdered, Search, Users, X } from 'lucide-react'

import { useGroupBoard, useLeaderboardMeta, useStudentBoard } from '@/hooks/usePublicLeaderboard'
import type { LeaderboardPeriod, LeaderboardStudent } from '@/types/leaderboard'
import { cn } from '@/utils/cn'

import { formatNumber, periodTitle, plural } from './format'
import { GroupList, MemberStack } from './GroupList'
import { Hero } from './Hero'
import { PeriodSwitcher, selectClass } from './PeriodSwitcher'
import { Podium } from './Podium'
import type { PodiumEntry } from './Podium'
import { HighlightsCard, RulesCard, TeamCard, TopGroupsCard, TopStudentsCard } from './SideCards'
import { StudentTable } from './StudentTable'
import { EmptyState, ErrorState, InfoHint, LoadMoreButton, Panel, PodiumSkeleton, RowsSkeleton } from './ui'
import { usePeriodParams } from './usePeriodParams'

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(id)
  }, [value, delay])
  return debounced
}

function SearchBox({ value, onChange, label }: { value: string; onChange: (value: string) => void; label: string }) {
  return (
    <div className="relative min-w-0 flex-1 sm:min-w-[13rem]">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-lb-muted" aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={label}
        aria-label={label}
        maxLength={100}
        className="h-10 w-full min-w-0 rounded-xl border-0 bg-lb-bg pl-9 pr-8 text-sm text-lb-ink placeholder:text-lb-muted transition focus:bg-white focus-visible:shadow-[0_0_0_2px_rgba(59,22,141,0.35)] focus-visible:outline-none [&::-webkit-search-cancel-button]:hidden"
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange('')}
          aria-label="Очистить поиск"
          className="absolute right-2 top-1/2 inline-flex size-6 -translate-y-1/2 items-center justify-center rounded-full text-lb-muted hover:bg-lb-line"
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
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(selectClass, 'w-full sm:w-auto sm:max-w-[13rem]', value && 'text-lb-purple shadow-[0_0_0_1.5px_rgba(59,22,141,0.45)]')}
    >
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
      className={cn(
        'inline-flex h-10 shrink-0 items-center gap-1.5 rounded-xl px-3 text-sm font-semibold transition focus-visible:outline-lb-purple',
        desc ? 'bg-lb-bg text-lb-muted hover:text-lb-purple' : 'bg-lb-purple-50 text-lb-purple',
      )}
    >
      <Icon className="size-4" aria-hidden />
      XP
    </button>
  )
}

/** A section card's head: an icon, a title, an optional chip and controls. */
function SectionHead({ icon, title, chip, children }: { icon: ReactNode; title: ReactNode; chip?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-3 pt-4 sm:px-5">
      <h2 className="flex min-w-0 items-center gap-2 text-lg font-black tracking-tight text-lb-deep">
        <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-xl bg-lb-purple text-lb-gold">{icon}</span>
        {title}
        {chip}
      </h2>
      {children}
    </div>
  )
}

function PeriodChip({ period }: { period: LeaderboardPeriod | undefined }) {
  if (!period) return null
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-lb-gold-soft px-2.5 py-1 text-xs font-bold text-lb-gold-dark">
      {period.is_current ? <span className="size-1.5 animate-pulse rounded-full bg-lb-success" aria-hidden /> : null}
      {periodTitle(period)}
    </span>
  )
}

/** The podium sits on a soft purple/gold glow — the visual centre of the page. */
function PodiumStage({ children }: { children: ReactNode }) {
  return (
    <div className="relative px-3 pt-6 sm:px-8 sm:pt-7">
      <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 top-6 bg-[radial-gradient(ellipse_at_50%_100%,rgba(246,184,47,0.18),transparent_60%),radial-gradient(ellipse_at_50%_20%,rgba(59,22,141,0.07),transparent_55%)]" />
      <div className="relative mx-auto max-w-2xl">{children}</div>
      <div aria-hidden className="relative h-2 rounded-t-sm bg-gradient-to-r from-transparent via-lb-line to-transparent" />
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

/** The biggest climb among the loaded rows (real `change` values only). */
function biggestClimb(rows: LeaderboardStudent[]) {
  let best: LeaderboardStudent | null = null
  for (const row of rows) {
    if (row.hidden || row.change?.status !== 'up') continue
    if (!best || row.change.value > (best.change?.value ?? 0)) best = row
  }
  return best
}

const layoutClass = 'grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]'

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
  const groupsTop = useGroupBoard({ ...state.params, page_size: 5 }, state.ready)
  const first = board.data?.pages[0]
  const rows = board.data?.pages.flatMap((page) => page.results) ?? []
  const meta = state.meta.data
  const groups = (meta?.groups ?? []).filter((g) => !course || g.course === course)
  const topGroups = groupsTop.data?.pages[0]

  const podium: PodiumEntry[] = (first?.podium ?? []).map((row) => ({
    key: row.key, rank: row.rank, title: row.name, subtitle: row.group?.name, detail: row.course?.name,
    value: `${formatNumber(row.xp)} XP`, valueCaption: 'за период', initials: row.initials, hidden: row.hidden,
    valueHint: `Посещаемость ${row.breakdown.attendance} · ДЗ ${row.breakdown.homework} · Тесты ${row.breakdown.tests}`,
  }))
  const loading = !state.ready || board.isPending
  const leader = first?.podium[0]
  const climber = !filtered ? biggestClimb(rows) : null
  const bestGroup = topGroups?.podium[0]

  return (
    <div className="space-y-5">
      <Hero
        description="Лучшие ученики академии за выбранный период. XP — за посещение занятий, сданные домашние задания и тесты, по одинаковым правилам для всех."
        students={first?.participants}
        groups={topGroups?.participants}
        period={first?.period}
        updatedAt={meta ? meta.last_activity ?? first?.generated_at ?? null : undefined}
      />
      <PeriodBar state={state} />

      <div className={layoutClass}>
        <div className="min-w-0 space-y-5">
          <Panel aria-label="Пьедестал" className="overflow-hidden">
            <SectionHead icon={<Crown className="size-4" aria-hidden />} title="Топ студентов" chip={<PeriodChip period={first?.period} />} />
            <PodiumStage>
              {loading ? <PodiumSkeleton /> : board.isError && !first ? null : podium.length ? (
                <Podium entries={podium} label="Три лучших студента" />
              ) : (
                <EmptyState title="Пока нет результатов" description="За этот период ещё нет начисленных XP. Выберите другой период или загляните позже." />
              )}
            </PodiumStage>
          </Panel>

          <Panel aria-label="Рейтинг студентов" className="overflow-hidden">
            <SectionHead
              icon={<ListOrdered className="size-4" aria-hidden />}
              title="Рейтинг"
              chip={first && filtered ? <span className="text-xs font-semibold text-lb-muted">Найдено: {formatNumber(first.count)}</span> : null}
            />
            <div className="flex flex-col gap-2 px-4 pb-3 sm:flex-row sm:flex-wrap sm:items-center sm:px-5">
              <SearchBox value={q} onChange={setQ} label="Поиск студента" />
              <FilterSelect label="Направление" value={course} onChange={(v) => { setCourse(v); setGroup('') }}
                options={(meta?.courses ?? []).map((c) => ({ value: c.key, label: c.name }))} />
              <FilterSelect label="Группа" value={group} onChange={setGroup}
                options={groups.map((g) => ({ value: g.key, label: g.name }))} />
              <OrderToggle order={order} onChange={setOrder} />
            </div>
            <div aria-live="polite" aria-busy={board.isFetching} className={cn('border-t border-lb-line transition-opacity', board.isFetching && !board.isFetchingNextPage && 'opacity-70')}>
              {loading ? <RowsSkeleton /> : board.isError && !first ? (
                <ErrorState onRetry={() => void board.refetch()} />
              ) : rows.length === 0 ? (
                filtered ? (
                  <EmptyState kind="search" title="Никого не нашли" description="Попробуйте изменить поиск или сбросить фильтры." />
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
          <HighlightsCard
            leader={leader && !leader.hidden ? { name: leader.name, detail: leader.group?.name ?? '', value: `${formatNumber(leader.xp)} XP` } : null}
            climber={climber && climber.change ? { name: climber.name, detail: climber.group?.name ?? '', value: climber.change.value } : null}
            group={bestGroup ? { name: bestGroup.name, value: formatNumber(bestGroup.average_xp) } : null}
          />
          <TopGroupsCard rows={topGroups?.results} isError={groupsTop.isError} />
          <TeamCard />
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
  const studentsTop = useStudentBoard({ ...state.params, page_size: 5 }, state.ready)
  const first = board.data?.pages[0]
  const rows = board.data?.pages.flatMap((page) => page.results) ?? []
  const meta = state.meta.data
  const loading = !state.ready || board.isPending
  const topStudents = studentsTop.data?.pages[0]

  const podium: PodiumEntry[] = (first?.podium ?? []).map((group) => ({
    key: group.key, rank: group.rank, title: group.name, subtitle: group.course?.name,
    detail: `${group.members} ${plural(group.members, ['студент', 'студента', 'студентов'])} · Σ ${formatNumber(group.total_xp)} XP`,
    value: `${formatNumber(group.average_xp)} XP`, valueCaption: 'в среднем на студента', valueHint: 'Средний XP на студента', initials: '',
    avatar: (
      <span className="flex h-14 items-center justify-center sm:h-[4.5rem]">
        <MemberStack members={group.top_members} groupKey={group.key} size="md" max={3} />
      </span>
    ),
  }))
  const leader = topStudents?.podium[0]
  const bestGroup = first?.podium[0]

  return (
    <div className="space-y-5">
      <Hero
        description="Рейтинг учебных групп за выбранный период. Группы сравниваются по среднему XP на одного студента — маленькие и большие группы в равных условиях."
        students={first?.students_ranked}
        groups={first?.participants}
        period={first?.period}
        updatedAt={meta ? meta.last_activity ?? first?.generated_at ?? null : undefined}
      />
      <PeriodBar state={state} />

      <div className={layoutClass}>
        <div className="min-w-0 space-y-5">
          <Panel aria-label="Пьедестал групп" className="overflow-hidden">
            <SectionHead
              icon={<Crown className="size-4" aria-hidden />}
              title={<>Топ групп <InfoHint label="Как считается рейтинг групп">Средний XP = сумма XP текущих студентов группы за период ÷ их число (включая студентов без баллов). Сумма XP показана справочно.</InfoHint></>}
              chip={<PeriodChip period={first?.period} />}
            />
            <PodiumStage>
              {loading ? <PodiumSkeleton /> : board.isError && !first ? null : podium.length ? (
                <Podium entries={podium} label="Три лучшие группы" />
              ) : (
                <EmptyState title="Пока нет результатов" description="За этот период у групп ещё нет начисленных XP." />
              )}
            </PodiumStage>
          </Panel>

          <Panel aria-label="Рейтинг групп" className="overflow-hidden">
            <SectionHead
              icon={<Users className="size-4" aria-hidden />}
              title="Все группы"
              chip={first && filtered ? <span className="text-xs font-semibold text-lb-muted">Найдено: {formatNumber(first.count)}</span> : null}
            />
            <div className="flex flex-col gap-2 px-4 pb-3 sm:flex-row sm:flex-wrap sm:items-center sm:px-5">
              <SearchBox value={q} onChange={setQ} label="Поиск группы" />
              <FilterSelect label="Направление" value={course} onChange={setCourse}
                options={(meta?.courses ?? []).map((c) => ({ value: c.key, label: c.name }))} />
              <OrderToggle order={order} onChange={setOrder} />
            </div>
            <p className="border-t border-lb-line bg-lb-bg/60 px-4 py-2 text-xs text-lb-muted sm:px-5">Нажмите на группу, чтобы увидеть её студентов за этот период.</p>
            <div aria-live="polite" aria-busy={board.isFetching} className={cn('transition-opacity', board.isFetching && !board.isFetchingNextPage && 'opacity-70')}>
              {loading ? <RowsSkeleton /> : board.isError && !first ? (
                <ErrorState onRetry={() => void board.refetch()} />
              ) : rows.length === 0 ? (
                filtered ? (
                  <EmptyState kind="search" title="Ничего не нашли" description="Попробуйте изменить поиск или фильтр." />
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
          <TeamCard link={false} />
          <HighlightsCard
            leader={leader && !leader.hidden ? { name: leader.name, detail: leader.group?.name ?? '', value: `${formatNumber(leader.xp)} XP` } : null}
            climber={null}
            group={bestGroup ? { name: bestGroup.name, value: formatNumber(bestGroup.average_xp) } : null}
          />
          <TopStudentsCard rows={topStudents?.results} isError={studentsTop.isError} />
          <RulesCard rules={meta?.rules} />
        </aside>
      </div>
    </div>
  )
}

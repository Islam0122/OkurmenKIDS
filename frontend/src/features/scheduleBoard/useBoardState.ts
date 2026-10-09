import { useCallback, useEffect, useMemo, useState } from 'react'
import { addDays, endOfWeek, format, isValid, parseISO, startOfWeek } from 'date-fns'
import { useSearchParams } from 'react-router-dom'

export type BoardView = 'day' | 'week'

export interface BoardFilters {
  teacher: number | null
  rooms: number[]
  group: number | null
}

export interface BoardState extends BoardFilters {
  view: BoardView
  /** The selected day (ISO). The week view shows that day's Mon–Sun. */
  date: string
}

export const EMPTY_FILTERS: BoardFilters = { teacher: null, rooms: [], group: null }

const iso = (date: Date) => format(date, 'yyyy-MM-dd')

function readSession(key: string): Partial<BoardState> {
  try {
    const raw = sessionStorage.getItem(key)
    return raw ? (JSON.parse(raw) as Partial<BoardState>) : {}
  } catch {
    return {}
  }
}

function writeSession(key: string, state: BoardState) {
  try {
    sessionStorage.setItem(key, JSON.stringify(state))
  } catch {
    // Private mode / quota — the board still works, it just won't remember.
  }
}

const num = (value: string | null) => (value && /^\d+$/.test(value) ? Number(value) : null)

/**
 * View, date and filters of a schedule board. Remembered for the browser
 * tab's session (sessionStorage, one key per page), so switching Day/Week,
 * opening a lesson or another section and coming back keeps them; a link
 * with ?view= ?date= ?teacher= ?group= ?room=1,2 overrides them once.
 */
export function useBoardState(storageKey: string) {
  const [params, setParams] = useSearchParams()
  const [state, setState] = useState<BoardState>(() => {
    const saved = readSession(storageKey)
    const fromUrl: Partial<BoardState> = {}
    const view = params.get('view')
    if (view === 'day' || view === 'week') fromUrl.view = view
    const date = params.get('date')
    if (date && isValid(parseISO(date))) fromUrl.date = date
    if (params.has('teacher')) fromUrl.teacher = num(params.get('teacher'))
    if (params.has('group')) fromUrl.group = num(params.get('group'))
    if (params.has('room')) fromUrl.rooms = (params.get('room') ?? '').split(',').map(num).filter((n): n is number => n !== null)
    return {
      view: 'day',
      date: iso(new Date()),
      ...EMPTY_FILTERS,
      ...saved,
      ...fromUrl,
    }
  })

  useEffect(() => {
    writeSession(storageKey, state)
  }, [storageKey, state])

  // A deep link applies once; afterwards the page's own state rules.
  useEffect(() => {
    if (['view', 'date', 'teacher', 'group', 'room'].some((key) => params.has(key))) {
      const next = new URLSearchParams(params)
      for (const key of ['view', 'date', 'teacher', 'group', 'room']) next.delete(key)
      setParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const update = useCallback((patch: Partial<BoardState>) => setState((current) => ({ ...current, ...patch })), [])
  const clearFilters = useCallback(() => setState((current) => ({ ...current, ...EMPTY_FILTERS })), [])

  const range = useMemo(() => {
    const anchor = parseISO(state.date)
    if (state.view === 'day') return { start: state.date, end: state.date }
    return { start: iso(startOfWeek(anchor, { weekStartsOn: 1 })), end: iso(endOfWeek(anchor, { weekStartsOn: 1 })) }
  }, [state.date, state.view])

  const shift = useCallback(
    (direction: 1 | -1) =>
      setState((current) => ({ ...current, date: iso(addDays(parseISO(current.date), current.view === 'day' ? direction : 7 * direction)) })),
    [],
  )

  const hasFilters = state.teacher !== null || state.group !== null || state.rooms.length > 0

  return { state, update, clearFilters, range, shift, hasFilters }
}

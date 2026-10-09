/**
 * Geometry of the schedule grid: the 08:00–24:00 working day, a lesson's
 * vertical position by its real start and end, and side-by-side lanes for
 * lessons that overlap in one column. Pure functions — unit-tested.
 */

export const DAY_START = 8 * 60
export const DAY_END = 24 * 60
export const DAY_MINUTES = DAY_END - DAY_START

/** «HH:MM» → minutes since midnight («24:00» → 1440). */
export function toMinutes(value: string): number {
  const [h, m] = value.split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

export function fromMinutes(total: number): string {
  const clamped = Math.max(0, Math.min(DAY_END, Math.round(total)))
  return `${String(Math.floor(clamped / 60)).padStart(2, '0')}:${String(clamped % 60).padStart(2, '0')}`
}

/** Hour lines of the grid: 08:00, 09:00 … 24:00 (17 labels, 16 rows). */
export function hourMarks(): string[] {
  return Array.from({ length: DAY_MINUTES / 60 + 1 }, (_, i) => fromMinutes(DAY_START + i * 60))
}

/** «1 ч 30 мин», «45 мин», «2 ч». */
export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (!h) return `${m} мин`
  return m ? `${h} ч ${m} мин` : `${h} ч`
}

export interface Placement {
  /** Offset from 08:00 and height, in minutes of the grid (clamped to 08:00–24:00). */
  top: number
  height: number
  /** The lesson starts before 08:00 / ends after the grid's end. */
  clippedStart: boolean
  clippedEnd: boolean
}

/** Where a lesson sits on the 08:00–24:00 axis; an end of 00:00 means midnight. */
export function place(start: string, end: string): Placement {
  const s = toMinutes(start)
  let e = toMinutes(end)
  if (e === 0 || e < s) e = DAY_END
  const top = Math.max(s, DAY_START) - DAY_START
  const bottom = Math.min(Math.max(e, DAY_START), DAY_END) - DAY_START
  return { top, height: Math.max(bottom - top, 0), clippedStart: s < DAY_START, clippedEnd: e > DAY_END }
}

export interface Laned<T> {
  item: T
  lane: number
  lanes: number
  /** Index of the overlap cluster the item belongs to (column-local). */
  cluster: number
}

/**
 * Overlapping items of one column side by side: each cluster of
 * (transitively) overlapping items is split into as many lanes as it needs;
 * touching ends (14:00–15:00, 15:00–16:00) share a lane.
 */
export function assignLanes<T extends { start: string; end: string }>(items: T[]): Laned<T>[] {
  const sorted = [...items].sort((a, b) => toMinutes(a.start) - toMinutes(b.start) || toMinutes(b.end) - toMinutes(a.end))
  const result: Laned<T>[] = []
  let cluster: Laned<T>[] = []
  let laneEnds: number[] = []
  let clusterEnd = -1
  let clusterIndex = 0

  const flush = () => {
    for (const entry of cluster) entry.lanes = laneEnds.length
    result.push(...cluster)
    cluster = []
    laneEnds = []
    clusterIndex += 1
  }

  for (const item of sorted) {
    const s = toMinutes(item.start)
    const e = toMinutes(item.end) || DAY_END
    if (cluster.length && s >= clusterEnd) flush()
    let lane = laneEnds.findIndex((end) => end <= s)
    if (lane === -1) {
      lane = laneEnds.length
      laneEnds.push(e)
    } else {
      laneEnds[lane] = e
    }
    cluster.push({ item, lane, lanes: 0, cluster: clusterIndex })
    clusterEnd = Math.max(clusterEnd, e)
  }
  flush()
  return result
}

/** Snap a click inside a column to a 30-minute slot start. */
export function slotAt(offsetMinutes: number, step = 30): number {
  const total = DAY_START + Math.floor(offsetMinutes / step) * step
  return Math.max(DAY_START, Math.min(DAY_END - step, total))
}

/** Shape of every DRF `PageNumberPagination` list response in this API. */
export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

/** `GroupScheduleSlot.day_of_week` / `CourseLessonPlan` weekday codes, as stored by the backend. */
export type DayOfWeek = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun'

export const DAY_LABELS: Record<DayOfWeek, string> = {
  mon: 'Пн',
  tue: 'Вт',
  wed: 'Ср',
  thu: 'Чт',
  fri: 'Пт',
  sat: 'Сб',
  sun: 'Вс',
}

export const DAY_LABELS_FULL: Record<DayOfWeek, string> = {
  mon: 'Понедельник',
  tue: 'Вторник',
  wed: 'Среда',
  thu: 'Четверг',
  fri: 'Пятница',
  sat: 'Суббота',
  sun: 'Воскресенье',
}

export const WEEKDAY_ORDER: DayOfWeek[] = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

/** The shape DRF returns for a validation error: usually `{field: [msgs]}` or `{detail: [...]}`. */
export type ApiErrorBody = Record<string, string[] | string> | string[] | string

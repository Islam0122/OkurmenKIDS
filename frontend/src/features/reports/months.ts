export const MONTH_OPTIONS = [
  { value: '1', label: 'Январь' },
  { value: '2', label: 'Февраль' },
  { value: '3', label: 'Март' },
  { value: '4', label: 'Апрель' },
  { value: '5', label: 'Май' },
  { value: '6', label: 'Июнь' },
  { value: '7', label: 'Июль' },
  { value: '8', label: 'Август' },
  { value: '9', label: 'Сентябрь' },
  { value: '10', label: 'Октябрь' },
  { value: '11', label: 'Ноябрь' },
  { value: '12', label: 'Декабрь' },
]

/** Current year back to three years ago — plenty for "which month am I
 * reporting on", without a free-text field that could produce a report for
 * some nonsense year. */
export function getYearOptions(today: Date = new Date()): { value: string; label: string }[] {
  const currentYear = today.getFullYear()
  return Array.from({ length: 4 }, (_, index) => currentYear - index).map((year) => ({
    value: String(year),
    label: String(year),
  }))
}

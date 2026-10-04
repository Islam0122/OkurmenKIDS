/** 125 → «02:05», 3725 → «1:02:05». */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(s / 3600)
  const minutes = Math.floor((s % 3600) / 60)
  const seconds = s % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(seconds).padStart(2, '0')
  return hours ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
}

/** 754 → «12 мүн 34 сек». */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  const minutes = Math.floor(s / 60)
  const seconds = s % 60
  if (!minutes) return `${seconds} сек`
  return `${minutes} мүн ${seconds} сек`
}

export function formatDate(value: string | number): string {
  return new Date(value).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

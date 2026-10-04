/*
 * The only place that touches localStorage. Used for the student's name,
 * the attempt in progress, finished results and the local leaderboard —
 * never for passwords, tokens or other sensitive data. Every call survives
 * a browser that blocks storage (private mode, disabled cookies).
 */

export const STORAGE_KEYS = {
  studentName: 'okurmen_student_name',
  trainingProgress: 'okurmen_training_progress',
  trainingResults: 'okurmen_training_results',
  leaderboard: 'okurmen_leaderboard',
} as const

function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage full or blocked — the app keeps working in memory */
  }
}

function remove(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
}

export const storageService = { read, write, remove }

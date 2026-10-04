/*
 * Temporary UI state only — never test data, questions, results or the
 * leaderboard (the backend owns those):
 *   okurmen_student_name     the name typed last, to prefill the form
 *   okurmen_active_attempts  {testId: {attemptId, token}} to resume after a reload
 * Every call survives a browser that blocks storage.
 */
const KEYS = {
  studentName: 'okurmen_student_name',
  activeAttempts: 'okurmen_active_attempts',
} as const

export interface AttemptRef {
  attemptId: string
  token: string
}

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
    /* storage blocked — the app still works, only resuming is lost */
  }
}

export const storageService = {
  getStudentName: (): string => read<string>(KEYS.studentName, ''),
  setStudentName: (name: string) => write(KEYS.studentName, name),

  getActiveAttempt: (testId: string): AttemptRef | null =>
    read<Record<string, AttemptRef>>(KEYS.activeAttempts, {})[testId] ?? null,
  setActiveAttempt(testId: string, ref: AttemptRef) {
    write(KEYS.activeAttempts, { ...read<Record<string, AttemptRef>>(KEYS.activeAttempts, {}), [testId]: ref })
  },
  clearActiveAttempt(testId: string) {
    const all = read<Record<string, AttemptRef>>(KEYS.activeAttempts, {})
    delete all[testId]
    write(KEYS.activeAttempts, all)
  },
}

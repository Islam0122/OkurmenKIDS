/** Ключ доступа «только чтение» к сайту «Общая статистика» (телевизор в офисе).
 * Хранится только в этом браузере; хранилище может быть недоступно
 * (приватный режим) — тогда ключ действует до перезагрузки страницы. */
const STORAGE_KEY = 'okurmenkids.dashboard_key'
let memory: string | null = null

export const dashboardKeyStorage = {
  get(): string | null {
    try {
      return window.localStorage.getItem(STORAGE_KEY) ?? memory
    } catch {
      return memory
    }
  },
  set(value: string): void {
    memory = value
    try {
      window.localStorage.setItem(STORAGE_KEY, value)
    } catch {
      /* только в памяти */
    }
  },
  clear(): void {
    memory = null
    try {
      window.localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* нечего очищать */
    }
  },
}

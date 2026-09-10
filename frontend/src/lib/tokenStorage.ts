/**
 * The only place JWTs touch browser storage. Kept tiny and isolated so
 * nothing else in the app reaches into localStorage directly, and so a
 * token never ends up in a `console.log` by accident elsewhere.
 */
const ACCESS_KEY = 'okurmenkids.access_token'
const REFRESH_KEY = 'okurmenkids.refresh_token'

export const tokenStorage = {
  getAccess(): string | null {
    return localStorage.getItem(ACCESS_KEY)
  },
  getRefresh(): string | null {
    return localStorage.getItem(REFRESH_KEY)
  },
  setTokens(access: string, refresh: string): void {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  setAccess(access: string): void {
    localStorage.setItem(ACCESS_KEY, access)
  },
  clear(): void {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

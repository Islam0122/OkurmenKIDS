/*
 * The only place that talks to the network. The backend URL comes from the
 * VITE_API_URL environment variable (e.g. https://okurmenkids.up.railway.app)
 * — never from the source code. Components use the functions in src/api/*,
 * not fetch().
 */

const API_PREFIX = '/api/v1/training'

export class ApiError extends Error {
  status: number
  code: string
  constructor(message: string, status: number, code = 'error') {
    super(message)
    this.status = status
    this.code = code
  }
}

export const NETWORK_ERROR = 'network'
export const CONFIG_ERROR = 'config'

export function apiBaseUrl(): string {
  return (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH'
  body?: unknown
  /** the attempt's token (X-Attempt-Token) */
  token?: string
  query?: Record<string, string | number | undefined>
  signal?: AbortSignal
  /** survives the page being closed (page-leave events) */
  keepalive?: boolean
}

async function request<T>(path: string, { method = 'GET', body, token, query, signal, keepalive }: RequestOptions = {}): Promise<T> {
  const base = apiBaseUrl()
  if (!base) throw new ApiError('VITE_API_URL орнотулган эмес.', 0, CONFIG_ERROR)
  const url = new URL(`${base}${API_PREFIX}${path}`)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== '') url.searchParams.set(key, String(value))
  }
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers['X-Attempt-Token'] = token

  let response: Response
  try {
    const init: RequestInit = { method, headers, signal, keepalive }
    if (method !== 'GET' && body !== undefined) init.body = JSON.stringify(body)
    response = await fetch(url, init)
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError('Сервер менен байланыш жок.', 0, NETWORK_ERROR)
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = (data && typeof data.detail === 'string' && data.detail) || 'Ката кетти. Кайра аракет кылыңыз.'
    throw new ApiError(message, response.status, (data && data.code) || 'error')
  }
  return data as T
}

export const apiClient = {
  get: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) => request<T>(path, options),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'POST', body: body ?? {} }),
  put: <T>(path: string, body: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'PUT', body }),
  patch: <T>(path: string, body: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
}

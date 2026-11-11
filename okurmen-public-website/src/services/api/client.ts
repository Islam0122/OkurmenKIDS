/**
 * The only place that talks to the network. Base URL from VITE_API_URL —
 * the existing Django LMS. Only public, unauthenticated endpoints
 * (/api/v1/public/...) are ever called: no tokens, no cookies.
 */
import axios, { AxiosError } from 'axios'

import { env } from '@/app/config/env'
import type { Lang } from '@/types/api'

export const api = axios.create({
  baseURL: `${env.apiUrl}/api/v1/public`,
  timeout: 15000,
  withCredentials: false,
  headers: { Accept: 'application/json' },
})

let currentLang: Lang = 'ru'

/** Called by the i18n provider: every request asks for the visitor's language. */
export function setApiLanguage(lang: Lang) {
  currentLang = lang
}

api.interceptors.request.use((config) => {
  config.headers.set('Accept-Language', currentLang)
  if ((config.method ?? 'get') === 'get') {
    config.params = { lang: currentLang, ...(config.params ?? {}) }
  }
  return config
})

export type ApiErrorKind = 'network' | 'not_found' | 'validation' | 'rate_limited' | 'conflict' | 'server' | 'config'

export class ApiError extends Error {
  kind: ApiErrorKind
  status: number
  /** Field errors from DRF: { phone: ["…"] } */
  fields: Record<string, string[]>

  constructor(kind: ApiErrorKind, status: number, message: string, fields: Record<string, string[]> = {}) {
    super(message)
    this.kind = kind
    this.status = status
    this.fields = fields
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  if (!env.apiUrl) return new ApiError('config', 0, 'VITE_API_URL is not set')
  const err = error as AxiosError<Record<string, unknown>>
  const status = err.response?.status ?? 0
  const data = err.response?.data ?? {}
  const detail = typeof data.detail === 'string' ? data.detail : err.message
  if (!err.response) return new ApiError('network', 0, detail)
  if (status === 404) return new ApiError('not_found', status, detail)
  if (status === 429) return new ApiError('rate_limited', status, detail)
  if (status === 409) return new ApiError('conflict', status, detail)
  if (status === 400) {
    const fields: Record<string, string[]> = {}
    for (const [key, value] of Object.entries(data)) {
      fields[key] = Array.isArray(value) ? value.map(String) : [String(value)]
    }
    return new ApiError('validation', status, detail, fields)
  }
  return new ApiError('server', status, detail)
}

export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  try {
    const { data } = await api.get<T>(url, { params: clean(params) })
    return data
  } catch (error) {
    throw toApiError(error)
  }
}

export async function post<T>(url: string, body: unknown): Promise<T> {
  try {
    const { data } = await api.post<T>(url, body)
    return data
  } catch (error) {
    throw toApiError(error)
  }
}

function clean(params?: Record<string, unknown>) {
  if (!params) return undefined
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== '' && v !== null && v !== 'all'))
}

import { AxiosError } from 'axios'

import type { ApiErrorBody } from '@/types/common'

const DEFAULT_MESSAGE = 'Что-то пошло не так. Попробуйте ещё раз.'

/** Turns a DRF error response (`{detail: [...]}`, `{field: [...]}`, or a plain string) into one readable line. */
export function extractErrorMessage(error: unknown, fallback: string = DEFAULT_MESSAGE): string {
  if (!(error instanceof AxiosError)) {
    return fallback
  }

  const body = error.response?.data as ApiErrorBody | undefined
  if (!body) {
    return error.message || fallback
  }

  if (typeof body === 'string') {
    return body
  }

  if (Array.isArray(body)) {
    return body.join(' ')
  }

  if ('detail' in body && body.detail) {
    return Array.isArray(body.detail) ? body.detail.join(' ') : String(body.detail)
  }

  const messages = Object.values(body).flatMap((value) => (Array.isArray(value) ? value : [String(value)]))
  return messages.length > 0 ? messages.join(' ') : fallback
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof AxiosError && error.response?.status === 401
}

export function isForbidden(error: unknown): boolean {
  return error instanceof AxiosError && error.response?.status === 403
}

export function isNotFound(error: unknown): boolean {
  return error instanceof AxiosError && error.response?.status === 404
}

/** True for a request that never reached the backend (offline, DNS, CORS) or that the backend itself failed to handle (5xx) — as opposed to a normal 4xx the API answered correctly. Used to tell "your session is invalid" apart from "we couldn't even ask the server". */
export function isNetworkOrServerError(error: unknown): boolean {
  if (!(error instanceof AxiosError)) return false
  if (!error.response) return true
  return error.response.status >= 500
}

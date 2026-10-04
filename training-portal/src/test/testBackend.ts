import { vi } from 'vitest'

/*
 * Test-only HTTP stub: routes fetch() calls of the API client to handlers,
 * so component tests exercise the real API layer. Never imported by the app.
 */
export type Handler = (init: { method: string; body: unknown; headers: Record<string, string>; url: URL }) => {
  status?: number
  body: unknown
}

export function routeFetch(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown; headers: Record<string, string> }[] = []
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input))
    const method = (init?.method ?? 'GET').toUpperCase()
    const headers = (init?.headers ?? {}) as Record<string, string>
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    const path = url.pathname.replace('/api/v1/training', '')
    calls.push({ method, path, body, headers })
    const handler = routes[`${method} ${path}`]
    if (!handler) return new Response(JSON.stringify({ detail: 'not found', code: 'not_found' }), { status: 404 })
    const { status = 200, body: payload } = handler({ method, body, headers, url })
    return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
  })
  return { calls, spy }
}

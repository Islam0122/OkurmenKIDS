import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '@/api/client'

export interface AsyncState<T> {
  data: T | undefined
  loading: boolean
  error: ApiError | null
  reload: () => void
}

/** Loads data from the API; `deps` change → reload. */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [state, setState] = useState<{ data: T | undefined; loading: boolean; error: ApiError | null }>({
    data: undefined, loading: true, error: null,
  })
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    load().then(
      (data) => { if (alive) setState({ data, loading: false, error: null }) },
      (error) => {
        if (!alive) return
        const apiError = error instanceof ApiError ? error : new ApiError(String(error?.message ?? error), 0)
        setState({ data: undefined, loading: false, error: apiError })
      },
    )
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])
  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { ...state, reload }
}

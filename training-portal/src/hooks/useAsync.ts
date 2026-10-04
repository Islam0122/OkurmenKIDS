import { useEffect, useState } from 'react'

/** Loads data from a service (static today, API later). */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[] = []): { data: T | undefined; loading: boolean } {
  const [state, setState] = useState<{ data: T | undefined; loading: boolean }>({ data: undefined, loading: true })
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true }))
    load().then((data) => { if (alive) setState({ data, loading: false }) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}

import { useEffect, useRef, useState } from 'react'

/** Seconds left until `deadline` (epoch ms); calls onExpire once at zero. */
export function useTimer(deadline: number | null, onExpire?: () => void): number | null {
  const [now, setNow] = useState(() => Date.now())
  const expired = useRef(false)
  const callback = useRef(onExpire)
  callback.current = onExpire

  useEffect(() => {
    expired.current = false
    if (deadline === null) return
    const id = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [deadline])

  const left = deadline === null ? null : Math.max(0, Math.ceil((deadline - now) / 1000))
  useEffect(() => {
    if (left === 0 && !expired.current) {
      expired.current = true
      callback.current?.()
    }
  }, [left])
  return left
}

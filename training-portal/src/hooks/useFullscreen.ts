import { useCallback, useEffect, useState } from 'react'

/** The real Browser Fullscreen API (never a stretched <div>). */
export function fullscreenSupported(): boolean {
  return typeof document !== 'undefined' && Boolean(document.documentElement.requestFullscreen) && document.fullscreenEnabled !== false
}

/** Must be called from a user gesture (click / submit) — browsers refuse otherwise. */
export function requestFullscreen(): void {
  if (!fullscreenSupported() || document.fullscreenElement) return
  document.documentElement.requestFullscreen().catch(() => { /* refused: the lock overlay asks again */ })
}

export function exitFullscreen(): void {
  if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {})
}

export function useFullscreen() {
  const [isFullscreen, setIsFullscreen] = useState(() => typeof document !== 'undefined' && Boolean(document.fullscreenElement))
  useEffect(() => {
    const sync = () => setIsFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])
  const request = useCallback(() => requestFullscreen(), [])
  return { isFullscreen, supported: fullscreenSupported(), request }
}

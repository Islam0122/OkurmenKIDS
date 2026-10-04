import { useEffect, useRef, useState } from 'react'

import type { SecuritySettings } from '@/types'

import { exitFullscreen, fullscreenSupported, useFullscreen } from './useFullscreen'

/*
 * Exam Mode restrictions — active only while a training / exam attempt is
 * running inside ExamLayout; unmounting (or `active` = false) removes them.
 *
 * Prevent where possible, detect, log, notify: a web page can't close other
 * tabs, block a second device or DevTools. So every attempt is reported to
 * the backend (onEvent), which counts it and may end the attempt; teachers
 * see it all in monitoring.
 */
export type GuardEvent =
  | 'TAB_SWITCH' | 'TAB_RETURN' | 'FULLSCREEN_ENTER' | 'FULLSCREEN_EXIT'
  | 'COPY_ATTEMPT' | 'PASTE_ATTEMPT' | 'CUT_ATTEMPT' | 'CONTEXT_MENU_ATTEMPT' | 'PAGE_LEAVE'

export type BlockedAction = 'copy' | 'paste' | 'cut' | 'context'

interface GuardOptions {
  active: boolean
  security: SecuritySettings
  onEvent: (type: GuardEvent, beacon?: boolean) => void
  onBlocked?: (action: BlockedAction) => void
}

const THROTTLE_MS = 1500

function inAnswerField(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest('textarea, input'))
}

export function useExamGuard({ active, security, onEvent, onBlocked }: GuardOptions) {
  const { isFullscreen, request } = useFullscreen()
  const [leftPage, setLeftPage] = useState(false)
  const handlers = useRef({ onEvent, onBlocked })
  handlers.current = { onEvent, onBlocked }

  useEffect(() => {
    if (!active) return
    const last: Record<string, number> = {}
    const send = (type: GuardEvent, beacon = false) => {
      const now = Date.now()
      if (!beacon && last[type] && now - last[type] < THROTTLE_MS) return
      last[type] = now
      handlers.current.onEvent(type, beacon)
    }
    const block = (event: Event, type: GuardEvent, action: BlockedAction) => {
      event.preventDefault()
      handlers.current.onBlocked?.(action)
      send(type)
    }

    const onVisibility = () => {
      if (!security.track_tab_switches) return
      if (document.visibilityState === 'hidden') send('TAB_SWITCH')
      else { send('TAB_RETURN'); setLeftPage(true) }
    }
    const onFullscreen = () => send(document.fullscreenElement ? 'FULLSCREEN_ENTER' : 'FULLSCREEN_EXIT')
    const onCopy = (e: ClipboardEvent) => security.block_copy_paste && block(e, 'COPY_ATTEMPT', 'copy')
    const onCut = (e: ClipboardEvent) => security.block_copy_paste && block(e, 'CUT_ATTEMPT', 'cut')
    const onPaste = (e: ClipboardEvent) => security.block_copy_paste && block(e, 'PASTE_ATTEMPT', 'paste')
    const onDrop = (e: DragEvent) => security.block_copy_paste && block(e, 'PASTE_ATTEMPT', 'paste')
    const onContext = (e: MouseEvent) => security.block_copy_paste && block(e, 'CONTEXT_MENU_ATTEMPT', 'context')
    const onSelectStart = (e: Event) => { if (security.block_copy_paste && !inAnswerField(e.target)) e.preventDefault() }
    const onBeforeUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    const onPageHide = () => send('PAGE_LEAVE', true)

    document.addEventListener('visibilitychange', onVisibility)
    document.addEventListener('fullscreenchange', onFullscreen)
    document.addEventListener('copy', onCopy, true)
    document.addEventListener('cut', onCut, true)
    document.addEventListener('paste', onPaste, true)
    document.addEventListener('drop', onDrop, true)
    document.addEventListener('contextmenu', onContext, true)
    document.addEventListener('selectstart', onSelectStart, true)
    window.addEventListener('beforeunload', onBeforeUnload)
    window.addEventListener('pagehide', onPageHide)
    document.body.classList.toggle('exam-protected', security.block_copy_paste)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      document.removeEventListener('fullscreenchange', onFullscreen)
      document.removeEventListener('copy', onCopy, true)
      document.removeEventListener('cut', onCut, true)
      document.removeEventListener('paste', onPaste, true)
      document.removeEventListener('drop', onDrop, true)
      document.removeEventListener('contextmenu', onContext, true)
      document.removeEventListener('selectstart', onSelectStart, true)
      window.removeEventListener('beforeunload', onBeforeUnload)
      window.removeEventListener('pagehide', onPageHide)
      document.body.classList.remove('exam-protected')
      exitFullscreen()
    }
  }, [active, security.track_tab_switches, security.block_copy_paste])

  return {
    isFullscreen,
    /** require_fullscreen and not in fullscreen → the test is covered by the lock overlay */
    locked: active && security.require_fullscreen && fullscreenSupported() && !isFullscreen,
    requestFullscreen: request,
    leftPage,
    dismissLeftPage: () => setLeftPage(false),
  }
}

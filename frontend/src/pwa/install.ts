import { getPwaState, markInstalled, setPwaState } from './store'

export type InstallOutcome = 'accepted' | 'dismissed' | 'unavailable'

/** Shows the browser's native install dialog. Must run inside a click handler. */
export async function promptInstall(): Promise<InstallOutcome> {
  const event = getPwaState().promptEvent
  if (!event) return 'unavailable'
  // A deferred prompt can be used only once.
  setPwaState({ promptEvent: null })
  try {
    await event.prompt()
    const { outcome } = await event.userChoice
    if (outcome === 'accepted') markInstalled()
    return outcome
  } catch {
    return 'unavailable'
  }
}

const PROMPT_KEY = 'okurmen.pwa.installPrompt'
/** After a «Не сейчас», stay quiet this long… */
const SNOOZE_MS = 21 * 24 * 60 * 60 * 1000
/** …and after this many, never offer on our own again (Settings still works). */
const MAX_DISMISSALS = 3

interface PromptMemory {
  dismissedAt: number
  count: number
}

function readMemory(): PromptMemory {
  try {
    const raw = localStorage.getItem(PROMPT_KEY)
    const parsed = raw ? (JSON.parse(raw) as Partial<PromptMemory>) : {}
    return { dismissedAt: Number(parsed.dismissedAt) || 0, count: Number(parsed.count) || 0 }
  } catch {
    return { dismissedAt: 0, count: 0 }
  }
}

export function canAutoPrompt(now: number = Date.now()): boolean {
  const memory = readMemory()
  return memory.count < MAX_DISMISSALS && now - memory.dismissedAt > SNOOZE_MS
}

export function rememberDismissal(now: number = Date.now()): void {
  const memory = readMemory()
  try {
    localStorage.setItem(PROMPT_KEY, JSON.stringify({ dismissedAt: now, count: memory.count + 1 }))
  } catch {
    /* storage unavailable: the prompt simply may show again next session */
  }
}

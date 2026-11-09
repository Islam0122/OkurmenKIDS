import { useSyncExternalStore } from 'react'

import { installMethod, isStandalone, type InstallMethod } from './platform'

/** The `beforeinstallprompt` event (Chromium only, not in lib.dom). */
export interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

export interface PwaState {
  /** Running as the installed app right now. */
  standalone: boolean
  /** Installed from this browser during this or an earlier visit. */
  installedHere: boolean
  method: InstallMethod
  /** The deferred Chromium prompt, while the browser offers installation. */
  promptEvent: BeforeInstallPromptEvent | null
  online: boolean
  /** A new version is installed and waiting for the user to switch. */
  updateReady: boolean
  /** The «Приложение» dialog (install + push settings) is open. */
  settingsOpen: boolean
}

const INSTALLED_KEY = 'okurmen.pwa.installed'

function readInstalledFlag(): boolean {
  try {
    return localStorage.getItem(INSTALLED_KEY) === '1'
  } catch {
    return false
  }
}

let state: PwaState = {
  standalone: isStandalone(),
  installedHere: readInstalledFlag(),
  method: installMethod(),
  promptEvent: null,
  online: typeof navigator === 'undefined' ? true : navigator.onLine,
  updateReady: false,
  settingsOpen: false,
}

const listeners = new Set<() => void>()

export function getPwaState(): PwaState {
  return state
}

export function setPwaState(patch: Partial<PwaState>): void {
  state = { ...state, ...patch }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function usePwaState(): PwaState {
  return useSyncExternalStore(subscribe, getPwaState, getPwaState)
}

export function markInstalled(): void {
  try {
    localStorage.setItem(INSTALLED_KEY, '1')
  } catch {
    /* private mode: the flag is only a hint */
  }
  setPwaState({ installedHere: true, promptEvent: null })
}

export function openAppSettings(): void {
  setPwaState({ settingsOpen: true })
}

export function closeAppSettings(): void {
  setPwaState({ settingsOpen: false })
}

/** Where installation stands, as the UI shows it. */
export type InstallAvailability = 'installed' | 'available' | 'manual' | 'in-app' | 'unsupported'

export function installAvailability(s: PwaState): InstallAvailability {
  if (s.standalone) return 'installed'
  if (s.promptEvent) return 'available'
  if (s.method === 'ios' || s.method === 'macos-safari') return 'manual'
  if (s.method === 'in-app') return 'in-app'
  if (s.method === 'prompt') {
    // Chromium without a pending prompt: installed from here earlier, or the
    // browser has not offered it yet — its menu's «Установить» still works.
    return s.installedHere ? 'installed' : 'manual'
  }
  return 'unsupported'
}

import { apiClient, refreshClient } from '@/api/client'

import { supportsPush } from './platform'
import { SW_ENABLED } from './register'

/** Backend: apps.push (/api/v1/push/…). The VAPID private key lives only on
 * the server; the browser gets the public key from /push/config/. */

export interface PushConfig {
  enabled: boolean
  public_key: string
}

export interface PushPreferences {
  tasks: boolean
  reports: boolean
  alerts: boolean
}

export const pushApi = {
  config: () => apiClient.get<PushConfig>('/push/config/').then((r) => r.data),
  preferences: () => apiClient.get<PushPreferences>('/push/preferences/').then((r) => r.data),
  updatePreferences: (patch: Partial<PushPreferences>) =>
    apiClient.patch<PushPreferences>('/push/preferences/', patch).then((r) => r.data),
  sendTest: () => apiClient.post<{ delivered: number }>('/push/test/').then((r) => r.data),
}

/** «The user turned push on for this device» — lets the app silently renew a
 * subscription the browser dropped (permission is already granted then). */
const ENABLED_KEY = 'okurmen.push.enabled'

function setEnabledFlag(on: boolean): void {
  try {
    if (on) localStorage.setItem(ENABLED_KEY, '1')
    else localStorage.removeItem(ENABLED_KEY)
  } catch {
    /* storage unavailable */
  }
}

function enabledFlag(): boolean {
  try {
    return localStorage.getItem(ENABLED_KEY) === '1'
  } catch {
    return false
  }
}

/** Push works only with the production service worker and a secure origin. */
export function pushAvailableHere(): boolean {
  return SW_ENABLED && supportsPush()
}

export function notificationPermission(): NotificationPermission | 'unsupported' {
  return typeof Notification === 'undefined' ? 'unsupported' : Notification.permission
}

function base64UrlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const padded = (value + '='.repeat((4 - (value.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(padded)
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i)
  return bytes
}

async function readyRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (!pushAvailableHere()) return null
  return navigator.serviceWorker.getRegistration('/').then((reg) => reg ?? null)
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await readyRegistration()
  return registration ? registration.pushManager.getSubscription() : null
}

async function sendSubscription(subscription: PushSubscription): Promise<void> {
  const json = subscription.toJSON()
  await apiClient.post('/push/subscriptions/', {
    endpoint: json.endpoint,
    keys: json.keys,
    user_agent: navigator.userAgent.slice(0, 255),
  })
}

/** Ask for permission (only ever from a click) and register this device. */
export async function enablePush(publicKey: string): Promise<'enabled' | 'denied' | 'unsupported'> {
  if (!pushAvailableHere()) return 'unsupported'
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return 'denied'
  const registration = await navigator.serviceWorker.ready
  let subscription = await registration.pushManager.getSubscription()
  const key = base64UrlToBytes(publicKey)
  if (subscription) {
    // A subscription made with another VAPID key (keys rotated) cannot be reused.
    const current = subscription.options.applicationServerKey
    const same = current && new Uint8Array(current).every((byte, i) => byte === key[i]) && current.byteLength === key.length
    if (!same) {
      await subscription.unsubscribe()
      subscription = null
    }
  }
  subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })
  try {
    await sendSubscription(subscription)
  } catch (error) {
    // The server refused: do not leave a browser subscription nobody uses.
    await subscription.unsubscribe().catch(() => {})
    throw error
  }
  setEnabledFlag(true)
  return 'enabled'
}

export async function disablePush(): Promise<void> {
  setEnabledFlag(false)
  const subscription = await currentSubscription()
  if (!subscription) return
  const { endpoint } = subscription
  await subscription.unsubscribe()
  await apiClient.post('/push/subscriptions/unsubscribe/', { endpoint }).catch(() => {})
}

/** On start (signed in): re-send the existing subscription so the server
 * row is current — after `pushsubscriptionchange`, key rotation on the
 * browser side, or a server-side cleanup. Idempotent; never prompts. */
export async function syncPushSubscription(): Promise<void> {
  if (!pushAvailableHere() || notificationPermission() !== 'granted') return
  try {
    const subscription = await currentSubscription()
    if (subscription) {
      await sendSubscription(subscription)
    } else if (enabledFlag()) {
      // Dropped by the browser (pushsubscriptionchange): renew silently —
      // permission is already granted, so nothing is asked.
      const config = await pushApi.config()
      if (config.enabled && config.public_key) await enablePush(config.public_key)
    }
  } catch {
    /* offline or push disabled on the server: try again next start */
  }
}

/** Logout: this device stops receiving the previous user's notifications.
 * The access token is passed in because the app clears storage right after. */
export async function unsubscribeOnLogout(accessToken: string | null): Promise<void> {
  setEnabledFlag(false)
  try {
    const subscription = await currentSubscription()
    if (!subscription) return
    const { endpoint } = subscription
    await subscription.unsubscribe()
    if (accessToken) {
      // The bare client: a 401 here must not re-enter the session-expired → logout path.
      await refreshClient
        .post('/push/subscriptions/unsubscribe/', { endpoint }, { headers: { Authorization: `Bearer ${accessToken}` } })
        .catch(() => {})
    }
  } catch {
    /* best effort: the server prunes dead endpoints on the next send (410) */
  }
}

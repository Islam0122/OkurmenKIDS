/** Разбор содержимого QR-кода офиса: `https://<LMS>/attendance/scan?office=<код>`.
 * Здесь только проверка формы ссылки; существует ли офис и активен ли он,
 * решает backend (`GET /staff-attendance/me/locations/<код>/`). */

export const OFFICE_CODE_RE = /^[A-Za-z0-9_-]{6,64}$/

export type ParsedQr = { ok: true; code: string } | { ok: false; reason: string }

export function parseOfficeQr(text: string, currentOrigin: string = window.location.origin): ParsedQr {
  let url: URL
  try {
    url = new URL(text.trim())
  } catch {
    return { ok: false, reason: 'Это не QR-код офиса OkurmenKIDS: в нём нет ссылки.' }
  }
  const sameOrigin = url.origin === currentOrigin
  if (url.protocol !== 'https:' && !sameOrigin) {
    return { ok: false, reason: 'QR-код содержит небезопасную ссылку (не HTTPS).' }
  }
  if (!url.pathname.replace(/\/+$/, '').endsWith('/attendance/scan')) {
    return { ok: false, reason: 'Это не QR-код отметки прихода и ухода OkurmenKIDS.' }
  }
  const code = url.searchParams.get('office') ?? ''
  if (!OFFICE_CODE_RE.test(code)) {
    return { ok: false, reason: 'В QR-коде нет корректного идентификатора офиса.' }
  }
  return { ok: true, code }
}

/** Ключ идемпотентности: повтор того же запроса (например, после обрыва
 * сети) не создаёт вторую отметку. */
export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

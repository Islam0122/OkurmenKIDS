import { API_BASE_URL } from '@/api/client'

/**
 * Turns a Django `ImageField` URL into one the browser can load.
 *
 * The API returns it either absolute (`https://<backend>/media/teachers/x.png`,
 * when the serializer had the request) or root-relative (`/media/teachers/x.png`,
 * e.g. `GET /trainers/me/`). In production the SPA (Vercel) and the API
 * (Railway) are different origins, so a root-relative path would be fetched
 * from the SPA's own domain — where the `index.html` rewrite answers instead
 * of the image. Resolve it against the API's origin instead. In dev
 * `VITE_API_BASE_URL` is unset, the base stays same-origin and the Vite proxy
 * serves `/media`.
 */
export function resolveMediaUrl(
  url: string | null | undefined,
  apiBaseUrl: string = API_BASE_URL,
): string | null {
  if (!url) return null
  // Already absolute (http:, https:, data:, blob:) or protocol-relative.
  if (!url.startsWith('/') || url.startsWith('//')) return url
  const apiOrigin = new URL(apiBaseUrl, window.location.origin).origin
  return new URL(url, apiOrigin).href
}

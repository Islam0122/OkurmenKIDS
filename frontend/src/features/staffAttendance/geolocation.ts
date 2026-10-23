/** Геолокация запрашивается непосредственно перед каждой отметкой (без
 * кэша браузера) и никуда, кроме запроса отметки, не передаётся. Фоновое
 * отслеживание не используется. Координаты браузера можно подменить —
 * поэтому сервер дополнительно проверяет QR-код офиса, точность и
 * (если включено) офисную сеть. */

export interface FreshPosition {
  latitude: number
  longitude: number
  accuracy: number
}

export type GeolocationFailureKind = 'unsupported' | 'insecure' | 'denied' | 'unavailable' | 'timeout'

export class GeolocationFailure extends Error {
  readonly kind: GeolocationFailureKind

  constructor(message: string, kind: GeolocationFailureKind) {
    super(message)
    this.kind = kind
  }
}

export function getFreshPosition(timeoutMs = 20_000): Promise<FreshPosition> {
  if (typeof window !== 'undefined' && window.isSecureContext === false) {
    return Promise.reject(new GeolocationFailure('Геолокация работает только по HTTPS. Откройте LMS по защищённой ссылке.', 'insecure'))
  }
  if (!('geolocation' in navigator)) {
    return Promise.reject(new GeolocationFailure('Этот браузер не поддерживает геолокацию.', 'unsupported'))
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy }),
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          reject(new GeolocationFailure('Доступ к геолокации запрещён. Разрешите его в настройках браузера для этого сайта и повторите попытку.', 'denied'))
        } else if (err.code === err.TIMEOUT) {
          reject(new GeolocationFailure('Не удалось определить местоположение вовремя. Выйдите ближе к окну и повторите попытку.', 'timeout'))
        } else {
          reject(new GeolocationFailure('Местоположение недоступно. Включите GPS / службы геолокации и повторите попытку.', 'unavailable'))
        }
      },
      { enableHighAccuracy: true, maximumAge: 0, timeout: timeoutMs },
    )
  })
}

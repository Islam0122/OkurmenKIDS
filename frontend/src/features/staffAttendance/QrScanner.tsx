import { useCallback, useEffect, useRef, useState } from 'react'
import { CameraOff, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/Button'

/** Минимальное описание BarcodeDetector (Chrome/Android, Edge, новые Safari) —
 * в lib.dom его пока нет. Где его нет, кадры декодирует jsQR. */
interface DetectedBarcode {
  rawValue: string
}
interface BarcodeDetectorLike {
  detect(source: CanvasImageSource): Promise<DetectedBarcode[]>
}
interface BarcodeDetectorCtor {
  new (options: { formats: string[] }): BarcodeDetectorLike
  getSupportedFormats?: () => Promise<string[]>
}

type Decoder = (video: HTMLVideoElement, canvas: HTMLCanvasElement) => Promise<string | null>

async function createDecoder(): Promise<Decoder> {
  const Native = (window as unknown as { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector
  if (Native) {
    try {
      const formats = (await Native.getSupportedFormats?.()) ?? ['qr_code']
      if (formats.includes('qr_code')) {
        const detector = new Native({ formats: ['qr_code'] })
        return async (video) => (await detector.detect(video))[0]?.rawValue ?? null
      }
    } catch {
      // упадём на jsQR
    }
  }
  const { default: jsQR } = await import('jsqr')
  return async (video, canvas) => {
    const width = video.videoWidth
    const height = video.videoHeight
    if (!width || !height) return null
    // Уменьшаем кадр: jsQR быстрее, а QR на стене остаётся читаемым.
    const scale = Math.min(1, 720 / Math.max(width, height))
    canvas.width = Math.round(width * scale)
    canvas.height = Math.round(height * scale)
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return null
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    const image = ctx.getImageData(0, 0, canvas.width, canvas.height)
    return jsQR(image.data, image.width, image.height, { inversionAttempts: 'dontInvert' })?.data ?? null
  }
}

function cameraErrorMessage(error: unknown): string {
  const name = (error as { name?: string } | null)?.name
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Доступ к камере запрещён. Разрешите камеру для этого сайта в настройках браузера и нажмите «Повторить».'
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'Камера не найдена на этом устройстве.'
  if (name === 'NotReadableError') return 'Камера занята другим приложением. Закройте его и нажмите «Повторить».'
  return 'Не удалось запустить камеру. Нажмите «Повторить».'
}

export interface QrScannerProps {
  /** Вызывается один раз на каждый распознанный код. */
  onResult: (text: string) => void
  /** Пока false — камера на паузе (например, идёт проверка кода). */
  active?: boolean
}

/** Камера + распознавание QR. Камера включается только после явного
 * действия пользователя (кнопка «Сканировать QR») и выключается, как только
 * компонент скрыт. Работает лишь в защищённом контексте (HTTPS). */
export function QrScanner({ onResult, active = true }: QrScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const onResultRef = useRef(onResult)
  const activeRef = useRef(active)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    onResultRef.current = onResult
    activeRef.current = active
  }, [onResult, active])

  useEffect(() => {
    let stream: MediaStream | null = null
    let frame = 0
    let cancelled = false
    let lastText = ''
    let lastAt = 0

    async function start() {
      setError(null)
      setStarting(true)
      if (window.isSecureContext === false) {
        setError('Камера доступна только по HTTPS. Откройте LMS по защищённой ссылке.')
        setStarting(false)
        return
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('Этот браузер не даёт доступ к камере. Откройте LMS в Chrome или Safari.')
        setStarting(false)
        return
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
        if (cancelled) return
        const video = videoRef.current
        if (!video) return
        video.srcObject = stream
        await video.play()
        const decode = await createDecoder()
        setStarting(false)
        let busy = false
        let lastScan = 0
        const tick = (now: number) => {
          if (cancelled) return
          frame = requestAnimationFrame(tick)
          if (busy || !activeRef.current || now - lastScan < 200 || !videoRef.current || !canvasRef.current) return
          lastScan = now
          busy = true
          decode(videoRef.current, canvasRef.current)
            .then((text) => {
              // Тот же код не сообщаем повторно чаще раза в 3 секунды.
              if (text && !cancelled && (text !== lastText || now - lastAt > 3000)) {
                lastText = text
                lastAt = now
                onResultRef.current(text)
              }
            })
            .catch(() => undefined)
            .finally(() => {
              busy = false
            })
        }
        frame = requestAnimationFrame(tick)
      } catch (err) {
        if (!cancelled) {
          setError(cameraErrorMessage(err))
          setStarting(false)
        }
      }
    }

    void start()
    return () => {
      cancelled = true
      cancelAnimationFrame(frame)
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [attempt])

  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-2xl border border-border bg-surface-muted px-6 py-10 text-center">
        <span className="flex size-14 items-center justify-center rounded-full bg-danger-soft text-danger">
          <CameraOff className="size-7" aria-hidden />
        </span>
        <p className="max-w-sm text-sm text-ink" role="alert">{error}</p>
        <Button variant="secondary" leftIcon={<RefreshCw className="size-4" aria-hidden />} onClick={retry}>
          Повторить
        </Button>
      </div>
    )
  }

  return (
    <div className="relative overflow-hidden rounded-2xl bg-ink">
      <video ref={videoRef} className="aspect-square w-full object-cover sm:aspect-[4/3]" playsInline muted aria-label="Камера для сканирования QR-кода" />
      <canvas ref={canvasRef} className="hidden" aria-hidden />
      {/* Рамка прицела */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="size-3/5 max-h-72 max-w-72 rounded-3xl border-4 border-white/90 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
      </div>
      <p className="absolute inset-x-0 bottom-3 text-center text-sm font-medium text-white drop-shadow">
        {starting ? 'Запускаем камеру…' : 'Наведите камеру на QR-код офиса'}
      </p>
    </div>
  )
}

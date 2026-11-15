import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, CheckCircle2, Copy, Download, FileCode2, Loader2, Printer, ShieldAlert, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'
import { homeFor } from '@/lib/roles'
import { cn } from '@/utils/cn'

import { useInstallLang, type InstallText } from './i18n'
import { decodeQr, installUrl, paintQr, qrFor, qrSvg } from './qr'
import { QrCode } from './QrCode'

/**
 * /install/qr — the official «install the app» QR code for staff (admin,
 * director, operations director, assistants). It always encodes the public
 * `<site>/install` address. Before offering the logo version the page paints
 * it and reads it back with a QR decoder at full and at small (print-sized)
 * resolution; if either fails, the plain code is used instead.
 *
 * Exports: PNG 2048 px, SVG (vector, logo embedded), and an A4 poster printed
 * by the browser (or saved as PDF from the print dialog).
 */

const RING = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600'
const LOGO_SRC = '/icons/icon-512.png'
const PNG_SIZE = 2048
type Check = 'checking' | 'verified' | 'fallback' | 'failed'

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error(`image ${src}`))
    // Never hang the self-check on an image that does not arrive.
    window.setTimeout(() => reject(new Error(`image ${src}: timeout`)), 8000)
    image.src = src
  })
}

function canvasFor(value: string, withLogo: boolean, logo: HTMLImageElement | null, pixels: number): HTMLCanvasElement | null {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = pixels
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  paintQr(ctx, qrFor(value, { withLogo }), { withLogo, logo, pixels })
  return canvas
}

async function readsBack(value: string, withLogo: boolean, logo: HTMLImageElement | null): Promise<boolean> {
  // Full resolution, and about what a 4 cm print looks like to a phone camera.
  for (const pixels of [1024, 220]) {
    const canvas = canvasFor(value, withLogo, logo, pixels)
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return false
    const { data } = ctx.getImageData(0, 0, pixels, pixels)
    if ((await decodeQr(data, pixels, pixels)) !== value) return false
  }
  return true
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function dataUrl(src: string): Promise<string> {
  const blob = await (await fetch(src)).blob()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

export function InstallQrPage() {
  const { lang, t, setLang } = useInstallLang()
  const { user } = useAuth()
  const url = useMemo(() => installUrl(), [])
  const [wantLogo, setWantLogo] = useState(true)
  const [check, setCheck] = useState<Check>('checking')
  const [logo, setLogo] = useState<HTMLImageElement | null>(null)
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState<'png' | 'svg' | null>(null)
  const withLogo = wantLogo && check !== 'fallback' && check !== 'failed'

  useEffect(() => {
    document.title = `${t.qr.pageTitle} — OkurmenKids`
  }, [t.qr.pageTitle])

  // Self-check: paint the code and read it back before anyone prints it.
  useEffect(() => {
    let cancelled = false
    setCheck('checking')
    void (async () => {
      try {
        if (!document.createElement('canvas').getContext('2d')) {
          setCheck('failed')
          return
        }
        const image = wantLogo ? await loadImage(LOGO_SRC).catch(() => null) : null
        if (cancelled) return
        setLogo(image)
        if (wantLogo && image && (await readsBack(url, true, image))) {
          if (!cancelled) setCheck('verified')
          return
        }
        const plain = await readsBack(url, false, null)
        if (cancelled) return
        setCheck(plain ? (wantLogo ? 'fallback' : 'verified') : 'failed')
      } catch {
        if (!cancelled) setCheck('failed')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [url, wantLogo])

  const exportPng = () => {
    setBusy('png')
    const canvas = canvasFor(url, withLogo, logo, PNG_SIZE)
    if (!canvas) {
      setBusy(null)
      return
    }
    canvas.toBlob((blob) => {
      if (blob) download(blob, 'okurmenkids-install-qr.png')
      setBusy(null)
    }, 'image/png')
  }

  const exportSvg = async () => {
    setBusy('svg')
    try {
      const href = withLogo ? await dataUrl(LOGO_SRC) : undefined
      const svg = qrSvg(qrFor(url, { withLogo }), { withLogo, logoHref: href, title: t.qr.poster.scan })
      download(new Blob([`<?xml version="1.0" encoding="UTF-8"?>\n${svg}`], { type: 'image/svg+xml' }), 'okurmenkids-install-qr.svg')
    } finally {
      setBusy(null)
    }
  }

  const copy = () => {
    void navigator.clipboard?.writeText(url).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    })
  }

  const back = user ? homeFor(user.role, '/app/dashboard') : '/'
  const exportReady = check === 'verified' || check === 'fallback'

  return (
    <div className="qr-page min-h-dvh bg-zinc-50 text-zinc-900">
      <style>{PRINT_CSS}</style>
      <div className="qr-controls mx-auto max-w-6xl px-4 py-5 sm:px-6 lg:py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link to={back} className={cn('inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-semibold text-zinc-600 hover:text-emerald-700', RING)}>
            <ArrowLeft className="size-4" aria-hidden />
            {t.qr.back}
          </Link>
          <div role="group" aria-label={t.langLabel} className="flex rounded-full border border-zinc-200 bg-white p-0.5 text-xs font-semibold">
            {(['ru', 'kg'] as const).map((id) => (
              <button key={id} type="button" onClick={() => setLang(id)} aria-pressed={lang === id}
                className={cn('rounded-full px-3 py-1.5', RING, lang === id ? 'bg-emerald-600 text-white' : 'text-zinc-600')}>
                {id === 'kg' ? 'KG' : 'RU'}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-6 lg:grid-cols-[380px_1fr]">
          <section className="min-w-0 space-y-4">
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight">{t.qr.pageTitle}</h1>
              <p className="mt-1.5 text-sm leading-relaxed text-zinc-600">{t.qr.lead}</p>
            </div>

            <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{t.qr.url}</div>
              <div className="mt-1.5 flex items-center gap-2">
                <code className="min-w-0 flex-1 break-all rounded-lg bg-zinc-50 px-2.5 py-2 text-[13px] text-zinc-800" data-testid="qr-url">{url}</code>
                <button type="button" onClick={copy} aria-label={t.qr.copy} title={t.qr.copy}
                  className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg border border-zinc-200 text-zinc-600 hover:text-emerald-700', RING)}>
                  {copied ? <CheckCircle2 className="size-4 text-emerald-600" aria-hidden /> : <Copy className="size-4" aria-hidden />}
                </button>
              </div>
              {!url.startsWith('https://') && !/\/\/(localhost|127\.0\.0\.1)/.test(url) && (
                <p className="mt-2 flex items-start gap-1.5 text-xs text-amber-700"><ShieldAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />{t.qr.https}</p>
              )}

              <div className="mt-4 text-xs font-semibold uppercase tracking-wide text-zinc-500">{t.qr.logo}</div>
              <div role="radiogroup" aria-label={t.qr.logo} className="mt-1.5 grid grid-cols-2 gap-1 rounded-xl bg-zinc-100 p-1 text-sm font-semibold">
                {[true, false].map((on) => (
                  <button key={String(on)} type="button" role="radio" aria-checked={wantLogo === on} onClick={() => setWantLogo(on)}
                    className={cn('rounded-lg px-3 py-2 transition', RING, wantLogo === on ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500')}>
                    {on ? t.qr.logoOn : t.qr.logoOff}
                  </button>
                ))}
              </div>

              <CheckNote check={check} t={t} />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button type="button" onClick={exportPng} disabled={!exportReady || busy !== null}
                className={cn('inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-bold text-white shadow hover:bg-emerald-700 disabled:opacity-50', RING)}>
                {busy === 'png' ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Download className="size-4" aria-hidden />}
                {t.qr.png}
              </button>
              <button type="button" onClick={() => void exportSvg()} disabled={!exportReady || busy !== null}
                className={cn('inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm font-bold text-zinc-800 hover:border-emerald-300 disabled:opacity-50', RING)}>
                {busy === 'svg' ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <FileCode2 className="size-4" aria-hidden />}
                {t.qr.svg}
              </button>
              <button type="button" onClick={() => window.print()} disabled={!exportReady}
                className={cn('col-span-2 inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm font-bold text-zinc-800 hover:border-emerald-300 disabled:opacity-50', RING)}>
                <Printer className="size-4" aria-hidden />
                {t.qr.print}
              </button>
            </div>

            <ul className="space-y-1.5 text-sm text-zinc-600">
              {t.qr.tips.map((tip) => <li key={tip} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-emerald-500" />{tip}</li>)}
            </ul>
          </section>

          <section aria-label={t.qr.preview} className="min-w-0">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">{t.qr.preview}</div>
            <SheetPreview>
              <Poster url={url} withLogo={withLogo} t={t} />
            </SheetPreview>
          </section>
        </div>
      </div>
      {/* The printed copy: only this is visible on paper. */}
      <div className="qr-print" aria-hidden>
        <Poster url={url} withLogo={withLogo} t={t} />
      </div>
    </div>
  )
}

function CheckNote({ check, t }: { check: Check; t: InstallText }) {
  const map = {
    checking: { icon: <Loader2 className="size-4 animate-spin" aria-hidden />, text: t.qr.checking, cls: 'text-zinc-500' },
    verified: { icon: <CheckCircle2 className="size-4" aria-hidden />, text: t.qr.verified, cls: 'text-emerald-700' },
    fallback: { icon: <TriangleAlert className="size-4" aria-hidden />, text: t.qr.logoFallback, cls: 'text-amber-700' },
    failed: { icon: <TriangleAlert className="size-4" aria-hidden />, text: t.qr.failed, cls: 'text-rose-700' },
  }[check]
  return (
    <p role="status" data-check={check} className={cn('mt-3 flex items-start gap-1.5 text-sm font-medium', map.cls)}>
      <span className="mt-0.5 shrink-0">{map.icon}</span>
      {map.text}
    </p>
  )
}

/** The A4 sheet scaled to fit its column (the sheet itself is laid out in mm). */
function SheetPreview({ children }: { children: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.5)
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const sheetPx = (210 / 25.4) * 96
    const update = () => setScale(Math.min(1, el.clientWidth / sheetPx))
    update()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const heightPx = (297 / 25.4) * 96 * scale
  return (
    <div ref={box} className="w-full max-w-[640px] overflow-hidden" style={{ height: heightPx }}>
      <div className="origin-top-left overflow-hidden rounded-md shadow-[0_20px_50px_-20px_rgba(0,0,0,0.35)] ring-1 ring-zinc-200" style={{ transform: `scale(${scale})`, width: '210mm', height: '297mm' }}>
        {children}
      </div>
    </div>
  )
}

/** The poster, laid out in millimetres for A4 (bilingual RU / KG). */
export function Poster({ url, withLogo, t }: { url: string; withLogo: boolean; t: InstallText }) {
  const p = t.qr.poster
  return (
    <div className="qr-sheet relative flex flex-col items-center bg-white text-zinc-900" style={{ width: '210mm', height: '297mm', padding: '16mm 18mm 14mm' }}>
      <div className="absolute inset-x-0 top-0 bg-emerald-600" style={{ height: '5mm' }} />
      <div className="flex items-center" style={{ gap: '4mm', marginTop: '4mm' }}>
        <img src="/logo.png" alt="" style={{ height: '16mm' }} />
        <div style={{ fontSize: '9mm', lineHeight: 1 }} className="font-extrabold tracking-tight">
          Okurmen<span className="text-emerald-600">Kids</span> <span className="font-semibold text-zinc-500">LMS</span>
        </div>
      </div>
      <h2 className="text-center font-extrabold tracking-tight" style={{ fontSize: '11mm', lineHeight: 1.1, marginTop: '11mm' }}>{p.scan}</h2>
      <p className="text-center text-zinc-700" style={{ fontSize: '5mm', marginTop: '4mm' }}>{p.ru}</p>
      <p className="text-center text-zinc-700" style={{ fontSize: '5mm', marginTop: '1.5mm' }} lang="ky">{p.kg}</p>

      <div className="rounded-[6mm] border-emerald-600 bg-white" style={{ marginTop: '10mm', padding: '4mm', borderWidth: '1.2mm' }}>
        <QrCode value={url} withLogo={withLogo} logoHref="/icons/icon-512.png" label={p.scan} className="block" />
        <style>{`.qr-sheet [role=img]{width:118mm;height:118mm}`}</style>
      </div>

      <div className="grid w-full grid-cols-3" style={{ gap: '5mm', marginTop: '11mm' }}>
        {p.steps.map((step, i) => (
          <div key={step} className="rounded-[4mm] bg-emerald-50 text-center" style={{ padding: '4mm 3mm' }}>
            <div className="mx-auto flex items-center justify-center rounded-full bg-emerald-600 font-bold text-white" style={{ width: '9mm', height: '9mm', fontSize: '4.5mm' }}>{i + 1}</div>
            <div className="font-semibold text-zinc-900" style={{ fontSize: '4mm', marginTop: '2.5mm', lineHeight: 1.25 }}>{step}</div>
            <div className="text-zinc-600" style={{ fontSize: '3.4mm', marginTop: '1.2mm', lineHeight: 1.25 }} lang="ky">{p.stepsKg[i]}</div>
          </div>
        ))}
      </div>

      <div className="mt-auto text-center">
        <div className="font-mono font-semibold text-zinc-800" style={{ fontSize: '4.2mm' }}>{url.replace(/^https?:\/\//, '')}</div>
        <div className="text-zinc-500" style={{ fontSize: '3.4mm', marginTop: '1.5mm' }}>{p.noStore}</div>
      </div>
    </div>
  )
}

const PRINT_CSS = `
.qr-print { display: none; }
@media print {
  @page { size: A4 portrait; margin: 0; }
  html, body { background: #fff !important; }
  .qr-page { min-height: 0 !important; background: #fff !important; }
  .qr-controls { display: none !important; }
  .qr-print { display: block; }
  .qr-print .qr-sheet { break-inside: avoid; page-break-after: avoid; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body > *:not(#root) { display: none !important; }
}
`

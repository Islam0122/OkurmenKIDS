import qrcode from 'qrcode-generator'

/**
 * The official «install the app» QR code.
 *
 * * Plain byte-mode URL, standard 4-module quiet zone, pure black on white —
 *   what the iPhone and Android camera apps read best.
 * * With the logo: error correction H (≈30 % of the code may be lost) and the
 *   logo covers a centred square of only ~5 % of the modules (≤ 23 % of the
 *   side), far from the three finder patterns. The modules under it are left
 *   light, so the logo sits on clean white.
 * * The logo is only an option: the page decodes the finished PNG itself
 *   (jsQR) and falls back to the plain code if it would not read back.
 */

export type Ecc = 'L' | 'M' | 'Q' | 'H'

export interface QrMatrix {
  /** Modules per side (without the quiet zone). */
  size: number
  isDark: (row: number, col: number) => boolean
  ecc: Ecc
}

export const QUIET_ZONE = 4
/** Share of the side the logo square takes (modules are rounded to an odd count). */
export const LOGO_SHARE = 0.23

export function makeQr(text: string, ecc: Ecc): QrMatrix {
  const qr = qrcode(0, ecc)
  qr.addData(text, 'Byte')
  qr.make()
  const size = qr.getModuleCount()
  return { size, isDark: (row, col) => qr.isDark(row, col), ecc }
}

/** The centred square (in modules) reserved for the logo. */
export function logoBox(size: number): { start: number; span: number } {
  let span = Math.round(size * LOGO_SHARE)
  if (span % 2 !== size % 2) span += 1 // keep it exactly centred
  return { start: (size - span) / 2, span }
}

export interface QrOptions {
  /** Draw the logo in the centre (uses error correction H). */
  withLogo: boolean
}

export function qrFor(text: string, { withLogo }: QrOptions): QrMatrix {
  return makeQr(text, withLogo ? 'H' : 'M')
}

/** Dark modules as rows of [row, col] — the logo square is left light. */
function darkModules(matrix: QrMatrix, withLogo: boolean): (row: number, col: number) => boolean {
  if (!withLogo) return matrix.isDark
  const { start, span } = logoBox(matrix.size)
  return (row, col) =>
    !(row >= start && row < start + span && col >= start && col < start + span) && matrix.isDark(row, col)
}

const DARK = '#000000'
const LIGHT = '#ffffff'

/**
 * A crisp, scalable SVG (one path, runs of modules merged per row). `logoHref`
 * is embedded as-is (a data: URL keeps the file self-contained).
 */
export function qrSvg(matrix: QrMatrix, options: { withLogo: boolean; logoHref?: string; title?: string }): string {
  const dark = darkModules(matrix, options.withLogo)
  const total = matrix.size + QUIET_ZONE * 2
  let path = ''
  for (let row = 0; row < matrix.size; row++) {
    let col = 0
    while (col < matrix.size) {
      if (!dark(row, col)) {
        col++
        continue
      }
      let run = 1
      while (col + run < matrix.size && dark(row, col + run)) run++
      path += `M${col + QUIET_ZONE} ${row + QUIET_ZONE}h${run}v1h-${run}z`
      col += run
    }
  }
  let logo = ''
  if (options.withLogo && options.logoHref) {
    const { start, span } = logoBox(matrix.size)
    const x = start + QUIET_ZONE
    // White plate with a small inset; the logo art sits inside it.
    const inset = span * 0.06
    logo =
      `<rect x="${x}" y="${x}" width="${span}" height="${span}" rx="${span * 0.18}" fill="${LIGHT}"/>` +
      `<image href="${escapeAttr(options.logoHref)}" x="${x + inset}" y="${x + inset}" width="${span - inset * 2}" height="${span - inset * 2}" preserveAspectRatio="xMidYMid meet"/>`
  }
  const title = options.title ? `<title>${escapeText(options.title)}</title>` : ''
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${total} ${total}" shape-rendering="crispEdges" role="img">` +
    title +
    `<rect width="${total}" height="${total}" fill="${LIGHT}"/>` +
    `<path d="${path}" fill="${DARK}"/>` +
    logo +
    `</svg>`
  )
}

function escapeAttr(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
}

function escapeText(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Paints the code onto a canvas `pixels` wide (whole pixels per module). */
export function paintQr(
  ctx: CanvasRenderingContext2D,
  matrix: QrMatrix,
  options: { withLogo: boolean; logo?: CanvasImageSource | null; pixels: number },
): void {
  const total = matrix.size + QUIET_ZONE * 2
  const cell = Math.max(1, Math.floor(options.pixels / total))
  const side = cell * total
  const offset = Math.floor((options.pixels - side) / 2)
  ctx.fillStyle = LIGHT
  ctx.fillRect(0, 0, options.pixels, options.pixels)
  ctx.fillStyle = DARK
  const dark = darkModules(matrix, options.withLogo)
  for (let row = 0; row < matrix.size; row++) {
    for (let col = 0; col < matrix.size; col++) {
      if (dark(row, col)) ctx.fillRect(offset + (col + QUIET_ZONE) * cell, offset + (row + QUIET_ZONE) * cell, cell, cell)
    }
  }
  if (options.withLogo && options.logo) {
    const { start, span } = logoBox(matrix.size)
    const x = offset + (start + QUIET_ZONE) * cell
    const w = span * cell
    const inset = w * 0.06
    ctx.fillStyle = LIGHT
    ctx.beginPath()
    ctx.roundRect(x, x, w, w, w * 0.18)
    ctx.fill()
    ctx.drawImage(options.logo, x + inset, x + inset, w - inset * 2, w - inset * 2)
  }
}

/** Reads a QR code back from RGBA pixels (the self-check before export). */
export async function decodeQr(data: Uint8ClampedArray, width: number, height: number): Promise<string | null> {
  const { default: jsQR } = await import('jsqr')
  return jsQR(data, width, height, { inversionAttempts: 'dontInvert' })?.data ?? null
}

/** The public address the code points to: `VITE_PUBLIC_APP_URL` if set, else this site. */
export function installUrl(origin: string = typeof window === 'undefined' ? '' : window.location.origin): string {
  const configured = (import.meta.env.VITE_PUBLIC_APP_URL as string | undefined)?.trim()
  const base = (configured || origin).replace(/\/+$/, '')
  return `${base}/install`
}

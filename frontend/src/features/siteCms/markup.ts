/**
 * Parser for the public site's safe content markup — a copy of
 * okurmen-public-website/src/features/content/markup.ts (the two apps share no
 * code), used here for the editor preview. Backend: apps/website/markup.py.
 * Produces a block tree; no HTML from the API is ever injected into the page.
 * Compatible with the public news format (blank line, «## », «- »).
 */
import { videoEmbed } from './video'

export type Inline =
  | { type: 'text'; text: string }
  | { type: 'bold'; children: Inline[] }
  | { type: 'italic'; children: Inline[] }
  | { type: 'link'; href: string; children: Inline[] }
  | { type: 'break' }

export type Block =
  | { type: 'heading'; level: 2 | 3; text: string }
  | { type: 'paragraph'; children: Inline[] }
  | { type: 'list'; ordered: boolean; items: Inline[][] }
  | { type: 'quote'; children: Inline[] }
  | { type: 'image'; src: string; alt: string }
  | { type: 'video'; src: string }
  | { type: 'divider' }
  | { type: 'note'; blocks: Block[] }

const SAFE_URL = /^(https?:\/\/|mailto:|tel:|\/(?!\/))/i
export const safeUrl = (url: string) => (SAFE_URL.test(url.trim()) ? url.trim() : null)

export function parseInline(text: string): Inline[] {
  const out: Inline[] = []
  const pattern = /(\*\*([^*]+)\*\*)|(\*([^*\s][^*]*)\*)|(\[([^\]]+)\]\(([^)\s]+)\))/g
  let last = 0
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > last) out.push({ type: 'text', text: text.slice(last, index) })
    if (match[2] !== undefined) out.push({ type: 'bold', children: parseInline(match[2]) })
    else if (match[4] !== undefined) out.push({ type: 'italic', children: parseInline(match[4]) })
    else if (match[6] !== undefined) {
      const href = safeUrl(match[7])
      out.push(href ? { type: 'link', href, children: parseInline(match[6]) } : { type: 'text', text: match[0] })
    }
    last = index + match[0].length
  }
  if (last < text.length) out.push({ type: 'text', text: text.slice(last) })
  return out
}

function joinLines(lines: string[]): Inline[] {
  const out: Inline[] = []
  lines.forEach((line, i) => {
    if (i > 0) out.push({ type: 'break' })
    out.push(...parseInline(line))
  })
  return out
}

const UL = /^\s*[-•*]\s+(.*)$/
const OL = /^\s*\d+[.)]\s+(.*)$/
const IMG = /^!\[([^\]]*)\]\(([^)\s]+)\)$/

export function parseMarkup(source: string): Block[] {
  const lines = (source ?? '').replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const raw = lines[i]
    const line = raw.trim()
    if (!line) {
      i++
      continue
    }
    if (line.startsWith(':::')) {
      const inner: string[] = []
      i++
      while (i < lines.length && lines[i].trim() !== ':::') inner.push(lines[i++])
      i++
      blocks.push({ type: 'note', blocks: parseMarkup(inner.join('\n')) })
      continue
    }
    if (/^(-{3,}|\*{3,})$/.test(line)) {
      blocks.push({ type: 'divider' })
      i++
      continue
    }
    const heading = line.match(/^(#{2,3})\s+(.*)$/)
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length === 2 ? 2 : 3, text: heading[2] })
      i++
      continue
    }
    const image = line.match(IMG)
    if (image) {
      const src = safeUrl(image[2])
      if (src) blocks.push({ type: 'image', src, alt: image[1] })
      i++
      continue
    }
    const video = /^https?:\/\/\S+$/.test(line) ? videoEmbed(line) : null
    if (video) {
      blocks.push({ type: 'video', src: video })
      i++
      continue
    }
    if (line.startsWith('>')) {
      const quote: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('>')) quote.push(lines[i++].trim().replace(/^>\s?/, ''))
      blocks.push({ type: 'quote', children: joinLines(quote) })
      continue
    }
    if (UL.test(raw) || OL.test(raw)) {
      const ordered = !UL.test(raw)
      const re = ordered ? OL : UL
      const items: Inline[][] = []
      while (i < lines.length && re.test(lines[i])) items.push(parseInline(lines[i++].match(re)![1]))
      blocks.push({ type: 'list', ordered, items })
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#{2,3}\s|>|:::|-{3,}$)/.test(lines[i].trim()) && !UL.test(lines[i]) && !OL.test(lines[i]) && !IMG.test(lines[i].trim())) {
      para.push(lines[i++].trim())
    }
    if (para.length) blocks.push({ type: 'paragraph', children: joinLines(para) })
    else i++
  }
  return blocks
}

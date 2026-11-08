import { useEffect, useState } from 'react'
import { Check, Facebook, Link2, MessageCircle, Send, Share2 } from 'lucide-react'

import { useI18n } from '@/features/portal/i18n'
import { copyText } from '@/utils/clipboard'

const chip =
  'inline-flex h-10 items-center justify-center gap-2 rounded-full border border-pd-line bg-pd-panel px-3.5 text-sm font-medium text-pd-ink pd-shadow transition hover:border-pd-green-line hover:text-pd-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pd-green'

/** Share an article: the phone's own share sheet, Telegram, WhatsApp, Facebook, or copy the link. */
export function ShareBar({ title }: { title: string }) {
  const { t } = useI18n()
  const n = t.news
  const [copied, setCopied] = useState(false)
  const url = typeof window !== 'undefined' ? window.location.href : ''
  const text = encodeURIComponent(title)
  const link = encodeURIComponent(url)
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'

  useEffect(() => {
    if (!copied) return
    const id = window.setTimeout(() => setCopied(false), 2500)
    return () => window.clearTimeout(id)
  }, [copied])

  async function copy() {
    try {
      await copyText(url)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label={n.share}>
      <span className="mr-1 text-sm font-semibold text-pd-muted">{n.share}</span>
      {canShare ? (
        <button type="button" className={chip} onClick={() => void navigator.share({ title, url }).catch(() => undefined)}>
          <Share2 className="size-4" aria-hidden />
          {n.share}
        </button>
      ) : null}
      <a className={chip} href={`https://t.me/share/url?url=${link}&text=${text}`} target="_blank" rel="noopener noreferrer" aria-label="Telegram">
        <Send className="size-4" aria-hidden />
        <span className="hidden sm:inline">Telegram</span>
      </a>
      <a className={chip} href={`https://wa.me/?text=${text}%20${link}`} target="_blank" rel="noopener noreferrer" aria-label="WhatsApp">
        <MessageCircle className="size-4" aria-hidden />
        <span className="hidden sm:inline">WhatsApp</span>
      </a>
      <a className={chip} href={`https://www.facebook.com/sharer/sharer.php?u=${link}`} target="_blank" rel="noopener noreferrer" aria-label="Facebook">
        <Facebook className="size-4" aria-hidden />
        <span className="hidden sm:inline">Facebook</span>
      </a>
      <button type="button" className={chip} onClick={() => void copy()}>
        {copied ? <Check className="size-4 text-pd-green" aria-hidden /> : <Link2 className="size-4" aria-hidden />}
        {copied ? n.copied : n.copyLink}
      </button>
      <span className="sr-only" aria-live="polite">{copied ? n.copied : ''}</span>
    </div>
  )
}

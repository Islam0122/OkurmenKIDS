import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Award,
  Bell,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Flag,
  GraduationCap,
  Heart,
  ImagePlus,
  Link2,
  Megaphone,
  MessageCircle,
  MoreHorizontal,
  Newspaper,
  PenLine,
  Pin,
  Plus,
  Rocket,
  Send,
  ShieldCheck,
  Sparkles,
  Star,
  Trash2,
  X,
} from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { communityApi } from '@/api/community'
import { extractErrorMessage } from '@/lib/apiError'
import type {
  CommunityAuthor,
  CommunityCategory,
  CommunityComment,
  CommunityFeedPage,
  CommunityImage,
  CommunityNotification,
  CommunityPost,
  PostInput,
  PostStatus,
  ReportReason,
} from '@/types/community'
import { cn } from '@/utils/cn'

import { PORTAL_KEY, usePortal } from '../context'
import { usePortalI18n, type Key, type TFunction } from '../i18n'
import { Empty, LoadError, PageTitle, Skeleton } from '../ui'

/**
 * «Сообщество» — the private community of the portal, as the selected child.
 * Only posts a moderator approved appear in the feed; a new post (and any
 * edit) goes to review first — the composer says so. No contact details, no
 * public pages, photos only through short-lived private links.
 */

export const COMMUNITY_KEY = [...PORTAL_KEY, 'community'] as const
const MAX_TEXT = 3000
const MAX_IMAGES = 6
const STUDENT_CATEGORIES: CommunityCategory[] = ['general', 'achievement', 'project', 'learning_progress', 'review']
const FILTERS: (CommunityCategory | '')[] = ['', 'achievement', 'project', 'learning_progress', 'review', 'news', 'general']

export const CATEGORY_STYLE: Record<CommunityCategory, { icon: typeof Star; tone: string }> = {
  general: { icon: Sparkles, tone: 'bg-slate-100 text-slate-700' },
  review: { icon: Star, tone: 'bg-amber-50 text-amber-800' },
  achievement: { icon: Award, tone: 'bg-brand-50 text-brand-700' },
  project: { icon: Rocket, tone: 'bg-sky-50 text-sky-700' },
  learning_progress: { icon: GraduationCap, tone: 'bg-violet-50 text-violet-700' },
  news: { icon: Newspaper, tone: 'bg-emerald-600 text-white' },
}

const STATUS_TONE: Record<PostStatus, string> = {
  draft: 'bg-surface-muted text-ink-secondary',
  pending: 'bg-amber-50 text-amber-800',
  approved: 'bg-brand-50 text-brand-700',
  rejected: 'bg-rose-50 text-rose-700',
  hidden: 'bg-rose-50 text-rose-700',
}

const k = (key: string) => key as Key

export function ago(t: TFunction, date: (iso: string, withYear?: boolean) => string, iso: string | null): string {
  if (!iso) return ''
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (minutes < 1) return t('cm.time.now')
  if (minutes < 60) return t('cm.time.min', { n: minutes })
  if (minutes < 24 * 60) return t('cm.time.hour', { n: Math.floor(minutes / 60) })
  if (minutes < 48 * 60) return t('cm.time.yesterday')
  return date(iso, new Date(iso).getFullYear() !== new Date().getFullYear())
}

// ------------------------------------------------------------------ small pieces

export function AuthorAvatar({ author, size = 'md' }: { author: Pick<CommunityAuthor, 'name' | 'photo' | 'type'>; size?: 'sm' | 'md' | 'lg' }) {
  const cls = size === 'sm' ? 'size-8 text-[11px]' : size === 'lg' ? 'size-20 text-2xl' : 'size-11 text-sm'
  if (author.type === 'academy') {
    return (
      <span className={cn(cls, 'flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-emerald-700 text-white ring-2 ring-white')}>
        <Megaphone className="size-1/2" aria-hidden />
      </span>
    )
  }
  if (author.photo) return <img src={author.photo} alt="" className={cn(cls, 'shrink-0 rounded-full object-cover ring-2 ring-white')} />
  const initials = author.name.split(' ').map((part) => part[0] ?? '').join('').slice(0, 2)
  // A stable soft colour per name, so a feed of initials is not monotone.
  const hues = ['from-brand-400 to-brand-600', 'from-sky-400 to-sky-600', 'from-violet-400 to-violet-600', 'from-amber-400 to-orange-500', 'from-rose-400 to-rose-600', 'from-teal-400 to-teal-600']
  const hue = hues[[...author.name].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % hues.length]
  return (
    <span className={cn(cls, 'flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br font-bold text-white ring-2 ring-white', hue)}>
      {initials}
    </span>
  )
}

export function CategoryBadge({ category }: { category: CommunityCategory }) {
  const { t } = usePortalI18n()
  const { icon: Icon, tone } = CATEGORY_STYLE[category]
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold', tone)}>
      <Icon className="size-3.5" aria-hidden />
      {t(k(`cat.${category}`))}
    </span>
  )
}

function Overlay({ children, onClose, label, wide = false }: { children: ReactNode; onClose: () => void; label: string; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
    }
  }, [onClose])
  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center sm:p-6" role="dialog" aria-modal="true" aria-label={label}>
      <button type="button" aria-label={label} tabIndex={-1} className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" onClick={onClose} />
      <div className={cn('sp-sheet relative flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-3xl bg-surface shadow-2xl sm:rounded-3xl', wide ? 'sm:max-w-3xl' : 'sm:max-w-xl')}>
        {children}
      </div>
    </div>,
    document.body,
  )
}

function SheetHeader({ title, onClose }: { title: string; onClose: () => void }) {
  const { t } = usePortalI18n()
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/70 px-5 py-4">
      <h2 className="text-base font-bold text-ink">{title}</h2>
      <button type="button" onClick={onClose} aria-label={t('cm.close')} className="sp-press flex size-9 items-center justify-center rounded-full text-ink-secondary hover:bg-surface-muted">
        <X className="size-5" aria-hidden />
      </button>
    </div>
  )
}

// ------------------------------------------------------------------ composer

function Composer({ post, onClose, onDone }: { post?: CommunityPost; onClose: () => void; onDone: (message: string) => void }) {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const qc = useQueryClient()
  const [text, setText] = useState(post?.text ?? '')
  const [category, setCategory] = useState<CommunityCategory>(post?.category && post.category !== 'news' ? post.category : 'general')
  const [audience, setAudience] = useState(post?.audience ?? 'academy')
  const [projectUrl, setProjectUrl] = useState(post?.project_url ?? '')
  const [consent, setConsent] = useState(post?.website_consent ?? false)
  const [files, setFiles] = useState<File[]>([])
  const [removed, setRemoved] = useState<number[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const input = useRef<HTMLInputElement>(null)
  const previews = useMemo(() => files.map((file) => ({ file, url: URL.createObjectURL(file) })), [files])
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews])
  const kept = (post?.images ?? []).filter((img) => !removed.includes(img.id))
  const room = MAX_IMAGES - kept.length - files.length

  const save = useMutation({
    mutationFn: (submit: boolean) => {
      const body: PostInput = { text, category, audience, project_url: projectUrl.trim(), website_consent: category === 'review' && consent, images: files, remove_images: removed, submit }
      return post ? communityApi.update(student.id, post.id, body) : communityApi.create(student.id, body)
    },
    onSuccess: (_data, submit) => {
      void qc.invalidateQueries({ queryKey: [...COMMUNITY_KEY, student.id] })
      onDone(submit ? t('cm.compose.sent') : t('cm.compose.saved'))
    },
    onError: (error) => {
      const data = (error as { response?: { data?: Record<string, unknown> } }).response?.data
      const next: Record<string, string> = {}
      if (data && typeof data === 'object') {
        for (const [field, value] of Object.entries(data)) next[field] = Array.isArray(value) ? value.join(' ') : String(value)
      }
      setErrors(Object.keys(next).length ? next : { detail: extractErrorMessage(error, t('cm.compose.error')) })
    },
  })

  const addFiles = (list: FileList | null) => {
    if (!list) return
    const images = [...list].filter((file) => /^image\/(jpeg|png|webp)$/.test(file.type)).slice(0, Math.max(room, 0))
    setFiles((current) => [...current, ...images])
  }
  const err = (field: string) => (errors[field] ? <p className="mt-1.5 text-sm text-rose-700" role="alert">{errors[field]}</p> : null)
  const canSubmit = text.trim().length > 0 && text.length <= MAX_TEXT && !save.isPending

  return (
    <Overlay onClose={onClose} label={post ? t('cm.compose.edit') : t('cm.compose.title')}>
      <SheetHeader title={post ? t('cm.compose.edit') : t('cm.compose.title')} onClose={onClose} />
      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
        <div className="flex items-start gap-3">
          <AuthorAvatar author={{ type: 'student', name: student.full_name, photo: student.photo }} />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink">{student.full_name}</p>
            <p className="text-xs text-ink-muted">{student.group?.name}</p>
          </div>
        </div>

        <div>
          <label htmlFor="cm-text" className="sr-only">{t('cm.compose.text')}</label>
          <textarea
            id="cm-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            maxLength={MAX_TEXT}
            autoFocus
            placeholder={t('cm.compose.placeholder', { name: student.first_name })}
            className="w-full resize-none rounded-2xl border border-border bg-surface-muted/50 px-4 py-3 text-[15px] leading-relaxed text-ink outline-none transition focus:border-brand-400 focus:bg-surface focus:ring-4 focus:ring-brand-100"
          />
          <div className="mt-1 flex justify-between gap-3 text-xs text-ink-muted">
            <span>{err('text')}</span>
            <span className="tabular-nums">{t('cm.compose.counter', { n: text.length, max: MAX_TEXT })}</span>
          </div>
        </div>

        <fieldset>
          <legend className="mb-2 text-sm font-semibold text-ink">{t('cm.compose.category')}</legend>
          <div className="flex flex-wrap gap-2">
            {STUDENT_CATEGORIES.map((c) => {
              const { icon: Icon } = CATEGORY_STYLE[c]
              const on = category === c
              return (
                <button key={c} type="button" aria-pressed={on} onClick={() => setCategory(c)}
                  className={cn('sp-press inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition',
                    on ? 'border-brand-500 bg-brand-500 text-white shadow-sm' : 'border-border bg-surface text-ink-secondary hover:border-brand-300')}>
                  <Icon className="size-4" aria-hidden />
                  {t(k(`cat.${c}`))}
                </button>
              )
            })}
          </div>
          {err('category')}
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-sm font-semibold text-ink">{t('cm.compose.audience')}</legend>
          <div className="inline-grid grid-cols-2 rounded-xl bg-surface-muted p-1 text-sm font-semibold">
            {(['academy', 'group'] as const).map((a) => (
              <button key={a} type="button" aria-pressed={audience === a} onClick={() => setAudience(a)}
                className={cn('rounded-lg px-3 py-2 transition', audience === a ? 'bg-surface text-ink shadow-sm' : 'text-ink-secondary')}>
                {t(a === 'academy' ? 'cm.audience.academy' : 'cm.audience.group')}
              </button>
            ))}
          </div>
        </fieldset>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold text-ink">{t('cm.compose.photos')}</span>
            <span className="text-xs text-ink-muted">{t('cm.compose.photoLimit', { n: MAX_IMAGES })}</span>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {kept.map((img) => (
              <Thumb key={`k${img.id}`} src={img.thumb} onRemove={() => setRemoved((r) => [...r, img.id])} label={t('cm.compose.removePhoto')} />
            ))}
            {previews.map((p, i) => (
              <Thumb key={p.url} src={p.url} onRemove={() => setFiles((f) => f.filter((_, j) => j !== i))} label={t('cm.compose.removePhoto')} />
            ))}
            {room > 0 ? (
              <button type="button" onClick={() => input.current?.click()}
                className="sp-press flex aspect-square flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-border text-xs font-semibold text-ink-secondary transition hover:border-brand-400 hover:text-brand-700">
                <ImagePlus className="size-6" aria-hidden />
                {t('cm.compose.addPhoto')}
              </button>
            ) : null}
          </div>
          <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
          {err('images')}
        </div>

        <div>
          <label htmlFor="cm-project" className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-ink">
            <Link2 className="size-4 text-ink-muted" aria-hidden />{t('cm.compose.project')}
          </label>
          <input id="cm-project" type="url" inputMode="url" value={projectUrl} onChange={(e) => setProjectUrl(e.target.value)} placeholder="https://github.com/…"
            className="w-full rounded-xl border border-border bg-surface px-3.5 py-2.5 text-sm outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100" />
          <p className="mt-1 text-xs text-ink-muted">{t('cm.compose.projectHint')}</p>
          {err('project_url')}
        </div>

        {category === 'review' ? (
          <label className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50/70 p-3.5 text-sm text-amber-950">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 size-4 accent-brand-600" />
            <span>{t('cm.compose.website')}</span>
          </label>
        ) : null}

        <p className="flex items-start gap-2 rounded-2xl bg-brand-50/70 p-3.5 text-sm text-brand-900">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden />
          {t('cm.compose.policy')}
        </p>
        {err('detail')}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border/70 px-5 py-3.5 pb-[max(0.875rem,env(safe-area-inset-bottom))]">
        <button type="button" onClick={onClose} className="sp-press rounded-xl px-4 py-2.5 text-sm font-semibold text-ink-secondary hover:bg-surface-muted">{t('cm.compose.cancel')}</button>
        <button type="button" disabled={!canSubmit} onClick={() => save.mutate(false)}
          className="sp-press rounded-xl border border-border px-4 py-2.5 text-sm font-semibold text-ink hover:bg-surface-muted disabled:opacity-50">{t('cm.compose.draft')}</button>
        <button type="button" disabled={!canSubmit} onClick={() => save.mutate(true)}
          className="sp-press inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-brand-700 disabled:opacity-50">
          <Send className="size-4" aria-hidden />{t('cm.compose.submit')}
        </button>
      </div>
    </Overlay>
  )
}

function Thumb({ src, onRemove, label }: { src: string; onRemove: () => void; label: string }) {
  return (
    <div className="group relative aspect-square overflow-hidden rounded-2xl bg-surface-muted">
      <img src={src} alt="" className="size-full object-cover" />
      <button type="button" onClick={onRemove} aria-label={label}
        className="absolute right-1.5 top-1.5 flex size-7 items-center justify-center rounded-full bg-ink/70 text-white backdrop-blur hover:bg-ink">
        <X className="size-4" aria-hidden />
      </button>
    </div>
  )
}

// ------------------------------------------------------------------ images

function Gallery({ images, onOpen }: { images: CommunityImage[]; onOpen: (index: number) => void }) {
  const { t } = usePortalI18n()
  if (!images.length) return null
  const shown = images.slice(0, 4)
  const extra = images.length - shown.length
  const grid = images.length === 1 ? 'grid-cols-1' : 'grid-cols-2'
  return (
    <div className={cn('mt-3 grid gap-1.5 overflow-hidden rounded-2xl', grid)}>
      {shown.map((img, i) => (
        <button key={img.id} type="button" onClick={() => onOpen(i)} aria-label={t('cm.photo', { n: i + 1, total: images.length })}
          className={cn('relative overflow-hidden bg-surface-muted', images.length === 1 ? 'max-h-[28rem]' : 'aspect-square', images.length === 3 && i === 0 ? 'row-span-2 aspect-auto' : '')}>
          <img src={img.thumb} alt="" loading="lazy" className="size-full object-cover transition duration-300 hover:scale-[1.02]"
            style={images.length === 1 && img.width && img.height ? { aspectRatio: `${img.width} / ${img.height}` } : undefined} />
          {extra > 0 && i === shown.length - 1 ? (
            <span className="absolute inset-0 flex items-center justify-center bg-ink/50 text-2xl font-bold text-white">{t('cm.photos.count', { n: extra })}</span>
          ) : null}
        </button>
      ))}
    </div>
  )
}

function Lightbox({ images, start, onClose }: { images: CommunityImage[]; start: number; onClose: () => void }) {
  const { t } = usePortalI18n()
  const [index, setIndex] = useState(start)
  const go = (delta: number) => setIndex((i) => (i + delta + images.length) % images.length)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') go(1)
      if (e.key === 'ArrowLeft') go(-1)
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  })
  const image = images[index]
  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/90" role="dialog" aria-modal="true" aria-label={t('cm.photo', { n: index + 1, total: images.length })}>
      <button type="button" onClick={onClose} aria-label={t('cm.close')} className="absolute right-4 top-[max(1rem,env(safe-area-inset-top))] z-10 flex size-10 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20">
        <X className="size-5" aria-hidden />
      </button>
      <img src={image.large} alt="" className="max-h-[88dvh] max-w-[94vw] rounded-lg object-contain" />
      {images.length > 1 ? (
        <>
          <button type="button" onClick={() => go(-1)} aria-label={t('cm.prev')} className="absolute left-3 flex size-11 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"><ChevronLeft className="size-6" aria-hidden /></button>
          <button type="button" onClick={() => go(1)} aria-label={t('cm.next')} className="absolute right-3 flex size-11 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"><ChevronRight className="size-6" aria-hidden /></button>
          <p className="absolute bottom-[max(1.25rem,env(safe-area-inset-bottom))] rounded-full bg-white/10 px-3 py-1 text-sm text-white">{index + 1} / {images.length}</p>
        </>
      ) : null}
    </div>,
    document.body,
  )
}

// ------------------------------------------------------------------ comments

function Comments({ post, onCount }: { post: CommunityPost; onCount: (delta: number) => void }) {
  const { student } = usePortal()
  const { t, date } = usePortalI18n()
  const qc = useQueryClient()
  const key = [...COMMUNITY_KEY, student.id, 'comments', post.id]
  const query = useQuery({ queryKey: key, queryFn: () => communityApi.comments(student.id, post.id) })
  const [text, setText] = useState('')
  const [replyTo, setReplyTo] = useState<CommunityComment | null>(null)
  const [error, setError] = useState('')
  const [reporting, setReporting] = useState<CommunityComment | null>(null)
  const field = useRef<HTMLInputElement>(null)
  const send = useMutation({
    mutationFn: () => communityApi.comment(student.id, post.id, text.trim(), replyTo?.id),
    onSuccess: () => {
      setText(''); setReplyTo(null); setError('')
      onCount(1)
      void qc.invalidateQueries({ queryKey: key })
    },
    onError: (e) => setError(extractErrorMessage(e, t('cm.compose.error'))),
  })
  const remove = useMutation({
    mutationFn: (id: number) => communityApi.deleteComment(student.id, id),
    onSuccess: () => { onCount(-1); void qc.invalidateQueries({ queryKey: key }) },
  })

  const row = (c: CommunityComment, reply = false) => (
    <li key={c.id} className={cn('flex gap-2.5', reply && 'ml-10')}>
      {c.author ? <AuthorAvatar author={c.author} size="sm" /> : <span className="size-8 shrink-0 rounded-full bg-surface-muted" />}
      <div className="min-w-0 flex-1">
        <div className="rounded-2xl rounded-tl-md bg-surface-muted px-3.5 py-2">
          {c.author ? (
            <p className="text-[13px] font-semibold text-ink">
              {c.author.student_id ? <Link to={`/student/community/u/${c.author.student_id}`} className="hover:underline">{c.author.name}</Link> : c.author.name}
              {c.author.group ? <span className="ml-1.5 font-normal text-ink-muted">· {c.author.group.name}</span> : null}
            </p>
          ) : null}
          <p className={cn('whitespace-pre-line break-words text-sm', c.status === 'visible' ? 'text-ink' : 'italic text-ink-muted')}>
            {c.status === 'visible' ? c.text : t(c.status === 'deleted' ? 'cm.comment.deleted' : 'cm.comment.hidden')}
          </p>
        </div>
        {c.status === 'visible' ? (
          <div className="mt-1 flex items-center gap-3 px-2 text-xs font-semibold text-ink-muted">
            <span className="font-normal">{ago(t, date, c.created_at)}</span>
            <button type="button" onClick={() => { setReplyTo(c); field.current?.focus() }} className="hover:text-brand-700">{t('cm.comment.reply')}</button>
            {c.mine ? (
              <button type="button" onClick={() => remove.mutate(c.id)} className="hover:text-rose-700">{t('cm.delete')}</button>
            ) : (
              <button type="button" onClick={() => setReporting(c)} className="hover:text-rose-700">{t('cm.report')}</button>
            )}
          </div>
        ) : null}
      </div>
    </li>
  )

  return (
    <div className="mt-3 border-t border-border/60 pt-3">
      {query.isPending ? <Skeleton className="h-12 w-full" /> : null}
      {query.data && !query.data.length ? <p className="py-2 text-center text-sm text-ink-muted">{t('cm.comment.empty')}</p> : null}
      <ul className="space-y-3">
        {(query.data ?? []).map((c) => (
          <li key={c.id} className="space-y-3">
            <ul>{row(c)}</ul>
            {c.replies?.length ? <ul className="space-y-3">{c.replies.map((r) => row(r, true))}</ul> : null}
          </li>
        ))}
      </ul>
      <form className="mt-3" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send.mutate() }}>
        {replyTo ? (
          <p className="mb-1.5 flex items-center gap-2 text-xs text-ink-secondary">
            {t('cm.comment.replyTo', { name: replyTo.author?.first_name ?? replyTo.author?.name ?? '' })}
            <button type="button" onClick={() => setReplyTo(null)} aria-label={t('cm.comment.cancelReply')} className="rounded-full p-0.5 hover:bg-surface-muted"><X className="size-3.5" aria-hidden /></button>
          </p>
        ) : null}
        <div className="flex items-center gap-2">
          <AuthorAvatar author={{ type: 'student', name: student.full_name, photo: student.photo }} size="sm" />
          <input ref={field} value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} aria-label={t('cm.comment.placeholder')}
            placeholder={t('cm.comment.placeholder')}
            className="min-w-0 flex-1 rounded-full border border-border bg-surface px-4 py-2.5 text-sm outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100" />
          <button type="submit" disabled={!text.trim() || send.isPending} aria-label={t('cm.comment.send')}
            className="sp-press flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white disabled:opacity-40">
            <Send className="size-4" aria-hidden />
          </button>
        </div>
        {error ? <p className="mt-1.5 text-sm text-rose-700" role="alert">{error}</p> : null}
      </form>
      {reporting ? <ReportDialog target={{ comment: reporting.id }} onClose={() => setReporting(null)} /> : null}
    </div>
  )
}

// ------------------------------------------------------------------ report

const REASONS: ReportReason[] = ['personal_info', 'bullying', 'inappropriate', 'spam', 'other']

function ReportDialog({ target, onClose }: { target: { post?: number; comment?: number }; onClose: () => void }) {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const [reason, setReason] = useState<ReportReason>('inappropriate')
  const [details, setDetails] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const send = useMutation({
    mutationFn: () => (target.post
      ? communityApi.reportPost(student.id, target.post, reason, details)
      : communityApi.reportComment(student.id, target.comment as number, reason, details)),
    onSuccess: () => setDone(true),
    onError: (e) => setError(extractErrorMessage(e, t('cm.compose.error'))),
  })
  return (
    <Overlay onClose={onClose} label={t('cm.report.title')}>
      <SheetHeader title={t('cm.report.title')} onClose={onClose} />
      {done ? (
        <div className="px-5 py-8 text-center">
          <ShieldCheck className="mx-auto size-10 text-brand-600" aria-hidden />
          <p className="mt-3 font-semibold text-ink" role="status">{t('cm.report.done')}</p>
          <button type="button" onClick={onClose} className="sp-press mt-5 rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-bold text-white">{t('cm.close')}</button>
        </div>
      ) : (
        <form className="space-y-3 overflow-y-auto px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]" onSubmit={(e) => { e.preventDefault(); send.mutate() }}>
          <div className="space-y-2" role="radiogroup" aria-label={t('cm.report.title')}>
            {REASONS.map((r) => (
              <label key={r} className={cn('flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 text-sm', reason === r ? 'border-brand-400 bg-brand-50/60' : 'border-border')}>
                <input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} className="accent-brand-600" />
                {t(k(`rr.${r}`))}
              </label>
            ))}
          </div>
          <textarea value={details} onChange={(e) => setDetails(e.target.value)} maxLength={500} rows={2} aria-label={t('cm.report.details')}
            placeholder={t('cm.report.details')} className="w-full rounded-2xl border border-border px-3.5 py-2.5 text-sm outline-none focus:border-brand-400" />
          {error ? <p className="text-sm text-rose-700" role="alert">{error}</p> : null}
          <button type="submit" disabled={send.isPending} className="sp-press w-full rounded-xl bg-rose-600 px-4 py-3 text-sm font-bold text-white hover:bg-rose-700 disabled:opacity-60">
            {t('cm.report.send')}
          </button>
        </form>
      )}
    </Overlay>
  )
}

// ------------------------------------------------------------------ post card

function TextBlock({ text }: { text: string }) {
  const { t } = usePortalI18n()
  const [open, setOpen] = useState(false)
  const long = text.length > 420
  return (
    <div className="mt-3">
      <p className={cn('whitespace-pre-line break-words text-[15px] leading-relaxed text-ink', long && !open && 'line-clamp-6')}>{text}</p>
      {long ? (
        <button type="button" onClick={() => setOpen(!open)} className="mt-1 text-sm font-semibold text-brand-700 hover:underline">
          {open ? t('cm.less') : t('cm.more')}
        </button>
      ) : null}
    </div>
  )
}

export function PostCard({ post, onEdit, onChanged, defaultOpenComments = false, compact = false }: {
  post: CommunityPost
  onEdit?: (post: CommunityPost) => void
  onChanged?: (message?: string) => void
  defaultOpenComments?: boolean
  compact?: boolean
}) {
  const { student } = usePortal()
  const { t, date } = usePortalI18n()
  const qc = useQueryClient()
  const [liked, setLiked] = useState(post.liked)
  const [likes, setLikes] = useState(post.likes)
  const [comments, setComments] = useState(post.comments)
  const [showComments, setShowComments] = useState(defaultOpenComments)
  const [lightbox, setLightbox] = useState<number | null>(null)
  const [menu, setMenu] = useState(false)
  const [reporting, setReporting] = useState(false)
  const [pop, setPop] = useState(0)
  useEffect(() => { setLiked(post.liked); setLikes(post.likes); setComments(post.comments) }, [post.liked, post.likes, post.comments])

  const like = useMutation({
    mutationFn: (next: boolean) => communityApi.like(student.id, post.id, next),
    onMutate: (next) => { setLiked(next); setLikes((n) => n + (next ? 1 : -1)); if (next) setPop((p) => p + 1) },
    onSuccess: (data) => { setLiked(data.liked); setLikes(data.likes) },
    onError: () => { setLiked(post.liked); setLikes(post.likes) },
  })
  const remove = useMutation({
    mutationFn: () => communityApi.remove(student.id, post.id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: [...COMMUNITY_KEY, student.id] }); onChanged?.(t('cm.deleted')) },
  })
  const resubmit = useMutation({
    mutationFn: () => communityApi.update(student.id, post.id, {
      text: post.text, category: post.category, audience: post.audience, project_url: post.project_url,
      website_consent: post.website_consent ?? false, images: [], submit: true,
    }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: [...COMMUNITY_KEY, student.id] }); onChanged?.(t('cm.compose.sent')) },
  })

  const published = post.status === 'approved'
  const a = post.author
  return (
    <article className={cn('sp-card relative overflow-visible px-4 py-4 sm:px-5', post.is_pinned && 'ring-1 ring-brand-200', post.is_announcement && 'bg-gradient-to-b from-brand-50/60 to-surface')} aria-label={a.name}>
      <header className="flex items-start gap-3">
        {a.student_id ? <Link to={`/student/community/u/${a.student_id}`} aria-label={a.name}><AuthorAvatar author={a} /></Link> : <AuthorAvatar author={a} />}
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-1.5 text-[15px] font-semibold leading-tight text-ink">
            {a.student_id ? <Link to={`/student/community/u/${a.student_id}`} className="truncate hover:underline">{a.name}</Link> : <span>{a.name}</span>}
            {post.is_announcement ? <span className="inline-flex items-center gap-0.5 rounded-full bg-brand-600 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"><ShieldCheck className="size-3" aria-hidden />{t('cm.official')}</span> : null}
          </p>
          <p className="mt-0.5 truncate text-xs text-ink-muted">
            {[a.group?.name, ago(t, date, post.published_at ?? post.created_at), post.edited_at ? t('cm.edited') : ''].filter(Boolean).join(' · ')}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {post.is_pinned ? <Pin className="size-4 text-brand-600" aria-label={t('cm.pinned')} /> : null}
          {!compact ? <CategoryBadge category={post.category} /> : null}
          {(post.mine || published) && !post.is_announcement ? (
            <div className="relative">
              <button type="button" onClick={() => setMenu(!menu)} aria-label={t('cm.menu')} aria-expanded={menu} aria-haspopup="menu"
                className="sp-press flex size-8 items-center justify-center rounded-full text-ink-muted hover:bg-surface-muted">
                <MoreHorizontal className="size-5" aria-hidden />
              </button>
              {menu ? (
                <>
                  <button type="button" aria-hidden tabIndex={-1} className="fixed inset-0 z-10 cursor-default" onClick={() => setMenu(false)} />
                  <div role="menu" className="sp-pop absolute right-0 top-9 z-20 w-48 overflow-hidden rounded-2xl border border-border bg-surface py-1 shadow-xl">
                    {post.mine && post.can_edit && onEdit ? (
                      <button role="menuitem" type="button" onClick={() => { setMenu(false); onEdit(post) }} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm hover:bg-surface-muted"><PenLine className="size-4" aria-hidden />{t('cm.edit')}</button>
                    ) : null}
                    {post.mine ? (
                      <button role="menuitem" type="button" onClick={() => { setMenu(false); if (window.confirm(t('cm.deleteConfirm'))) remove.mutate() }} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-rose-700 hover:bg-rose-50"><Trash2 className="size-4" aria-hidden />{t('cm.delete')}</button>
                    ) : (
                      <button role="menuitem" type="button" onClick={() => { setMenu(false); setReporting(true) }} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-rose-700 hover:bg-rose-50"><Flag className="size-4" aria-hidden />{t('cm.report')}</button>
                    )}
                  </div>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
      </header>

      {post.mine && post.status !== 'approved' ? (
        <div className={cn('mt-3 rounded-2xl px-3.5 py-2.5 text-sm', STATUS_TONE[post.status])}>
          <p className="font-semibold">{t(k(`pst.${post.status}`))}</p>
          {post.moderation?.note ? <p className="mt-0.5"><span className="font-medium">{t('cm.moderatorNote')}:</span> {post.moderation.note}</p> : null}
          {post.status === 'draft' || post.status === 'rejected' ? (
            <div className="mt-2 flex flex-wrap gap-2">
              {onEdit ? <button type="button" onClick={() => onEdit(post)} className="sp-press rounded-lg bg-surface px-3 py-1.5 text-xs font-bold text-ink shadow-sm">{t('cm.resubmit')}</button> : null}
              {post.status === 'draft' ? <button type="button" onClick={() => resubmit.mutate()} className="sp-press rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-bold text-white">{t('cm.submitDraft')}</button> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      <TextBlock text={post.text} />
      {post.project_url ? (
        <a href={post.project_url} target="_blank" rel="noopener noreferrer nofollow"
          className="sp-press mt-3 inline-flex max-w-full items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-semibold text-sky-800 hover:bg-sky-100">
          <Rocket className="size-4 shrink-0" aria-hidden />
          <span className="truncate">{t('cm.project')} · {new URL(post.project_url).hostname}</span>
          <ExternalLink className="size-3.5 shrink-0" aria-hidden />
        </a>
      ) : null}
      <Gallery images={post.images} onOpen={setLightbox} />
      {post.mine && post.website_consent && post.category === 'review' ? (
        <p className="mt-2 text-xs text-ink-muted">✓ {t('cm.website.yes')}</p>
      ) : null}

      {published ? (
        <footer className="mt-3 flex items-center gap-1 border-t border-border/60 pt-2">
          <button type="button" onClick={() => like.mutate(!liked)} aria-pressed={liked} aria-label={liked ? t('cm.unlike') : t('cm.like')}
            className={cn('sp-press inline-flex min-h-11 items-center gap-2 rounded-full px-3.5 text-sm font-semibold transition', liked ? 'text-rose-600' : 'text-ink-secondary hover:bg-surface-muted')}>
            <Heart key={pop} className={cn('size-5', liked && 'fill-rose-500 text-rose-500', pop && liked && 'sp-pop')} aria-hidden />
            <span className="tabular-nums">{likes}</span>
          </button>
          <button type="button" onClick={() => setShowComments(!showComments)} aria-expanded={showComments}
            className="sp-press inline-flex min-h-11 items-center gap-2 rounded-full px-3.5 text-sm font-semibold text-ink-secondary hover:bg-surface-muted">
            <MessageCircle className="size-5" aria-hidden />
            <span className="tabular-nums">{comments}</span>
            <span className="sr-only">{t('cm.comments')}</span>
          </button>
        </footer>
      ) : null}
      {published && showComments ? <Comments post={post} onCount={(d) => setComments((n) => Math.max(0, n + d))} /> : null}
      {lightbox !== null ? <Lightbox images={post.images} start={lightbox} onClose={() => setLightbox(null)} /> : null}
      {reporting ? <ReportDialog target={{ post: post.id }} onClose={() => setReporting(false)} /> : null}
    </article>
  )
}

// ------------------------------------------------------------------ notifications

export function notificationText(t: TFunction, n: CommunityNotification) {
  return t(k(`cm.notif.${n.kind}`), { actor: n.actor })
}

function NotificationsSheet({ onClose, onOpenPost }: { onClose: () => void; onOpenPost: (id: number) => void }) {
  const { student } = usePortal()
  const { t, date } = usePortalI18n()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: [...COMMUNITY_KEY, student.id, 'notifications'], queryFn: () => communityApi.notifications(student.id) })
  const read = useMutation({
    mutationFn: () => communityApi.readNotifications(student.id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...COMMUNITY_KEY, student.id, 'summary'] }),
  })
  useEffect(() => { if (query.data?.unread) read.mutate() }, [query.data?.unread]) // eslint-disable-line react-hooks/exhaustive-deps
  const icon = { comment: MessageCircle, reply: MessageCircle, like: Heart, approved: ShieldCheck, rejected: Flag, hidden: Flag }
  return (
    <Overlay onClose={onClose} label={t('cm.notifications')}>
      <SheetHeader title={t('cm.notifications')} onClose={onClose} />
      <div className="flex-1 overflow-y-auto px-2 py-2 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        {query.isPending ? <div className="space-y-2 p-3"><Skeleton className="h-14 w-full" /><Skeleton className="h-14 w-full" /></div> : null}
        {query.data && !query.data.results.length ? <p className="px-4 py-10 text-center text-sm text-ink-muted">{t('cm.notifications.empty')}</p> : null}
        <ul>
          {(query.data?.results ?? []).map((n) => {
            const Icon = icon[n.kind]
            return (
              <li key={n.id}>
                <button type="button" disabled={!n.post_id} onClick={() => n.post_id && onOpenPost(n.post_id)}
                  className={cn('flex w-full items-start gap-3 rounded-2xl px-3 py-3 text-left hover:bg-surface-muted', !n.is_read && 'bg-brand-50/60')}>
                  <span className={cn('mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full', n.kind === 'rejected' || n.kind === 'hidden' ? 'bg-rose-50 text-rose-600' : n.kind === 'like' ? 'bg-rose-50 text-rose-500' : 'bg-brand-50 text-brand-600')}>
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-ink">{notificationText(t, n)}</span>
                    {n.note ? <span className="mt-0.5 block text-sm text-ink-secondary">{t('cm.moderatorNote')}: {n.note}</span> : null}
                    {n.post_excerpt ? <span className="mt-0.5 block truncate text-xs text-ink-muted">«{n.post_excerpt}»</span> : null}
                    <span className="mt-0.5 block text-xs text-ink-muted">{ago(t, date, n.created_at)}</span>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </Overlay>
  )
}

function PostModal({ postId, onClose, onEdit }: { postId: number; onClose: () => void; onEdit: (post: CommunityPost) => void }) {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const query = useQuery({ queryKey: [...COMMUNITY_KEY, student.id, 'post', postId], queryFn: () => communityApi.post(student.id, postId), retry: false })
  return (
    <Overlay onClose={onClose} label={t('cm.viewPost')}>
      <SheetHeader title={t('cm.viewPost')} onClose={onClose} />
      <div className="flex-1 overflow-y-auto bg-surface-muted/40 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:p-4">
        {query.isPending ? <Skeleton className="h-48 w-full" /> : null}
        {query.isError ? <Empty>{t('cm.empty.title')}</Empty> : null}
        {query.data ? <PostCard post={query.data} defaultOpenComments onEdit={onEdit} onChanged={onClose} /> : null}
      </div>
    </Overlay>
  )
}

// ------------------------------------------------------------------ page

function FeedSkeleton() {
  return (
    <div className="space-y-4" aria-hidden>
      {[0, 1].map((i) => (
        <div key={i} className="sp-card space-y-3 p-5">
          <div className="flex items-center gap-3"><Skeleton className="size-11 rounded-full" /><div className="flex-1 space-y-2"><Skeleton className="h-3.5 w-40" /><Skeleton className="h-3 w-24" /></div></div>
          <Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-4/5" /><Skeleton className="h-44 w-full rounded-2xl" />
        </div>
      ))}
    </div>
  )
}

function PostList({ tab, category, onEdit, onNotice }: { tab: 'feed' | 'mine'; category: string; onEdit: (p: CommunityPost) => void; onNotice: (m: string) => void }) {
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const query = useInfiniteQuery({
    queryKey: [...COMMUNITY_KEY, student.id, tab, category],
    queryFn: ({ pageParam }) => (tab === 'feed' ? communityApi.feed(student.id, pageParam, category) : communityApi.mine(student.id, pageParam)),
    initialPageParam: 1,
    getNextPageParam: (last: CommunityFeedPage, pages) => (last.next ? pages.length + 1 : undefined),
    refetchOnWindowFocus: true,
  })
  const sentinel = useRef<HTMLDivElement>(null)
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = query
  useEffect(() => {
    const node = sentinel.current
    if (!node || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) void fetchNextPage()
    }, { rootMargin: '400px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  if (query.isPending) return <FeedSkeleton />
  if (query.isError) return <LoadError onRetry={() => void query.refetch()} />
  const pinned = query.data.pages[0]?.pinned ?? []
  const posts = query.data.pages.flatMap((page) => page.results)
  if (!posts.length && !pinned.length) {
    return tab === 'feed'
      ? <Empty illustration title={t('cm.empty.title')}>{t('cm.empty.text')}</Empty>
      : <Empty illustration title={t('cm.mine.empty')}>{t('cm.empty.text')}</Empty>
  }
  return (
    <div className="space-y-4">
      {[...pinned, ...posts].map((post, i) => (
        <div key={post.id} className="sp-rise" style={{ animationDelay: `${Math.min(i, 6) * 40}ms` }}>
          <PostCard post={post} onEdit={onEdit} onChanged={(m) => m && onNotice(m)} />
        </div>
      ))}
      <div ref={sentinel} />
      {hasNextPage ? (
        <button type="button" onClick={() => void fetchNextPage()} disabled={isFetchingNextPage}
          className="sp-press mx-auto block rounded-xl border border-border bg-surface px-5 py-2.5 text-sm font-semibold text-ink-secondary hover:bg-surface-muted">
          {t('cm.loadMore')}
        </button>
      ) : null}
    </div>
  )
}

/** Children's community: never indexed, even if a link leaks. */
export function useNoIndex() {
  useEffect(() => {
    const meta = document.createElement('meta')
    meta.name = 'robots'
    meta.content = 'noindex, nofollow, noarchive'
    document.head.appendChild(meta)
    return () => meta.remove()
  }, [])
}

export function StudentCommunityPage() {
  useNoIndex()
  const { student } = usePortal()
  const { t } = usePortalI18n()
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState<'feed' | 'mine'>(params.get('tab') === 'mine' ? 'mine' : 'feed')
  const [category, setCategory] = useState('')
  const [composer, setComposer] = useState<{ post?: CommunityPost } | null>(null)
  const [notifications, setNotifications] = useState(false)
  const [notice, setNotice] = useState('')
  const openPost = Number(params.get('post')) || null
  const summary = useQuery({ queryKey: [...COMMUNITY_KEY, student.id, 'summary'], queryFn: () => communityApi.summary(student.id), refetchInterval: 60_000 })
  const canPost = summary.data?.can_post ?? true
  useEffect(() => {
    if (!notice) return
    const id = window.setTimeout(() => setNotice(''), 4000)
    return () => window.clearTimeout(id)
  }, [notice])

  const setPost = (id: number | null) => {
    const next = new URLSearchParams(params)
    if (id) next.set('post', String(id))
    else next.delete('post')
    setParams(next, { replace: true })
  }
  const done = (message: string) => {
    setComposer(null)
    setNotice(message)
    setTab('mine')
  }
  const unread = summary.data?.unread ?? 0
  const pendingCount = (summary.data?.pending ?? 0) + (summary.data?.rejected ?? 0)

  return (
    <div className="mx-auto max-w-6xl">
      <PageTitle
        title={t('cm.title')}
        subtitle={t('cm.subtitle')}
        actions={
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => setNotifications(true)} aria-label={`${t('cm.notifications')}${unread ? ` (${unread})` : ''}`}
              className="sp-press relative flex size-11 items-center justify-center rounded-2xl border border-border bg-surface text-ink-secondary shadow-sm hover:text-brand-700">
              <Bell className="size-5" aria-hidden />
              {unread ? <span className="absolute -right-1 -top-1 flex min-w-5 items-center justify-center rounded-full bg-rose-500 px-1 text-[11px] font-bold text-white ring-2 ring-surface">{unread > 9 ? '9+' : unread}</span> : null}
            </button>
            <Link to={`/student/community/u/${student.id}`} aria-label={t('cm.profile.mine')}
              className="sp-press inline-flex items-center gap-2 rounded-2xl border border-border bg-surface p-1.5 text-sm font-semibold text-ink shadow-sm hover:border-brand-300 sm:pr-3.5">
              <AuthorAvatar author={{ type: 'student', name: student.full_name, photo: student.photo }} size="sm" />
              <span className="hidden sm:inline">{t('cm.profile.mine')}</span>
            </Link>
          </div>
        }
      />

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="mx-auto w-full min-w-0 max-w-2xl space-y-4">
          {canPost ? (
            <button type="button" onClick={() => setComposer({})}
              className="sp-card sp-press flex w-full items-center gap-3 px-4 py-3.5 text-left transition hover:shadow-md">
              <AuthorAvatar author={{ type: 'student', name: student.full_name, photo: student.photo }} />
              <span className="flex-1 truncate rounded-full bg-surface-muted px-4 py-2.5 text-sm text-ink-muted">{t('cm.compose.placeholder', { name: student.first_name })}</span>
              <ImagePlus className="size-5 shrink-0 text-brand-600" aria-hidden />
            </button>
          ) : (
            <p className="rounded-2xl bg-surface-muted px-4 py-3 text-sm text-ink-secondary">{t('cm.compose.cantPost')}</p>
          )}

          <div className="flex items-center gap-1 rounded-2xl bg-surface-muted p-1 text-sm font-semibold" role="tablist" aria-label={t('cm.title')}>
            {(['feed', 'mine'] as const).map((key) => (
              <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
                className={cn('flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2.5 transition', tab === key ? 'bg-surface text-ink shadow-sm' : 'text-ink-secondary')}>
                {t(key === 'feed' ? 'cm.tab.feed' : 'cm.tab.mine')}
                {key === 'mine' && pendingCount ? <span className="rounded-full bg-amber-100 px-1.5 text-xs text-amber-800">{pendingCount}</span> : null}
              </button>
            ))}
          </div>

          {tab === 'feed' ? (
            <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0" role="group" aria-label={t('cm.compose.category')}>
              {FILTERS.map((c) => (
                <button key={c || 'all'} type="button" aria-pressed={category === c} onClick={() => setCategory(c)}
                  className={cn('sp-press shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-medium transition',
                    category === c ? 'border-ink bg-ink text-white' : 'border-border bg-surface text-ink-secondary hover:border-brand-300')}>
                  {t(k(c ? `cat.${c}` : 'cat.all'))}
                </button>
              ))}
            </div>
          ) : null}

          {notice ? <p role="status" className="sp-rise rounded-2xl bg-brand-50 px-4 py-3 text-sm font-medium text-brand-800">{notice}</p> : null}

          <PostList tab={tab} category={tab === 'feed' ? category : ''} onEdit={(post) => setComposer({ post })} onNotice={setNotice} />
        </div>

        <aside className="hidden space-y-4 lg:block">
          <div className="sp-card sticky top-6 space-y-3 p-5">
            <h2 className="flex items-center gap-2 text-sm font-bold text-ink"><ShieldCheck className="size-4 text-brand-600" aria-hidden />{t('cm.policy.title')}</h2>
            <ul className="space-y-2.5 text-sm text-ink-secondary">
              {(['cm.policy.1', 'cm.policy.2', 'cm.policy.3', 'cm.policy.4'] as const).map((key) => (
                <li key={key} className="flex gap-2"><span className="mt-2 size-1.5 shrink-0 rounded-full bg-brand-500" />{t(key)}</li>
              ))}
            </ul>
            {summary.data ? (
              <dl className="grid grid-cols-2 gap-2 border-t border-border/60 pt-3 text-center">
                <div className="rounded-xl bg-surface-muted py-2"><dt className="text-xs text-ink-muted">{t('pst.approved')}</dt><dd className="text-lg font-bold text-ink">{summary.data.published}</dd></div>
                <div className="rounded-xl bg-surface-muted py-2"><dt className="text-xs text-ink-muted">{t('pst.pending')}</dt><dd className="text-lg font-bold text-ink">{summary.data.pending}</dd></div>
              </dl>
            ) : null}
          </div>
        </aside>
      </div>

      {canPost ? (
        <button type="button" onClick={() => setComposer({})} aria-label={t('cm.compose.open')}
          className="sp-press fixed bottom-[calc(5.25rem+env(safe-area-inset-bottom))] right-4 z-30 flex size-14 items-center justify-center rounded-full bg-brand-600 text-white shadow-[0_12px_28px_-8px_rgba(31,95,60,0.6)] lg:hidden">
          <Plus className="size-7" aria-hidden />
        </button>
      ) : null}

      {composer ? <Composer post={composer.post} onClose={() => setComposer(null)} onDone={done} /> : null}
      {notifications ? <NotificationsSheet onClose={() => setNotifications(false)} onOpenPost={(id) => { setNotifications(false); setPost(id) }} /> : null}
      {openPost ? <PostModal postId={openPost} onClose={() => setPost(null)} onEdit={(post) => { setPost(null); setComposer({ post }) }} /> : null}
    </div>
  )
}

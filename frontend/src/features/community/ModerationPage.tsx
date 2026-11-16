import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  EyeOff,
  Flag,
  Globe,
  ImagePlus,
  Megaphone,
  MessageCircle,
  Pin,
  PinOff,
  RotateCcw,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react'

import { moderationApi } from '@/api/community'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { Tabs } from '@/components/ui/Tabs'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'
import type { CommunityCategory, CommunityComment, CommunityPost, ModerationReport, PostStatus } from '@/types/community'
import { cn } from '@/utils/cn'

/**
 * «Сообщество» — moderation for staff (/app/community, /assistant/community).
 * Admin, assistants, team leads: everything; a trainer: their own groups (the
 * server decides). Student posts appear here PENDING and reach the feed only
 * when approved; a rejection needs a note for the student. Nothing here
 * changes student accounts.
 */

const KEY = ['community-moderation'] as const
type ModerationAction = 'approve' | 'reject' | 'hide' | 'pin' | 'to-website' | 'from-website'
type Tab = 'pending' | 'website' | 'reports' | 'approved' | 'rejected' | 'hidden' | 'announce'

const CATEGORY: Record<CommunityCategory, string> = {
  general: 'Общее', review: 'Отзыв', achievement: 'Достижение', project: 'Проект', learning_progress: 'Прогресс в учёбе', news: 'Новости',
}
const STATUS: Record<PostStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: 'Черновик', tone: 'muted' },
  pending: { label: 'На проверке', tone: 'warning' },
  approved: { label: 'Опубликовано в LMS', tone: 'success' },
  rejected: { label: 'Отклонено', tone: 'danger' },
  hidden: { label: 'Скрыто', tone: 'danger' },
}

function when(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function useInvalidate() {
  const qc = useQueryClient()
  return () => void qc.invalidateQueries({ queryKey: KEY })
}

export function CommunityModerationPage() {
  const [tab, setTab] = useState<Tab>('pending')
  const meta = useQuery({ queryKey: [...KEY, 'meta'], queryFn: moderationApi.meta, refetchInterval: 60_000 })
  const tabs = [
    { key: 'pending' as const, label: `На проверке${meta.data?.pending ? ` · ${meta.data.pending}` : ''}` },
    { key: 'reports' as const, label: `Жалобы${meta.data?.open_reports ? ` · ${meta.data.open_reports}` : ''}` },
    { key: 'website' as const, label: `Для сайта${meta.data?.website_waiting ? ` · ${meta.data.website_waiting}` : ''}` },
    { key: 'approved' as const, label: 'Опубликованные в LMS' },
    { key: 'rejected' as const, label: 'Отклонённые' },
    { key: 'hidden' as const, label: 'Скрытые' },
    { key: 'announce' as const, label: 'Объявление' },
  ]
  return (
    <div>
      <PageHeader
        title="Сообщество учеников"
        description="Публикации учеников появляются в ленте только после проверки. Ученики — дети: контакты, адреса и чужие фото не публикуются."
      />
      <Tabs aria-label="Разделы модерации" items={tabs} value={tab} onChange={setTab} />
      <div className="mt-5">
        {tab === 'reports' ? <ReportsList /> : tab === 'announce' ? <AnnouncementForm onDone={() => setTab('approved')} /> : <PostsList status={tab === 'website' ? 'approved' : tab} website={tab === 'website' ? 'waiting' : undefined} canWebsite={meta.data?.can_send_to_website ?? false} />}
      </div>
    </div>
  )
}

function PostsList({ status, website, canWebsite }: { status: PostStatus; website?: 'waiting'; canWebsite: boolean }) {
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const query = useQuery({ queryKey: [...KEY, 'posts', status, website, page, q], queryFn: () => moderationApi.posts(status, page, q, website) })
  return (
    <div className="space-y-4">
      <div className="max-w-sm"><SearchInput value={q} onChange={(v) => { setQ(v); setPage(1) }} placeholder="Поиск по тексту, ученику, группе…" /></div>
      {query.isPending ? <LoadingState label="Загружаем публикации…" /> : null}
      {query.isError ? <ErrorState onRetry={() => void query.refetch()} /> : null}
      {query.data && !query.data.results.length ? (
        <EmptyState icon={ShieldCheck} title={website ? 'Все отзывы с согласием семьи уже на сайте' : status === 'pending' ? 'Все публикации проверены' : 'Здесь пусто'} />
      ) : null}
      <div className="grid gap-4 xl:grid-cols-2">
        {query.data?.results.map((post) => <ModerationCard key={post.id} post={post} canWebsite={canWebsite} />)}
      </div>
      {query.data && query.data.count > 20 ? <Pagination page={page} pageSize={20} totalCount={query.data.count} onPageChange={setPage} /> : null}
    </div>
  )
}

function ModerationCard({ post, canWebsite }: { post: CommunityPost; canWebsite: boolean }) {
  const invalidate = useInvalidate()
  const { showToast } = useToast()
  const [noteFor, setNoteFor] = useState<'reject' | 'hide' | null>(null)
  const [note, setNote] = useState('')
  const [detail, setDetail] = useState(false)
  const act = useMutation({
    mutationFn: ({ action, body }: { action: ModerationAction; body?: object }) => moderationApi.act(post.id, action, body),
    onSuccess: (_data, { action, body }) => {
      const done = {
        approve: body && 'website' in body ? 'Одобрено и опубликовано на сайте okurmenkids.com' : 'Опубликовано',
        reject: 'Отклонено — ученик увидит комментарий', hide: 'Скрыто', pin: 'Готово',
        'to-website': 'Отзыв опубликован на сайте okurmenkids.com', 'from-website': 'Отзыв снят с сайта',
      }
      showToast(done[action], 'success')
      setNoteFor(null); setNote('')
      invalidate()
    },
    onError: (error) => showToast(extractErrorMessage(error, 'Не удалось выполнить действие'), 'error'),
  })
  const remove = useMutation({
    mutationFn: () => moderationApi.removeAnnouncement(post.id),
    onSuccess: () => { showToast('Объявление удалено', 'success'); invalidate() },
  })
  const s = STATUS[post.status]
  // An approved review the family allowed for the website — publishing it is the administrator's / director's call.
  const websiteReady = canWebsite && post.category === 'review' && post.website_consent && !post.is_announcement
  return (
    <article className="card card-body space-y-3">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-ink">{post.author.name}{post.is_announcement ? ' · объявление' : ''}</p>
          <p className="text-xs text-ink-muted">
            {[post.group?.name, post.audience === 'group' ? 'только группа' : 'вся академия', `отправлено ${when(post.moderation?.submitted_at ?? post.created_at)}`].filter(Boolean).join(' · ')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="info">{CATEGORY[post.category]}</Badge>
          <Badge tone={s.tone}>{s.label}</Badge>
          {post.is_pinned ? <Badge tone="brand">Закреплено</Badge> : null}
          {post.open_reports ? <Badge tone="danger">Жалоб: {post.open_reports}</Badge> : null}
        </div>
      </header>
      <p className="whitespace-pre-line break-words text-sm leading-relaxed text-ink">{post.text}</p>
      {post.project_url ? <a href={post.project_url} target="_blank" rel="noopener noreferrer nofollow" className="block truncate text-sm text-brand-700 underline">{post.project_url}</a> : null}
      {post.images.length ? (
        <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4">
          {post.images.map((img) => (
            <a key={img.id} href={img.large} target="_blank" rel="noreferrer" className="aspect-square overflow-hidden rounded-lg bg-surface-hover">
              <img src={img.thumb} alt="" className="size-full object-cover" loading="lazy" />
            </a>
          ))}
        </div>
      ) : null}
      {post.moderation?.note ? <p className="rounded-lg bg-surface-hover px-3 py-2 text-xs text-ink-secondary">Комментарий модератора{post.moderation.by ? ` (${post.moderation.by})` : ''}: {post.moderation.note}</p> : null}
      {post.category === 'review' && !post.is_announcement ? <WebsitePanel post={post} canWebsite={canWebsite} busy={act.isPending}
        onPublish={() => act.mutate({ action: 'to-website' })} onUnpublish={() => act.mutate({ action: 'from-website' })} /> : null}

      {noteFor ? (
        <div className="space-y-2 rounded-lg border border-border p-3">
          <label className="block text-sm font-medium text-ink" htmlFor={`note-${post.id}`}>
            {noteFor === 'reject' ? 'Что исправить (ученик увидит)' : 'Причина (ученик увидит)'}
          </label>
          <textarea id={`note-${post.id}`} className="form-control" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2">
            <Button size="sm" variant="danger" isLoading={act.isPending} disabled={noteFor === 'reject' && !note.trim()}
              onClick={() => act.mutate({ action: noteFor, body: { note } })}>{noteFor === 'reject' ? 'Отклонить' : 'Скрыть'}</Button>
            <Button size="sm" variant="ghost" onClick={() => setNoteFor(null)} leftIcon={<X className="size-4" aria-hidden />}>Отмена</Button>
          </div>
        </div>
      ) : (
        <footer className="flex flex-wrap gap-2 border-t border-border pt-3">
          {post.status === 'pending' || post.status === 'hidden' || post.status === 'rejected' ? (
            <Button size="sm" leftIcon={post.status === 'pending' ? <Check className="size-4" aria-hidden /> : <RotateCcw className="size-4" aria-hidden />}
              isLoading={act.isPending} onClick={() => act.mutate({ action: 'approve' })}>{post.status === 'pending' ? 'Одобрить' : 'Вернуть в ленту'}</Button>
          ) : null}
          {websiteReady && post.status === 'pending' ? (
            <Button size="sm" variant="secondary" leftIcon={<Globe className="size-4" aria-hidden />} isLoading={act.isPending}
              onClick={() => act.mutate({ action: 'approve', body: { website: true } })}>Одобрить и опубликовать на сайте</Button>
          ) : null}
          {post.status === 'pending' || post.status === 'approved' ? (
            !post.is_announcement ? <Button size="sm" variant="secondary" leftIcon={<X className="size-4" aria-hidden />} onClick={() => setNoteFor('reject')}>Отклонить</Button> : null
          ) : null}
          {post.status === 'approved' ? (
            <>
              <Button size="sm" variant="secondary" leftIcon={<EyeOff className="size-4" aria-hidden />} onClick={() => setNoteFor('hide')}>Скрыть</Button>
              <Button size="sm" variant="ghost" leftIcon={post.is_pinned ? <PinOff className="size-4" aria-hidden /> : <Pin className="size-4" aria-hidden />}
                onClick={() => act.mutate({ action: 'pin', body: { pinned: !post.is_pinned } })}>{post.is_pinned ? 'Открепить' : 'Закрепить'}</Button>
              {post.comments ? <Button size="sm" variant="ghost" leftIcon={<MessageCircle className="size-4" aria-hidden />} onClick={() => setDetail(true)}>Комментарии · {post.comments}</Button> : null}
            </>
          ) : null}
          {post.is_announcement ? (
            <Button size="sm" variant="ghost" leftIcon={<Trash2 className="size-4" aria-hidden />} onClick={() => { if (window.confirm('Удалить объявление?')) remove.mutate() }}>Удалить</Button>
          ) : null}
        </footer>
      )}
      {detail ? <PostDetail postId={post.id} onClose={() => setDetail(false)} /> : null}
    </article>
  )
}

/**
 * The website status of a review, apart from its LMS status: «Опубликовано в
 * LMS» only means the community feed. A review is on okurmenkids.com only when
 * this panel says «На сайте okurmenkids.com».
 */
function WebsitePanel({ post, canWebsite, busy, onPublish, onUnpublish }: {
  post: CommunityPost
  canWebsite: boolean
  busy: boolean
  onPublish: () => void
  onUnpublish: () => void
}) {
  const live = Boolean(post.website?.is_public)
  const eligible = Boolean(post.website_eligible)
  const state = live
    ? { tone: 'success' as const, badge: 'На сайте okurmenkids.com', text: 'Отзыв показывается на /testimonials, /ky/testimonials и /en/testimonials.' }
    : eligible
      ? { tone: 'warning' as const, badge: 'Не на сайте', text: post.website?.status === 'archived' ? 'Отзыв был снят с сайта.' : 'Опубликован только в LMS. Семья разрешила показать его на сайте.' }
      : post.website_consent && post.status === 'pending'
        ? { tone: 'muted' as const, badge: 'Не на сайте', text: 'Семья разрешила показать отзыв на сайте — его можно опубликовать вместе с одобрением.' }
        : post.website_consent
          ? { tone: 'muted' as const, badge: 'Не на сайте', text: 'На сайт можно только одобренный отзыв.' }
          : { tone: 'muted' as const, badge: 'Без согласия семьи', text: 'Семья не разрешила показывать этот отзыв — на сайт он не попадёт.' }
  return (
    <section aria-label="Сайт okurmenkids.com" className={cn('flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border px-3 py-2.5',
      live ? 'border-brand-200 bg-brand-50/60' : eligible ? 'border-warning/30 bg-warning-soft/40' : 'border-border bg-surface-hover/50')}>
      <Globe className={cn('size-4 shrink-0', live ? 'text-brand-600' : 'text-ink-muted')} aria-hidden />
      <span className="text-xs font-semibold text-ink">Сайт:</span>
      <Badge tone={state.tone}>{state.badge}</Badge>
      <span className="min-w-0 flex-1 basis-56 text-xs text-ink-secondary">{state.text}</span>
      {eligible && !live ? (
        canWebsite
          ? <Button size="sm" leftIcon={<Globe className="size-4" aria-hidden />} isLoading={busy} onClick={onPublish}>Опубликовать на сайте</Button>
          : <span className="text-xs font-medium text-warning">Опубликовать на сайте может директор или администратор.</span>
      ) : null}
      {live && canWebsite ? <Button size="sm" variant="ghost" onClick={onUnpublish}>Снять с сайта</Button> : null}
    </section>
  )
}

function PostDetail({ postId, onClose }: { postId: number; onClose: () => void }) {
  const query = useQuery({ queryKey: [...KEY, 'post', postId], queryFn: () => moderationApi.post(postId) })
  const invalidate = useInvalidate()
  const hide = useMutation({
    mutationFn: ({ id, hidden }: { id: number; hidden: boolean }) => moderationApi.hideComment(id, hidden),
    onSuccess: invalidate,
  })
  const row = (c: CommunityComment) => (
    <li key={c.id} className={cn('flex items-start justify-between gap-3 rounded-lg border border-border px-3 py-2', c.parent && 'ml-6')}>
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{c.author?.name ?? '—'} <span className="font-normal text-ink-muted">· {when(c.created_at)}</span></p>
        <p className={cn('whitespace-pre-line break-words text-sm', c.status !== 'visible' && 'text-ink-muted line-through')}>{c.text}</p>
        {c.open_reports ? <Badge tone="danger" className="mt-1">Жалоб: {c.open_reports}</Badge> : null}
      </div>
      {c.status !== 'deleted' ? (
        <Button size="sm" variant="ghost" onClick={() => hide.mutate({ id: c.id, hidden: c.status === 'visible' })}>
          {c.status === 'visible' ? 'Скрыть' : 'Вернуть'}
        </Button>
      ) : <Badge tone="muted">удалён автором</Badge>}
    </li>
  )
  return (
    <Modal isOpen onClose={onClose} title="Комментарии" size="lg">
      {query.isPending ? <LoadingState /> : null}
      {query.data ? (
        query.data.comment_list?.length ? (
          <ul className="space-y-2">{query.data.comment_list.flatMap((c) => [row(c), ...(c.replies ?? []).map(row)])}</ul>
        ) : <p className="text-sm text-ink-muted">Комментариев нет.</p>
      ) : null}
    </Modal>
  )
}

function ReportsList() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<'open' | 'resolved' | 'dismissed'>('open')
  const query = useQuery({ queryKey: [...KEY, 'reports', status, page], queryFn: () => moderationApi.reports(status, page) })
  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-lg bg-surface-hover p-1 text-sm">
        {(['open', 'resolved', 'dismissed'] as const).map((s) => (
          <button key={s} type="button" aria-pressed={status === s} onClick={() => { setStatus(s); setPage(1) }}
            className={cn('rounded-md px-3 py-1.5', status === s ? 'bg-surface font-semibold text-ink shadow-sm' : 'text-ink-secondary')}>
            {{ open: 'Открытые', resolved: 'Приняты меры', dismissed: 'Отклонённые' }[s]}
          </button>
        ))}
      </div>
      {query.isPending ? <LoadingState label="Загружаем жалобы…" /> : null}
      {query.isError ? <ErrorState onRetry={() => void query.refetch()} /> : null}
      {query.data && !query.data.results.length ? <EmptyState icon={Flag} title="Жалоб нет" /> : null}
      <div className="space-y-3">{query.data?.results.map((r) => <ReportRow key={r.id} report={r} />)}</div>
      {query.data && query.data.count > 20 ? <Pagination page={page} pageSize={20} totalCount={query.data.count} onPageChange={setPage} /> : null}
    </div>
  )
}

function ReportRow({ report }: { report: ModerationReport }) {
  const invalidate = useInvalidate()
  const { showToast } = useToast()
  const [detail, setDetail] = useState(false)
  const close = useMutation({
    mutationFn: (status: 'resolved' | 'dismissed') => moderationApi.closeReport(report.id, status),
    onSuccess: () => { showToast('Жалоба закрыта', 'success'); invalidate() },
  })
  const hide = useMutation({
    mutationFn: async (): Promise<void> => {
      if (report.comment) await moderationApi.hideComment(report.comment.id, true)
      else await moderationApi.act(report.post_id, 'hide', { note: 'Скрыто после жалобы.' })
    },
    onSuccess: () => { showToast('Скрыто', 'success'); invalidate() },
    onError: (error) => showToast(extractErrorMessage(error, 'Не удалось скрыть'), 'error'),
  })
  return (
    <div className="card card-body space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="danger">{report.reason_display}</Badge>
        <Badge tone="muted">{report.target === 'post' ? 'Публикация' : 'Комментарий'}</Badge>
        <span className="text-xs text-ink-muted">от {report.reporter} · {when(report.created_at)}</span>
      </div>
      {report.details ? <p className="text-sm text-ink">«{report.details}»</p> : null}
      {report.comment ? (
        <p className="rounded-lg bg-danger-soft/40 px-3 py-2 text-sm"><b>{report.comment.author?.name}:</b> {report.comment.text}</p>
      ) : null}
      <p className="line-clamp-3 text-sm text-ink-secondary">Публикация: {report.post_excerpt}</p>
      {report.status === 'open' ? (
        <div className="flex flex-wrap gap-2 pt-1">
          <Button size="sm" variant="danger" leftIcon={<EyeOff className="size-4" aria-hidden />} isLoading={hide.isPending} onClick={() => hide.mutate()}>Скрыть</Button>
          <Button size="sm" variant="secondary" onClick={() => close.mutate('resolved')}>Меры приняты</Button>
          <Button size="sm" variant="ghost" onClick={() => close.mutate('dismissed')}>Жалоба необоснованна</Button>
          <Button size="sm" variant="ghost" onClick={() => setDetail(true)}>Открыть публикацию</Button>
        </div>
      ) : null}
      {detail ? <PostDetail postId={report.post_id} onClose={() => setDetail(false)} /> : null}
    </div>
  )
}

function AnnouncementForm({ onDone }: { onDone: () => void }) {
  const meta = useQuery({ queryKey: [...KEY, 'meta'], queryFn: moderationApi.meta })
  const invalidate = useInvalidate()
  const { showToast } = useToast()
  const [text, setText] = useState('')
  const [group, setGroup] = useState<string>('')
  const [pinned, setPinned] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const academy = meta.data?.can_announce_academy ?? false
  const save = useMutation({
    mutationFn: () => moderationApi.announce({ text, group: group ? Number(group) : null, pinned, images: files }),
    onSuccess: () => { showToast('Объявление опубликовано', 'success'); invalidate(); onDone() },
    onError: (error) => showToast(extractErrorMessage(error, 'Не удалось опубликовать'), 'error'),
  })
  return (
    <form className="card card-body max-w-2xl space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
      <p className="flex items-center gap-2 text-sm text-ink-secondary"><Megaphone className="size-4 text-brand-600" aria-hidden />Официальное объявление академии публикуется сразу.</p>
      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-ink">Кому</span>
        <select className="form-control" value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Кому">
          {academy ? <option value="">Вся академия</option> : <option value="" disabled>Выберите группу</option>}
          {meta.data?.groups.map((g) => <option key={g.id} value={g.id}>Группа {g.name}</option>)}
        </select>
      </label>
      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-ink">Текст</span>
        <textarea className="form-control" rows={5} maxLength={3000} value={text} onChange={(e) => setText(e.target.value)} required />
      </label>
      <label className="flex items-center gap-2 text-sm text-ink">
        <ImagePlus className="size-4 text-ink-muted" aria-hidden />
        <input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(e) => setFiles([...(e.target.files ?? [])].slice(0, 6))} />
      </label>
      <label className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} /> Закрепить вверху ленты
      </label>
      <Button type="submit" isLoading={save.isPending} disabled={!text.trim() || (!academy && !group)} leftIcon={<Megaphone className="size-4" aria-hidden />}>Опубликовать</Button>
    </form>
  )
}

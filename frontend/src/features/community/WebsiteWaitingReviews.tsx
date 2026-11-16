import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Globe, MessageSquareQuote } from 'lucide-react'

import { moderationApi } from '@/api/community'
import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { extractErrorMessage } from '@/lib/apiError'

/**
 * «Отзывы из LMS — ждут публикации на сайте»: approved student reviews whose
 * family allowed the website, not on okurmenkids.com yet. Shown in the site
 * CMS (Управление сайтом → Отзывы), where directors and administrators —
 * the people who publish on the website — manage testimonials; the LMS
 * moderation page is out of a director's reach. Same API and rules as the
 * moderation page (apps.community): nothing without consent, one testimonial
 * per review. Renders nothing for users who cannot moderate the community.
 */
export function WebsiteWaitingReviews({ onPublished }: { onPublished?: () => void }) {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const meta = useQuery({ queryKey: ['community-moderation', 'meta'], queryFn: moderationApi.meta, retry: false })
  const waiting = useQuery({
    queryKey: ['community-moderation', 'posts', 'approved', 'waiting', 1, ''],
    queryFn: () => moderationApi.posts('approved', 1, '', 'waiting'),
    enabled: Boolean(meta.data?.website_waiting),
    retry: false,
  })
  const publish = useMutation({
    mutationFn: (postId: number) => moderationApi.act(postId, 'to-website'),
    onSuccess: () => {
      showToast('Отзыв опубликован на сайте okurmenkids.com', 'success')
      void qc.invalidateQueries({ queryKey: ['community-moderation'] })
      onPublished?.()
    },
    onError: (error) => showToast(extractErrorMessage(error, 'Не удалось опубликовать'), 'error'),
  })
  if (!meta.data?.website_waiting || !waiting.data?.results.length) return null
  const canPublish = meta.data.can_send_to_website
  return (
    <section aria-labelledby="lms-reviews" className="rounded-xl border border-warning/30 bg-warning-soft/30 p-4">
      <h2 id="lms-reviews" className="flex items-center gap-2 text-sm font-semibold text-ink">
        <MessageSquareQuote className="size-4 text-warning" aria-hidden />
        Отзывы из LMS ждут публикации на сайте · {meta.data.website_waiting}
      </h2>
      <p className="mt-1 text-xs text-ink-secondary">
        Одобрены в сообществе учеников, семья разрешила показать их на сайте. На okurmenkids.com они появятся после публикации —
        имя и первая буква фамилии, без фото.
      </p>
      <ul className="mt-3 space-y-2">
        {waiting.data.results.map((post) => (
          <li key={post.id} className="flex flex-wrap items-start gap-3 rounded-lg border border-border bg-surface p-3">
            <div className="min-w-0 flex-1 basis-64">
              <p className="text-sm font-semibold text-ink">{post.author.name}{post.group ? <span className="font-normal text-ink-muted"> · {post.group.name}</span> : null}</p>
              <p className="mt-1 line-clamp-3 whitespace-pre-line text-sm text-ink-secondary">{post.text}</p>
            </div>
            {canPublish ? (
              <Button size="sm" leftIcon={<Globe className="size-4" aria-hidden />} isLoading={publish.isPending && publish.variables === post.id}
                onClick={() => publish.mutate(post.id)}>Опубликовать на сайте</Button>
            ) : <span className="text-xs font-medium text-warning">Публикует директор или администратор.</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}

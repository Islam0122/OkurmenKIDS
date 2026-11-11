import { Fragment, type ReactNode } from 'react'
import { Lightbulb } from 'lucide-react'

import { cn } from '@/utils/cn'
import { mediaUrl } from '@/utils/media'

import { parseMarkup, type Block, type Inline } from './markup'
import { VideoEmbed } from './VideoEmbed'

function renderInline(nodes: Inline[]): ReactNode {
  return nodes.map((node, i) => {
    switch (node.type) {
      case 'text':
        return <Fragment key={i}>{node.text}</Fragment>
      case 'break':
        return <br key={i} />
      case 'bold':
        return <strong key={i} className="font-bold text-ink">{renderInline(node.children)}</strong>
      case 'italic':
        return <em key={i}>{renderInline(node.children)}</em>
      case 'link': {
        const external = /^https?:/.test(node.href)
        return (
          <a key={i} href={node.href} className="font-semibold text-brand-600 underline decoration-gold-400 decoration-2 underline-offset-4 hover:text-brand-800" {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
            {renderInline(node.children)}
          </a>
        )
      }
    }
  })
}

function renderBlock(block: Block, i: number): ReactNode {
  switch (block.type) {
    case 'heading':
      return block.level === 2 ? (
        <h2 key={i} className="mt-10 mb-4 text-2xl font-extrabold sm:text-3xl">{block.text}</h2>
      ) : (
        <h3 key={i} className="mt-8 mb-3 text-xl font-extrabold">{block.text}</h3>
      )
    case 'paragraph':
      return <p key={i} className="my-5">{renderInline(block.children)}</p>
    case 'list': {
      const Tag = block.ordered ? 'ol' : 'ul'
      return (
        <Tag key={i} className={cn('my-5 space-y-2 pl-6', block.ordered ? 'list-decimal marker:font-bold marker:text-brand-500' : 'list-disc marker:text-gold-500')}>
          {block.items.map((item, j) => <li key={j} className="pl-1">{renderInline(item)}</li>)}
        </Tag>
      )
    }
    case 'quote':
      return (
        <blockquote key={i} className="my-8 rounded-r-2xl border-l-4 border-gold-400 bg-gold-50 px-6 py-5 font-display text-lg font-semibold text-brand-800 italic sm:text-xl">
          {renderInline(block.children)}
        </blockquote>
      )
    case 'image':
      return (
        <figure key={i} className="my-8">
          <img src={mediaUrl(block.src)} alt={block.alt} loading="lazy" decoding="async" className="w-full rounded-2xl bg-brand-50" />
          {block.alt ? <figcaption className="mt-2 text-center text-sm text-muted">{block.alt}</figcaption> : null}
        </figure>
      )
    case 'video':
      return <VideoEmbed key={i} src={block.src} className="my-8" />
    case 'divider':
      return <hr key={i} className="my-10 border-line" />
    case 'note':
      return (
        <aside key={i} className="my-8 flex gap-4 rounded-2xl border border-brand-100 bg-brand-50 p-5 sm:p-6">
          <Lightbulb className="mt-1 size-5 shrink-0 text-brand-500" aria-hidden />
          <div className="[&>*:first-child]:mt-0 [&>*:last-child]:mb-0">{block.blocks.map(renderBlock)}</div>
        </aside>
      )
  }
}

/** Renders article / event / course text written in the CMS editor. */
export function RichText({ source, className }: { source: string; className?: string }) {
  const blocks = parseMarkup(source)
  if (!blocks.length) return null
  return <div className={cn('prose-site [&>*:first-child]:mt-0', className)}>{blocks.map(renderBlock)}</div>
}

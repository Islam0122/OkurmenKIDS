import { Fragment, useRef, useState, type ReactNode } from 'react'
import {
  Bold, Eye, Heading2, Heading3, Image as ImageIcon, Italic, Lightbulb, Link2, List, ListOrdered, Minus, Pencil, Quote, Youtube,
} from 'lucide-react'

import { cn } from '@/utils/cn'

import { parseMarkup, type Block, type Inline } from './markup'
import { MediaPicker } from './MediaPicker'

interface Props {
  id?: string
  value: string
  onChange: (value: string) => void
  rows?: number
  placeholder?: string
}

type Tool = { icon: typeof Bold; label: string; run: () => void }

/**
 * Редактор текста для сайта без HTML и без знания разметки: кнопки
 * вставляют заголовки, списки, ссылки, картинки из медиатеки, видео YouTube,
 * цитаты и блоки-заметки; «Просмотр» показывает, как это будет на сайте.
 */
export function RichTextEditor({ id, value, onChange, rows = 14, placeholder }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const [mode, setMode] = useState<'edit' | 'preview'>('edit')
  const [picker, setPicker] = useState(false)

  const apply = (transform: (selected: string) => { text: string; select?: [number, number] }, block = false) => {
    const el = ref.current
    if (!el) return
    const { selectionStart: start, selectionEnd: end } = el
    const before = value.slice(0, start)
    const selected = value.slice(start, end)
    const after = value.slice(end)
    const result = transform(selected)
    let text = result.text
    if (block) {
      if (before && !before.endsWith('\n\n')) text = (before.endsWith('\n') ? '\n' : '\n\n') + text
      text += after.startsWith('\n') ? '\n' : '\n\n'
    }
    const next = before + text + after
    onChange(next)
    requestAnimationFrame(() => {
      el.focus()
      const offset = before.length + (block && before && !before.endsWith('\n\n') ? (before.endsWith('\n') ? 1 : 2) : 0)
      const [s, e] = result.select ?? [result.text.length, result.text.length]
      el.setSelectionRange(offset + s, offset + e)
    })
  }

  const wrap = (mark: string, placeholder: string) =>
    apply((sel) => {
      const inner = sel || placeholder
      return { text: `${mark}${inner}${mark}`, select: [mark.length, mark.length + inner.length] }
    })
  const prefixLines = (prefix: (i: number) => string, placeholder: string) =>
    apply((sel) => {
      const lines = (sel || placeholder).split('\n')
      const text = lines.map((l, i) => `${prefix(i)}${l.replace(/^(#{2,3}\s|[-•*]\s|\d+[.)]\s|>\s?)/, '')}`).join('\n')
      return { text }
    }, true)

  const tools: (Tool | 'sep')[] = [
    { icon: Heading2, label: 'Заголовок', run: () => prefixLines(() => '## ', 'Заголовок') },
    { icon: Heading3, label: 'Подзаголовок', run: () => prefixLines(() => '### ', 'Подзаголовок') },
    'sep',
    { icon: Bold, label: 'Жирный', run: () => wrap('**', 'жирный текст') },
    { icon: Italic, label: 'Курсив', run: () => wrap('*', 'курсив') },
    {
      icon: Link2,
      label: 'Ссылка',
      run: () => {
        const url = window.prompt('Адрес ссылки (https://… или /courses)', 'https://')
        if (!url || url === 'https://') return
        apply((sel) => ({ text: `[${sel || 'текст ссылки'}](${url.trim()})`, select: [1, 1 + (sel || 'текст ссылки').length] }))
      },
    },
    'sep',
    { icon: List, label: 'Список', run: () => prefixLines(() => '- ', 'Пункт списка') },
    { icon: ListOrdered, label: 'Нумерованный список', run: () => prefixLines((i) => `${i + 1}. `, 'Первый пункт') },
    { icon: Quote, label: 'Цитата', run: () => prefixLines(() => '> ', 'Цитата') },
    { icon: Lightbulb, label: 'Блок-заметка', run: () => apply((sel) => ({ text: `:::\n${sel || 'Важная информация'}\n:::` }), true) },
    { icon: Minus, label: 'Разделитель', run: () => apply(() => ({ text: '---' }), true) },
    'sep',
    { icon: ImageIcon, label: 'Изображение из медиатеки', run: () => setPicker(true) },
    {
      icon: Youtube,
      label: 'Видео YouTube / Vimeo',
      run: () => {
        const url = window.prompt('Ссылка на видео YouTube или Vimeo')
        if (url?.trim()) apply(() => ({ text: url.trim() }), true)
      },
    },
  ]

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100">
      <div className="flex flex-wrap items-center gap-0.5 border-b border-border bg-surface-muted px-1.5 py-1" role="toolbar" aria-label="Оформление текста">
        {tools.map((tool, i) =>
          tool === 'sep' ? (
            <span key={i} className="mx-1 h-5 w-px bg-border" aria-hidden />
          ) : (
            <button key={tool.label} type="button" title={tool.label} aria-label={tool.label} disabled={mode === 'preview'} onClick={tool.run}
              className="grid size-8 place-items-center rounded-md text-ink-secondary hover:bg-surface hover:text-ink disabled:opacity-40">
              <tool.icon className="size-4" aria-hidden />
            </button>
          ),
        )}
        <div className="ml-auto flex rounded-md bg-surface p-0.5 text-xs font-medium">
          <button type="button" onClick={() => setMode('edit')} className={cn('flex items-center gap-1 rounded px-2 py-1', mode === 'edit' ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary')}>
            <Pencil className="size-3.5" aria-hidden /> Текст
          </button>
          <button type="button" onClick={() => setMode('preview')} className={cn('flex items-center gap-1 rounded px-2 py-1', mode === 'preview' ? 'bg-brand-50 text-brand-700' : 'text-ink-secondary')}>
            <Eye className="size-3.5" aria-hidden /> Просмотр
          </button>
        </div>
      </div>
      {mode === 'edit' ? (
        <textarea id={id} ref={ref} rows={rows} value={value} onChange={(e) => onChange(e.target.value)}
          className="block w-full resize-y border-0 bg-transparent px-3 py-2.5 font-mono text-sm leading-relaxed text-ink outline-none"
          placeholder={placeholder ?? 'Пишите текст. Пустая строка — новый абзац. Кнопки сверху добавляют оформление.'} />
      ) : (
        <div className="max-h-[32rem] min-h-40 overflow-y-auto px-4 py-3 text-sm leading-relaxed text-ink">
          {value.trim() ? <MarkupPreview blocks={parseMarkup(value)} /> : <p className="text-ink-muted">Пока пусто.</p>}
        </div>
      )}
      <MediaPicker
        isOpen={picker}
        onClose={() => setPicker(false)}
        onPick={(asset) => {
          setPicker(false)
          apply(() => ({ text: `![${asset.alt || asset.title}](${asset.url})` }), true)
        }}
      />
    </div>
  )
}

function inline(nodes: Inline[]): ReactNode {
  return nodes.map((n, i) => {
    if (n.type === 'text') return <Fragment key={i}>{n.text}</Fragment>
    if (n.type === 'break') return <br key={i} />
    if (n.type === 'bold') return <strong key={i}>{inline(n.children)}</strong>
    if (n.type === 'italic') return <em key={i}>{inline(n.children)}</em>
    return <a key={i} href={n.href} target="_blank" rel="noreferrer" className="text-brand-600 underline">{inline(n.children)}</a>
  })
}

/** Renders the site markup as the public site does (editor and page previews). */
export function MarkupPreview({ blocks }: { blocks: Block[] }) {
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.type) {
          case 'heading':
            return b.level === 2 ? <h2 key={i} className="mt-4 mb-2 text-lg font-bold">{b.text}</h2> : <h3 key={i} className="mt-3 mb-1.5 font-bold">{b.text}</h3>
          case 'paragraph':
            return <p key={i} className="my-2">{inline(b.children)}</p>
          case 'list': {
            const Tag = b.ordered ? 'ol' : 'ul'
            return <Tag key={i} className={cn('my-2 pl-5', b.ordered ? 'list-decimal' : 'list-disc')}>{b.items.map((it, j) => <li key={j}>{inline(it)}</li>)}</Tag>
          }
          case 'quote':
            return <blockquote key={i} className="my-3 border-l-4 border-amber-400 bg-amber-50 px-3 py-2 italic">{inline(b.children)}</blockquote>
          case 'image':
            return <figure key={i} className="my-3"><img src={b.src} alt={b.alt} className="max-h-64 rounded-lg" />{b.alt ? <figcaption className="text-xs text-ink-muted">{b.alt}</figcaption> : null}</figure>
          case 'video':
            return <div key={i} className="my-3 aspect-video max-w-md overflow-hidden rounded-lg bg-black"><iframe src={b.src} title="video" className="size-full" allowFullScreen /></div>
          case 'divider':
            return <hr key={i} className="my-4 border-border" />
          case 'note':
            return <aside key={i} className="my-3 rounded-lg border border-brand-100 bg-brand-50 px-3 py-2"><MarkupPreview blocks={b.blocks} /></aside>
        }
      })}
    </>
  )
}

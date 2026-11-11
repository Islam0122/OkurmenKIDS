import { parseInline, parseMarkup } from '@/features/content/markup'

describe('content markup', () => {
  it('parses headings, lists, quotes, videos, images and paragraphs', () => {
    const blocks = parseMarkup([
      '## Заголовок',
      'Первая строка',
      'вторая строка',
      '',
      '- один',
      '- два',
      '1. первый',
      '> цитата',
      'https://youtu.be/dQw4w9WgXcQ',
      '![Подпись](https://cdn.example.kg/a.png)',
      '---',
      ':::',
      'заметка',
      ':::',
    ].join('\n'))
    expect(blocks.map((b) => b.type)).toEqual(['heading', 'paragraph', 'list', 'list', 'quote', 'video', 'image', 'divider', 'note'])
    expect(blocks[5]).toEqual({ type: 'video', src: 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ' })
  })

  it('never produces unsafe links', () => {
    const nodes = parseInline('[x](javascript:alert(1)) **bold** [ok](https://okurmen.kg)')
    expect(nodes.some((n) => n.type === 'link' && n.href.startsWith('javascript'))).toBe(false)
    expect(nodes.find((n) => n.type === 'link')).toMatchObject({ href: 'https://okurmen.kg' })
    expect(parseMarkup('![x](javascript:alert(1))').some((b) => b.type === 'image')).toBe(false)
    expect(parseMarkup('![x](javascript:void)')).toEqual([])
  })

  it('keeps the old news format working', () => {
    expect(parseMarkup('Абзац\n\n## Итоги\n- пункт').map((b) => b.type)).toEqual(['paragraph', 'heading', 'list'])
  })
})

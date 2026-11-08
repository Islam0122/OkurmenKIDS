/** The article text as typed in the admin: blank line = new paragraph,
 * «## » = subheading, «- » = list item. Plain text only — never HTML. */
type Block = { kind: 'p'; text: string } | { kind: 'h'; text: string } | { kind: 'ul'; items: string[] }

export function parseBody(body: string): Block[] {
  const blocks: Block[] = []
  for (const chunk of body.replace(/\r\n?/g, '\n').split(/\n\s*\n/)) {
    const lines = chunk.split('\n').map((line) => line.trimEnd()).filter((line) => line.trim())
    let paragraph: string[] = []
    const flush = () => {
      if (paragraph.length) blocks.push({ kind: 'p', text: paragraph.join('\n') })
      paragraph = []
    }
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('## ')) {
        flush()
        blocks.push({ kind: 'h', text: trimmed.slice(3).trim() })
      } else if (/^[-•]\s+/.test(trimmed)) {
        flush()
        const item = trimmed.replace(/^[-•]\s+/, '')
        const last = blocks[blocks.length - 1]
        if (last?.kind === 'ul') last.items.push(item)
        else blocks.push({ kind: 'ul', items: [item] })
      } else {
        paragraph.push(trimmed)
      }
    }
    flush()
  }
  return blocks
}

export function ArticleBody({ body }: { body: string }) {
  return (
    <div className="space-y-5 text-[17px] leading-[1.8] text-zinc-700 [overflow-wrap:anywhere]">
      {parseBody(body).map((block, index) =>
        block.kind === 'h' ? (
          <h2 key={index} className="pt-3 text-2xl font-bold leading-snug tracking-tight text-pd-ink">
            {block.text}
          </h2>
        ) : block.kind === 'ul' ? (
          <ul key={index} className="space-y-2 pl-1">
            {block.items.map((item, i) => (
              <li key={i} className="flex gap-3">
                <span className="mt-[0.7em] size-1.5 shrink-0 rounded-full bg-pd-green" aria-hidden />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p key={index} className="whitespace-pre-line">
            {block.text}
          </p>
        ),
      )}
    </div>
  )
}

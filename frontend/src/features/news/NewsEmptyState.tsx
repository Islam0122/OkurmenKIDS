/** Compact "nothing here yet" state — intentionally smaller than the generic
 * EmptyState (no py-14 block): News is meant to disappear quietly, not leave
 * a big empty card sitting in the Dashboard or the full feed. */
export function NewsEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 rounded-2xl border border-dashed border-border bg-surface px-4 py-8 text-center">
      <span className="text-2xl leading-none" aria-hidden>
        📢
      </span>
      <p className="text-sm font-medium text-ink">Новостей пока нет</p>
      <p className="text-xs text-ink-secondary">Здесь будут отображаться важные объявления.</p>
    </div>
  )
}

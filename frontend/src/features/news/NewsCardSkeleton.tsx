/** Placeholder shown while the feed loads — mirrors NewsCard's own shape so nothing jumps once real cards swap in. */
export function NewsCardSkeleton() {
  return (
    <div className="animate-pulse rounded-2xl border border-border bg-surface p-4" aria-hidden>
      <div className="flex gap-3">
        <div className="size-10 shrink-0 rounded-xl bg-surface-hover sm:size-11" />
        <div className="min-w-0 flex-1 space-y-2 py-0.5">
          <div className="flex items-center justify-between gap-2">
            <div className="h-3 w-16 rounded bg-surface-hover" />
            <div className="h-3 w-14 rounded bg-surface-hover" />
          </div>
          <div className="h-4 w-2/3 rounded bg-surface-hover" />
          <div className="h-3 w-5/6 rounded bg-surface-hover" />
          <div className="h-3 w-1/3 rounded bg-surface-hover" />
        </div>
      </div>
    </div>
  )
}

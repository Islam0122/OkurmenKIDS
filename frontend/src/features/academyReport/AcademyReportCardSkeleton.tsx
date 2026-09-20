export function AcademyReportCardSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-border bg-surface p-5">
      <div className="flex items-center gap-2.5">
        <span className="size-9 rounded-lg bg-surface-hover" />
        <span className="h-4 w-32 rounded bg-surface-hover" />
      </div>
      <div className="mt-4 h-4 w-56 rounded bg-surface-hover" />
      <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
        <span className="h-4 w-24 rounded bg-surface-hover" />
        <span className="h-4 w-16 rounded bg-surface-hover" />
      </div>
      <div className="mt-3 h-8 w-full rounded-lg bg-surface-hover" />
    </div>
  )
}

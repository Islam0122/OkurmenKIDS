const KEY = 'okurmen_utm'
const FIELDS = ['utm_source', 'utm_medium', 'utm_campaign'] as const
type Utm = Partial<Record<(typeof FIELDS)[number], string>>

/** Remember the ad campaign a visitor came from (per browser session) for the lead. */
export function captureUtm(search: string) {
  const params = new URLSearchParams(search)
  const found: Utm = {}
  for (const field of FIELDS) {
    const value = params.get(field)
    if (value) found[field] = value.slice(0, 100)
  }
  if (Object.keys(found).length) {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(found))
    } catch {
      /* storage disabled */
    }
  }
}

export function storedUtm(): Utm {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) ?? '{}') as Utm
  } catch {
    return {}
  }
}

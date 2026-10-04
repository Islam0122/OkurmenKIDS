/** Client-side hints only — the backend validates the name again. */
export const NAME_MIN = 2
export const NAME_MAX = 50

export type NameError = 'required' | 'tooShort' | 'tooLong'

export function cleanName(raw: string): string {
  return raw.trim().replace(/\s+/g, ' ')
}

export function validateName(raw: string): NameError | null {
  const name = cleanName(raw)
  if (!name) return 'required'
  if (name.length < NAME_MIN) return 'tooShort'
  if (name.length > NAME_MAX) return 'tooLong'
  return null
}

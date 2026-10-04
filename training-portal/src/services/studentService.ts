import { STORAGE_KEYS, storageService } from './storageService'

/** The student's name — kept on this device only, never sent anywhere. */
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

export const studentService = {
  getName(): string {
    return storageService.read<string>(STORAGE_KEYS.studentName, '')
  },
  setName(name: string): void {
    storageService.write(STORAGE_KEYS.studentName, cleanName(name))
  },
}

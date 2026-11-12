import { extractErrorMessage } from '@/lib/apiError'

/** The server answered, but not in the format of the CMS API (an HTML page from a misconfigured proxy, `null`…). */
export class CmsFormatError extends Error {
  constructor(what: string) {
    super(`Сервер вернул ${what} в неожиданном формате. Обновите страницу; если ошибка повторится — сообщите администратору.`)
    this.name = 'CmsFormatError'
  }
}

/** The message of a failed CMS request: API errors via extractErrorMessage, format errors as they are. */
export const cmsErrorMessage = (error: unknown) => (error instanceof CmsFormatError ? error.message : extractErrorMessage(error))

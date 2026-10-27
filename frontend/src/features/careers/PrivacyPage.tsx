import { Link } from 'react-router-dom'

import { COMPANY, CONSENT_TEXT } from './content'
import { absoluteUrl, useDocumentMeta } from './useDocumentMeta'

/** /careers/privacy — условия обработки персональных данных кандидатов. */
export function CareersPrivacyPage() {
  useDocumentMeta({ title: `Обработка персональных данных — ${COMPANY.siteName}`, url: absoluteUrl('/careers/privacy') })
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <h1 className="text-2xl font-bold text-ink">Обработка персональных данных кандидатов</h1>
      <div className="mt-5 space-y-4 leading-relaxed text-ink-secondary">
        {CONSENT_TEXT.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
      </div>
      <Link to="/careers" className="mt-8 inline-flex text-sm font-medium text-brand-700 hover:underline">← К вакансиям</Link>
    </div>
  )
}

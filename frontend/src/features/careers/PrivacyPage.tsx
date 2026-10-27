import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'

import { COMPANY, CONSENT_TEXT } from './content'
import { Eyebrow } from './Eyebrow'
import { absoluteUrl, useDocumentMeta } from './useDocumentMeta'

/** /careers/privacy — условия обработки персональных данных кандидатов. */
export function CareersPrivacyPage() {
  useDocumentMeta({ title: `Обработка персональных данных — ${COMPANY.siteName}`, url: absoluteUrl('/careers/privacy') })
  return (
    <div className="mx-auto max-w-3xl px-5 py-14 sm:px-8 lg:py-20">
      <Link to="/careers" className="inline-flex items-center gap-1.5 text-[15px] font-semibold text-ok-muted hover:text-ok-indigo">
        <ArrowLeft className="size-4" aria-hidden />К вакансиям
      </Link>
      <div className="mt-8"><Eyebrow>Кандидатам</Eyebrow></div>
      <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-[-0.02em] text-ok-indigo">Обработка персональных данных кандидатов</h1>
      <div className="mt-8 space-y-5 text-[17px] leading-relaxed text-ok-ink/85">
        {CONSENT_TEXT.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
      </div>
    </div>
  )
}

import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { CheckCircle2, FileText, Paperclip, X } from 'lucide-react'
import { AxiosError } from 'axios'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useApply, useCareersFilters } from '@/hooks/useCareers'
import { extractErrorMessage } from '@/lib/apiError'
import type { ApplyInput, ApplyResult } from '@/types/careers'

import { newSubmissionToken } from './format'

type FieldName = 'full_name' | 'phone' | 'email' | 'city' | 'experience' | 'education' | 'skills' | 'cover_letter'
  | 'portfolio_url' | 'source' | 'consent' | 'resume'
type Errors = Partial<Record<FieldName, string>>

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const PHONE_RE = /^\+?[\d\s()-]{5,32}$/
const RESUME_EXT = ['pdf', 'docx']

function blank(): Omit<ApplyInput, 'submission_token' | 'resume'> {
  return { full_name: '', phone: '', email: '', city: '', experience: '', education: '', skills: '', cover_letter: '',
    portfolio_url: '', source: '', consent: false, website: '' }
}

export function validateApply(form: Omit<ApplyInput, 'submission_token'>, maxMb: number): Errors {
  const errors: Errors = {}
  const name = form.full_name.trim()
  if (name.length < 2 || !/\p{L}/u.test(name)) errors.full_name = 'Укажите фамилию и имя.'
  const digits = form.phone.replace(/\D/g, '')
  if (!form.phone.trim()) errors.phone = 'Укажите телефон.'
  else if (!PHONE_RE.test(form.phone.trim()) || digits.length < 7 || digits.length > 15) errors.phone = 'Проверьте номер телефона.'
  if (!form.email.trim()) errors.email = 'Укажите email.'
  else if (!EMAIL_RE.test(form.email.trim())) errors.email = 'Проверьте адрес электронной почты.'
  if (form.portfolio_url.trim() && !/^https?:\/\//i.test(form.portfolio_url.trim())) {
    errors.portfolio_url = 'Ссылка должна начинаться с http:// или https://.'
  }
  if (!form.consent) errors.consent = 'Нужно согласие на обработку персональных данных.'
  if (form.resume) {
    const ext = form.resume.name.split('.').pop()?.toLowerCase() ?? ''
    if (!RESUME_EXT.includes(ext)) errors.resume = 'Резюме — только в формате PDF или DOCX.'
    else if (form.resume.size > maxMb * 1024 * 1024) errors.resume = `Файл больше ${maxMb} МБ.`
    else if (form.resume.size === 0) errors.resume = 'Файл пустой.'
  }
  return errors
}

function serverErrors(error: unknown): { fields: Errors; message: string | null } {
  if (error instanceof AxiosError && error.response?.status === 400 && error.response.data && typeof error.response.data === 'object') {
    const data = error.response.data as Record<string, unknown>
    const fields: Errors = {}
    for (const [key, value] of Object.entries(data)) {
      if (key === 'detail') continue
      fields[key as FieldName] = Array.isArray(value) ? value.join(' ') : String(value)
    }
    const detail = data.detail ? (Array.isArray(data.detail) ? data.detail.join(' ') : String(data.detail)) : null
    return { fields, message: detail ?? (Object.keys(fields).length ? 'Проверьте поля формы.' : extractErrorMessage(error)) }
  }
  if (error instanceof AxiosError && error.response?.status === 429) {
    return { fields: {}, message: 'Слишком много заявок с вашего адреса. Попробуйте позже.' }
  }
  return { fields: {}, message: extractErrorMessage(error, 'Не удалось отправить заявку. Проверьте соединение и попробуйте ещё раз.') }
}

function Row({ id, label, required, hint, error, children }: { id: string; label: string; required?: boolean; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block field-label">{label}{required ? <span className="text-danger"> *</span> : null}</label>
      {children}
      {error ? <p id={`${id}-error`} className="mt-1 text-xs text-danger" role="alert">{error}</p>
        : hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  )
}

/** Отклик без регистрации. Обязательны только ФИО, телефон, email и согласие;
 * остальное — по желанию. Проверки повторяет сервер. */
export function ApplyForm({ slug, vacancyTitle }: { slug: string; vacancyTitle: string }) {
  const apply = useApply(slug)
  const filters = useCareersFilters()
  const maxMb = filters.data?.resume_max_mb ?? 5
  // Один ключ на форму: повторная отправка (двойной клик, обрыв связи) не создаст второй отклик.
  const token = useRef(newSubmissionToken())
  const fileInput = useRef<HTMLInputElement>(null)
  const [form, setForm] = useState(blank)
  const [resume, setResume] = useState<File | null>(null)
  const [errors, setErrors] = useState<Errors>({})
  const [message, setMessage] = useState<string | null>(null)
  const [done, setDone] = useState<ApplyResult | null>(null)

  const set = (key: keyof ReturnType<typeof blank>) => (e: { target: { value: string } }) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
  }
  const describedBy = (key: FieldName) => (errors[key] ? `apply-${key}-error` : undefined)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (apply.isPending) return
    setMessage(null)
    const found = validateApply({ ...form, resume }, maxMb)
    setErrors(found)
    if (Object.keys(found).length) {
      setMessage('Проверьте выделенные поля.')
      document.getElementById(`apply-${Object.keys(found)[0]}`)?.focus()
      return
    }
    try {
      const result = await apply.mutateAsync({
        ...form, full_name: form.full_name.trim(), phone: form.phone.trim(), email: form.email.trim(),
        portfolio_url: form.portfolio_url.trim(), submission_token: token.current, resume,
      })
      setDone(result)
    } catch (err) {
      const parsed = serverErrors(err)
      setErrors(parsed.fields)
      setMessage(parsed.message)
    }
  }

  if (done) {
    return (
      <div className="rounded-2xl border border-brand-200 bg-brand-50 p-6 text-center" role="status">
        <CheckCircle2 className="mx-auto size-10 text-brand-600" aria-hidden />
        <h3 className="mt-3 text-lg font-semibold text-ink">Заявка отправлена</h3>
        <p className="mt-1 text-sm text-ink-secondary">{done.message}</p>
        <p className="mt-4 text-sm text-ink-secondary">Номер заявки</p>
        <p className="font-mono text-2xl font-semibold tracking-wider text-brand-700">{done.number}</p>
        <p className="mt-4 text-xs text-ink-muted">Сохраните номер — назовите его HR, если будете уточнять статус отклика на «{vacancyTitle}».</p>
        <Link to="/careers" className="mt-5 inline-flex h-10 items-center rounded-lg border border-brand-200 bg-surface px-4 text-sm font-medium text-brand-700 hover:bg-brand-50">
          Другие вакансии
        </Link>
      </div>
    )
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-label={`Отклик на вакансию «${vacancyTitle}»`}>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Row id="apply-full_name" label="ФИО" required error={errors.full_name}>
            <Input id="apply-full_name" value={form.full_name} onChange={set('full_name')} autoComplete="name" maxLength={200}
              aria-invalid={Boolean(errors.full_name)} aria-describedby={describedBy('full_name')} placeholder="Фамилия Имя Отчество" />
          </Row>
        </div>
        <Row id="apply-phone" label="Телефон" required error={errors.phone}>
          <Input id="apply-phone" type="tel" value={form.phone} onChange={set('phone')} autoComplete="tel" maxLength={32}
            aria-invalid={Boolean(errors.phone)} aria-describedby={describedBy('phone')} placeholder="+996 555 123 456" />
        </Row>
        <Row id="apply-email" label="Электронная почта" required error={errors.email}>
          <Input id="apply-email" type="email" value={form.email} onChange={set('email')} autoComplete="email" maxLength={254}
            aria-invalid={Boolean(errors.email)} aria-describedby={describedBy('email')} placeholder="name@mail.kg" />
        </Row>
        <Row id="apply-city" label="Город проживания" error={errors.city}>
          <Input id="apply-city" value={form.city} onChange={set('city')} autoComplete="address-level2" maxLength={100} />
        </Row>
        <Row id="apply-portfolio_url" label="Портфолио или профиль" hint="LinkedIn, GitHub, Behance — по желанию" error={errors.portfolio_url}>
          <Input id="apply-portfolio_url" type="url" value={form.portfolio_url} onChange={set('portfolio_url')} placeholder="https://"
            aria-invalid={Boolean(errors.portfolio_url)} aria-describedby={describedBy('portfolio_url')} maxLength={200} />
        </Row>
      </div>
      <Row id="apply-experience" label="Опыт работы" hint="Кратко: где и кем работали" error={errors.experience}>
        <Textarea id="apply-experience" rows={3} value={form.experience} onChange={set('experience')} maxLength={3000} />
      </Row>
      <div className="grid gap-4 sm:grid-cols-2">
        <Row id="apply-education" label="Образование" error={errors.education}>
          <Textarea id="apply-education" rows={2} value={form.education} onChange={set('education')} maxLength={2000} />
        </Row>
        <Row id="apply-skills" label="Профессиональные навыки" error={errors.skills}>
          <Textarea id="apply-skills" rows={2} value={form.skills} onChange={set('skills')} maxLength={2000} />
        </Row>
      </div>
      <Row id="apply-cover_letter" label="Сопроводительное письмо" hint="Почему вам интересна эта вакансия" error={errors.cover_letter}>
        <Textarea id="apply-cover_letter" rows={4} value={form.cover_letter} onChange={set('cover_letter')} maxLength={5000} />
      </Row>
      <div className="grid gap-4 sm:grid-cols-2">
        <Row id="apply-resume" label="Резюме" hint={`PDF или DOCX, до ${maxMb} МБ — по желанию`} error={errors.resume}>
          <input ref={fileInput} id="apply-resume" type="file" className="sr-only"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(e) => { setResume(e.target.files?.[0] ?? null); setErrors((p) => ({ ...p, resume: undefined })) }}
            aria-describedby={describedBy('resume')} />
          {resume ? (
            <div className="flex h-10 items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 text-sm">
              <span className="flex min-w-0 items-center gap-2"><FileText className="size-4 shrink-0 text-brand-600" aria-hidden /><span className="truncate">{resume.name}</span></span>
              <button type="button" aria-label="Убрать файл" className="text-ink-muted hover:text-danger"
                onClick={() => { setResume(null); if (fileInput.current) fileInput.current.value = '' }}>
                <X className="size-4" aria-hidden />
              </button>
            </div>
          ) : (
            <Button type="button" variant="secondary" className="w-full" leftIcon={<Paperclip className="size-4" aria-hidden />} onClick={() => fileInput.current?.click()}>
              Прикрепить файл
            </Button>
          )}
        </Row>
        <Row id="apply-source" label="Откуда вы узнали о вакансии" error={errors.source}>
          <Select id="apply-source" value={form.source} onChange={set('source')} placeholder="Не указывать" options={filters.data?.sources ?? []} />
        </Row>
      </div>
      {/* Ловушка для ботов: скрыта от людей и программ чтения экрана. */}
      <div aria-hidden className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
        <label htmlFor="apply-website">Сайт</label>
        <input id="apply-website" tabIndex={-1} autoComplete="off" value={form.website} onChange={set('website')} />
      </div>
      <div>
        <label className="flex items-start gap-2.5 text-sm text-ink">
          <input id="apply-consent" type="checkbox" className="mt-0.5 size-4 shrink-0 accent-brand-600" checked={form.consent}
            onChange={(e) => { setForm((f) => ({ ...f, consent: e.target.checked })); setErrors((p) => ({ ...p, consent: undefined })) }}
            aria-invalid={Boolean(errors.consent)} aria-describedby={describedBy('consent')} />
          <span>
            Я согласен(на) на обработку персональных данных для рассмотрения моей кандидатуры —{' '}
            <Link to="/careers/privacy" target="_blank" className="text-brand-700 underline">условия обработки</Link>
            <span className="text-danger"> *</span>
          </span>
        </label>
        {errors.consent ? <p id="apply-consent-error" className="mt-1 text-xs text-danger" role="alert">{errors.consent}</p> : null}
      </div>
      {message ? <p className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{message}</p> : null}
      <Button type="submit" size="lg" className="w-full sm:w-auto" isLoading={apply.isPending} disabled={apply.isPending}>
        Отправить заявку
      </Button>
      <p className="text-xs text-ink-muted">Регистрация не нужна. Учётная запись не создаётся — HR свяжется с вами по указанным контактам.</p>
    </form>
  )
}

import { useState } from 'react'
import { MessageSquarePlus, MessageSquareText, Plus, Trash2 } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { surveysApi, type QuestionInput, type SurveyInput } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { FilterBar, FilterField } from '@/components/ui/FilterBar'
import { Input } from '@/components/ui/Input'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Pagination } from '@/components/ui/Pagination'
import { SearchInput } from '@/components/ui/SearchInput'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { useAssistantFormMutation, useAssistantMutation, useAssistantOptions, useSurveys } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { QuestionType, SurveyStatus } from '@/types/assistant'
import { formatDateShort } from '@/utils/format'

import { Field, FormError, ModalActions } from '../ui'

export const SURVEY_STATUS: Record<SurveyStatus, { label: string; tone: 'muted' | 'success' | 'warning' }> = {
  draft: { label: 'Черновик', tone: 'muted' },
  published: { label: 'Опубликован', tone: 'success' },
  closed: { label: 'Закрыт', tone: 'warning' },
}

const QUESTION_TYPES: { value: QuestionType; label: string }[] = [
  { value: 'single_choice', label: 'Один вариант' },
  { value: 'multiple_choice', label: 'Несколько вариантов' },
  { value: 'text', label: 'Текстовый ответ' },
]

type Target = 'group' | 'groups' | 'academy'

interface DraftQuestion {
  text: string
  question_type: QuestionType
  is_required: boolean
  options: string[]
}

const emptyQuestion = (): DraftQuestion => ({ text: '', question_type: 'single_choice', is_required: true, options: ['', ''] })

/**
 * «+ Опрос»: who it's for (one group, several groups, the whole academy),
 * the questions, and publish right away. A survey belongs to one group in
 * the existing feedback module, so «several groups» creates one survey per
 * group with the same questions.
 */
function CreateSurveyModal({ presetGroup, onClose }: { presetGroup?: string; onClose: () => void }) {
  const navigate = useNavigate()
  const { data: options } = useAssistantOptions()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [audience, setAudience] = useState<SurveyInput['audience']>('parent')
  const [visibility, setVisibility] = useState<SurveyInput['visibility_mode']>('both')
  const [target, setTarget] = useState<Target>('group')
  const [groups, setGroups] = useState<string[]>(presetGroup ? [presetGroup] : [])
  const [questions, setQuestions] = useState<DraftQuestion[]>([emptyQuestion()])
  const [publish, setPublish] = useState(true)

  const targets = target === 'academy' ? [null] : groups.map(Number)
  const mutation = useAssistantFormMutation(async () => {
    const created = []
    for (const group of targets) {
      const groupName = options?.groups.find((g) => g.id === group)?.name
      const survey = await surveysApi.create({
        title: target === 'groups' && groupName ? `${title.trim()} — ${groupName}` : title.trim(),
        description, audience, visibility_mode: visibility, group,
      })
      for (const q of questions) {
        const body: QuestionInput = { text: q.text.trim(), question_type: q.question_type, is_required: q.is_required }
        if (q.question_type !== 'text') body.options = q.options.filter((o) => o.trim()).map((text) => ({ text: text.trim() }))
        await surveysApi.addQuestion(survey.id, body)
      }
      if (publish) await surveysApi.publish(survey.id)
      created.push(survey)
    }
    return created
  }, (created) => (created.length > 1 ? `Создано опросов: ${created.length}` : 'Опрос создан'))

  const questionsValid = questions.length > 0 && questions.every((q) => q.text.trim() && (q.question_type === 'text' || q.options.filter((o) => o.trim()).length >= 2))
  const canSubmit = title.trim() !== '' && (target === 'academy' || groups.length > 0) && questionsValid
  const updateQuestion = (index: number, patch: Partial<DraftQuestion>) => setQuestions(questions.map((q, i) => (i === index ? { ...q, ...patch } : q)))
  const groupOptions = (options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))

  return (
    <Modal isOpen onClose={onClose} title="Новый опрос" size="lg" icon={<MessageSquarePlus className="size-5 text-brand-600" aria-hidden />}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (!canSubmit) return
          mutation.mutate(undefined, { onSuccess: (created) => { onClose(); if (created.length === 1) navigate(`/assistant/surveys/${created[0].id}`) } })
        }}
      >
        <Field label="Название" htmlFor="survey-title" required><Input id="survey-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={180} /></Field>
        <Field label="Описание" htmlFor="survey-description"><Textarea id="survey-description" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Кто отвечает" htmlFor="survey-audience">
            <Select id="survey-audience" value={audience} onChange={(e) => setAudience(e.target.value as SurveyInput['audience'])} options={[{ value: 'parent', label: 'Родители' }, { value: 'student', label: 'Студенты' }]} />
          </Field>
          <Field label="Анонимность" htmlFor="survey-visibility">
            <Select id="survey-visibility" value={visibility} onChange={(e) => setVisibility(e.target.value as SurveyInput['visibility_mode'])}
              options={[{ value: 'both', label: 'На выбор респондента' }, { value: 'open', label: 'Открытый' }, { value: 'anonymous', label: 'Анонимный' }]} />
          </Field>
        </div>
        <Field label="Для кого">
          <SegmentedControl aria-label="Для кого" value={target} onChange={setTarget}
            options={[{ value: 'group', label: 'Группа' }, { value: 'groups', label: 'Несколько групп' }, { value: 'academy', label: 'Вся академия' }]} />
        </Field>
        {target === 'group' ? (
          <Select aria-label="Группа" value={groups[0] ?? ''} onChange={(e) => setGroups(e.target.value ? [e.target.value] : [])} options={groupOptions} placeholder="Выберите группу" />
        ) : null}
        {target === 'groups' ? (
          <div className="grid max-h-48 grid-cols-2 gap-1 overflow-y-auto rounded-lg border border-border p-2 sm:grid-cols-3">
            {groupOptions.map((g) => (
              <label key={g.value} className="flex items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-hover">
                <input type="checkbox" className="size-4 accent-brand-500" checked={groups.includes(g.value)}
                  onChange={(e) => setGroups(e.target.checked ? [...groups, g.value] : groups.filter((v) => v !== g.value))} />
                <span className="truncate">{g.label}</span>
              </label>
            ))}
          </div>
        ) : null}

        <div>
          <p className="mb-2 text-sm font-medium text-ink">Вопросы</p>
          <div className="space-y-3">
            {questions.map((q, index) => (
              <div key={index} className="rounded-lg border border-border p-3">
                <div className="flex items-start gap-2">
                  <span className="mt-2.5 text-sm font-semibold text-ink-muted">{index + 1}.</span>
                  <div className="min-w-0 flex-1 space-y-2">
                    <Input aria-label={`Вопрос ${index + 1}`} value={q.text} onChange={(e) => updateQuestion(index, { text: e.target.value })} placeholder="Текст вопроса" />
                    <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                      <Select aria-label="Тип вопроса" value={q.question_type} onChange={(e) => updateQuestion(index, { question_type: e.target.value as QuestionType })} options={QUESTION_TYPES} />
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <input type="checkbox" className="size-4 accent-brand-500" checked={q.is_required} onChange={(e) => updateQuestion(index, { is_required: e.target.checked })} />
                        Обязательный
                      </label>
                    </div>
                    {q.question_type !== 'text' ? (
                      <div className="space-y-1.5">
                        {q.options.map((option, oi) => (
                          <div key={oi} className="flex gap-1.5">
                            <Input aria-label={`Вариант ${oi + 1}`} value={option} placeholder={`Вариант ${oi + 1}`}
                              onChange={(e) => updateQuestion(index, { options: q.options.map((o, i) => (i === oi ? e.target.value : o)) })} />
                            {q.options.length > 2 ? (
                              <button type="button" aria-label="Удалить вариант" onClick={() => updateQuestion(index, { options: q.options.filter((_, i) => i !== oi) })}
                                className="flex size-10 shrink-0 items-center justify-center rounded-lg text-ink-muted hover:bg-danger-soft hover:text-danger"><Trash2 className="size-4" aria-hidden /></button>
                            ) : null}
                          </div>
                        ))}
                        <Button type="button" size="sm" variant="ghost" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => updateQuestion(index, { options: [...q.options, ''] })}>Вариант</Button>
                      </div>
                    ) : null}
                  </div>
                  {questions.length > 1 ? (
                    <button type="button" aria-label="Удалить вопрос" onClick={() => setQuestions(questions.filter((_, i) => i !== index))}
                      className="flex size-9 shrink-0 items-center justify-center rounded-lg text-ink-muted hover:bg-danger-soft hover:text-danger"><Trash2 className="size-4" aria-hidden /></button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
          <Button type="button" variant="secondary" size="sm" className="mt-2" leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setQuestions([...questions, emptyQuestion()])}>
            Добавить вопрос
          </Button>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" className="size-4 accent-brand-500" checked={publish} onChange={(e) => setPublish(e.target.checked)} />
          Сразу опубликовать (появится ссылка для ответа)
        </label>
        <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
        <ModalActions>
          <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
          <Button type="submit" disabled={!canSubmit || mutation.isPending} isLoading={mutation.isPending}>Создать опрос</Button>
        </ModalActions>
      </form>
    </Modal>
  )
}

export function AssistantSurveysPage() {
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState<'' | SurveyStatus>(() => (['draft', 'published', 'closed'].includes(params.get('status') ?? '') ? params.get('status') as SurveyStatus : ''))
  const close = useAssistantMutation((id: number) => surveysApi.close(id), 'Опрос закрыт')
  const [group, setGroup] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const { data: options } = useAssistantOptions()
  const { data, isPending, isError, refetch } = useSurveys({ status: status || undefined, group: group ? Number(group) : undefined, search: search || undefined, page })
  const groupName = (id: number | null) => (id ? options?.groups.find((g) => g.id === id)?.name ?? `Группа #${id}` : 'Вся академия')
  const groupSize = (id: number | null) => (id ? options?.groups.find((g) => g.id === id)?.students_count : undefined)

  return (
    <div>
      <PageHeader title="Опросы" description="Обратная связь от родителей и студентов."
        actions={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setParams({ create: '1' }, { replace: true })}>Опрос</Button>} />
      <FilterBar>
        <FilterField size="lg"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1) }} placeholder="Поиск опросов…" /></FilterField>
        <FilterField><Select aria-label="Группа" value={group} placeholder="Все группы" onChange={(e) => { setGroup(e.target.value); setPage(1) }} options={(options?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))} /></FilterField>
        <SegmentedControl aria-label="Статус" value={status} onChange={(v) => { setStatus(v); setPage(1) }}
          options={[{ value: '', label: 'Все' }, { value: 'draft', label: 'Черновики' }, { value: 'published', label: 'Активные' }, { value: 'closed', label: 'Закрытые' }]} />
      </FilterBar>
      {isPending ? <LoadingState label="Загружаем опросы…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.results.length === 0 ? (
        <EmptyState icon={MessageSquareText} title="Опросов пока нет" action={<Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setParams({ create: '1' }, { replace: true })}>Создать опрос</Button>} />
      ) : null}
      {data && data.results.length > 0 ? (
        <>
          <div className="card overflow-x-auto">
            <table className="data-table min-w-[720px]">
              <thead><tr><th>Опрос</th><th>Для кого</th><th>Создан</th><th>Ответы</th><th>Статус</th><th className="text-right">Действия</th></tr></thead>
              <tbody>
                {data.results.map((survey) => {
                  const size = groupSize(survey.group)
                  return (
                    <tr key={survey.id}>
                      <td className="max-w-72"><Link to={`/assistant/surveys/${survey.id}`} className="block truncate font-medium text-ink hover:text-brand-700">{survey.title}</Link></td>
                      <td className="text-ink-secondary">{groupName(survey.group)} · {survey.audience === 'parent' ? 'родители' : 'студенты'}</td>
                      <td className="whitespace-nowrap text-ink-secondary">{formatDateShort(survey.created_at.slice(0, 10))}</td>
                      <td className="tabular-nums">{survey.response_count}{size ? <span className="text-ink-muted"> · {Math.round((survey.response_count / size) * 100)}%</span> : null}</td>
                      <td><Badge tone={SURVEY_STATUS[survey.status].tone}>{SURVEY_STATUS[survey.status].label}</Badge></td>
                      <td className="text-right whitespace-nowrap">
                        <Link to={`/assistant/surveys/${survey.id}`} className="inline-flex h-8 items-center rounded-lg px-2.5 text-sm font-medium text-brand-700 hover:bg-brand-50">
                          {survey.status === 'draft' ? 'Открыть' : 'Результаты'}
                        </Link>
                        {survey.status === 'published' ? (
                          <Button size="sm" variant="ghost" disabled={close.isPending} onClick={() => close.mutate(survey.id)}>Закрыть</Button>
                        ) : null}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-6"><Pagination page={page} pageSize={20} totalCount={data.count} onPageChange={setPage} /></div>
        </>
      ) : null}
      {params.get('create') === '1' ? <CreateSurveyModal presetGroup={params.get('group') ?? undefined} onClose={() => setParams({}, { replace: true })} /> : null}
    </div>
  )
}

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Award, Calculator, Plus } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { assistantApi } from '@/api/assistant'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorState } from '@/components/ui/ErrorState'
import { LoadingState } from '@/components/ui/LoadingState'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { ASSISTANT_KEY, useAssistantFormMutation, useAssistantScholarships } from '@/hooks/useAssistant'
import { extractErrorMessage } from '@/lib/apiError'
import type { ScholarshipPeriodRow } from '@/types/assistant'
import { formatDateShort } from '@/utils/format'

import { Field, FormError, ModalActions } from '../ui'

/**
 * «+ Стипендия»: a scholarship is always part of a period's ranking (the
 * academy's existing scholarship rules), so it is given to an eligible
 * student of a draft period. Approval and payment stay with the Admin.
 */
function AddAwardModal({ periods, onClose }: { periods: ScholarshipPeriodRow[]; onClose: () => void }) {
  const drafts = periods.filter((p) => p.status === 'draft')
  const [period, setPeriod] = useState(drafts[0] ? String(drafts[0].id) : '')
  const [evaluation, setEvaluation] = useState('')
  const candidates = useQuery({
    queryKey: [...ASSISTANT_KEY, 'scholarship-candidates', period],
    queryFn: () => assistantApi.scholarshipCandidates(Number(period)),
    enabled: period !== '',
  })
  const mutation = useAssistantFormMutation(() => assistantApi.addScholarshipAward(Number(period), Number(evaluation)), 'Стипендия назначена')

  return (
    <Modal isOpen onClose={onClose} title="Назначить стипендию" icon={<Award className="size-5 text-brand-600" aria-hidden />}>
      {drafts.length === 0 ? (
        <>
          <p className="text-sm text-ink-secondary">Нет периода в статусе «Черновик». Сначала сформируйте период — кнопка «Сформировать период».</p>
          <ModalActions><Button onClick={onClose}>Понятно</Button></ModalActions>
        </>
      ) : (
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); mutation.mutate(undefined, { onSuccess: onClose }) }}>
          <Field label="Период" htmlFor="award-period" required>
            <Select id="award-period" value={period} onChange={(e) => { setPeriod(e.target.value); setEvaluation('') }}
              options={drafts.map((p) => ({ value: String(p.id), label: `${formatDateShort(p.period_start)} – ${formatDateShort(p.period_end)}` }))} />
          </Field>
          <Field label="Студент" htmlFor="award-student" required hint="Только допущенные по правилам стипендии и ещё без стипендии в этом периоде.">
            {candidates.isPending ? <LoadingState label="Загружаем студентов…" /> : (
              <Select id="award-student" value={evaluation} onChange={(e) => setEvaluation(e.target.value)} placeholder={candidates.data?.length ? 'Выберите студента' : 'Нет допущенных студентов'}
                options={(candidates.data ?? []).map((c) => ({ value: String(c.id), label: `${c.rank ?? '—'}. ${c.student_name} · ${c.group_name}${c.overall_score ? ` · ${c.overall_score}` : ''}` }))} />
            )}
          </Field>
          <FormError message={mutation.error ? extractErrorMessage(mutation.error) : null} />
          <ModalActions>
            <Button type="button" variant="secondary" onClick={onClose}>Отмена</Button>
            <Button type="submit" disabled={!evaluation || mutation.isPending} isLoading={mutation.isPending}>Назначить</Button>
          </ModalActions>
        </form>
      )}
    </Modal>
  )
}

export function AssistantScholarshipsPage() {
  const [params, setParams] = useSearchParams()
  const { data, isPending, isError, refetch } = useAssistantScholarships()
  const [awardDay, setAwardDay] = useState('')
  const generate = useAssistantFormMutation(
    () => assistantApi.generateScholarship({ award_day: awardDay ? Number(awardDay) : null }),
    (res) => (res.created ? 'Период сформирован' : 'Этот период уже был сформирован'),
  )
  const creating = params.get('create') === '1'
  const closeCreate = () => setParams({}, { replace: true })

  return (
    <div>
      <PageHeader
        title="Стипендии"
        description="Периоды, стипендиаты и выплаты. Утверждение и выдача денег — у администратора."
        actions={
          <>
            {data && data.award_days.length > 1 ? (
              <Select aria-label="Цикл" value={awardDay} onChange={(e) => setAwardDay(e.target.value)} placeholder="Ближайший цикл"
                options={data.award_days.map((d) => ({ value: String(d), label: `${d}-го числа` }))} />
            ) : null}
            <Button variant="secondary" leftIcon={<Calculator className="size-4" aria-hidden />} isLoading={generate.isPending} disabled={generate.isPending} onClick={() => generate.mutate(undefined)}>
              Сформировать период
            </Button>
            <Button leftIcon={<Plus className="size-4" aria-hidden />} onClick={() => setParams({ create: '1' }, { replace: true })}>Стипендия</Button>
          </>
        }
      />
      {generate.error ? <div className="mb-4"><FormError message={extractErrorMessage(generate.error)} /></div> : null}
      {isPending ? <LoadingState label="Загружаем стипендии…" /> : null}
      {isError ? <ErrorState onRetry={() => void refetch()} /> : null}
      {data && data.periods.length === 0 ? (
        <EmptyState icon={Award} title="Стипендиальных периодов пока нет" description="Сформируйте первый период — система посчитает рейтинг по правилам стипендии." />
      ) : null}
      <div className="space-y-6">
        {data?.periods.map((period) => (
          <Card key={period.id}
            title={`${formatDateShort(period.period_start)} – ${formatDateShort(period.period_end)}`}
            description={`Начисление ${formatDateShort(period.evaluation_date)} · лимит ${period.max_recipients ?? 'без ограничения'}${period.award_amount ? ` · ${period.award_amount} сом` : ''}`}
            actions={<Badge tone={period.status === 'approved' ? 'success' : 'warning'}>{period.status_display}</Badge>}>
            {period.awards.length === 0 ? <p className="text-sm text-ink-secondary">Стипендиатов нет.</p> : (
              <div className="-mx-4 overflow-x-auto sm:-mx-5">
                <table className="data-table min-w-[560px]">
                  <thead><tr><th>Место</th><th>Студент</th><th>Группа</th><th>Сумма</th><th>Статус</th><th>Выплата</th></tr></thead>
                  <tbody>
                    {period.awards.map((award) => (
                      <tr key={award.id}>
                        <td className="tabular-nums">{award.rank}</td>
                        <td><Link to={`/assistant/students/${award.student.id}?tab=scholarships`} className="font-medium text-ink hover:text-brand-700">{award.student.name}</Link></td>
                        <td className="text-ink-secondary">{award.group || '—'}</td>
                        <td className="tabular-nums">{award.amount}</td>
                        <td><Badge tone={award.status === 'approved' ? 'success' : 'warning'}>{award.status_display}</Badge></td>
                        <td><Badge tone={award.payment_status === 'paid' ? 'success' : 'muted'}>{award.payment_status_display}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        ))}
      </div>
      {creating && data ? <AddAwardModal periods={data.periods} onClose={closeCreate} /> : null}
    </div>
  )
}

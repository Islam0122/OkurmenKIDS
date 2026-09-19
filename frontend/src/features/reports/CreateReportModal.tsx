import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Select } from '@/components/ui/Select'
import { useToast } from '@/components/ui/Toast'
import { useCreateMonthlyReport } from '@/hooks/useMonthlyReports'
import { extractErrorMessage } from '@/lib/apiError'
import { formatMonthYear } from '@/utils/format'

import { getYearOptions, MONTH_OPTIONS } from './months'

export interface CreateReportModalProps {
  isOpen: boolean
  onClose: () => void
}

const YEAR_OPTIONS = getYearOptions()

export function CreateReportModal({ isOpen, onClose }: CreateReportModalProps) {
  const today = new Date()
  const [year, setYear] = useState(String(today.getFullYear()))
  const [month, setMonth] = useState(String(today.getMonth() + 1))
  const [existingReportId, setExistingReportId] = useState<number | null>(null)

  const navigate = useNavigate()
  const { showToast } = useToast()
  const mutation = useCreateMonthlyReport()

  function handleClose() {
    setExistingReportId(null)
    mutation.reset()
    onClose()
  }

  function selectPeriod(nextYear: string, nextMonth: string) {
    setYear(nextYear)
    setMonth(nextMonth)
    setExistingReportId(null)
  }

  async function handleSubmit() {
    try {
      const result = await mutation.mutateAsync({ year: Number(year), month: Number(month) })
      if (result.created) {
        handleClose()
        navigate(`/app/reports/${result.report.id}`)
      } else {
        // Not an error — a report for this month already exists (spec:
        // one report per teacher per month). Offer to open it instead of
        // failing the form.
        setExistingReportId(result.report.id)
      }
    } catch (error) {
      showToast(extractErrorMessage(error, 'Не удалось создать отчёт'), 'error')
    }
  }

  function handleOpenExisting() {
    if (existingReportId === null) return
    handleClose()
    navigate(`/app/reports/${existingReportId}`)
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Создание месячного отчёта">
      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink-secondary">Год</label>
          <Select
            value={year}
            onChange={(event) => selectPeriod(event.target.value, month)}
            options={YEAR_OPTIONS}
          />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink-secondary">Месяц</label>
          <Select
            value={month}
            onChange={(event) => selectPeriod(year, event.target.value)}
            options={MONTH_OPTIONS}
          />
        </div>

        {existingReportId === null ? (
          <p className="text-xs text-ink-muted">Статистика за выбранный месяц будет рассчитана автоматически.</p>
        ) : (
          <div className="rounded-lg border border-warning-soft bg-warning-soft px-3 py-2.5 text-sm text-warning">
            Отчёт за {formatMonthYear(Number(year), Number(month))} уже существует.
          </div>
        )}
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <Button variant="secondary" onClick={handleClose}>
          Отмена
        </Button>
        {existingReportId === null ? (
          <Button onClick={() => void handleSubmit()} isLoading={mutation.isPending}>
            Создать отчёт
          </Button>
        ) : (
          <Button onClick={handleOpenExisting}>Открыть отчёт</Button>
        )}
      </div>
    </Modal>
  )
}

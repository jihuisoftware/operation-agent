import type { ReportSummary } from './analysis-types'
import { ChoiceField, type Choice } from './configuration-choices'
import { ReportDateCalendar } from './report-date-calendar'

const timeFormat = new Intl.DateTimeFormat('zh-CN', {
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
})

interface ReportVersionPickerProps {
  reports: ReportSummary[]
  selectedId?: string
  loadedReport: ReportSummary | null
  onSelect: (id: string) => void
}

export function ReportVersionPicker({ reports, selectedId, loadedReport, onSelect }: ReportVersionPickerProps) {
  // A report opened from a direct link may be older than the history catalog.
  const rows = loadedReport && loadedReport.id === selectedId && !reports.some(row => row.id === selectedId)
    ? [...reports, loadedReport] : reports
  const byDate = new Map<number | null, Choice[]>()
  let selectedDay: number | null | undefined
  for (const row of rows) {
    const date = new Date(row.created)
    const valid = Number.isFinite(date.getTime())
    const time = valid ? timeFormat.format(date) : '时间未知'
    const day = valid ? new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime() : null
    const versions = byDate.get(day) || []
    versions.push({ value: row.id, label: time })
    byDate.set(day, versions)
    if (row.id === selectedId) selectedDay = day
  }

  if (!byDate.size) return null
  const versions = selectedDay === undefined ? [] : byDate.get(selectedDay) || []
  const timeOptions = versions.map((entry, index) =>
    versions.some((other, i) => i !== index && other.label === entry.label)
      ? { ...entry, label: `${entry.label}（版本 ${versions.length - index}）` } : entry
  )

  return (
    <section className="space-y-3">
      <h2 className="font-semibold">报告版本</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <ReportDateCalendar days={[...byDate.keys()]} selectedDay={selectedDay}
          onSelect={day => {
            const latest = byDate.get(day)?.[0]
            if (latest) onSelect(latest.value)
          }} />
        <ChoiceField allowCustom={false} allowEmpty={false} label="当日版本" onChange={onSelect}
          options={timeOptions} value={selectedId || ''} />
      </div>
    </section>
  )
}

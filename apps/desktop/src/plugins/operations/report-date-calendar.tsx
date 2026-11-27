import { Button, Codicon, Popover, PopoverContent, PopoverTrigger } from '@hermes/plugin-sdk'
import { useState } from 'react'

const dayFormat = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long' })
const week = ['一', '二', '三', '四', '五', '六', '日']

interface ReportDateCalendarProps {
  days: (number | null)[]
  selectedDay: number | null | undefined
  onSelect: (day: number | null) => void
}

function CalendarMonth({ days, selectedDay, onSelect }: ReportDateCalendarProps) {
  const dates = days.flatMap(day => day === null ? [] : [new Date(day)])
  const [month, setMonth] = useState(() => new Date(selectedDay ?? dates[0]?.getTime() ?? Date.now()))
  const year = month.getFullYear()
  const monthIndex = month.getMonth()
  const years = [...new Set(dates.map(date => date.getFullYear()))]
  const availableMonths = new Set(dates.filter(date => date.getFullYear() === year).map(date => date.getMonth()))
  const leading = (new Date(year, monthIndex, 1).getDay() + 6) % 7
  const length = new Date(year, monthIndex + 1, 0).getDate()
  const available = new Set(days)

  return <>
    {dates.length > 0 && <>
      <div className="mb-2 flex gap-2">
        <select aria-label="年份" className="flex-1 rounded border bg-background p-1" value={year}
          onChange={event => {
            const chosenYear = Number(event.target.value)
            const inYear = dates.filter(day => day.getFullYear() === chosenYear)
            setMonth(inYear.find(day => day.getMonth() === monthIndex) ?? inYear[0])
          }}>
          {years.map(value => <option key={value} value={value}>{value}年</option>)}
        </select>
        <select aria-label="月份" className="flex-1 rounded border bg-background p-1" value={monthIndex + 1}
          onChange={event => setMonth(new Date(year, Number(event.target.value) - 1, 1))}>
          {Array.from({ length: 12 }, (_, i) => <option key={i} value={i + 1} disabled={!availableMonths.has(i)}>{i + 1}月</option>)}
        </select>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center">
        {week.map(label => <span key={label} aria-hidden="true" className="text-xs text-muted-foreground">{label}</span>)}
        {Array.from({ length: leading }, (_, i) => <span key={`pad-${i}`} aria-hidden="true" />)}
        {Array.from({ length }, (_, index) => {
          const day = new Date(year, monthIndex, index + 1).getTime()
          return <Button key={day} aria-label={dayFormat.format(day)} aria-pressed={day === selectedDay}
            disabled={!available.has(day)} onClick={() => onSelect(day)} size="sm"
            variant={day === selectedDay ? 'secondary' : 'ghost'}>{index + 1}</Button>
        })}
      </div>
    </>}
    {available.has(null) && <Button onClick={() => onSelect(null)} size="sm" variant="ghost">日期未知</Button>}
  </>
}

export function ReportDateCalendar(props: ReportDateCalendarProps) {
  const [open, setOpen] = useState(false)
  const { selectedDay, onSelect } = props
  const label = selectedDay === undefined ? '请选择日期' : selectedDay === null ? '日期未知' : dayFormat.format(selectedDay)
  return <div className="grid gap-2">
    <span>报告日期</span>
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button aria-label={`报告日期，${label}`} className="justify-between" variant="outline">
          {label}<Codicon name="calendar" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" aria-label="选择报告日期">
        <CalendarMonth {...props} onSelect={day => { onSelect(day); setOpen(false) }} />
      </PopoverContent>
    </Popover>
  </div>
}

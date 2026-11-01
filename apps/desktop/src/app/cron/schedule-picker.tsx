import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface SchedulePickerProps {
  preset: string
  expression: string
  onChange: (expression: string) => void
}

function PickNumber({ label, value, options, onChange }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (value: string) => void }) {
  return <div className="grid gap-2"><span className="text-sm">{label}</span>
    <Select onValueChange={onChange} value={value}>
      <SelectTrigger aria-label={label}><SelectValue /></SelectTrigger>
      <SelectContent>{options.map(option => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
    </Select>
  </div>
}

export function SchedulePicker({ preset, expression, onChange }: SchedulePickerProps) {
  if (!['daily', 'weekdays', 'weekly', 'monthly', 'hourly'].includes(preset)) { return null }
  const parts = expression.trim().split(/\s+/)

  if (parts.length !== 5) { return null }
  const update = (index: number, value: string) => onChange(parts.map((part, i) => i === index ? value : part).join(' '))

  return <div className="grid gap-3 sm:grid-cols-2">
    {preset !== 'hourly' && <label className="grid gap-2 text-sm">执行时间
      <Input onChange={event => {
        if (!event.target.value) { return }
        const [hour, minute] = event.target.value.split(':')
        onChange([String(Number(minute)), String(Number(hour)), ...parts.slice(2)].join(' '))
      }} step={60} type="time" value={`${parts[1].padStart(2, '0')}:${parts[0].padStart(2, '0')}`} />
    </label>}
    {preset === 'weekly' && <PickNumber label="每周执行日" onChange={value => update(4, value)} options={['周日', '周一', '周二', '周三', '周四', '周五', '周六'].map((label, day) => ({ label, value: String(day) }))} value={parts[4] === '7' ? '0' : parts[4]} />}
    {preset === 'monthly' && <>
      <PickNumber label="每月执行日" onChange={value => update(2, value)} options={Array.from({ length: 31 }, (_, i) => ({ label: `${i + 1} 日`, value: String(i + 1) }))} value={parts[2]} />
      <p className="text-xs text-muted-foreground">没有所选日期的月份不执行。</p>
    </>}
    {preset === 'hourly' && <PickNumber label="每小时第几分钟" onChange={value => update(0, value)} options={Array.from({ length: 60 }, (_, i) => ({ label: `${i} 分`, value: String(i) }))} value={parts[0]} />}
  </div>
}

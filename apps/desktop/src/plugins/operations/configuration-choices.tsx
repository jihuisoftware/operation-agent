import { Button, Codicon, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@hermes/plugin-sdk'
import { useId, useState } from 'react'

export interface Choice {
  value: string
  label: string
}

export const choices = (values: string[]): Choice[] => values.map(value => ({ value, label: value }))

interface ChoiceFieldProps {
  label: string
  value: string
  options: Choice[]
  onChange: (value: string) => void
  placeholder?: string
  type?: 'text' | 'number'
  max?: number
  allowCustom?: boolean
  allowEmpty?: boolean
}

/** Saved values outside the presets remain editable; rendering never applies a default. */
export function ChoiceField({ label, value, options, onChange, placeholder, type = 'text', max, allowCustom = true, allowEmpty = type !== 'number' }: ChoiceFieldProps) {
  const id = useId()
  const [custom, setCustom] = useState(false)
  const isCustom = allowCustom && (custom || (!!value && !options.some(option => option.value === value)))

  return <div className="grid gap-2">
    <label htmlFor={id}>{label}</label>
    <Select onValueChange={next => {
      setCustom(next === '__custom__')

      if (next !== '__custom__') { onChange(next === '__empty__' ? '' : next) }
    }} value={isCustom ? '__custom__' : value || '__empty__'}>
      <SelectTrigger id={id}><SelectValue /></SelectTrigger>
      <SelectContent>
        {allowEmpty && <SelectItem value="__empty__">请选择</SelectItem>}
        {options.map(option => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
        {allowCustom && <SelectItem value="__custom__">自定义／手动添加</SelectItem>}
      </SelectContent>
    </Select>
    {isCustom && <Input aria-label={`自定义${label}`} max={max} min={type === 'number' ? 0 : undefined} onChange={event => onChange(event.target.value)} placeholder={placeholder || `输入${label}`} type={type} value={value} />}
  </div>
}

export function TimeSlots({ label, values, onChange }: { label: string; values: string[]; onChange: (values: string[]) => void }) {
  const add = () => {
    const available = Array.from({ length: 24 }, (_, hour) => `${String((hour + 9) % 24).padStart(2, '0')}:00`)
    onChange([...values, available.find(time => !values.includes(time))!])
  }

  return <fieldset className="space-y-2">
    <legend className="mb-2 font-medium">{label}时间</legend>
    {values.map((value, index) => <div className="flex items-center gap-2" key={index}>
      <Input aria-label={`${label}时间 ${index + 1}`} onChange={event => onChange(values.map((time, i) => i === index ? event.target.value : time))} step={60} type="time" value={value} />
      <Button aria-label={`删除${label}时间 ${index + 1}`} disabled={values.length === 1} onClick={() => onChange(values.filter((_, i) => i !== index))} size="icon-sm" variant="ghost"><Codicon name="close" /></Button>
    </div>)}
    <Button disabled={values.length >= 12} onClick={add} size="sm" variant="outline"><Codicon name="add" />添加{label}时间</Button>
  </fieldset>
}

export function KeywordChoices({ values, onChange }: { values: string[]; onChange: (values: string[]) => void }) {
  const [draft, setDraft] = useState('')
  const suggestions = ['常见问题', '使用教程', '行业动态', '选购指南', '案例分析', '经验分享']

  const add = (value: string) => {
    const next = value.trim()

    if (next && !values.includes(next) && values.length < 100) { onChange([...values, next]) }
  }

  return <fieldset className="space-y-3">
    <legend>检索关键词（可多选）</legend>
    <div className="flex flex-wrap gap-2">{[...new Set([...suggestions, ...values])].map(word => <Button aria-pressed={values.includes(word)} disabled={values.length >= 100 && !values.includes(word)} key={word} onClick={() => values.includes(word) ? onChange(values.filter(value => value !== word)) : add(word)} size="sm" variant={values.includes(word) ? 'secondary' : 'outline'}>
      {values.includes(word) && <Codicon name="check" />}{word}
    </Button>)}</div>
    <div className="flex items-center gap-2">
      <Input aria-label="手动添加关键词" onChange={event => setDraft(event.target.value)} placeholder="添加更具体的关键词" value={draft} />
      <Button disabled={!draft.trim() || values.length >= 100} onClick={() => { add(draft); setDraft('') }} variant="outline">添加</Button>
    </div>
    <p className="text-xs text-muted-foreground">不选关键词也会按运营主题检索。</p>
  </fieldset>
}

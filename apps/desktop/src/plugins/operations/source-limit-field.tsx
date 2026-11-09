import { ChoiceField } from './configuration-choices'

interface Props { value: number; onChange: (value: number) => void }
const PRESETS = [100, 200, 300, 500, 1000, 2000, 3000, 5000, 10000]

export function SourceLimitField({ value, onChange }: Props) {
  const options = PRESETS.map(limit => ({ value: String(limit), label: `${limit.toLocaleString()} 次 / 天` }))

  if (!PRESETS.includes(value)) { options.unshift({ value: String(value), label: `当前值：${value.toLocaleString()} 次 / 天` }) }

  return <div className="space-y-2">
    <ChoiceField allowCustom={false} allowEmpty={false} label="采集每日上限" onChange={next => onChange(Number(next))} options={options} value={String(value)} />
    <p className="text-xs text-muted-foreground">可选 100–10,000 次。按正文读取尝试计数，失败与重试也占用额度；不代表每天必须采集满额。</p>
    {value < 100 && <p className="text-xs">这是历史额度，请选择 100–10,000 之间的新上限。</p>}
  </div>
}

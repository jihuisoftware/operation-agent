import { Input } from '@hermes/plugin-sdk'

export interface ModelBudget {
  mode: 'calls' | 'tokens'
  calls: number
  tokens: number
}

interface Props {
  value: ModelBudget
  onChange: (value: ModelBudget) => void
  label?: string
}

export function ModelBudgetFields({ value, onChange, label = '当前主题' }: Props) {
  const tokenMode = value.mode === 'tokens'

  return <fieldset className="space-y-3">
    <legend className="font-medium">{label}的每日模型预算</legend>
    <label className="grid gap-2">{label}预算方式
      <select aria-label={`${label}预算方式`} className="rounded border bg-background p-2" onChange={event => onChange({ ...value, mode: event.target.value as ModelBudget['mode'] })} value={value.mode}>
        <option value="calls">按调用次数</option><option value="tokens">按 Token 用量</option>
      </select>
    </label>
    <label className="grid gap-2">{tokenMode ? `${label}每日 Token 上限` : `${label}每日模型调用上限`}
      <Input max={tokenMode ? 1_000_000_000 : 1000} min={0} onChange={event => onChange({ ...value, [tokenMode ? 'tokens' : 'calls']: Number(event.target.value) })} step={1} type="number" value={tokenMode ? value.tokens : value.calls} />
    </label>
    <p className="text-xs text-muted-foreground">新计划默认每天 200 次，0 表示停止该范围的正常模型调用。开发调试不限额，用量仍会记录。</p>
    {tokenMode && <p className="text-xs text-muted-foreground">按回执累计输入（含缓存）与输出，推理不重复计算。达到上限后停止后续调用，最后一次可能超出上限。用量未返回或无法确认时暂停 Token 模式；实际费用取决于模型价格。</p>}
  </fieldset>
}

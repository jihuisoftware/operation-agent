import { Button, Input } from '@hermes/plugin-sdk'
import { useState } from 'react'

import type { AnalysisApi, AnalysisCatalog } from './analysis-types'
import { ChoiceField, choices } from './configuration-choices'

export function AnalysisSettings({ data, api, saved, failed }: { data: AnalysisCatalog; api: AnalysisApi; saved: () => void; failed: (error: string) => void }) {
  const [config, setConfig] = useState(data.settings.config)
  const [busy, setBusy] = useState(false)
  const [focus, setFocus] = useState('')

  const save = async () => {
    setBusy(true)

    try { await api('/settings', { version: data.settings.version, config }); saved() }
    catch (error) { failed(String(error)) }
    finally { setBusy(false) }
  }

  return <details className="space-y-4 border-b pb-4">
    <summary className="cursor-pointer">分析范围与周期 · 当前主题：{data.policy.topic || '未设置'}</summary>
    <div className="grid gap-4 md:grid-cols-3">
      <ChoiceField allowCustom={false} allowEmpty={false} label="分析周期" onChange={period => setConfig({ ...config, period })} options={[{ value: '1', label: '今日' }, { value: '7', label: '最近 7 天' }, { value: '30', label: '最近 30 天' }, { value: 'custom', label: '选择日期' }]} value={config.period} />
      {config.period === 'custom' && <>
        <label>开始日期<Input onChange={e => setConfig({ ...config, start: e.target.value })} type="date" value={config.start} /></label>
        <label>结束日期<Input onChange={e => setConfig({ ...config, end: e.target.value })} type="date" value={config.end} /></label>
      </>}
      <ChoiceField label="行业" onChange={industry => setConfig({ ...config, industry })} options={choices(['制造业', '零售电商', '本地生活', '内容与传媒', '专业服务', '教育培训'])} value={config.industry} />
      <ChoiceField label="地区（可选）" onChange={region => setConfig({ ...config, region })} options={choices(['中国', '华东', '华南', '华北', '海外'])} value={config.region} />
    </div>
    <ChoiceField label="关注品牌／产品／对象" onChange={setFocus} options={choices(data.policy.keywords)} value={focus} />
    <div className="flex flex-wrap gap-2">
      <Button disabled={!focus.trim() || config.focus.includes(focus.trim()) || config.focus.length >= 30} onClick={() => { setConfig({ ...config, focus: [...config.focus, focus.trim()] }); setFocus('') }} size="sm" variant="outline">添加关注对象</Button>
      {config.focus.map(item => <Button aria-label={`移除 ${item}`} key={item} onClick={() => setConfig({ ...config, focus: config.focus.filter(i => i !== item) })} size="sm" variant="secondary">{item} ×</Button>)}
    </div>
    <p className="text-xs text-muted-foreground">与前一个等长周期比较。未指定地区时不生成地域性结论；修改后需重新运行分析。</p>
    <Button disabled={busy} onClick={() => void save()}>保存分析范围</Button>
  </details>
}

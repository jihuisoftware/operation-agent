import type { PluginContext } from '@hermes/plugin-sdk'
import { useSearchParams } from 'react-router'

import { Workbench } from './workbench'

const sections: Record<string, string> = {
  rules: '目标与规则', content: '素材与内容', tasks: '任务与执行', sources: '信息采集', topics: '选题管理', reports: '每日总结'
}

export function WorkbenchPage({ ctx }: { ctx: PluginContext }) {
  const [params] = useSearchParams()
  const tab = sections[params.get('section') || 'rules'] || sections.rules

  return <Workbench ctx={ctx} initialTab={tab} key={tab} />
}

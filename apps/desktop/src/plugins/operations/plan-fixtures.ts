import { type BlueprintCatalog, type BlueprintTemplate, moduleLabels } from './blueprint-types'

export function catalog(topic = ''): BlueprintCatalog {
  const modules = Object.fromEntries(Object.keys(moduleLabels).map(m => [m, false]))

  return {
    version: 4,
    online: false,
    next_at: null,
    draft: null,
    assets: [],
    timeline: [],
    policy: {
      schema_version: 4,
      modules,
      topic,
      goal: '整理可追溯资料',
      enabled: false,
      paused: false,
      audience: '',
      brand: '',
      style: '',
      account_id: '',
      timezone: 'Asia/Shanghai',
      deadline: '',
      priority: 1,
      model_calls: 10,
      sources: [],
      rss_sources: [],
      keywords: [],
      knowledge: [],
      follow_terms: [],
      allowed: { publish: false, comment: false, reply: false, dm: false, follow: false },
      limits: { source: 3, publish: 1, comment: 2, reply: 2, dm: 1, follow: 1 },
      times: Object.fromEntries(Object.keys(modules).map(m => [m, ['09:00']]))
    },
    templates: [
      { id: 'daily', title: '每日自动运营', modules: ['research', 'content', 'report'] },
      ...Object.entries(moduleLabels).map(([id, title]) => ({ id, title, modules: [id] }))
    ].map(t => ({
      ...t,
      category: '运营',
      description: '根据目标执行',
      output: '执行记录',
      status: '未加入',
      missing: [],
      times: {}
    }))
  }
}

export const business: BlueprintTemplate = {
  id: 'business-factory',
  kind: 'business',
  title: '工厂与制造企业',
  category: '业务主题',
  description: '展示真实制造能力',
  output: '资料与草稿',
  modules: ['research', 'content', 'report'],
  status: '未加入',
  missing: [],
  times: { research: ['09:00'], content: ['09:40'], report: ['21:00'] },
  subtypes: ['源头工厂', '加工定制'],
  content_directions: ['生产流程', '质检'],
  questions: ['如何确认交期？'],
  defaults: {
    topic: '工厂与制造企业',
    goal: '展示真实生产与交付能力',
    audience: '采购负责人',
    style: '专业务实',
    keywords: ['采购需求', '质量检验']
  }
}

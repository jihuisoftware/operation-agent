import { seedTemplateDefaults } from './business-config'
import type { Policy } from './types'

export interface BlueprintTemplate {
  id: string
  title: string
  category: string
  description: string
  output: string
  modules: string[]
  status: string
  missing: string[]
  times: Record<string, string[]>
  kind?: 'scenario' | 'business'
  defaults?: Partial<Pick<Policy, 'topic' | 'goal' | 'audience' | 'style' | 'keywords'>>
  subtypes?: string[]
  content_directions?: string[]
  questions?: string[]
}
export interface PlanTime {
  module: string
  label: string
  time: string
  next_at: string
}
export interface BlueprintCatalog {
  version: number
  schedule_state?: 'ready' | 'missing' | 'paused'
  policy: Policy
  online: boolean
  templates: BlueprintTemplate[]
  timeline: PlanTime[]
  next_at: string | null
  draft: { policy: Policy; version: number } | null
  assets: { id: string; name: string; revoked: boolean }[]
}
export interface BlueprintPreview {
  version: number
  policy: Policy
  missing: Record<string, string[]>
  changes: { field: string; before: unknown; after: unknown }[]
  timeline: PlanTime[]
}
export const moduleLabels: Record<string, string> = {
  research: '信息采集',
  topics: '选题策划',
  content: '图文内容生产',
  publish: '小红书图文发布',
  comments: '评论互动',
  dm: '收到私信处理',
  follow: '条件回关',
  report: '运营日报与复盘'
}
export const actionModules: Record<string, string> = {
  publish: 'publish',
  comment: 'comments',
  reply: 'comments',
  dm: 'dm',
  follow: 'follow'
}
export const actionLabels: Record<string, string> = {
  source: '读取来源',
  publish: '发布图文',
  comment: '主动评论',
  reply: '评论回复',
  dm: '私信回复',
  follow: '条件回关'
}

export function seedBlueprint(catalog: BlueprintCatalog, template: BlueprintTemplate): Policy {
  const initial = !Object.values(catalog.policy.modules).some(Boolean)
  const policy = seedTemplateDefaults(catalog.policy, template, initial && catalog.version === 0)

  if (template.id !== 'daily' || initial) {
    for (const module of template.modules) {
      if (!policy.modules[module]) {
        for (const [action, owner] of Object.entries(actionModules)) {
          if (owner === module && action !== 'follow') {
            policy.allowed[action] = true
          }
        }
      }

      policy.modules[module] = true
    }
  }

  return policy
}

export function enableDefaultOperations(current: Policy): Policy {
  const policy = structuredClone(current)

  for (const module of ['research', 'topics', 'content', 'publish', 'comments', 'dm', 'report']) {
    policy.modules[module] = true
  }

  for (const action of ['publish', 'comment', 'reply', 'dm']) {
    policy.allowed[action] = true
  }

  return policy
}

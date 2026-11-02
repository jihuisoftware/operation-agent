import type { BlueprintCatalog } from './blueprint-types'
import { seedTemplateDefaults } from './business-config'
import type { Policy } from './types'

export type WorkMode = 'research' | 'content' | 'automatic' | 'custom'

const modes: Record<string, string[]> = {
  research: ['research', 'organize', 'analytics', 'industry', 'report'],
  content: ['research', 'organize', 'analytics', 'industry', 'topics', 'content', 'report'],
  automatic: [
    'research',
    'organize',
    'analytics',
    'industry',
    'topics',
    'content',
    'publish',
    'comments',
    'dm',
    'report'
  ]
}

export function workMode(policy: Policy): WorkMode {
  const selected = Object.keys(policy.modules)
    .filter(key => policy.modules[key])
    .sort()
    .join(',')

  return (Object.keys(modes).find(key => [...modes[key]].sort().join(',') === selected) as WorkMode) || 'custom'
}

export function selectMode(policy: Policy, mode: WorkMode): Policy {
  if (mode === 'custom') {
    return policy
  }

  return {
    ...policy,
    modules: Object.fromEntries(Object.keys(policy.modules).map(key => [key, modes[mode].includes(key)]))
  }
}

export function initialPlan(catalog: BlueprintCatalog): Policy {
  if (catalog.version > 0 || Object.values(catalog.policy.modules).some(Boolean)) {
    return structuredClone(catalog.policy)
  }

  return selectMode(structuredClone(catalog.policy), 'automatic')
}

export function selectBusiness(policy: Policy, catalog: BlueprintCatalog, business: string): Policy {
  const template = catalog.templates.find(t => t.id === business)

  return template
    ? { ...seedTemplateDefaults(policy, template, catalog.version === 0), topic: policy.topic }
    : { ...policy, business_theme: business ? 'custom' : '', business_subtype: business }
}

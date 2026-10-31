import type { BlueprintTemplate } from './blueprint-types'
import type { Policy } from './types'

const contentFields = ['topic', 'goal', 'audience', 'style'] as const

function keywordsFor(template: BlueprintTemplate, subtype: string): string[] {
  return (template.defaults?.keywords ?? []).map(word => (subtype ? `${subtype} ${word}` : word))
}

function topicFor(template: BlueprintTemplate, subtype: string): string {
  const topic = template.defaults?.topic || template.title

  return subtype ? `${topic} · ${subtype}` : topic
}

export function seedTemplateDefaults(current: Policy, template: BlueprintTemplate, fresh: boolean): Policy {
  const policy = structuredClone(current)

  for (const field of contentFields) {
    const value = template.defaults?.[field]

    // Replace only the untouched server starter style, never a saved/custom style.
    const initialStyle =
      field === 'style' && fresh && template.kind === 'business' && policy.style === '真实、清楚、具体'

    if (value && (!policy[field].trim() || initialStyle)) {
      policy[field] = value
    }
  }

  if (!policy.keywords.length && template.defaults?.keywords) {
    policy.keywords = [...template.defaults.keywords]
  }

  if (template.kind === 'business') {
    policy.business_subtype = policy.business_theme === template.id ? policy.business_subtype || '' : ''
    policy.business_theme = template.id
  }

  return policy
}

/** Explicitly replaces only positioning fields; account, evidence and authorization stay owned by the user. */
export function adoptBusinessDefaults(policy: Policy, template: BlueprintTemplate): Policy {
  const next = { ...policy }

  for (const field of contentFields) {
    const value = template.defaults?.[field]

    if (value !== undefined) {
      next[field] = value
    }
  }

  next.topic = topicFor(template, policy.business_subtype || '')
  next.keywords = keywordsFor(template, policy.business_subtype || '')

  return next
}

export function selectBusinessSubtype(policy: Policy, template: BlueprintTemplate, subtype: string): Policy {
  const previous = policy.business_subtype || ''
  const next = { ...policy, business_subtype: subtype }

  if (policy.topic === topicFor(template, previous)) {
    next.topic = topicFor(template, subtype)
  }

  if (JSON.stringify(policy.keywords) === JSON.stringify(keywordsFor(template, previous))) {
    next.keywords = keywordsFor(template, subtype)
  }

  return next
}

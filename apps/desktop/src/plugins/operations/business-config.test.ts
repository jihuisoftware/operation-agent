import { expect, it } from 'vitest'

import { seedBlueprint } from './blueprint-types'
import { adoptBusinessDefaults, selectBusinessSubtype } from './business-config'
import { business, catalog } from './plan-fixtures'

it('keeps existing business content until explicitly adopting defaults, without changing permissions or resources', () => {
  const initial = catalog('已有的产品方向')
  initial.policy.style = '我自己的写作风格'
  initial.policy.keywords = ['真实产品型号']
  initial.policy.knowledge = ['已确认的营业时间']
  initial.policy.account_id = 'real-account'
  initial.policy.times.research = ['08:30']
  const seeded = seedBlueprint(initial, business)
  expect(seeded).toMatchObject({
    topic: initial.policy.topic,
    goal: initial.policy.goal,
    style: initial.policy.style,
    keywords: initial.policy.keywords,
    limits: initial.policy.limits,
    allowed: initial.policy.allowed
  })
  const subtype = selectBusinessSubtype(seeded, business, '源头工厂')
  expect(subtype.topic).toBe(initial.policy.topic)
  expect(subtype.keywords).toEqual(initial.policy.keywords)
  const adopted = adoptBusinessDefaults(subtype, business)
  expect(adopted.goal).toBe(business.defaults?.goal)
  expect(adopted.topic).toBe('工厂与制造企业 · 源头工厂')
  expect(adopted).toMatchObject({
    account_id: initial.policy.account_id,
    knowledge: initial.policy.knowledge,
    limits: initial.policy.limits,
    allowed: initial.policy.allowed,
    times: initial.policy.times
  })
  expect(initial.policy.topic).toBe('已有的产品方向')
})

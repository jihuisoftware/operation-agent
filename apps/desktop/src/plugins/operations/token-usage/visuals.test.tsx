import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'

import type { Summary } from './types'
import { UsageTrend } from './visuals'

afterEach(cleanup)

function summary(trend: Summary['trend']): Summary {
  return {
    totals: {
      total_tokens: 100,
      prompt_tokens: 60,
      input_tokens: 60,
      output_tokens: 40,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
      reasoning_tokens: 0,
      calls: 1,
      running: 0,
      unknown: 0
    },
    groups: {},
    trend,
    since: 0,
    start: 0,
    until: 1,
    period: 'day',
    timezone: 'Asia/Shanghai',
    partial_history: false
  }
}

it('keeps a single trend bucket as a centered bar instead of a full blue block', () => {
  render(
    <UsageTrend
      compact
      data={summary([
        {
          at: '1970-01-01T00:00:01Z',
          total_tokens: 100,
          prompt_tokens: 60,
          input_tokens: 60,
          output_tokens: 40,
          cache_read_tokens: 0,
          cache_write_tokens: 0,
          reasoning_tokens: 0,
          calls: 1,
          running: 0,
          unknown: 0
        }
      ])}
    />
  )

  const bar = screen.getByRole('img').querySelector('rect')
  expect(Number(bar?.getAttribute('width'))).toBeLessThan(600)
  expect(Number(bar?.getAttribute('x'))).toBeGreaterThan(0)
})

it('shows a useful empty state when no calls have returned yet', () => {
  render(<UsageTrend compact data={summary([])} />)

  expect(screen.getByText('暂无已返回的调用记录')).toBeTruthy()
  expect(screen.queryByRole('img')).toBeNull()
})

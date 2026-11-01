import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'

import { stubMenuDomApis } from '@/test/jsdom'

import { SchedulePicker } from './schedule-picker'

beforeAll(stubMenuDomApis)
afterEach(cleanup)

it('edits a weekly time and weekday without rewriting untouched cron fields', async () => {
  const changed = vi.fn()
  function Harness() {
    const [expression, setExpression] = useState('40 18 * * 7')

    return <SchedulePicker expression={expression} onChange={next => { changed(next); setExpression(next) }} preset="weekly" />
  }
  render(<Harness />)
  expect(changed).not.toHaveBeenCalled()
  expect((screen.getByLabelText('执行时间') as HTMLInputElement).value).toBe('18:40')
  expect(screen.getByRole('combobox', { name: '每周执行日' }).textContent).toBe('周日')
  fireEvent.change(screen.getByLabelText('执行时间'), { target: { value: '08:15' } })
  expect(changed).toHaveBeenLastCalledWith('15 8 * * 7')
  fireEvent.keyDown(screen.getByRole('combobox', { name: '每周执行日' }), { key: 'ArrowDown' })
  fireEvent.click(await screen.findByRole('option', { name: '周二' }))
  expect(changed).toHaveBeenLastCalledWith('15 8 * * 2')
})

it('waits for the editor defaults and leaves advanced schedules untouched', () => {
  const onChange = vi.fn()
  const view = render(<SchedulePicker expression="" onChange={onChange} preset="daily" />)
  expect(screen.queryByLabelText('执行时间')).toBeNull()
  view.rerender(<SchedulePicker expression="0 9,17 * * 1-5" onChange={onChange} preset="custom" />)
  expect(screen.queryByLabelText('执行时间')).toBeNull()
  expect(onChange).not.toHaveBeenCalled()
})

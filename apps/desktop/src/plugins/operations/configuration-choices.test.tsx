import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'

import { ScheduleFields } from './blueprint-fields'
import { ChoiceField, choices } from './configuration-choices'
import type { Policy } from './types'

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.setPointerCapture ??= () => undefined
  Element.prototype.releasePointerCapture ??= () => undefined
  Element.prototype.scrollIntoView ??= () => undefined
})
afterEach(cleanup)

it('preserves a saved custom value and allows choosing a preset then manually extending it', async () => {
  const changed = vi.fn()

  function Harness() {
    const [value, setValue] = useState('小户型厨房收纳')

    return <ChoiceField label="运营主题" onChange={next => { changed(next); setValue(next) }} options={choices(['家居与收纳', '工厂获客'])} value={value} />
  }

  render(<Harness />)
  expect((screen.getByLabelText('自定义运营主题') as HTMLInputElement).value).toBe('小户型厨房收纳')
  expect(changed).not.toHaveBeenCalled()
  fireEvent.keyDown(screen.getByRole('combobox', { name: '运营主题' }), { key: 'ArrowDown' })
  fireEvent.click(await screen.findByRole('option', { name: '工厂获客' }))
  expect(changed).toHaveBeenLastCalledWith('工厂获客')
  expect(screen.queryByLabelText('自定义运营主题')).toBeNull()
  fireEvent.keyDown(screen.getByRole('combobox', { name: '运营主题' }), { key: 'ArrowDown' })
  fireEvent.click(await screen.findByRole('option', { name: '自定义／手动添加' }))
  expect((screen.getByLabelText('自定义运营主题') as HTMLInputElement).value).toBe('工厂获客')
  fireEvent.change(screen.getByLabelText('自定义运营主题'), { target: { value: '服装工厂获客' } })
  expect(changed).toHaveBeenLastCalledWith('服装工厂获客')
})

it('edits individual times and a date while retaining custom quotas and untouched schedule fields', () => {
  const initial = { modules: { research: true }, times: { research: ['08:45', '16:10'] },
    limits: { source: 7 }, allowed: {}, timezone: 'Asia/Shanghai', deadline: '2026-12-01T18:30:00',
    priority: 2, model_calls: 17, sources: [], rss_sources: [], keywords: ['自有关键词'] } as unknown as Policy

  const changed = vi.fn()

  function Harness() {
    const [policy, setPolicy] = useState(initial)

    return <ScheduleFields onChange={next => { changed(next); setPolicy(next) }} policy={policy} />
  }

  render(<Harness />)
  expect(changed).not.toHaveBeenCalled()
  expect(screen.getByLabelText('信息采集时间 1').getAttribute('type')).toBe('time')
  fireEvent.change(screen.getByLabelText('信息采集时间 1'), { target: { value: '09:15' } })
  expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ times: { research: ['09:15', '16:10'] }, limits: { source: 7 }, deadline: initial.deadline }))
  const date = screen.getByLabelText(/截止日期/) as HTMLInputElement
  expect(date.type).toBe('date')
  expect(date.value).toBe('2026-12-01')
  fireEvent.change(date, { target: { value: '2026-12-03' } })
  expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ deadline: '2026-12-03', limits: { source: 7 }, model_calls: 17 }))
  fireEvent.click(screen.getByRole('button', { name: '删除信息采集时间 2' }))
  expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ times: { research: ['09:15'] } }))
  expect((screen.getByRole('button', { name: '删除信息采集时间 1' }) as HTMLButtonElement).disabled).toBe(true)
})

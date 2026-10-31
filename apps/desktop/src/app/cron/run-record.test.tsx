import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type * as ApiClient from '@/api/client'
import { hermesApiAs } from '@/api/client'
import type { SessionInfo } from '@/types/hermes'

import { RunRecord } from './run-record'

vi.mock('@/api/client', async importOriginal => ({
  ...(await importOriginal<typeof ApiClient>()),
  hermesApiAs: vi.fn(),
  resolveOwnerNow: (owner: unknown) => owner
}))

const run = {
  id: 'cron_output:one:2026-10-31_18-24-51',
  title: 'COMPLETED · short preview',
  preview: 'short preview',
  source: 'cron_output',
  output_file: '2026-10-31_18-24-51.md',
  profile: 'work',
  connection_id: 'remote-one'
} as SessionInfo

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

it('loads complete text only on expansion, preserves its owner and copies the entire output', async () => {
  const output = '完整记录\n'.repeat(100) + 'END-OF-OUTPUT'
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  vi.mocked(hermesApiAs).mockResolvedValue({ output })
  render(<RunRecord jobId="one" run={run} time="18:24" />)
  expect(hermesApiAs).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: /short preview/ }))
  await screen.findByText(/END-OF-OUTPUT/)
  expect(hermesApiAs).toHaveBeenCalledWith(
    { connectionId: 'remote-one', profile: 'work' },
    { path: '/api/cron/jobs/one/output?filename=2026-10-31_18-24-51.md' }
  )
  fireEvent.click(screen.getByRole('button', { name: '复制' }))
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(output))
  fireEvent.click(screen.getByRole('button', { name: /short preview/ }))
  expect(screen.queryByText(/END-OF-OUTPUT/)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /short preview/ }))
  expect(hermesApiAs).toHaveBeenCalledTimes(1)
})

it('shows a load error and retries instead of presenting the truncated preview as complete', async () => {
  vi.mocked(hermesApiAs).mockRejectedValueOnce(new Error('读取失败')).mockResolvedValueOnce({ output: '完整内容' })
  render(<RunRecord jobId="one" run={run} time="18:24" />)
  fireEvent.click(screen.getByRole('button', { name: /short preview/ }))
  expect((await screen.findByRole('alert')).textContent).toContain('读取失败')
  expect((screen.getByRole('button', { name: '复制' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '重试' }))
  await screen.findByText('完整内容')
})

it('expands an execution failure with no output document without a network request', () => {
  const failure = { ...run, output_file: undefined, title: 'FAILED', preview: 'Fire claim lost; execution was not started.' }
  render(<RunRecord jobId="one" run={failure} time="18:24" />)
  fireEvent.click(screen.getByRole('button', { name: /FAILED/ }))
  expect(screen.getByText(failure.preview)).toBeTruthy()
  expect(hermesApiAs).not.toHaveBeenCalled()
})

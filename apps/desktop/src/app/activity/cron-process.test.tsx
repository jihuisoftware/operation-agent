import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type * as ApiClient from '@/api/client'
import { hermesApiAs } from '@/api/client'

import { CronProcess } from './cron-process'

vi.mock('@/api/client', async importOriginal => ({ ...(await importOriginal<typeof ApiClient>()), hermesApiAs: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

it('reads only the current scheduler-owned transcript through its pinned connection and Profile', async () => {
  const owner = { connectionId: 'remote', profile: 'work' }
  vi.mocked(hermesApiAs).mockResolvedValueOnce({ runs: [
    { id: 'old-run', scheduler_owned: false, source: 'cron' },
    { id: 'active-run', scheduler_owned: true, source: 'cron' }
  ] }).mockResolvedValueOnce({ messages: [{ role: 'assistant', content: '正在核对原始来源', timestamp: 1793408400 }] })
  render(<CronProcess jobId="job1" owner={owner} />)
  await screen.findByText('正在核对原始来源')
  expect(hermesApiAs).toHaveBeenNthCalledWith(2, owner, {
    path: '/api/sessions/active-run/messages?limit=500&order=latest&inline_images=false'
  })
})

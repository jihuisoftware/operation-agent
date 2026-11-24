import { QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import type * as HermesApi from '@/hermes'
import { queryClient } from '@/lib/query-client'
import { closePluginInstallRequest } from '@/store/plugin-install-request'

import { PluginInstallModal } from '../settings/plugin-install-modal'

import { CapabilitiesView } from './index'

vi.mock('@/hermes', async original => ({
  ...(await original<typeof HermesApi>()),
  getSkills: async () => [],
  getToolsets: async () => [],
  getProfiles: async () => ({ profiles: [] })
}))

afterEach(() => {
  cleanup()
  closePluginInstallRequest()
  queryClient.clear()
  vi.unstubAllGlobals()
})

it.each(['toolsets', 'plugins'])('opens the installation dialog from the %s route', async tab => {
  const api = vi.fn().mockResolvedValue({ entries: [] })
  vi.stubGlobal('hermesDesktop', { api })
  render(
    <MemoryRouter initialEntries={[`/capabilities?tab=${tab}`]}>
      <QueryClientProvider client={queryClient}>
        <CapabilitiesView fixedProfile="research" />
        <PluginInstallModal />
      </QueryClientProvider>
    </MemoryRouter>
  )

  if (tab === 'toolsets') {
    fireEvent.click(screen.getByRole('button', { name: '管理插件' }))
  }
  fireEvent.click(await screen.findByRole('button', { name: '从 Git 安装' }))
  expect(await screen.findByRole('dialog')).toBeTruthy()
  expect(api).toHaveBeenCalledWith(expect.objectContaining({ path: '/api/dashboard/plugins/catalog', profile: 'research' }))
})

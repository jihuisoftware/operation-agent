import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { $desktopOnboarding, closeManualOnboarding, type OnboardingContext } from '@/store/onboarding'
import { makeOAuthProvider } from '@/test/oauth-provider'

import { Picker } from '.'

afterEach(() => {
  cleanup()
  closeManualOnboarding()
  vi.unstubAllGlobals()
})

it.each([
  ['Kimi（中国区）', 'KIMI_CN_API_KEY', 'kimi-coding-cn'],
  ['DeepSeek', 'DEEPSEEK_API_KEY', 'deepseek'],
  ['Kimi（国际区）', 'KIMI_API_KEY', 'kimi-coding']
])('connects %s to its own model even when Nous is first in the catalog', async (name, envKey, provider) => {
  const api = vi.fn(async ({ path }: { path: string }) => {
    if (path.startsWith('/api/model/options')) {
      return {
        providers: [
          { slug: 'nous', name: 'Nous Portal', models: ['nous-fixture'] },
          { slug: provider, name, models: ['direct-fixture'], key_env: envKey, auth_type: 'api_key' }
        ]
      }
    }

    if (path.startsWith('/api/model/recommended-default')) {
      return { model: 'direct-fixture' }
    }

    return { ok: true }
  })

  vi.stubGlobal('hermesDesktop', { api })

  const requestGateway = vi.fn(
    async (method: string) => (method === 'setup.status' ? { provider_configured: true } : { ok: true }) as never
  )

  const ctx: OnboardingContext = { requestGateway, scope: { profile: 'writing' } }
  $desktopOnboarding.set({
    ...$desktopOnboarding.get(),
    manual: true,
    mode: 'oauth',
    flow: { status: 'idle' },
    localEndpoint: false,
    providers: [makeOAuthProvider('nous', 'Nous Portal')]
  })
  render(<Picker ctx={ctx} />)

  // Both direct providers are reachable without expanding "Other providers".
  expect(screen.getByRole('button', { name: /^DeepSeek/ })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: name === 'DeepSeek' ? /^DeepSeek/ : /^Kimi（中国区）/ }))

  if (provider === 'kimi-coding') {
    fireEvent.click(screen.getByRole('button', { name: /^Kimi（国际区）/ }))
  }

  fireEvent.change(screen.getByPlaceholderText('粘贴 API 密钥'), { target: { value: 'fixture-key' } })
  fireEvent.click(screen.getByRole('button', { name: '连接' }))

  await waitFor(() =>
    expect($desktopOnboarding.get().flow).toMatchObject({
      status: 'confirming_model',
      providerSlug: provider,
      currentModel: 'direct-fixture'
    })
  )
  expect(api).toHaveBeenCalledWith(
    expect.objectContaining({
      path: '/api/env',
      profile: 'writing',
      body: expect.objectContaining({ key: envKey, value: 'fixture-key', provider_setup: true })
    })
  )
  expect(requestGateway).toHaveBeenCalledWith('setup.runtime_check', expect.objectContaining({ provider }))
  expect(api.mock.calls.some(([request]) => request.path === '/api/model/set')).toBe(false)
})

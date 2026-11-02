import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { $desktopOnboarding, type DesktopOnboardingState, type OnboardingContext } from '@/store/onboarding'
import { makeOAuthProvider } from '@/test/oauth-provider'
import type { OAuthProvider } from '@/types/hermes'

import { ApiKeyForm, Picker } from '.'

function setProviders(providers: OAuthProvider[]) {
  $desktopOnboarding.set({
    configured: false,
    flow: { status: 'idle' },
    mode: 'oauth',
    providers,
    reason: null,
    requested: false,
    firstRunSkipped: false,
    manual: false,
    localEndpoint: false,
    freeTierReady: false
  } satisfies DesktopOnboardingState)
}

const ctx: OnboardingContext = { requestGateway: async () => undefined as never }

afterEach(() => {
  cleanup()

  try {
    window.localStorage.clear()
  } catch {
    // jsdom localStorage should always be present; ignore if not.
  }

  $desktopOnboarding.set({
    configured: null,
    flow: { status: 'idle' },
    mode: 'oauth',
    providers: null,
    reason: null,
    requested: false,
    firstRunSkipped: false,
    manual: false,
    localEndpoint: false,
    freeTierReady: false
  })
})

describe('onboarding Picker', () => {
  it('hides retired providers from a backend response and keeps extensions visible', () => {
    setProviders([
      makeOAuthProvider('anthropic', 'Anthropic Claude'),
      makeOAuthProvider('nous', 'Nous Portal'),
      makeOAuthProvider('qwen-oauth', 'Qwen Code'),
      makeOAuthProvider('private-extension', '企业模型服务')
    ])
    render(<Picker ctx={ctx} />)

    expect(screen.queryByText('Nous Portal')).toBeNull()
    expect(screen.queryByText('Qwen Code')).toBeNull()
    expect(screen.queryByText('推荐')).toBeNull()
    expect(screen.getByText('Fireworks AI')).toBeTruthy()
    expect(screen.getByText('Anthropic（Claude）')).toBeTruthy()
    expect(screen.getByText('企业模型服务')).toBeTruthy()
  })

  it('shows every provider directly when Nous Portal is absent', () => {
    setProviders([
      makeOAuthProvider('anthropic', 'Anthropic Claude'),
      makeOAuthProvider('openai-codex', 'OpenAI Codex / ChatGPT')
    ])
    render(<Picker ctx={ctx} />)

    expect(screen.getByText('Fireworks AI')).toBeTruthy()
    expect(screen.getByText('Anthropic（Claude）')).toBeTruthy()
    expect(screen.getByText('ChatGPT / Codex 订阅')).toBeTruthy()
    expect(screen.queryByText('其他登录选项')).toBeNull()
    expect(screen.queryByText('推荐')).toBeNull()
  })

  it('offers "choose later" on first run and persists the skip', () => {
    setProviders([makeOAuthProvider('nous', 'Nous Portal')])
    render(<Picker ctx={ctx} />)

    const skip = screen.getByRole('button', { name: '稍后再选择提供方' })

    fireEvent.click(skip)

    expect($desktopOnboarding.get().firstRunSkipped).toBe(true)
    expect(window.localStorage.getItem('hermes-onboarding-skipped-v1')).toBe('1')
  })

  it('hides "choose later" in manual (add-provider) mode', () => {
    setProviders([makeOAuthProvider('nous', 'Nous Portal')])
    $desktopOnboarding.set({ ...$desktopOnboarding.get(), manual: true })
    render(<Picker ctx={ctx} />)

    expect(screen.queryByRole('button', { name: '稍后再选择提供方' })).toBeNull()
  })
})

describe('ApiKeyForm manual local-model fallback', () => {
  it('reveals the model-name input only after the endpoint enumerates no models, then forwards the name', async () => {
    // First Connect: reachable endpoint, empty /v1/models — the wizard must ask
    // for a manual model name instead of dead-ending. Second Connect: the typed
    // name is forwarded as the 5th onSave argument.
    const onSave = vi
      .fn<
        (
          envKey: string,
          value: string,
          name: string,
          apiKey?: string,
          modelName?: string
        ) => Promise<{ message?: string; needsModelInput?: boolean; ok: boolean }>
      >()
      .mockResolvedValueOnce({
        ok: false,
        needsModelInput: true,
        message: "Connected, but it didn't enumerate any models at /v1/models."
      })
      .mockResolvedValueOnce({ ok: true })

    render(<ApiKeyForm canGoBack={false} initialEnvKey="OPENAI_BASE_URL" onBack={() => undefined} onSave={onSave} />)

    fireEvent.change(screen.getByPlaceholderText('http://127.0.0.1:8000/v1'), {
      target: { value: 'https://api.cohere.ai/compatibility/v1' }
    })

    // Hidden on the happy path — discovery hasn't failed yet.
    expect(screen.queryByPlaceholderText('模型名称（例如 command-a-plus-05-2026）')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '连接' }))

    await waitFor(() => {
      expect(screen.getByPlaceholderText('模型名称（例如 command-a-plus-05-2026）')).toBeTruthy()
    })

    fireEvent.change(screen.getByPlaceholderText('模型名称（例如 command-a-plus-05-2026）'), {
      target: { value: 'command-a-plus-05-2026' }
    })
    fireEvent.click(screen.getByRole('button', { name: '连接' }))

    await waitFor(() => {
      // apiKey is the (empty) local-key field, forwarded as-is for the local option.
      expect(onSave).toHaveBeenLastCalledWith(
        'OPENAI_BASE_URL',
        'https://api.cohere.ai/compatibility/v1',
        '本地模型 / 自定义接口',
        '',
        'command-a-plus-05-2026'
      )
    })
  })
})

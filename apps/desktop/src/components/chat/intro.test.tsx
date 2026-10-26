import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import { zh } from '@/i18n/zh'

import { Intro } from './intro'
import stock from './intro-copy.jsonl?raw'

function Fixture({ personality, seed = 0 }: { personality?: string; seed?: number }) {
  return (
    <I18nProvider>
      <Intro personality={personality} seed={seed} />
    </I18nProvider>
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('renders each stock greeting in Chinese at the same personality and rotation position', () => {
  vi.spyOn(Math, 'random').mockReturnValue(0)

  const entries = stock
    .trim()
    .split('\n')
    .map(line => JSON.parse(line) as { personality: string; body: string })

  const { container, rerender } = render(<Fixture />)
  const indices = new Map<string, number>()

  for (const entry of entries) {
    const seed = indices.get(entry.personality) ?? 0
    indices.set(entry.personality, seed + 1)
    rerender(<Fixture personality={entry.personality} seed={seed} />)
    const body = container.querySelector('[data-slot="aui_intro"] > div > p:last-child')!.textContent
    expect(body).toBe(zh.intro.stock[entry.personality][seed])
    expect(body).toMatch(/[\u3400-\u9fff]/)
  }
})

it('keeps the user-supplied personality name in the Chinese fallback greeting', () => {
  vi.spyOn(Math, 'random').mockReturnValue(0)
  const { container } = render(<Fixture personality="My Custom Voice" seed={4} />)
  const body = container.querySelector('[data-slot="aui_intro"] > div > p:last-child')!.textContent
  expect(body).toContain('My Custom Voice')
  expect(body).toMatch(/[\u3400-\u9fff]/)
})

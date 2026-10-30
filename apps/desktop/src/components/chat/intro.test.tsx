import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { I18nProvider, registerAppLocale } from '@/i18n'
import { resetAppLocaleRegistry } from '@/i18n/registry'
import { zh } from '@/i18n/zh'

import { Intro } from './intro'

function Fixture({ personality, seed = 0 }: { personality?: string; seed?: number }) {
  return (
    <I18nProvider>
      <Intro personality={personality} seed={seed} />
    </I18nProvider>
  )
}

afterEach(() => {
  cleanup()
  resetAppLocaleRegistry()
  vi.restoreAllMocks()
})

it('rotates Chinese greetings and keeps the same greeting across rerenders', () => {
  vi.spyOn(Math, 'random').mockReturnValue(0)
  const { container, rerender } = render(<Fixture />)
  const body = () => container.querySelector('[data-slot="aui_intro"] > div > p:last-child')!.textContent

  expect(body()).toBe(zh.intro.stock.none[0])
  rerender(<Fixture />)
  expect(body()).toBe(zh.intro.stock.none[0])
  rerender(<Fixture seed={1} />)
  expect(body()).toBe(zh.intro.stock.none[1])
  rerender(<Fixture seed={zh.intro.stock.none.length} />)
  expect(body()).toBe(zh.intro.stock.none[0])
})

it('keeps a Chinese greeting when an overlay supplies an empty rotation', () => {
  registerAppLocale('zh', { translations: { intro: { stock: { none: [] } } } })
  const { container } = render(<Fixture />)
  expect(container.querySelector('[data-slot="aui_intro"] > div > p:last-child')!.textContent).toBe(zh.intro.stock.none[0])
})

it('keeps the user-supplied personality name in the Chinese fallback greeting', () => {
  vi.spyOn(Math, 'random').mockReturnValue(0)
  const { container } = render(<Fixture personality="My Custom Voice" seed={4} />)
  const body = container.querySelector('[data-slot="aui_intro"] > div > p:last-child')!.textContent
  expect(body).toContain('My Custom Voice')
  expect(body).toMatch(/[\u3400-\u9fff]/)
})

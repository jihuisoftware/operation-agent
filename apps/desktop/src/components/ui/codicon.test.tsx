import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'

import { Codicon } from './codicon'

afterEach(cleanup)

it('renders semantic codicon names through the shared SVG icon family', () => {
  const { container } = render(<Codicon name="graph" size={20} />)
  const host = container.querySelector('.codicon-graph')
  const svg = host?.querySelector('svg')

  expect(host).not.toBeNull()
  expect(host?.classList.contains('codicon-custom')).toBe(true)
  expect(svg).not.toBeNull()
  expect(host?.getAttribute('style')).toContain('font-size: 20px')
})

it('keeps unknown persisted names visible with a safe fallback glyph', () => {
  const { container } = render(<Codicon name="plugin-added-later" />)

  expect(container.querySelector('.codicon-plugin-added-later svg')).not.toBeNull()
})

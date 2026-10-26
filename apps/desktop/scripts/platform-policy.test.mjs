import { expect, it, vi } from 'vitest'
import { requireMacOS } from '../platform-policy.cjs'
import { runElectronBuilder } from './run-electron-builder.mjs'

it('admits macOS and rejects other runtime platforms', () => {
  expect(() => requireMacOS('darwin')).not.toThrow()
  for (const platform of ['linux', 'win32', 'freebsd']) {
    expect(() => requireMacOS(platform)).toThrow('仅支持 macOS')
  }
})

it('rejects unsupported build targets before starting preparation', () => {
  const spawn = vi.fn()
  for (const target of ['--linux', '--win']) {
    expect(() => runElectronBuilder([target], { spawn })).toThrow('仅支持 macOS')
  }
  expect(spawn).not.toHaveBeenCalled()
})

import { expect, it, vi } from 'vitest'
import { requireDesktopPlatform } from '../platform-policy.cjs'
import { runElectronBuilder } from './run-electron-builder.mjs'

it('admits the native desktop architectures and rejects retired targets', () => {
  for (const [platform, arch] of [['darwin', 'arm64'], ['darwin', 'x64'], ['win32', 'x64']]) {
    expect(() => requireDesktopPlatform(platform, arch)).not.toThrow()
  }
  for (const [platform, arch] of [['linux', 'x64'], ['win32', 'arm64'], ['win32', 'ia32'], ['freebsd', 'x64']]) {
    expect(() => requireDesktopPlatform(platform, arch)).toThrow('Windows x64')
  }
})

it('rejects unsupported or foreign-host packaging before preparation', () => {
  const spawn = vi.fn()
  expect(() => runElectronBuilder(['--linux'], { spawn })).toThrow()
  const foreign = process.platform === 'darwin' ? '--win' : '--mac'
  expect(() => runElectronBuilder([foreign], { spawn })).toThrow('native operating system')
  expect(spawn).not.toHaveBeenCalled()
})

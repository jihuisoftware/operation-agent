import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, type Mock, vi } from 'vitest'

import type { DesktopVersionInfo } from '@/global'
import { I18nProvider } from '@/i18n'
import { $previewTabs, closeRightRail } from '@/store/preview'
import { $updateStatus } from '@/store/updates'

import { VersionDetails } from './version-details'

afterEach((): void => {
  cleanup()
  $updateStatus.set(null)
  closeRightRail()
  vi.unstubAllGlobals()
})

const baseVersion: DesktopVersionInfo = {
  appVersion: '0.19.0',
  electronVersion: '37.0.0',
  hermesRoot: '/tmp/hermes',
  nodeVersion: '22.0.0',
  platform: 'linux'
}

describe('VersionDetails', () => {
  interface VersionCase {
    version: Partial<DesktopVersionInfo>
    visible: string[]
    absent?: string[]
  }

  const cases: VersionCase[] = [
    { version: { source: 'ci', branch: null }, visible: ['构建来源', 'CI'] },
    { version: { source: 'ci', branch: 'unknown' }, visible: ['CI (unknown)'] },
    { version: { source: 'nix', distribution: 'nix' }, visible: ['构建来源', 'Nix', '发行版'] },
    { version: { source: 'ci', distribution: 'docker' }, visible: ['CI', '发行版', 'Docker'] },
    {
      version: { distribution: 'desktop-app', hermesRuntime: { type: 'embedded' } },
      visible: ['运行时', '嵌入式（捆绑）']
    },
    {
      version: { hermesRuntime: { type: 'external', source: { type: 'git', root: '/home/u/.hermes/hermes-agent' } } },
      visible: ['运行时', 'git (/home/u/.hermes/hermes-agent)'],
      absent: ['外部']
    },
    { version: { hermesRuntime: { type: 'external' } }, visible: ['运行时', '外部'] },
    {
      version: { distribution: 'desktop-app', updateMechanism: 'microsoft-store' },
      visible: ['发行版', 'Microsoft Store'],
      absent: ['桌面应用 (MSIX)']
    },
    {
      version: { distribution: 'desktop-app', updateMechanism: 'app-installer', payload: 'bundled' },
      visible: ['桌面应用 (MSIX)'],
      absent: ['Microsoft Store']
    },
    {
      version: { distribution: 'desktop-app', updateMechanism: 'electron-updater', payload: 'bundled' },
      visible: ['桌面应用'],
      absent: ['桌面应用 (MSIX)']
    },
    // Old-style installer shell (bootstrap artifact over a managed checkout —
    // e.g. iris's v0.17.6 .app): named as the installer, never as MSIX.
    {
      version: { distribution: 'desktop-app', updateMechanism: 'self', payload: 'bootstrap' },
      visible: ['桌面应用（安装器）'],
      absent: ['桌面应用 (MSIX)', 'Microsoft Store']
    },
    // `hermes desktop` packs the same bootstrap payload from a source checkout;
    // a locally built stamp names the source install, never the installer.
    {
      version: {
        distribution: 'desktop-app',
        updateMechanism: 'self',
        payload: 'bootstrap',
        source: 'local',
        installedByScript: true
      },
      visible: ['源码（安装脚本）+ hermes desktop'],
      absent: ['桌面应用（安装器）']
    },
    {
      version: { distribution: 'desktop-app', updateMechanism: 'self', payload: 'bootstrap', source: 'local' },
      visible: ['源码 + hermes desktop'],
      absent: ['桌面应用（安装器）']
    },
    // install.sh / install.ps1 checkout (receipt present) vs a manual git
    // clone (live provenance, no receipt): both honestly say Source.
    { version: { installedByScript: true }, visible: ['源码（安装脚本）'] },
    { version: { source: 'git' }, visible: ['发行版', '源码'], absent: ['源码（安装脚本）'] },
    { version: {}, visible: ['版本'], absent: ['发行版'] }
  ]

  it.each(cases)('renders $version', ({ version, visible, absent = [] }: VersionCase): void => {
    render(
      <I18nProvider>
        <VersionDetails version={{ ...baseVersion, ...version }} />
      </I18nProvider>
    )

    for (const text of visible) {
      expect(screen.getAllByText(text).length).toBeGreaterThan(0)
    }

    for (const text of absent) {
      expect(screen.queryByText(text)).toBeNull()
    }

    if (version.source === 'nix') {
      expect(screen.getAllByText('Nix')).toHaveLength(2)
    }
  })

  it('opens the commit URL via the system-browser bridge without opening a preview tab', async () => {
    const openExternal: Mock<Window['hermesDesktop']['openExternal']> = vi
      .fn<Window['hermesDesktop']['openExternal']>()
      .mockResolvedValue(undefined)

    vi.stubGlobal('hermesDesktop', { openExternal } satisfies Pick<Window['hermesDesktop'], 'openExternal'>)

    render(
      <I18nProvider>
        <VersionDetails version={{ ...baseVersion, commit: 'd233b6d7a9c5b79288e48dfb3b29e2ead106ac73' }} />
      </I18nProvider>
    )

    fireEvent.click(screen.getByText('d233b6d7a9c5b7'))

    await waitFor(() => {
      expect(openExternal).toHaveBeenCalledWith(
        'https://github.com/NousResearch/hermes-agent/commit/d233b6d7a9c5b79288e48dfb3b29e2ead106ac73'
      )
    })
    expect($previewTabs.get()).toHaveLength(0)
  })

  it('names the source channel, and offers the change action only where the caller passes one', () => {
    const render_ = (action?: boolean) =>
      render(
        <I18nProvider>
          <VersionDetails
            channelAction={action ? <button type="button">Change</button> : undefined}
            version={baseVersion}
          />
        </I18nProvider>
      )

    $updateStatus.set({ supported: true, mechanism: 'posix-handoff', channel: 'stable' })
    render_()
    expect(screen.getByText('渠道')).toBeTruthy()
    expect(screen.getByText('稳定版发布')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Change' })).toBeNull()
    cleanup()

    $updateStatus.set({ supported: true, mechanism: 'windows-handoff', branch: 'main' })
    render_(true)
    expect(screen.getByText(/每个提交 \(main\)/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Change' })).toBeTruthy()
    cleanup()

    $updateStatus.set({ supported: true, mechanism: 'posix-handoff', branch: 'feature/gui' })
    render_(true)
    expect(screen.getByText(/分支：feature\/gui/)).toBeTruthy()
    cleanup()

    // A packaged install's channel is the package's, not a source track: no row.
    $updateStatus.set({ supported: true, mechanism: 'electron-updater', channel: 'stable' })
    render_(true)
    expect(screen.queryByText('渠道')).toBeNull()
  })
})

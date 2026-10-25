import { describe, expect, it, vi } from 'vitest'

import { discoverBundledPlugins } from './plugins'
import { $pluginDecisions, $pluginRecords, pluginActive, publishPlugin, setPluginEnabled } from './plugins-store'

vi.mock('./runtime-loader', () => ({ watchRuntimePlugins: vi.fn() }))

describe('operations plugin scope', () => {
  it('does not load retired plugins even when an older install enabled them', async () => {
    $pluginDecisions.set({ 'hermes-bots': true, kanban: true, radio: true })

    await discoverBundledPlugins()

    for (const id of ['hermes-bots', 'kanban', 'radio']) {
      expect($pluginRecords.get()[id]).toBeUndefined()
      expect(pluginActive(id)).toBe(false)
    }
  })

  it('refuses activation of retired plugins while keeping ordinary content extensions usable', async () => {
    const retired = { activate: vi.fn(), deactivate: vi.fn() }
    const content = { activate: vi.fn(), deactivate: vi.fn() }
    publishPlugin({ id: 'hermes-bots', name: 'Bots', kind: 'disk', status: 'disabled' }, retired)
    publishPlugin({ id: 'content-pack', name: 'Content', kind: 'disk', status: 'disabled' }, content)

    await setPluginEnabled('hermes-bots', true)
    await setPluginEnabled('content-pack', true)

    expect(retired.activate).not.toHaveBeenCalled()
    expect(content.activate).toHaveBeenCalledOnce()
  })
})

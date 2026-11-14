import { describe, expect, it, vi } from 'vitest'

import { discoverBundledPlugins } from './plugins'
import { $pluginDecisions, $pluginRecords, pluginActive, publishPlugin, setPluginEnabled } from './plugins-store'

vi.mock('./runtime-loader', () => ({ watchRuntimePlugins: vi.fn() }))

describe('operations plugin scope', () => {
  it('loads Kanban by default while retired plugins stay unavailable', async () => {
    $pluginDecisions.set({ 'hermes-bots': true, radio: true })

    await discoverBundledPlugins()

    for (const id of ['hermes-bots', 'radio']) {
      expect($pluginRecords.get()[id]).toBeUndefined()
      expect(pluginActive(id)).toBe(false)
    }
    expect(pluginActive('kanban')).toBe(true)
    await setPluginEnabled('kanban', false)
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

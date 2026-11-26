import type { CronBlueprintOwner, PluginContext } from '@hermes/plugin-sdk'
import { useMemo } from 'react'

import { scopedContext } from './workspace-state'

export function useOwnerContext(ctx: PluginContext, owner: CronBlueprintOwner): PluginContext {
  return useMemo(() => scopedContext(ctx, owner), [ctx, owner])
}

import { type CronBlueprintOwner, host } from '@hermes/plugin-sdk'

import { chooseScope, type OperationScope, ownerKey, scopePath } from './workspace-state'

export function recordAction(owner: CronBlueprintOwner, scope: OperationScope | undefined, path: string) {
  if (!scope) { return undefined }

  return {
    label: '查看记录',
    onClick: () => {
      if (ownerKey(host.state.requestOwner.get()) !== ownerKey(owner)) {
        host.notify({ kind: 'info', message: `该记录属于 ${owner.profile || 'default'} Profile，请先切换到对应连接和 Profile。` })

        return
      }

      chooseScope(owner, scope, false)
      host.navigate(scopePath(path, scope))
    }
  }
}

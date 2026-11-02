import { type CronBlueprintOwner, useValue } from '@hermes/plugin-sdk'

import { $workspaces, ownerKey, showAccount } from './workspace-state'

export function AccountViewHeader({ scope, taskLabel }: { scope: CronBlueprintOwner & { account_id?: string }; taskLabel: string }) {
  const state = useValue($workspaces)[ownerKey(scope)]

  if (!scope.account_id || !state?.catalog) { return null }

  return <div className="space-y-1 border-b p-2 text-xs">
    <label>查看账号 <select aria-label="运营画面账号" className="rounded border bg-background p-1" onChange={e => showAccount(scope, e.target.value)} value={scope.account_id}>
      {state.catalog.accounts.filter(a => state.catalog!.businesses.some(b => !b.archived && b.account === a.id)).map(a => <option key={a.id} value={a.id}>{state.catalog!.businesses.filter(b => b.account === a.id).map(b => b.name).join('、')} · {a.identity || '待登录'}</option>)}
    </select></label>
    {taskLabel && <p>最近执行主题：{taskLabel}</p>}
  </div>
}

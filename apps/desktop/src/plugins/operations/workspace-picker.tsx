import { Button, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { $workspaceDirty, $workspaces, chooseScope, loadWorkspaces, type OperationScope, ownerKey, scopeKey } from './workspace-state'

export function WorkspacePicker({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const state = useValue($workspaces)[ownerKey(owner)]
  const dirty = useValue($workspaceDirty)
  const [query, setQuery] = useState('')
  const [name, setName] = useState('')
  const [pending, setPending] = useState<OperationScope | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { void loadWorkspaces(ctx, owner); setPending(null); setName(''); setError(''); setBusy(false) }, [ctx, owner])
  const { catalog, selected } = state || {}

  if (!catalog || !selected) { return <p className="p-2 text-xs">{state?.error || '读取业务空间…'}</p> }
  const business = catalog.businesses.find(b => b.id === selected.business_id)
  const topic = catalog.topics.find(t => t.id === selected.topic_id)

  const change = (next: OperationScope) => {
    if (dirty[scopeKey(owner, selected)]) { setPending(next) } else { chooseScope(owner, next) }
  }

  const manage = async (body: Record<string, unknown>) => {
    setBusy(true); setError('')

    try {
      const result = await ctx.rest<OperationScope>('/workspaces', { owner, method: 'POST', body })
      await loadWorkspaces(ctx, owner)

      if (ownerKey(host.state.requestOwner.get()) !== ownerKey(owner)) { return }

      if (result.topic_id) { change(result) }
      setName('')
    } catch (reason) {
      if (ownerKey(host.state.requestOwner.get()) === ownerKey(owner)) { setError(String(reason)) }
    } finally {
      if (ownerKey(host.state.requestOwner.get()) === ownerKey(owner)) { setBusy(false) }
    }
  }

  return <section aria-label="业务与主题" className="max-h-[50vh] space-y-2 overflow-y-auto p-2 text-xs">
    <label className="block">业务空间<select aria-label="业务空间" className="mt-1 w-full rounded border bg-background p-2" onChange={e => {
      const next = catalog.topics.find(t => t.business_id === e.target.value && !t.archived) || catalog.topics.find(t => t.business_id === e.target.value)

      if (next) { change({ business_id: next.business_id, topic_id: next.id }) }
    }} value={selected.business_id}>{catalog.businesses.map(b => <option key={b.id} value={b.id}>{b.name}{b.archived ? '（已归档）' : b.paused ? '（已暂停）' : ''}</option>)}</select></label>
    <label className="block">运营主题<select aria-label="运营主题" className="mt-1 w-full rounded border bg-background p-2" onChange={e => change({ business_id: selected.business_id, topic_id: e.target.value })} value={selected.topic_id}>
      {catalog.topics.filter(t => t.business_id === selected.business_id).map(t => <option key={t.id} value={t.id}>{t.name}{t.archived ? '（已归档）' : ''}</option>)}
    </select></label>
    {pending && <div className="space-y-2" role="alert"><p>当前设置尚未保存，切换将放弃修改。</p><Button onClick={() => { chooseScope(owner, pending); setPending(null) }}>放弃修改并切换</Button><Button onClick={() => setPending(null)} variant="ghost">继续编辑</Button></div>}
    <details><summary className="cursor-pointer text-muted-foreground">管理业务与主题</summary>
      <div className="mt-2 space-y-2">
        <input aria-label="搜索业务或主题" className="w-full rounded border bg-background p-2" onChange={e => setQuery(e.target.value)} placeholder="搜索业务或主题" value={query} />
        {query && catalog.topics.filter(t => `${catalog.businesses.find(b => b.id === t.business_id)?.name} ${t.name}`.includes(query)).map(t => <Button key={t.id} onClick={() => change({ business_id: t.business_id, topic_id: t.id })} variant="ghost">{catalog.businesses.find(b => b.id === t.business_id)?.name} / {t.name}</Button>)}
        <input aria-label="新名称" className="w-full rounded border bg-background p-2" onChange={e => setName(e.target.value)} placeholder="输入名称" value={name} />
        <div className="flex flex-wrap gap-1">
          <Button disabled={busy || !name.trim()} onClick={() => void manage({ action: 'create', name })}>新增业务</Button>
          <Button disabled={busy || !name.trim()} onClick={() => void manage({ action: 'create', name, copy_topic: selected.topic_id })}>复制配置为新业务</Button>
          <Button disabled={busy || !name.trim()} onClick={() => void manage({ action: 'create', name, business_id: selected.business_id })}>新增主题</Button>
          <Button disabled={busy || !name.trim()} onClick={() => void manage({ action: 'create', name, business_id: selected.business_id, copy_topic: selected.topic_id })}>复制配置为新主题</Button>
          <Button disabled={busy || !name.trim()} onClick={() => void manage({ action: 'rename', kind: 'businesses', id: business?.id, name })} variant="ghost">重命名业务</Button>
          <Button disabled={busy || !name.trim()} onClick={() => void manage({ action: 'rename', kind: 'topics', id: topic?.id, name })} variant="ghost">重命名主题</Button>
          <Button disabled={busy} onClick={() => void manage({ action: business?.paused ? 'resume' : 'pause', kind: 'businesses', id: business?.id })} variant="ghost">{business?.paused ? '恢复业务' : '暂停业务'}</Button>
          <Button disabled={busy} onClick={() => void manage({ action: catalog.paused ? 'resume' : 'pause', kind: 'profile' })} variant="ghost">{catalog.paused ? '恢复全部运营' : '暂停全部运营'}</Button>
        </div>
        <details><summary>归档（保留历史）</summary><Button disabled={busy} onClick={() => void manage({ action: 'archive', kind: 'topics', id: topic?.id })}>归档当前主题</Button><Button disabled={busy} onClick={() => void manage({ action: 'archive', kind: 'businesses', id: business?.id })}>归档当前业务</Button></details>
        <label className="block">关联账号<select aria-label="关联账号" className="w-full rounded border bg-background p-2" onChange={e => void manage({ action: 'link_account', business_id: business?.id, account_id: e.target.value })} value={business?.account}>{catalog.accounts.map(a => <option key={a.id} value={a.id}>{a.identity || `独立登录 ${a.id.slice(0, 8)}`}{a.conflict ? '（重复账号待关联）' : ''}</option>)}</select></label>
        <p className="text-muted-foreground">共用账号会共享登录、额度与网页队列；资料保持独立。</p>
      </div>
    </details>
    {(error || state?.error) && <p className="text-destructive" role="alert">{error || state?.error}</p>}
  </section>
}

import { Button, host, useQuery, useQueryClient, useValue } from '@hermes/plugin-sdk'
import { useState } from 'react'

import {
  $boardSlug,
  boardKeyPrefix,
  executionKey,
  fetchExecution,
  runBoardOnce,
  saveExecution,
  useKanbanScope
} from './api'

export function useBoardExecution() {
  const scope = useKanbanScope()
  const slug = useValue($boardSlug)

  return useQuery({ queryKey: executionKey(scope, slug), queryFn: () => fetchExecution(slug), refetchInterval: 15000 })
}

export function ExecutionControls() {
  const scope = useKanbanScope()
  const slug = useValue($boardSlug)
  const query = useBoardExecution()
  const cache = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(false)

  const change = async (enabled: boolean) => {
    if (!query.data) {
      return
    }
    setBusy(true)

    try {
      const result = await saveExecution(query.data.board, enabled, query.data.revision)
      cache.setQueryData(executionKey(scope, slug), result)
      setConfirm(false)
    } catch (error) {
      host.notify({ kind: 'error', message: String(error) })
      await cache.invalidateQueries({ queryKey: executionKey(scope, slug) })
    } finally {
      setBusy(false)
    }
  }
  const once = async () => {
    setBusy(true)

    try {
      const result = await runBoardOnce(query.data!.board)
      host.notify({
        kind: 'info',
        message: result.spawned.length
          ? '本次已领取一个任务，可在执行中查看。'
          : '本次未领取任务，请检查待执行任务的负责人、依赖及并发状态。'
      })
      await cache.invalidateQueries({ queryKey: boardKeyPrefix(scope) })
    } catch (error) {
      host.notify({ kind: 'error', message: String(error) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="看板执行设置" className="space-y-2 border-b px-4 py-3 text-sm">
      {query.error ? (
        <p role="alert">无法读取执行设置：{String(query.error)}</p>
      ) : !query.data ? (
        <p>正在读取执行设置…</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <span>{query.data.enabled ? '自动执行已开启' : '手动模式 · 自动执行关闭'}</span>
            <Button
              disabled={busy}
              onClick={() => (query.data.enabled ? void change(false) : setConfirm(true))}
              size="sm"
              variant="outline"
            >
              {query.data.enabled ? '关闭自动执行' : '开启本看板自动执行'}
            </Button>
            <Button disabled={busy} onClick={() => void once()} size="sm" variant="outline">
              运行一次
            </Button>
            <span>执行中 {query.data.running} 项</span>
          </div>
          {query.data.enabled && !query.data.dispatcher_running && (
            <p role="status">自动执行已开启，但调度器不可用：{query.data.dispatcher_detail || '请启动后台服务'}</p>
          )}
          <p className="text-muted-foreground">
            默认最多同时执行一个任务。关闭开关只停止新领取，正在执行的任务可在详情中停止。
          </p>
          {confirm && !query.data.enabled && (
            <div className="flex flex-wrap items-center gap-3" role="alert">
              <span>开启后将自动处理本看板已有及后续的待执行任务，并使用其执行配置的模型与权限。</span>
              <Button disabled={busy} onClick={() => void change(true)} size="sm">
                确认开启
              </Button>
              <Button disabled={busy} onClick={() => setConfirm(false)} size="sm" variant="ghost">
                暂不开启
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}

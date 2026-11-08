import type { PluginContext } from '@hermes/plugin-sdk'
import { atom } from 'nanostores'

import { journal, type Pending, type Recovery } from './journal'
import { base, type Draft, type Fields, fields } from './types'
interface State extends Recovery {
  status: string
  conflict: boolean
  error: string
}

export function writer(ctx: PluginContext, key: string, initial: Recovery) {
  const state = atom<State>({
    ...initial,
    status: initial.dirty ? '有本机恢复内容，等待同步' : '已保存',
    conflict: false,
    error: ''
  })

  let timer: ReturnType<typeof setTimeout> | undefined,
    saving: Promise<void> | undefined,
    disposed = false,
    composing = false

  let writes = Promise.resolve(),
    retries = 0

  const patch = (value: Partial<State>) => state.set({ ...state.get(), ...value })

  const persist = () => {
    const { draft, dirty, pending } = state.get()
    writes = writes
      .catch(() => undefined)
      .then(async () => {
        await journal(key, { draft, dirty, pending })
      })

    return writes.catch(reason => {
      patch({ error: `本机恢复副本不可用，请确认后台保存成功后再离开：${String(reason)}` })
      throw reason
    })
  }

  const attempt = async () => {
    while (state.get().dirty || state.get().pending) {
      if (state.get().conflict) {
        throw new Error('409 版本冲突，请另存副本或载入服务器版本')
      }

      if (composing) {
        return
      }

      const current = state.get()

      const pending: Pending = current.pending || {
        fields: fields(current.draft),
        expected_revision: current.draft.revision,
        request_id: crypto.randomUUID()
      }

      patch({ pending, status: '正在保存…', error: '' })
      await persist().catch(() => undefined)

      try {
        const ack = await ctx.rest<Partial<Draft>>(`${base}/${current.draft.id}`, {
          method: 'PUT',
          body: { ...pending.fields, expected_revision: pending.expected_revision, request_id: pending.request_id }
        })

        const latest = state.get().draft
        const dirty = JSON.stringify(fields(latest)) !== JSON.stringify(pending.fields)
        retries = 0
        patch({
          draft: { ...latest, revision: ack.revision!, updated: ack.updated! },
          pending: undefined,
          dirty,
          status: dirty ? '等待保存' : '已保存'
        })
        await persist().catch(() => undefined)
      } catch (reason) {
        const error = String(reason),
          conflict = /409/.test(error)

        patch({
          status: conflict ? '版本冲突，已保留本机内容' : '仅本机暂存 · 点击保存重试',
          conflict,
          error,
          ...(/40[023]|413|422/.test(error) ? { pending: undefined } : {})
        })
        await persist().catch(() => undefined)
        throw reason
      }
    }
  }

  const save = () => {
    clearTimeout(timer)

    if (!saving) {
      saving = attempt()
        .catch(reason => {
          if (!disposed && !/40[0-9]|413|422/.test(String(reason)) && retries < 3) {
            timer = setTimeout(() => {
              void save().catch(() => undefined)
            }, [5000, 15000, 30000][retries++])
          }

          throw reason
        })
        .finally(() => {
          saving = undefined
        })
    }

    return saving
  }

  const schedule = () => {
    clearTimeout(timer)

    if (!disposed && !composing) {
      timer = setTimeout(() => {
        void save().catch(() => undefined)
      }, 2000)
    }
  }

  return {
    state,
    save,
    edit(value: Partial<Fields>) {
      patch({ draft: { ...state.get().draft, ...value }, dirty: true, status: '等待保存' })
      void persist().catch(() => undefined)
      schedule()
    },
    composition(active: boolean) {
      composing = active

      if (!active) {
        schedule()
      }
    },
    async reload() {
      if (saving) {
        await saving.catch(() => undefined)
      }

      const draft = await ctx.rest<Draft>(`${base}/${state.get().draft.id}`)
      patch({ draft, dirty: false, pending: undefined, conflict: false, error: '', status: '已重新载入' })
      await persist().catch(() => undefined)
    },
    async submit() {
      await save()
      const current = state.get()

      if (current.dirty || current.conflict || current.pending) {
        throw new Error('请先完成保存并处理冲突')
      }

      const detail = await ctx.rest<Draft>(`${base}/${current.draft.id}`)

      return ctx.rest<{ content_id: string }>(`${base}/${current.draft.id}/submit`, {
        method: 'POST',
        body: {
          expected_revision: current.draft.revision,
          version: detail.policy_version,
          request_id: crypto.randomUUID()
        }
      })
    },
    async copy() {
      const current = state.get()

      return ctx.rest<{ id: string }>(base, {
        method: 'POST',
        body: { copy_from: current.draft.id, local: fields(current.draft), request_id: crypto.randomUUID() }
      })
    },
    dispose() {
      disposed = true
      clearTimeout(timer)
      void persist().catch(() => undefined)
    }
  }
}

export type Writer = ReturnType<typeof writer>

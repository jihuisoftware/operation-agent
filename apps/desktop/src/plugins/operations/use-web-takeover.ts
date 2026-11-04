import { type RefObject, useCallback, useRef } from 'react'

import type { Api, Guest } from './types'

export interface WebControlState { held: boolean; owned: boolean }

interface Props {
  api: Api
  guest: Guest
  worker: string
  execution: RefObject<{ pending: Promise<unknown> | null }>
  onStatus: (message: string) => void
}

export function useWebTakeover({ api, guest, worker, execution, onStatus }: Props) {
  const manual = useRef(false)
  const revision = useRef(0)
  const changing = useRef(false)
  const queue = useRef<Promise<unknown>>(Promise.resolve())

  const send = useCallback((active: boolean) => {
    const request = () => api('/worker/takeover', { worker, active })
    queue.current = queue.current.then(request, request)

    return queue.current
  }, [api, worker])

  const takeOver = useCallback(async () => {
    let current = ++revision.current
    const previous = manual.current
    manual.current = true
    changing.current = true

    try {
      await send(true)

      if (revision.current !== current) { return }
      changing.current = false
      current = ++revision.current
      onStatus('已暂停，等待当前网页操作退出…')
      await execution.current.pending?.then(() => undefined, error => {
        if (revision.current === current) { onStatus(String(error)) }
      })

      if (revision.current !== current || !manual.current) { return }
      guest.style.pointerEvents = 'auto'
      onStatus('网页已接管，完成后点击结束接管')
    } catch (reason) {
      if (revision.current === current) { manual.current = previous; throw reason }
    } finally {
      if (revision.current === current && changing.current) { changing.current = false; revision.current += 1 }
    }
  }, [send, execution, guest, onStatus])

  const release = useCallback(async () => {
    const current = ++revision.current
    changing.current = true

    try {
      await send(false)

      if (revision.current !== current) { return }
      manual.current = false
      guest.style.pointerEvents = 'none'
      onStatus('已结束接管，网页动作按后续排期执行；全局暂停保持原设置')
    } catch (reason) {
      if (revision.current === current) { throw reason }
    } finally {
      if (revision.current === current) { changing.current = false; revision.current += 1 }
    }
  }, [send, guest, onStatus])

  const reconcile = useCallback((state: WebControlState | undefined, observedRevision: number) => {
    if (!state || changing.current || observedRevision !== revision.current || state.owned === manual.current) { return }
    manual.current = state.owned
    guest.style.pointerEvents = state.owned ? 'auto' : 'none'
    onStatus(state.owned ? '网页正在人工接管，完成后点击结束接管' : state.held ? '其他窗口正在人工接管' : '接管已结束；如需手动操作，请重新接管')
  }, [guest, onStatus])

  return { manual, revision, takeOver, release, reconcile }
}

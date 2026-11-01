export function createExecutionClock(tick: () => void) {
  const worker = new Worker(new URL('./execution-clock.worker.ts', import.meta.url), { type: 'module' })
  const waiting = new Map<number, { resolve: () => void; reject: (error: Error) => void }>()
  let sequence = 0

  worker.onmessage = ({ data }) => {
    if (data.kind === 'tick') {
      tick()
    } else {
      waiting.get(data.id)?.resolve()
      waiting.delete(data.id)
    }
  }

  worker.postMessage({ kind: 'start', ms: 2000 })

  return {
    sleep: (ms: number) => new Promise<void>((resolve, reject) => {
      const id = ++sequence
      waiting.set(id, { resolve, reject })
      worker.postMessage({ kind: 'sleep', id, ms })
    }),
    dispose: () => {
      worker.terminate()

      for (const pending of waiting.values()) { pending.reject(new Error('桌面执行器已断开')) }
      waiting.clear()
    }
  }
}

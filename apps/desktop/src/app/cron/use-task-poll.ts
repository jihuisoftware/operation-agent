import { useEffect, useState } from 'react'

/** Page-local polling, serialized with visible stale data and owner-bound teardown. */
export function useTaskPoll<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let disposed = false
    let busy = false

    const refresh = async () => {
      if (busy || document.visibilityState === 'hidden') {return}
      busy = true

      try {
        const value = await load()

        if (!disposed) { setData(value); setError('') }
      } catch (reason) {
        if (!disposed) {setError(String(reason))}
      } finally { busy = false }
    }

    void refresh()
    const timer = window.setInterval(() => { void refresh() }, 3000)
    document.addEventListener('visibilitychange', refresh)

    return () => { disposed = true; clearInterval(timer); document.removeEventListener('visibilitychange', refresh) }
  }, [load, revision])

  return { data, error, refresh: () => setRevision(value => value + 1) }
}

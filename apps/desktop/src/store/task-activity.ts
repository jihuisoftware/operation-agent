import { atom, onMount, type ReadableAtom } from 'nanostores'

export interface TaskActivity {
  running: number
  unavailable?: boolean
}

export interface TaskActivityOwner {
  connectionId: string | null
  profile: string | null
}

export const IDLE_TASK_ACTIVITY: TaskActivity = { running: 0 }

/** One observer per mounted store, independent of the selected page. */
export function createTaskActivity(
  owners: ReadableAtom<TaskActivityOwner>,
  load: (owner: TaskActivityOwner) => Promise<TaskActivity>
) {
  const activity = atom<TaskActivity>(IDLE_TASK_ACTIVITY)

  onMount(activity, () => {
    let stop = () => {}
    let key = ''

    const unsubscribe = owners.subscribe(owner => {
      const nextKey = JSON.stringify([owner.connectionId, owner.profile || 'default'])

      if (key === nextKey) { return }
      key = nextKey
      stop()
      activity.set(IDLE_TASK_ACTIVITY)
      stop = observeActivity(() => load({ ...owner }), value => activity.set(value))
    })

    return () => { unsubscribe(); stop(); activity.set(IDLE_TASK_ACTIVITY) }
  })

  return activity
}

function observeActivity(load: () => Promise<TaskActivity>, publish: (value: TaskActivity) => void) {
  let disposed = false
  let busy = false
  let failures = 0

  const refresh = async () => {
    if (disposed || busy || failures >= 3 || document.visibilityState === 'hidden') { return }
    busy = true

    try {
      const result = await load()

      if (!disposed) { publish(result) }
      failures = 0
    } catch {
      failures += 1

      if (!disposed) { publish({ running: 0, unavailable: true }) }
    } finally { busy = false }
  }

  const resume = () => { failures = 0; void refresh() }
  const timer = window.setInterval(() => void refresh(), 3000)
  document.addEventListener('visibilitychange', resume)
  window.addEventListener('focus', resume)
  void refresh()

  return () => {
    disposed = true
    clearInterval(timer)
    document.removeEventListener('visibilitychange', resume)
    window.removeEventListener('focus', resume)
  }
}

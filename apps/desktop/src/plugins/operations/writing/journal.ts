import type { Draft, Fields } from './types'
export interface Pending {
  fields: Fields
  expected_revision: number
  request_id: string
}
export interface Recovery {
  draft: Draft
  dirty: boolean
  pending?: Pending
}

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('operations-writing', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('copies')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function windowKey() {
  const key = 'writing-window-id'
  let id = sessionStorage.getItem(key)

  if (!id) {
    id = crypto.randomUUID()
    sessionStorage.setItem(key, id)
  }

  return id
}

interface Entry {
  key: string
  window: string
  at: number
  value: Recovery
}

export async function journal(key: string, value?: Recovery): Promise<Recovery | undefined> {
  const db = await database(),
    window = windowKey(),
    entryKey = JSON.stringify([key, window])

  return new Promise((resolve, reject) => {
    const tx = db.transaction('copies', value ? 'readwrite' : 'readonly')

    const request = value
      ? tx.objectStore('copies').put({ key, window, at: Date.now(), value } satisfies Entry, entryKey)
      : tx.objectStore('copies').getAll()

    tx.oncomplete = () => {
      db.close()

      if (value) {
        resolve(value)

        return
      }

      const entries = (request.result as Entry[]).filter(entry => entry.key === key).sort((a, b) => b.at - a.at)
      resolve(
        (
          entries.find(entry => entry.window === window) ||
          entries.find(entry => entry.value.dirty || entry.value.pending) ||
          entries[0]
        )?.value
      )
    }

    tx.onerror = () => {
      db.close()
      reject(tx.error)
    }

    tx.onabort = () => {
      db.close()
      reject(tx.error)
    }
  })
}

export async function changeProfile(change: { connectionId: string; profile: string; renamedTo?: string }) {
  const db = await database()

  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction('copies', 'readwrite'),
      copies = tx.objectStore('copies'),
      cursor = copies.openCursor()

    cursor.onsuccess = () => {
      const row = cursor.result

      if (!row) {
        return
      }

      const entry = row.value as Entry

      const [scopeKey, id] = JSON.parse(entry.key),
        [ownerKey, business, topic] = JSON.parse(scopeKey),
        [connection, profile] = JSON.parse(ownerKey)

      if (connection === change.connectionId && profile === change.profile) {
        row.delete()

        if (change.renamedTo) {
          const nextScope = JSON.stringify([JSON.stringify([connection, change.renamedTo]), business, topic])
          const key = JSON.stringify([nextScope, id])
          copies.put({ ...entry, key }, JSON.stringify([key, entry.window]))
        }
      }

      row.continue()
    }

    tx.oncomplete = () => {
      db.close()
      resolve()
    }

    tx.onerror = () => {
      db.close()
      reject(tx.error)
    }
  })
}

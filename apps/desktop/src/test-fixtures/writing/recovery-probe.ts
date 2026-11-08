import { changeProfile, journal } from '../../plugins/operations/writing/journal'
import type { Draft } from '../../plugins/operations/writing/types'

export async function recoveryProbe(draft: Draft) {
  const key = (connection: string, profile: string) =>
    JSON.stringify([JSON.stringify([JSON.stringify([connection, profile]), 'b', 't']), 'probe'])

  const originalWindow = sessionStorage.getItem('writing-window-id')!
  const recovery = (title: string) => ({ draft: { ...draft, title }, dirty: true })
  await journal(key('a', 'p'), recovery('窗口一'))
  await journal(key('b', 'p'), recovery('另一个连接'))
  sessionStorage.setItem('writing-window-id', 'second-test-window')
  await journal(key('a', 'p'), recovery('窗口二'))
  sessionStorage.setItem('writing-window-id', originalWindow)

  if ((await journal(key('a', 'p')))?.draft.title !== '窗口一') {
    throw new Error('窗口恢复副本被覆盖')
  }

  await changeProfile({ connectionId: 'a', profile: 'p', renamedTo: 'renamed' })

  if ((await journal(key('a', 'renamed')))?.draft.title !== '窗口一') {
    throw new Error('重命名后恢复副本丢失')
  }

  if (await journal(key('a', 'p'))) {
    throw new Error('旧 Profile 残留副本')
  }

  await changeProfile({ connectionId: 'a', profile: 'renamed' })

  if (await journal(key('a', 'renamed'))) {
    throw new Error('删除后残留副本')
  }

  if ((await journal(key('b', 'p')))?.draft.title !== '另一个连接') {
    throw new Error('跨连接误删')
  }

  return true
}

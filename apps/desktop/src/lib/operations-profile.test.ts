import { describe, expect, it } from 'vitest'

import { appViewForPath, routeSessionId } from '@/app/routes'
import { isDesktopSlashCommand } from '@/lib/desktop-slash-commands'

describe('operations entry points', () => {
  it('does not interpret retired pages as sessions or expose their slash actions', () => {
    for (const path of ['/agents', '/starmap', '/webhooks', '/session-import']) {
      expect(routeSessionId(path)).toBeNull()
      expect(appViewForPath(path)).toBe('chat')
    }
    for (const command of ['/agents', '/tasks', '/profile', '/hatch', '/pet', '/import']) {
      expect(isDesktopSlashCommand(command)).toBe(false)
    }
  })

  it('keeps outputs, skills, scheduling and normal conversations reachable', () => {
    expect(appViewForPath('/artifacts')).toBe('artifacts')
    expect(appViewForPath('/capabilities')).toBe('capabilities')
    expect(appViewForPath('/cron')).toBe('cron')
    expect(routeSessionId('/content-draft')).toBe('content-draft')
    expect(isDesktopSlashCommand('/new')).toBe(true)
    expect(isDesktopSlashCommand('/stop')).toBe(true)
  })
})

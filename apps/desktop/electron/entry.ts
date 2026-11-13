import { requireDesktopPlatform } from '../platform-policy.cjs'

requireDesktopPlatform()
await import('./main')

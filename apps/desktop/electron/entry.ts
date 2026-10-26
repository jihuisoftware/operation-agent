import { requireMacOS } from '../platform-policy.cjs'

requireMacOS()
await import('./main')

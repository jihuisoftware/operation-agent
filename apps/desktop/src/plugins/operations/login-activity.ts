import { host } from '@hermes/plugin-sdk'
import { computed } from 'nanostores'

import { $loginNavigation, $loginRequest, sameLoginOwner } from './login-state'

export const $loginActivity = computed(
  [host.state.requestOwner, $loginNavigation, $loginRequest],
  (owner, navigation, request) => ({
    running: navigation && request && sameLoginOwner(owner, request.owner) ? 1 : 0
  })
)

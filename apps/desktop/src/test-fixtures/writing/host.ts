import { atom } from 'nanostores'
export { Button } from '../../components/ui/button'
export { useStore as useValue } from '@nanostores/react'
export const host = {
  state: { requestOwner: atom({ connectionId: 'fixture', profile: 'isolated' }) },
  navigate: (path: string) => {
    window.history.pushState(null, '', path)
  }
}

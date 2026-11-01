import { host } from '@hermes/plugin-sdk'
import { type CSSProperties, useEffect, useState } from 'react'

import { $showOperationsBrowser } from './state'

const PANE = 'plugin-workspace:operations-browser'
const ANCHOR = '--operations-browser-dock'

/** The shell reserves space; the native guest keeps its original connected DOM host. */
export function useBrowserDock(shown: boolean) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!shown) {
      setVisible(false)

      return
    }

    const close = host.openWorkspace('operations-browser', {
      title: '运营画面',
      dock: { pane: 'workspace', pos: 'right' },
      minWidth: '24rem',
      headerVeto: true,
      onClose: () => $showOperationsBrowser.set(false),
      render: () => <div aria-hidden className="h-full min-h-0 w-full" style={{ anchorName: ANCHOR } as CSSProperties} />
    })

    const unsubscribe = host.paneVisibility(PANE).subscribe(setVisible)

    return () => { unsubscribe(); close(); setVisible(false) }
  }, [shown])

  return shown && visible
}

export function browserDockStyle(visible: boolean): CSSProperties {
  // CSS anchors are the same mechanism the shell uses for kept-alive native guests.
  return visible ? {
    position: 'absolute', positionAnchor: ANCHOR,
    left: 'anchor(left, -10000px)', top: 'anchor(top, -10000px)',
    width: 'anchor-size(width, 1000px)', height: 'anchor-size(height, 800px)', zIndex: 1
  } as CSSProperties : { position: 'fixed', left: -10000, top: 0, width: 1000, height: 800 }
}

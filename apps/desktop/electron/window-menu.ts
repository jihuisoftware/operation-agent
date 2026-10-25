import type { MenuItemConstructorOptions } from 'electron'

interface WindowMenuItem extends MenuItemConstructorOptions {
  submenu: MenuItemConstructorOptions[]
}

function windowMenuTemplate(isMac: boolean): WindowMenuItem {
  return {
    label: '窗口',
    // Mark the macOS menu as AppKit's standard Window menu. Without this role,
    // macOS still exposes tiling from the green button but does not attach its
    // Move & Resize commands (and their keyboard shortcuts) to the app menu.
    ...(isMac ? { role: 'windowMenu' } : {}),
    submenu: isMac
      ? [
          { role: 'minimize', label: '最小化' },
          { role: 'zoom', label: '缩放' },
          { role: 'front', label: '全部置于前台' }
        ]
      : // Click-only Close: the `close` role would register its default
        // CommandOrControl+W accelerator, claiming the chord before the
        // before-input-event run that routes a terminal-focused Ctrl+W to the
        // shell's word erase (#65457). The menu item still closes the focused
        // window when clicked.
        [
          { role: 'minimize', label: '最小化' },
          {
            click: (_menuItem, window) => window?.close(),
            label: '关闭',
            registerAccelerator: false
          }
        ]
  }
}

export { windowMenuTemplate }

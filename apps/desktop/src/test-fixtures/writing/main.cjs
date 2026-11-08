const { app, BrowserWindow } = require('electron')
const [userData, html] = process.argv.slice(-2)
app.setPath('userData', userData)
app.whenReady().then(() => {
  const window = new BrowserWindow({
    width: 1440,
    height: 1000,
    webPreferences: { contextIsolation: true, nodeIntegration: false }
  })
  window.webContents.on('will-prevent-unload', event => event.preventDefault())
  window.loadFile(html)
})
app.on('window-all-closed', () => app.quit())

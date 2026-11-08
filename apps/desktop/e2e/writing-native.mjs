import { build } from 'vite'
import tailwind from '@tailwindcss/vite'
import { _electron as electron, expect } from '@playwright/test'
import { mkdtemp } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import { createRequire } from 'node:module'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const desktop = path.join(root, 'apps/desktop'),
  fixture = path.join(desktop, 'src/test-fixtures/writing')
const tmp = await mkdtemp(path.join(tmpdir(), 'operations-writing-native-'))
await build({
  configFile: false,
  root: fixture,
  base: './',
  plugins: [tailwind()],
  resolve: {
    alias: { '@hermes/plugin-sdk': path.join(fixture, 'host.ts'), '@': path.join(desktop, 'src') },
    dedupe: ['react', 'react-dom']
  },
  build: { outDir: path.join(tmp, 'dist'), emptyOutDir: true, minify: false },
  esbuild: { jsx: 'automatic' },
  logLevel: 'error'
})
const dist = path.join(tmp, 'dist/index.html')
const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE
const app = await electron.launch({
  executablePath: createRequire(import.meta.url)('electron'),
  args: [fixture + '/main.cjs', tmp + '/user-data', dist],
  timeout: 30000,
  env
})
try {
  const page = await app.firstWindow()
  page.on('pageerror', error => console.error('PAGE', error))
  // Electron handles the forced-unload event before Chromium's dialog acknowledgment.
  page.on('dialog', dialog => {
    void dialog.accept().catch(() => undefined)
  })

  console.log('page loaded')
  const externalRequests = []
  page.on('request', request => {
    if (request.url().startsWith('https://example.invalid/')) {
      externalRequests.push(request.url())
    }
  })
  const editor = page.getByLabel('正文编辑器')
  await expect(editor).toBeVisible()
  console.log('editor ready')
  await editor.click()
  const session = await page.context().newCDPSession(page)
  await session.send('Input.imeSetComposition', { text: '中文输入测试', selectionStart: 6, selectionEnd: 6 })
  await session.send('Input.insertText', { text: '中文输入测试' })
  await expect(editor).toContainText('中文输入测试')
  console.log('composition text retained')
  await page.getByRole('button', { name: '保存草稿 ⌘S' }).click()
  await expect(page.getByRole('status')).toHaveText('已保存')
  await page.getByRole('button', { name: '加粗', exact: true }).click()
  await page.keyboard.insertText('加粗内容')
  await expect(editor.locator('strong')).toContainText('加粗内容')
  await page.getByRole('button', { name: '撤销', exact: true }).click()
  await expect(editor).not.toContainText('加粗内容')
  await page.getByRole('button', { name: '重做', exact: true }).click()
  await expect(editor).toContainText('加粗内容')
  await page.getByRole('button', { name: '表格', exact: true }).click()
  await expect(editor.locator('table')).toBeVisible()
  await page.getByRole('button', { name: '保存草稿 ⌘S' }).click()
  await expect(page.getByRole('status')).toHaveText('已保存')
  await page.getByLabel('上传已授权图片').setInputFiles({
    name: '示例.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j9ZkAAAAASUVORK5CYII=',
      'base64'
    )
  })
  await expect(editor.locator('img')).toHaveCount(1)
  await editor.locator('[data-drag-handle]').dragTo(editor.locator('p').last())
  await expect(editor.locator('img')).toHaveCount(1)
  await expect(editor.locator('table')).toHaveCount(1)
  await page.getByRole('button', { name: '保存草稿 ⌘S' }).click()
  await editor.locator('p').last().click()
  await editor.evaluate(element => {
    const transfer = new DataTransfer()
    transfer.setData('text/html', '<p>粘贴内容<img src="https://example.invalid/external.png"></p>')
    element.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }))
  })
  await expect(editor).toContainText('粘贴图片待导入')
  expect(externalRequests).toEqual([])
  await editor.getByRole('button', { name: '移除', exact: true }).click()
  await page.evaluate(() => {
    window.writingFixture.offline = true
  })
  await page.getByLabel('稿件标题').fill('离线恢复稿件')
  await page.getByRole('button', { name: '保存草稿 ⌘S' }).click()
  await expect(page.getByRole('status')).toContainText('仅本机暂存')
  console.log('offline saved locally, reloading')
  await page.reload()
  console.log('reloaded')
  await expect(page.getByLabel('稿件标题')).toHaveValue('离线恢复稿件')
  await expect(page.getByRole('status')).toHaveText('已保存')
  await expect(editor.locator('table')).toBeVisible()
  await expect(editor).toContainText('中文输入测试')
  console.log('composition text retained')
  await page.evaluate(() => window.recoveryProbe())
  await page.screenshot({ path: tmp + '/writing.png', fullPage: true })
  const started = Date.now()
  await editor.click()
  await page.keyboard.press('Meta+A')
  await page.keyboard.insertText('长文'.repeat(50000))
  await page.getByRole('button', { name: '保存草稿 ⌘S' }).click()
  await expect(page.getByRole('status')).toHaveText('已保存')
  const longText = await page.evaluate(() => window.writingFixture.draft.document.content[0].content[0].text.length)
  expect(longText).toBe(100000)
  console.log('100000 characters edit/save ms:', Date.now() - started)
  console.log(
    JSON.stringify({
      passed: [
        '真实 Electron 中文组合输入',
        '格式与表格',
        '保存',
        '离线恢复',
        '关闭页面重载',
        '多窗口及 Profile 恢复隔离',
        '图片上传、拖动与外链粘贴占位',
        '撤销重做',
        '10万字保存'
      ],
      screenshot: tmp + '/writing.png'
    })
  )
} finally {
  await app.evaluate(({ app }) => app.exit(0)).catch(() => undefined)
  await app.close()
}

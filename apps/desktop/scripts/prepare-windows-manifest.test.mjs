import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, expect, it, vi } from 'vitest'
import { launcherApplications, prepareWindowsManifest } from './prepare-windows-manifest.mjs'

const roots = []
afterEach(() => { for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true }); vi.unstubAllEnvs() })

it('stages a real manifest with native version, shared data policy and separate administrative aliases', () => {
  for (const key of ['HERMES_BUILD_COMMIT', 'HERMES_PAYLOAD_TAG', '_HERMES_CHANNEL_REQUEST_JSON']) vi.stubEnv(key, '')
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'windows-manifest-')); roots.push(root)
  fs.mkdirSync(path.join(root, 'assets/appx'), { recursive: true })
  fs.mkdirSync(path.join(root, 'build/agent-payload'), { recursive: true })
  fs.copyFileSync(path.join(import.meta.dirname, '../assets/msix-manifest.xml'), path.join(root, 'assets/msix-manifest.xml'))
  for (const name of ['Square44x44Logo.png','Square150x150Logo.png','StoreLogo.png']) fs.writeFileSync(path.join(root, 'assets/appx', name), 'fixture')
  fs.writeFileSync(path.join(root, 'product-identity.cjs'), "module.exports={appNamePascal:'TestAgent',artifactNamePascal:'TestAgent',displayName:'Test & Agent'}")
  fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify({ version: '1.2.3' }))
  fs.writeFileSync(path.join(root, 'build/agent-payload/manifest.json'), JSON.stringify({ launchers: ['hermes', 'hermes-acp'] }))
  prepareWindowsManifest(root)
  const xml = fs.readFileSync(path.join(root, 'build/msix-manifest.xml'), 'utf8')
  expect(xml).toContain('Version="1.2.3.0"')
  expect(xml).toContain('FileSystemWriteVirtualization>disabled')
  expect(xml).toContain('Id="TestAgentCli0"')
  expect(xml).toContain('Id="TestAgentCli1"')
  expect(xml).toContain('Test &#38; Agent')
  expect(xml).toContain('bin\\hermes-acp.exe')
  expect(() => launcherApplications(['../escape'], { appNamePascal: 'Test', displayName: 'Test' })).toThrow()
})

import fs from 'node:fs'
import path from 'node:path'
import { appIdentity, nativeManifestTemplate } from '../../../scripts/msix-shared.mjs'

/** @param {string} text */
export function xmlAttribute(text) {
  return String(text).replace(/[&<>"']/g, char => `&#${char.charCodeAt(0)};`)
}

/** Each retained administrative launcher owns an independent hidden application.
 * @param {string[]} launchers
 * @param {{appNamePascal: string, displayName: string}} identity
 */
export function launcherApplications(launchers, identity) {
  return launchers.map((name, index) => {
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(name)) throw new Error('Invalid payload launcher name')
    const executable = `app\\resources\\agent-payload\\bin\\${name}.exe`
    return `<Application Id="${xmlAttribute(identity.appNamePascal)}Cli${index}" Executable="${executable}" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="${xmlAttribute(identity.displayName)}" Description="Administrative CLI"
        Square150x150Logo="assets\\Square150x150Logo.png" Square44x44Logo="assets\\Square44x44Logo.png"
        BackgroundColor="transparent" AppListEntry="none" />
      <Extensions><uap5:Extension Category="windows.appExecutionAlias" Executable="${executable}" EntryPoint="Windows.FullTrustApplication">
        <uap5:AppExecutionAlias><uap5:ExecutionAlias Alias="${name}.exe" /></uap5:AppExecutionAlias>
      </uap5:Extension></Extensions>
    </Application>`
  }).join('\n')
}

/** @param {string} desktop */
export function prepareWindowsManifest(desktop) {
  const { identity, version } = appIdentity(desktop)
  const build = path.join(desktop, 'build')
  const assets = path.join(desktop, 'assets/appx')
  fs.mkdirSync(path.join(build, 'appx'), { recursive: true })
  for (const required of ['Square44x44Logo.png', 'Square150x150Logo.png', 'StoreLogo.png']) {
    if (!fs.existsSync(path.join(assets, required))) throw new Error(`Missing Windows asset: ${required}`)
  }
  for (const name of fs.readdirSync(assets).filter(name => name.endsWith('.png'))) {
    fs.copyFileSync(path.join(assets, name), path.join(build, 'appx', name))
  }
  const payload = JSON.parse(fs.readFileSync(path.join(build, 'agent-payload/manifest.json'), 'utf8'))
  if (!Array.isArray(payload.launchers)) throw new Error('Bundled payload has no declared launchers')
  const template = fs.readFileSync(path.join(desktop, 'assets/msix-manifest.xml'), 'utf8')
  const applications = launcherApplications(payload.launchers, identity)
  const manifest = nativeManifestTemplate(template, version).replace('</Applications>', `${applications}\n</Applications>`)
  fs.writeFileSync(path.join(build, 'msix-manifest.xml'), manifest)
}

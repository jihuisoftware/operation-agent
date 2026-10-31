import { existsSync, realpathSync } from 'node:fs'
import path from 'node:path'

import { buildDesktopBackendEnv } from './backend-env'
import { resolveSourcePython } from './source-python'
import { launcherInstallDirectoryAsync, resolveInstallationLauncher } from './updater-process'

export interface SourceBackend {
  kind: 'command' | 'python'
  label: string
  command: string
  args: string[]
  env: NodeJS.ProcessEnv
  root: string
  bootstrap: false
  shell: boolean
  local: 'installed'
}

interface SourceOptions {
  isWindows?: boolean
  env?: NodeJS.ProcessEnv
}

/** Resolve the explicitly selected checkout used by Desktop development. */
export async function resolveDevelopmentSourceBackend(
  root: string,
  args: string[],
  options: SourceOptions & { hermesHome?: string } = {}
): Promise<SourceBackend | null> {
  const env = options.env ?? process.env
  const override = env.HERMES_DESKTOP_PYTHON

  if (override && existsSync(override)) {
    return createSourcePythonBackend(root, override, args, options)
  }

  // A committed PM runtime owns the ABI. A leftover venv may predate that Python.
  if (resolveInstallationLauncher(root, options.isWindows, options.hermesHome ?? env.HERMES_HOME)) {
    const backend = await resolveSourceInstallationBackend(root, args, {
      ...options, hermesHome: options.hermesHome ?? env.HERMES_HOME
    })

    if (!backend) {
      throw new Error(`仓库运行时启动器不可用或指向其他目录：${root}。请在该仓库执行 source ./activate 后重试。`)
    }

    return backend
  }

  return createSourcePythonBackend(root, resolveSourcePython(root, {
    isWindows: options.isWindows
  }), args, options)
}

/** Keep the validated command. PM owns interpreter and generation selection. */
export async function resolveSourceInstallationBackend(
  root: string,
  args: string[],
  options: SourceOptions & { hermesHome?: string } = {}
): Promise<SourceBackend | null> {
  if (!existsSync(path.join(root, 'hermes_cli', 'main.py'))) {
    return null
  }

  const isWindows: boolean = options.isWindows ?? process.platform === 'win32'
  const launcher: string | null = resolveInstallationLauncher(root, isWindows, options.hermesHome)

  if (!launcher) {
    return null
  }

  const shell: boolean = isWindows && /\.(cmd|bat)$/i.test(launcher)
  const command: string = shell ? `"${launcher}"` : launcher
  const env: NodeJS.ProcessEnv = buildDesktopBackendEnv({ currentEnv: options.env ?? process.env })

  const reportedRoot = await launcherInstallDirectoryAsync(launcher, root, {
    ...process.env, ...options.env, ...env
  })

  if (reportedRoot !== realpathSync(root)) {
    return null
  }

  return {
    kind: 'command',
    label: `Hermes at ${root}`,
    command,
    args: [...args],
    env,
    root,
    bootstrap: false,
    shell,
    local: 'installed'
  }
}

/** Developer overrides retain their interpreter, even outside the checkout. */
export function createSourcePythonBackend(
  root: string,
  python: string | null,
  args: string[],
  options: SourceOptions = {}
): SourceBackend | null {
  if (!python) {
    return null
  }

  let command: string = python

  if ((options.isWindows ?? process.platform === 'win32') && /[\\/]pythonw\.exe$/i.test(python)) {
    // Use only the console interpreter beside the selected windowless one.
    const consolePython: string = python.replace(/pythonw\.exe$/i, 'python.exe')

    if (existsSync(consolePython)) {
      command = consolePython
    }
  }

  return {
    kind: 'python',
    label: `Hermes source at ${root}`,
    command,
    args: ['-m', 'hermes_cli.main', ...args],
    // The backend runs in the user's workspace cwd, and the selected
    // interpreter need not have this checkout installed: name it explicitly.
    // (The scrubbed inherited value could point at another checkout.)
    env: { ...buildDesktopBackendEnv({ currentEnv: options.env ?? process.env }), PYTHONPATH: root },
    root,
    bootstrap: false,
    shell: false,
    local: 'installed'
  }
}

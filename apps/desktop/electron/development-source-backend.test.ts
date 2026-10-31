import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test } from 'vitest'

import { resolveDevelopmentSourceBackend } from './source-backend'

test.skipIf(process.platform === 'win32')('development starts the selected installation instead of a stale checkout Python', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'desktop-dev-runtime-'))

  try {
    fs.mkdirSync(path.join(root, 'hermes_cli'))
    fs.writeFileSync(path.join(root, 'hermes_cli', 'main.py'), '')
    fs.mkdirSync(path.join(root, '.hermes', 'bin'), { recursive: true })
    fs.mkdirSync(path.join(root, 'venv', 'bin'), { recursive: true })
    const launcher = path.join(root, '.hermes', 'bin', 'hermes')
    const stale = path.join(root, 'venv', 'bin', 'python')
    fs.writeFileSync(launcher, `#!/bin/sh\nif [ "$1" = --version ]; then\n  echo 'Install directory: ${fs.realpathSync(root)}'\nelse\n  echo managed-runtime\nfi\n`, { mode: 0o755 })
    fs.writeFileSync(stale, '#!/bin/sh\nexit 93\n', { mode: 0o755 })
    const env = { HERMES_HOME: path.join(root, 'profile') }
    const backend = await resolveDevelopmentSourceBackend(root, ['gateway', 'ensure', '--json'], { env })

    assert.ok(backend)
    assert.equal(backend.command, launcher)
    assert.deepEqual(backend.args, ['gateway', 'ensure', '--json'])
    assert.equal(execFileSync(backend.command, backend.args, { env: { ...process.env, ...env, ...backend.env }, encoding: 'utf8' }).trim(), 'managed-runtime')

    fs.writeFileSync(launcher, '#!/bin/sh\nexit 1\n', { mode: 0o755 })
    await assert.rejects(resolveDevelopmentSourceBackend(root, [], { env }), /source \.\/activate/)

    fs.writeFileSync(launcher, '#!/bin/sh\necho "Install directory: /"\n', { mode: 0o755 })
    await assert.rejects(resolveDevelopmentSourceBackend(root, [], { env }), /source \.\/activate/)

    const explicit = await resolveDevelopmentSourceBackend(root, [], {
      env: { ...env, HERMES_DESKTOP_PYTHON: stale }
    })

    assert.equal(explicit?.command, stale, 'an explicit developer interpreter retains its owner')
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

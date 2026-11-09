import { execFileSync } from 'node:child_process'
import { copyFileSync, realpathSync, mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, symlinkSync, statSync, utimesSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { afterEach, expect, test } from 'vitest'
import { productOutput, publishDirectory, withProduct } from '../scripts/build/frontend-common.mjs'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(import.meta.url)
const temporary = []
afterEach(() => { for (const dir of temporary.splice(0)) rmSync(dir, { recursive: true, force: true }) })
function fixture() {
  const dir = mkdtempSync(path.join(realpathSync(tmpdir()), 'product builders '))
  temporary.push(dir)
  return dir
}
function put(root, name, content) {
  const file = path.join(root, name)
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, content)
}
function dependency(root, workspace, name) {
  const target = path.dirname(require.resolve(`${name}/package.json`))
  const link = path.join(root, workspace, 'node_modules', name)
  mkdirSync(path.dirname(link), { recursive: true })
  symlinkSync(target, link, 'junction')
}
test('product outputs exclude the source tree except supported generated destinations', async () => {
  const inputs = ['apps/desktop/src', 'apps/shared', 'node_modules']
  // Only call the read-only validator on real source paths: never publish here.
  for (const name of ['pm', 'hermes_cli', 'scripts', 'pyproject.toml', '.git', 'tools', '.build', 'apps/desktop/build/products']) {
    expect(() => productOutput(repo, path.join(repo, name), inputs), name).toThrow(/output/i)
  }
  const base = fixture()
  const source = path.join(base, 'source')
  mkdirSync(source)
  for (const name of ['new-source-file', 'pm/generated', 'hermes_cli/tui_dist-copy', 'apps/desktop/dist-copy', 'apps/desktop/build/native-deps-copy', 'hermes_cli/tui_dist/assets',
    'apps/desktop/build/native-deps-win32-x64/nested', 'apps/desktop/build/native-deps-freebsd-x64', 'apps/desktop/build/native-deps-win32-ia32']) {
    expect(() => productOutput(source, path.join(source, name), inputs), name).toThrow(/output/i)
  }
  for (const name of ['apps/desktop/dist', 'apps/desktop/build/native-deps', 'apps/desktop/build/native-deps-win32-x64',
    'apps/desktop/build/native-deps-darwin-arm64', 'apps/desktop/build/products/tui', '.build/tui', '.build/termux/tui']) {
    const out = path.join(source, name)
    expect(productOutput(source, out, inputs).out).toBe(out)
    expect(existsSync(out)).toBe(false)
    await withProduct(out, product => put(product, 'built.txt', 'product'))
    expect(productOutput(source, out, inputs).out).toBe(out)
  }
  const adjacent = path.join(base, 'tui-product')
  expect(productOutput(source, adjacent, inputs).out).toBe(adjacent)
  // Ownership never exempts a directory from source/input protection.
  const sourceDir = path.join(source, 'pm')
  await withProduct(sourceDir, product => put(product, 'keep.txt', 'source'))
  expect(() => productOutput(source, sourceDir, inputs)).toThrow(/output/i)
  const generatedInput = path.join(source, '.build/tui')
  expect(() => productOutput(source, generatedInput, ['.build/tui'])).toThrow(/overlap/)
  symlinkSync(sourceDir, path.join(source, '.build/redirect'), 'junction')
  symlinkSync(sourceDir, path.join(base, 'source-alias'), 'junction')
  for (const alias of [path.join(source, '.build/redirect'), path.join(base, 'source-alias')]) {
    expect(() => productOutput(source, path.join(alias, 'output'), inputs)).toThrow(/output/i)
  }
})

test('publication replaces only builder-owned directories and rechecks ownership after compilation', async () => {
  const base = fixture()
  const source = path.join(base, 'source')
  mkdirSync(source)
  const unowned = path.join(base, 'unowned')
  put(unowned, 'keep.txt', 'not a product')
  mkdirSync(path.join(base, 'empty'))
  put(base, 'file', 'not a directory')
  symlinkSync(unowned, path.join(base, 'link'), 'junction')
  symlinkSync(path.join(base, 'absent'), path.join(base, 'dangling'), 'junction')
  const inTree = path.join(source, '.build/unowned')
  put(inTree, 'keep.txt', 'not a product either')
  for (const out of [unowned, path.join(base, 'empty'), path.join(base, 'file'), path.join(base, 'link'), path.join(base, 'dangling'), inTree]) {
    expect(() => productOutput(source, out, []), out).toThrow(/output/i)
    let compiled = false
    await expect(withProduct(out, () => { compiled = true })).rejects.toThrow(/output/i)
    expect(compiled).toBe(false)
  }
  const staged = path.join(base, 'staged')
  put(staged, 'new.txt', 'new product')
  expect(() => publishDirectory(staged, unowned)).toThrow(/output/i)
  expect(readFileSync(path.join(unowned, 'keep.txt'), 'utf8')).toBe('not a product')
  expect(readFileSync(path.join(staged, 'new.txt'), 'utf8')).toBe('new product')

  const out = path.join(base, 'product')
  await withProduct(out, product => put(product, 'old.txt', 'old product'))
  expect(productOutput(source, out, []).out).toBe(out)
  await withProduct(out, product => put(product, 'new.txt', 'new product'))
  expect(existsSync(path.join(out, 'old.txt'))).toBe(false)
  await expect(withProduct(out, () => { throw new Error('compile failed') })).rejects.toThrow('compile failed')
  expect(readFileSync(path.join(out, 'new.txt'), 'utf8')).toBe('new product')

  const occupied = path.join(base, 'occupied-during-build')
  await expect(withProduct(occupied, product => {
    put(product, 'new.txt', 'new product')
    put(occupied, 'keep.txt', 'created by someone else')
  })).rejects.toThrow(/output/i)
  expect(readFileSync(path.join(occupied, 'keep.txt'), 'utf8')).toBe('created by someone else')
})

test('existing npm build directories can be rebuilt without adopting arbitrary outputs', async () => {
  const source = fixture()
  for (const name of ['apps/desktop/dist', 'apps/desktop/build/native-deps']) {
    const out = path.join(source, name)
    put(out, 'old-output', 'previous compiler output')
    await withProduct(out, product => put(product, 'new-output', 'rebuilt'), { source })
    expect(existsSync(path.join(out, 'old-output'))).toBe(false)
    expect(readFileSync(path.join(out, 'new-output'), 'utf8')).toBe('rebuilt')
  }
  const unrelated = path.join(source, 'pm')
  put(unrelated, 'keep', 'source')
  await expect(withProduct(unrelated, () => {}, { source })).rejects.toThrow(/output/i)
})

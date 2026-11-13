/** Desktop hosts admitted by the operations distribution. */
function requireDesktopPlatform(platform = process.platform, arch = process.arch) {
  if ((platform === 'darwin' && ['arm64', 'x64'].includes(arch)) || (platform === 'win32' && arch === 'x64')) return
  throw new Error('运营平台支持 macOS（Apple Silicon / Intel）和 Windows x64。')
}

module.exports = { requireDesktopPlatform }

if (require.main === module) requireDesktopPlatform()

/** The operations desktop is distributed and run only on macOS. */
function requireMacOS(platform = process.platform) {
  if (platform !== 'darwin') throw new Error('宠物社区运营助手仅支持 macOS。')
}

module.exports = { requireMacOS }

if (require.main === module) requireMacOS()

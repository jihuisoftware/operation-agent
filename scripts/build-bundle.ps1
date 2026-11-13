# Build the checked-out commit as a native Windows x64 MSIX. No uploads or channel promotion.
# Run from a developer shell with Git and Python 3.11+; PM supplies the pinned build tools.
param([switch]$Signed, [switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw 'This entry requires Windows x64.' }
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = (Get-Command python -ErrorAction Stop).Source
& $python -c 'import sys,struct; assert sys.version_info >= (3,11) and struct.calcsize(chr(80)) == 8'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ x64 is required.' }
Push-Location $repo
$signingKeys = @('CSC_LINK','CSC_KEY_PASSWORD','CSC_NAME','WIN_CSC_LINK','WIN_CSC_KEY_PASSWORD',
  'AZURE_SIGN_ENDPOINT','AZURE_SIGN_ACCOUNT','AZURE_SIGN_PROFILE','AZURE_SIGN_PUBLISHER',
  'AZURE_CLIENT_ID','AZURE_CLIENT_SECRET','AZURE_TENANT_ID','CSC_IDENTITY_AUTO_DISCOVERY')
$saved = @{}
try {
  $changes = & git status --porcelain --untracked-files=all
  if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Commit the intended changes first: the bundle contains HEAD, not the working tree.' }
  $commit = (& git rev-parse HEAD).Trim()
  if ($Signed -and -not (($env:AZURE_SIGN_ENDPOINT -and $env:AZURE_CLIENT_ID) -or $env:CSC_LINK -or $env:WIN_CSC_LINK)) {
    throw 'Signed build requested without configured Windows signing credentials.'
  }
  foreach ($key in $signingKeys) { $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process') }
  if (-not $Signed) {
    foreach ($key in $signingKeys) { [Environment]::SetEnvironmentVariable($key, $null, 'Process') }
    $env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
  }
  $arguments = @('scripts/bundles/desktop.py', '--commit', $commit, '--variant', 'bundled', '--clean')
  if ($PrepareOnly) { $arguments += '--prepare-only' }
  if ($Signed) { $arguments += @('--', '-c.forceCodeSigning=true') }
  & $python @arguments
  if ($LASTEXITCODE -ne 0) { throw "Windows bundle failed: $LASTEXITCODE" }
  Write-Host 'Output: apps/desktop/release. Unsigned MSIX is a test artifact, not a distributable installer.'
} finally {
  foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
  Pop-Location
}

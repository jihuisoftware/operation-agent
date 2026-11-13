# Read-only startup acceptance of an unpacked Windows bundle using an isolated Profile.
# Does not log in, publish content, or install certificates.
param([Parameter(Mandatory=$true)][string]$AppDirectory)
$ErrorActionPreference = 'Stop'
$appDir = (Resolve-Path $AppDirectory).Path
$payload = Join-Path $appDir 'resources/agent-payload'
$manifest = Get-Content -LiteralPath (Join-Path $payload 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.target -ne 'win32-x64') { throw 'Expected a Windows x64 payload.' }
$launcher = Join-Path $payload $manifest.runtime.commands.hermes
if (-not (Test-Path -LiteralPath $launcher)) { throw 'Missing bundled administrative launcher.' }
$executables = @(Get-ChildItem -LiteralPath $appDir -File -Filter '*.exe' | Where-Object { $_.Name -notin @('elevate.exe', 'Uninstall.exe') })
if ($executables.Count -ne 1) { throw 'Expected exactly one desktop executable in the unpacked root.' }
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('operations-windows-smoke-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$previous = @{}
foreach ($key in @('HERMES_HOME','HERMES_DESKTOP_USER_DATA_DIR','ELECTRON_RUN_AS_NODE')) {
  $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
$appProcess = $null
try {
  $env:HERMES_HOME = Join-Path $testRoot 'profile'
  $env:HERMES_DESKTOP_USER_DATA_DIR = Join-Path $testRoot 'desktop'
  Remove-Item env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
  & $launcher gateway stop
  if ($LASTEXITCODE -ne 0) { throw 'Could not establish a stopped isolated Gateway before startup.' }
  $appProcess = Start-Process -FilePath $executables[0].FullName -PassThru
  $deadline = [DateTime]::UtcNow.AddSeconds(120)
  $ready = $false
  while ([DateTime]::UtcNow -lt $deadline) {
    $appProcess.Refresh()
    if ($appProcess.HasExited) { throw 'Desktop exited before startup acceptance.' }
    $statusFile = Join-Path $env:HERMES_HOME 'gateway_state.json'
    if (Test-Path -LiteralPath $statusFile) {
      $status = Get-Content -LiteralPath $statusFile -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($status.pid -and (Get-Process -Id $status.pid -ErrorAction SilentlyContinue) -and $appProcess.MainWindowHandle -ne 0) {
        $ready = $true; break
      }
    }
    Start-Sleep -Milliseconds 250
  }
  if (-not $ready) { throw 'Desktop window and isolated Gateway did not become available within 120 seconds.' }
  Write-Host "Startup accepted. Isolated evidence directory: $testRoot"
} finally {
  if ($appProcess -and -not $appProcess.HasExited) {
    [void]$appProcess.CloseMainWindow()
    if (-not $appProcess.WaitForExit(10000)) { Stop-Process -Id $appProcess.Id -Force }
  }
  & $launcher gateway stop
  $stopCode = $LASTEXITCODE
  foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
  if ($stopCode -ne 0) { throw 'Isolated Gateway cleanup failed.' }
}

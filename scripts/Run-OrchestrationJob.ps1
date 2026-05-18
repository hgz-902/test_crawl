param(
  [Parameter(Mandatory=$true)][string]$ProjectRoot,
  [string]$JobId = "",
  [switch]$AllowEmailSend
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $ProjectRoot

$envPath = Join-Path $ProjectRoot ".env"
if (Test-Path -LiteralPath $envPath) {
  Get-Content -LiteralPath $envPath -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
    $parts = $line.Split("=", 2)
    $name = $parts[0].Trim()
    $value = $parts[1].Trim().Trim('"').Trim("'")
    if ($name) {
      [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
  }
}

$logDir = Join-Path $ProjectRoot "runtime\scheduled-task"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeRunName = if ($JobId) { ($JobId -replace '[^\p{L}\p{Nd}_-]+', '_') } else { "batch" }
$logPath = Join-Path $logDir "$stamp-$safeRunName.log"

$args = @("-m", "crawler_app.scheduled_runner")
if ($JobId) {
  $args += @("--job-id", $JobId)
}
if ($AllowEmailSend) {
  $args += "--allow-email-send"
}

$pythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
  $pythonPath = "python"
}

& $pythonPath @args *> $logPath
exit $LASTEXITCODE

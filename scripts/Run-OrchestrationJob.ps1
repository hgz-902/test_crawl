param(
  [Parameter(Mandatory=$true)][string]$ProjectRoot,
  [string]$JobId = "",
  [switch]$AllowEmailSend
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $ProjectRoot

$logDir = Join-Path $ProjectRoot "runtime\scheduled-task"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$safeRunName = if ($JobId) { ($JobId -replace '[^\p{L}\p{Nd}_-]+', '_') } else { "batch" }
$logPath = Join-Path $logDir "$stamp-$safeRunName.log"

function Write-RunLog {
  param([string]$Message)
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff K"
  Add-Content -LiteralPath $logPath -Encoding UTF8 -Value "[$timestamp] $Message"
}

Write-RunLog "Scheduled orchestration task started."
Write-RunLog "ProjectRoot=$ProjectRoot"
Write-RunLog "JobId=$JobId"
Write-RunLog "AllowEmailSend=$AllowEmailSend"
Write-RunLog "PowerShell=$($PSVersionTable.PSVersion)"

function Load-DotEnvFile {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [switch]$Override
  )
  if (-not (Test-Path -LiteralPath $Path)) {
    Write-RunLog ".env not found. path=$Path"
    return
  }
  $envCount = 0
  try {
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
      $line = $_.Trim()
      if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
      $parts = $line.Split("=", 2)
      $name = $parts[0].Trim()
      $value = $parts[1].Trim().Trim('"').Trim("'")
      if ($name) {
        $existing = [Environment]::GetEnvironmentVariable($name, "Process")
        if ($Override -or [string]::IsNullOrEmpty($existing)) {
          [Environment]::SetEnvironmentVariable($name, $value, "Process")
          $script:envCount += 1
        }
      }
    }
    Write-RunLog ".env loaded. path=$Path entries=$envCount override=$Override"
  } catch {
    Write-RunLog ".env load failed. path=$Path error=$($_.Exception.Message)"
    exit 1
  }
}

$projectEnvPath = Join-Path $ProjectRoot ".env"
$sharedEnvPath = $env:CRAWLER_SHARED_ENV_FILE
if (-not $sharedEnvPath) {
  $desktopPath = [Environment]::GetFolderPath("Desktop")
  $sharedEnvPath = Get-ChildItem -LiteralPath $desktopPath -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "00. HGZ\.env" } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1
}
Load-DotEnvFile -Path $projectEnvPath -Override
if ($sharedEnvPath) {
  Load-DotEnvFile -Path $sharedEnvPath
} else {
  Write-RunLog "shared .env not found under Desktop\\*\\00. HGZ\\.env"
}

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

Write-RunLog "PythonPath=$pythonPath"
Write-RunLog "PythonArgs=$($args -join ' ')"

$stdoutPath = Join-Path $logDir "$stamp-$safeRunName.stdout.tmp"
$stderrPath = Join-Path $logDir "$stamp-$safeRunName.stderr.tmp"

try {
  $process = Start-Process `
    -FilePath $pythonPath `
    -ArgumentList $args `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -NoNewWindow `
    -Wait `
    -PassThru
  $exitCode = $process.ExitCode
  Write-RunLog "Python process finished. exit_code=$exitCode"
  if (Test-Path -LiteralPath $stdoutPath) {
    $stdout = Get-Content -LiteralPath $stdoutPath -Raw -Encoding UTF8
    if ($stdout) {
      Write-RunLog "----- python stdout begin -----"
      Add-Content -LiteralPath $logPath -Encoding UTF8 -Value $stdout.TrimEnd()
      Write-RunLog "----- python stdout end -----"
    } else {
      Write-RunLog "Python stdout was empty."
    }
  }
  if (Test-Path -LiteralPath $stderrPath) {
    $stderr = Get-Content -LiteralPath $stderrPath -Raw -Encoding UTF8
    if ($stderr) {
      Write-RunLog "----- python stderr begin -----"
      Add-Content -LiteralPath $logPath -Encoding UTF8 -Value $stderr.TrimEnd()
      Write-RunLog "----- python stderr end -----"
    } else {
      Write-RunLog "Python stderr was empty."
    }
  }
} catch {
  Write-RunLog "PowerShell wrapper failed: $($_.Exception.Message)"
  $exitCode = 1
} finally {
  Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
}

Write-RunLog "Scheduled orchestration task finished. exit_code=$exitCode"
exit $exitCode

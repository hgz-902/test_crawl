[CmdletBinding(SupportsShouldProcess=$true)]
param(
  [string]$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path,
  [switch]$DeleteTasks,
  [switch]$DeleteLaunchers
)

$ErrorActionPreference = "Stop"

function Get-ProjectNamespace {
  param([string]$Root)
  $resolved = (Resolve-Path -LiteralPath $Root).Path.ToLowerInvariant()
  $sha1 = [System.Security.Cryptography.SHA1]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($resolved)
    $hash = $sha1.ComputeHash($bytes)
    (($hash | ForEach-Object { $_.ToString("x2") }) -join "").Substring(0, 12)
  }
  finally {
    $sha1.Dispose()
  }
}

function Test-ScheduledTaskNotFoundError {
  param([System.Management.Automation.ErrorRecord]$ErrorRecord)
  $message = [string]$ErrorRecord.Exception.Message
  $fullyQualifiedId = [string]$ErrorRecord.FullyQualifiedErrorId
  return (
    $fullyQualifiedId -like "*NotFound*" -or
    $message -match "찾지 못|찾을 수|not found|cannot find|No MSFT_ScheduledTask|ObjectNotFound"
  )
}

$namespace = Get-ProjectNamespace -Root $ProjectRoot
$taskPath = "\CrawlerOrchestration\$namespace\"
$launcherDir = Join-Path $env:LOCALAPPDATA "CrawlerOrchestration\$namespace"
$registryPath = Join-Path $ProjectRoot "orchestration_state\scheduler_registry.json"

Write-Host "ProjectRoot=$ProjectRoot"
Write-Host "TaskPath=$taskPath"

$tasks = @(Get-ScheduledTask -TaskPath $taskPath -ErrorAction SilentlyContinue)
if ($tasks.Count -eq 0) {
  Write-Host "No managed orchestration tasks found."
}

foreach ($task in $tasks) {
  $fullName = "$($task.TaskPath)$($task.TaskName)"
  if ($PSCmdlet.ShouldProcess($fullName, "Stop scheduled task")) {
    try {
      if ($task.State -eq "Running") {
        Stop-ScheduledTask -TaskPath $task.TaskPath -TaskName $task.TaskName
        Write-Host "Stopped $fullName"
      }
      else {
        Write-Host "Skipped stop for $fullName (state=$($task.State))"
      }
    }
    catch {
      Write-Warning "Failed to stop ${fullName}: $($_.Exception.Message)"
    }
  }

  if ($DeleteTasks -and $PSCmdlet.ShouldProcess($fullName, "Delete scheduled task")) {
    try {
      Unregister-ScheduledTask -TaskPath $task.TaskPath -TaskName $task.TaskName -Confirm:$false -ErrorAction Stop
      Write-Host "Deleted $fullName"
    }
    catch {
      if (Test-ScheduledTaskNotFoundError -ErrorRecord $_) {
        Write-Host "Deleted $fullName (already missing)"
      }
      else {
        throw
      }
    }
  }
}

if ($DeleteLaunchers -and (Test-Path -LiteralPath $launcherDir)) {
  if ($PSCmdlet.ShouldProcess($launcherDir, "Delete generated launcher files")) {
    Get-ChildItem -LiteralPath $launcherDir -Filter "crawler_*.ps1" -File -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -LiteralPath $launcherDir -Filter "crawler_*.cmd" -File -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-Host "Deleted managed launcher files under $launcherDir"
  }
}

if ($DeleteTasks) {
  $registryDir = Split-Path -Parent $registryPath
  New-Item -ItemType Directory -Force -Path $registryDir | Out-Null
  $registryPayload = [PSCustomObject]@{
    updated_at = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:sszzz")
    tasks = @()
  } | ConvertTo-Json -Depth 4
  Set-Content -LiteralPath $registryPath -Value ($registryPayload + "`n") -Encoding UTF8
  Write-Host "Cleared scheduler registry $registryPath"
}

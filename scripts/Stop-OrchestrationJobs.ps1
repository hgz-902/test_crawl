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

function Test-TaskCommandNotFoundMessage {
  param([string]$Message)
  return $Message -match "찾지 못|찾을 수|not found|cannot find|No MSFT_ScheduledTask|ObjectNotFound"
}

function Invoke-ScheduledTaskCommand {
  param([string[]]$Arguments)
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = (& schtasks.exe @Arguments 2>&1 | ForEach-Object { "$_" } | Out-String).Trim()
    $exitCode = $LASTEXITCODE
  }
  catch {
    $output = [string]$_.Exception.Message
    $exitCode = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 1 }
  }
  finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  [PSCustomObject]@{
    ExitCode = $exitCode
    Output = $output
  }
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
    if ($task.State -eq "Running") {
      $endResult = Invoke-ScheduledTaskCommand -Arguments @("/End", "/TN", $fullName)
      if ($endResult.ExitCode -eq 0) {
        Write-Host "Stopped $fullName"
      }
      elseif (Test-TaskCommandNotFoundMessage -Message $endResult.Output) {
        Write-Host "Stopped $fullName (already missing)"
      }
      else {
        Write-Warning "Failed to stop ${fullName}: $($endResult.Output)"
      }
    }
    else {
      Write-Host "Skipped stop for $fullName (state=$($task.State))"
    }
  }

  if ($DeleteTasks -and $PSCmdlet.ShouldProcess($fullName, "Delete scheduled task")) {
    $deleteResult = Invoke-ScheduledTaskCommand -Arguments @("/Delete", "/TN", $fullName, "/F")
    if ($deleteResult.ExitCode -eq 0) {
      Write-Host "Deleted $fullName"
    }
    elseif (Test-TaskCommandNotFoundMessage -Message $deleteResult.Output) {
      Write-Host "Deleted $fullName (already missing)"
    }
    else {
      throw "Failed to delete ${fullName}: $($deleteResult.Output). Run the crawler server or VS Code with an account that can delete this project's Windows Task Scheduler tasks."
    }
  }
}

if ($DeleteTasks) {
  $remainingTasks = @(Get-ScheduledTask -TaskPath $taskPath -ErrorAction SilentlyContinue)
  if ($remainingTasks.Count -gt 0) {
    $remainingNames = ($remainingTasks | ForEach-Object { "$($_.TaskPath)$($_.TaskName)" }) -join ", "
    throw "Monitoring stop did not delete all managed tasks. Remaining tasks: $remainingNames"
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

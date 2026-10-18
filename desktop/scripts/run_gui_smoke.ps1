param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [Parameter(Mandatory = $true)][string]$Destination,
    [ValidateSet("offscreen", "windows")][string]$Platform = "offscreen"
)

$ErrorActionPreference = 'Stop'
$taskExecutable = [System.IO.Path]::GetFullPath($Executable)
$taskDestination = [System.IO.Path]::GetFullPath($Destination)
if (-not (Test-Path -LiteralPath $taskExecutable -PathType Leaf)) {
    throw 'GUI executable not found'
}
# Launch the windowed program through the native Windows process API. The
# structured report carries diagnostics; no redirected console handles needed.
$env:QT_QPA_PLATFORM = $Platform
$env:QSG_RHI_BACKEND = 'software'
$taskArguments = @('--smoke-test', ('"' + $taskDestination + '"'))
$taskProcess = Start-Process -FilePath $taskExecutable -ArgumentList $taskArguments -WindowStyle Hidden -PassThru
if (-not $taskProcess.WaitForExit(55000)) {
    # This is exactly the process created above, never another open application.
    Stop-Process -Id $taskProcess.Id -ErrorAction SilentlyContinue
    throw 'Packaged GUI smoke timed out'
}
if ($taskProcess.ExitCode -ne 0) { throw "GUI exited with code $($taskProcess.ExitCode)" }
$taskReportPath = Join-Path $taskDestination 'result.json'
$taskReport = Get-Content -LiteralPath $taskReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $taskReport.success) { throw $taskReport.message }
Write-Output $taskReport.message

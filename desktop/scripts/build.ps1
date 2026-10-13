$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
& $taskPython -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $taskPython scripts/lock_dependencies.py
if ($LASTEXITCODE -ne 0) { throw 'Dependency lock failed' }
& $taskPython -m unittest discover -s tests -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
& $taskPython -m PyInstaller --noconfirm ChaoxingDesktop.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item -LiteralPath README.md,LICENSE,THIRD_PARTY_NOTICES.md -Destination dist/ChaoxingDesktop
Set-Location -LiteralPath ([System.IO.Directory]::GetParent($taskRoot).FullName)
& $taskPython (Join-Path $taskRoot 'tests/release_smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Packaged release smoke test failed' }
Write-Output 'Built dist/ChaoxingDesktop/ChaoxingDesktop.exe. Keep the entire folder together.'

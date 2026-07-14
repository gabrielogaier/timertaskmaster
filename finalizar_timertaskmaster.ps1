$ErrorActionPreference = "SilentlyContinue"
$root = [System.IO.Path]::GetFullPath($PSScriptRoot)
$targets = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^pythonw?\.exe$' -and
    $_.CommandLine -and
    $_.CommandLine -like ('*' + $root + '*') -and
    $_.CommandLine -like '*app.py*'
}
if (-not $targets) {
    Write-Host "Nenhum processo do Timer Task Master foi encontrado."
    exit 0
}
foreach ($process in $targets) {
    Write-Host ("Finalizando PID {0}..." -f $process.ProcessId)
    Stop-Process -Id $process.ProcessId -Force
}
Write-Host "Timer Task Master finalizado."

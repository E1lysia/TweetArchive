param([int]$Index = 0, [string]$DataRoot = '', [string]$RuntimeRoot = '')

[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$ErrorActionPreference = 'Stop'
if (-not $RuntimeRoot) { $RuntimeRoot = Split-Path -Parent $PSScriptRoot }
if (-not $DataRoot) {
    $pointer = Join-Path $RuntimeRoot 'tools\storage.local.json'
    if (Test-Path -LiteralPath $pointer) {
        $DataRoot = (Get-Content -LiteralPath $pointer -Raw -Encoding UTF8 | ConvertFrom-Json).data_root
        if (-not (Test-Path -LiteralPath (Join-Path $DataRoot '_推文归档\tweets.sqlite'))) { throw '资料库磁盘不可用，请在软件中重新选择资料库。' }
    } else { $DataRoot = $RuntimeRoot }
}
$PY = Join-Path $RuntimeRoot 'python\python.exe'
& $PY -X utf8 (Join-Path $RuntimeRoot 'tools\latest_tweets.py') --root $DataRoot --runtime-root $RuntimeRoot --index $Index
exit $LASTEXITCODE

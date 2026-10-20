param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$RunArguments
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PSScriptRoot '.browsers'
$interpreterPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $interpreterPath)) {
    throw '未找到虚拟环境，请按 README 的安装步骤创建 .venv。'
}
Push-Location $PSScriptRoot
try {
    & $interpreterPath -m framework.cli @RunArguments
    $runExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $runExitCode

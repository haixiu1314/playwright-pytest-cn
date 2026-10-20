param([ValidateSet('chromium')][string]$Browser = 'chromium')
$ErrorActionPreference = 'Stop'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PSScriptRoot '.browsers'
$env:PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT = '30000'
& (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -m playwright install $Browser
if ($LASTEXITCODE -ne 0) {
    Write-Host '浏览器下载失败。若本机已有 Edge，将 config/environments.yaml 的 browser 改成 msedge。'
    exit $LASTEXITCODE
}
Write-Host "浏览器安装目录：$env:PLAYWRIGHT_BROWSERS_PATH"

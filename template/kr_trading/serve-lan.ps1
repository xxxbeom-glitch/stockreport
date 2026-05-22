# 스마트폰 미리보기 — 예전처럼 python http.server 한 줄과 동일 (+ LAN 주소만 출력)
# 사용: .\serve-lan.ps1

param(
    [int]$Port = 0
)

$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8
# JSON은 data/mock_trading/ — 프로젝트 루트에서 서빙
Set-Location (Join-Path $PSScriptRoot "..\..")

function Get-LanIPv4 {
    $candidates = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notmatch "^169\.254\." -and
            $_.PrefixOrigin -ne "WellKnown"
        }
    if (-not $candidates) { return $null }
    $wifi = $candidates | Where-Object { $_.InterfaceAlias -match "Wi-?Fi|WLAN|무선|Wireless" } | Select-Object -First 1
    if ($wifi) { return $wifi.IPAddress }
    return ($candidates | Select-Object -First 1 -ExpandProperty IPAddress)
}

function Test-PortFree([int]$P) {
    -not (Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue)
}

$ip = Get-LanIPv4
if (-not $ip) {
    Write-Host "Wi-Fi/이더넷 IP를 찾지 못했습니다." -ForegroundColor Red
    exit 1
}

if ($Port -le 0) {
    foreach ($p in @(8080, 5500, 5501, 8888)) {
        if (Test-PortFree $p) { $Port = $p; break }
    }
}
if ($Port -le 0) {
    Write-Host "8080/5500/5501/8888 포트가 모두 사용 중입니다." -ForegroundColor Red
    Write-Host "다른 PowerShell 창의 python 서버를 Ctrl+C로 종료한 뒤 다시 실행하세요."
    exit 1
}

Write-Host ""
Write-Host "스마트폰 주소:" -ForegroundColor Cyan
Write-Host "http://${ip}:${Port}/template/kr_trading/" -ForegroundColor Yellow
Write-Host ""
Write-Host "(PC 브라우저: http://127.0.0.1:${Port}/template/kr_trading/ )"
Write-Host "종료: Ctrl+C"
Write-Host ""

python -m http.server $Port --bind 0.0.0.0

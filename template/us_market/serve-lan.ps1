# 같은 Wi-Fi 스마트폰에서 미리보기 — 0.0.0.0 바인딩 + LAN URL 출력
$Port = 8080
$Dir = $PSScriptRoot

$ip = (
  Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object {
    $_.IPAddress -notlike '127.*' -and
    $_.PrefixOrigin -ne 'WellKnown' -and
    $_.InterfaceAlias -notmatch 'vEthernet|Loopback'
  } |
  Select-Object -First 1 -ExpandProperty IPAddress
)

if (-not $ip) {
  Write-Host "LAN IP를 찾지 못했습니다. ipconfig 로 IPv4를 확인하세요."
  exit 1
}

Write-Host ""
Write-Host "PC에서:     http://127.0.0.1:$Port/index.html"
Write-Host "스마트폰:   http://${ip}:$Port/index.html"
Write-Host "(스타일 안 보이면 강력 새로고침 / 캐시 삭제)"
Write-Host ""
Write-Host "폰에서 안 열리면 Windows 방화벽에서 Python 또는 포트 $Port 인바운드를 허용하세요."
Write-Host "(관리자 PowerShell) netsh advfirewall firewall add rule name=`"HTTP $Port`" dir=in action=allow protocol=TCP localport=$Port"
Write-Host ""

Set-Location $Dir
python -m http.server $Port --bind 0.0.0.0

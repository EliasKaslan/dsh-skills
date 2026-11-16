# Pure ASCII. Keep codex / ChatGPT working while BOTH UniVPN instances are up.
#
# Symptom: single VPN is fine; with the blue-zone instance AND the A5 instance
# both connected, codex / chatgpt.com cannot connect (TLS fails, app hangs).
#
# Cause: the blue-zone client injects DNS 114.114.114.114 on its TAP and the TAP
# has InterfaceMetric 1 (Ethernet is 25), so Windows prefers 114DNS. When the
# 114.114.114.114/32 tunnel route flaps (the client rewrites routes about every
# 6 s), a query can escape to the physical link and come back GFW-poisoned, e.g.
# chatgpt.com -> 162.125.34.133 / 2001::76b8:1a71 (Dropbox IP + bogus AAAA),
# while 8.8.8.8 / 1.1.1.1 answer correctly with 104.18.32.47 / 172.64.155.209.
# Windows caches the poisoned answer, so the failure is intermittent and hard to
# reproduce on demand.
#
# Fix: stop depending on the VPN-injected resolver at all.
#   1) put a trusted resolver on the VPN TAP (replacing whatever it injects),
#   2) add NRPT rules so OpenAI/ChatGPT names always go to public resolvers
#      (the VPN client never touches NRPT, so this survives reconnects/reboots).
#
# Usage (needs elevation, one shot):
#   Start-Process powershell -Verb RunAs -Wait -ArgumentList `
#     '-NoProfile -ExecutionPolicy Bypass -File "<path>\fix-vpn-openai-dns.ps1"'
#
# Rollback:
#   Get-DnsClientNrptRule | Remove-DnsClientNrptRule -Force
#   Set-DnsClientServerAddress -InterfaceIndex <tap> -ResetServerAddresses

$log = Join-Path $env:TEMP 'fix-vpn-openai-dns.log'
"=== start $(Get-Date -Format s) ===" | Out-File -FilePath $log -Encoding UTF8
function W($m) { "$(Get-Date -Format 'HH:mm:ss')  $m" | Out-File -FilePath $log -Append -Encoding UTF8 }

$id = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
W ("elevated=" + $id.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))

# Locate the blue-zone TAP by route, never by ifIndex (ifIndex changes on reinstall).
$tap = @(Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue |
         Where-Object { $_.DestinationPrefix -eq '192.168.0.0/16' } |
         Select-Object -First 1)
if ($tap.Count -gt 0) {
    $tapIdx = $tap[0].InterfaceIndex
    $tapName = (Get-NetAdapter -InterfaceIndex $tapIdx -ErrorAction SilentlyContinue).Name
    W ("blue TAP = ifIndex $tapIdx / $tapName")

    # 1) replace the injected resolver with a trusted one
    try {
        Set-DnsClientServerAddress -InterfaceIndex $tapIdx -ServerAddresses '8.8.8.8', '1.1.1.1' -ErrorAction Stop
        W "OK  TAP resolver -> 8.8.8.8,1.1.1.1"
    } catch { W ('FAIL set TAP resolver: ' + $_.Exception.Message) }
} else {
    W 'SKIP blue-zone tunnel not up (no 192.168.0.0/16 route); NRPT only'
}

# 2) NRPT: pin OpenAI/ChatGPT namespaces to public resolvers
$ns = '.chatgpt.com', '.openai.com', '.oaistatic.com', '.oaiusercontent.com', '.openai.org'
$existing = @(Get-DnsClientNrptRule -ErrorAction SilentlyContinue)
foreach ($n in $ns) {
    if (@($existing | Where-Object { $_.Namespace -eq $n }).Count -gt 0) { W ("SKIP nrpt $n (present)"); continue }
    try {
        Add-DnsClientNrptRule -Namespace $n -NameServers '8.8.8.8', '1.1.1.1' -ErrorAction Stop
        W ("OK  nrpt $n")
    } catch { W ("FAIL nrpt $n : " + $_.Exception.Message) }
}

try { Clear-DnsClientCache -ErrorAction Stop; W 'OK  dns cache cleared' }
catch { W ('FAIL flushdns: ' + $_.Exception.Message) }

# 3) verify
W '--- verify ---'
foreach ($n in 'chatgpt.com', 'api.openai.com') {
    $ips = (Resolve-DnsName $n -Type A -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress) -join ', '
    W ("$n -> " + $ips)
}
W '--- nrpt ---'
(Get-DnsClientNrptRule | Format-Table -AutoSize Namespace, NameServers | Out-String) |
    Out-File -FilePath $log -Append -Encoding UTF8
W '--- resolvers ---'
(Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses.Count -gt 0 }) |
    Format-Table InterfaceIndex, InterfaceAlias, ServerAddresses -AutoSize | Out-String |
    Out-File -FilePath $log -Append -Encoding UTF8
"=== end $(Get-Date -Format s) ===" | Out-File -FilePath $log -Append -Encoding UTF8
Write-Host "log: $log"

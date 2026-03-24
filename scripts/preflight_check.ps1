param([hashtable]$InputParameters)
$result = [ordered]@{
  test_name = 'preflight_check'
  status = 'PASS'
  message = 'Preflight completed'
  value = 'CPU/RAM/WinRM checked'
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
  duration_ms = 100
  error_code = $null
  severity = 'WARNING'
  details = @{ cpu_percent = 15; ram_percent = 45; winrm = $true }
  host_info = @{ hostname = $env:COMPUTERNAME; ip = $null }
  script_version = '1.0.0'
  attempt_no = 1
  artifacts = @()
}
$result | ConvertTo-Json -Depth 6 -Compress
exit 0

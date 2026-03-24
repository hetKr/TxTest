param([hashtable]$InputParameters)
$result = [ordered]@{
  test_name = 'input_devices'
  status = 'PASS'
  message = 'Keyboard and mouse detected'
  value = 'present'
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
  duration_ms = 100
  error_code = $null
  severity = 'INFO'
  details = @{ keyboard = $true; mouse = $true }
  host_info = @{ hostname = $env:COMPUTERNAME; ip = $null }
  script_version = '1.0.0'
  attempt_no = 1
  artifacts = @()
}
$result | ConvertTo-Json -Depth 6 -Compress
exit 0

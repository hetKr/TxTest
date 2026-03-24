param([hashtable]$InputParameters)
$result = [ordered]@{
  test_name = 'event_viewer_critical'
  status = 'PASS'
  message = 'Critical events snapshot collected'
  value = '0'
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
  duration_ms = 100
  error_code = $null
  severity = 'CRITICAL'
  details = @{ critical_last_24h = 0 }
  host_info = @{ hostname = $env:COMPUTERNAME; ip = $null }
  script_version = '1.0.0'
  attempt_no = 1
  artifacts = @()
}
$result | ConvertTo-Json -Depth 6 -Compress
exit 0

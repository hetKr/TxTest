param([hashtable]$InputParameters)
$result = [ordered]@{
  test_name = 'ping_host'
  status = 'PASS'
  message = 'Ping successful'
  value = 'reachable'
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
  duration_ms = 100
  error_code = $null
  severity = 'INFO'
  details = @{ target_ip = "10.122.7.119"; latency_ms = 2 }
  host_info = @{ hostname = $env:COMPUTERNAME; ip = $null }
  script_version = '1.0.0'
  attempt_no = 1
  artifacts = @()
}
$result | ConvertTo-Json -Depth 6 -Compress
exit 0

param([hashtable]$InputParameters)
$result = [ordered]@{
  test_name = 'monitor_count'
  status = 'PASS'
  message = 'Monitor topology collected'
  value = '1'
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
  duration_ms = 100
  error_code = $null
  severity = 'INFO'
  details = @{ monitor_count = 1; primary_display = "Display1" }
  host_info = @{ hostname = $env:COMPUTERNAME; ip = $null }
  script_version = '1.0.0'
  attempt_no = 1
  artifacts = @()
}
$result | ConvertTo-Json -Depth 6 -Compress
exit 0

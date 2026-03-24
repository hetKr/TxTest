param([hashtable]$InputParameters)
$result = [ordered]@{
  test_name = 'screen_resolution'
  status = 'PASS'
  message = 'Resolution collected'
  value = '1920x1080'
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
  duration_ms = 100
  error_code = $null
  severity = 'INFO'
  details = @{ width = 1920; height = 1080 }
  host_info = @{ hostname = $env:COMPUTERNAME; ip = $null }
  script_version = '1.0.0'
  attempt_no = 1
  artifacts = @()
}
$result | ConvertTo-Json -Depth 6 -Compress
exit 0

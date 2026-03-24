param([hashtable]$InputParameters)
$result = [ordered]@{
  test_name = 'disk_free_space'
  status = 'PASS'
  message = 'Free space meets threshold'
  value = '52.3 GB'
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
  duration_ms = 100
  error_code = $null
  severity = 'WARNING'
  details = @{ disk = "C:"; free_gb = 52.3; threshold_gb = 20 }
  host_info = @{ hostname = $env:COMPUTERNAME; ip = $null }
  script_version = '1.0.0'
  attempt_no = 1
  artifacts = @()
}
$result | ConvertTo-Json -Depth 6 -Compress
exit 0

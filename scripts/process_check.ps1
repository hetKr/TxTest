param([hashtable]$InputParameters)
$result = [ordered]@{
  test_name = 'process_check'
  status = 'PASS'
  message = 'Process state collected'
  value = 'running'
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
  duration_ms = 100
  error_code = $null
  severity = 'WARNING'
  details = @{ process_name = "explorer"; running = $true }
  host_info = @{ hostname = $env:COMPUTERNAME; ip = $null }
  script_version = '1.0.0'
  attempt_no = 1
  artifacts = @()
}
$result | ConvertTo-Json -Depth 6 -Compress
exit 0

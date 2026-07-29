Get-Process python | Format-Table Id, ProcessName
Write-Host "---"
Get-Process python | Where-Object { $_.CommandLine -like "*app.py*" } | ForEach-Object {
    Write-Host "Killing PID: $($_.Id)"
    Stop-Process -Force -Id $_.Id
}
Start-Sleep -Seconds 2
netstat -ano | Select-String ":5001"

function Test-EduScanPort {
    param([int]$Port)

    $client = [Net.Sockets.TcpClient]::new()
    try {
        return $client.ConnectAsync('127.0.0.1', $Port).Wait(400) -and $client.Connected
    } catch [AggregateException] {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Save-EduScanProcess {
    param([string]$Directory, [int]$Port, [Diagnostics.Process]$Process, [bool]$Offline)

    $statePath = Join-Path $Directory "service-$Port.json"
    $state = @{
        ProcessId = $Process.Id
        StartTicks = $Process.StartTime.ToUniversalTime().Ticks
        Offline = $Offline
    } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($statePath, $state)
}

function Get-EduScanProcess {
    param([string]$Directory, [int]$Port)

    $statePath = Join-Path $Directory "service-$Port.json"
    if (-not (Test-Path -LiteralPath $statePath)) { return }
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json -ErrorAction Stop
        $process = Get-Process -Id $state.ProcessId -ErrorAction Stop
        if ($process.StartTime.ToUniversalTime().Ticks -eq $state.StartTicks) {
            return [pscustomobject]@{ Process = $process; Offline = [bool]$state.Offline }
        }
    } catch {
        # A stopped or inaccessible process cannot be safely managed by its old PID.
    }
}

function Stop-EduScanProcess {
    param([Diagnostics.Process]$Process)

    if ($Process -and -not $Process.HasExited) {
        try {
            $Process.Kill()
        } catch {
            if (-not $Process.HasExited) { throw }
        }
        if (-not $Process.WaitForExit(5000)) { throw "EduScan process $($Process.Id) did not stop." }
    }
}

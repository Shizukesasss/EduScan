$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$manager = Join-Path $PSScriptRoot 'manage-eduscan.ps1'
$form = New-Object System.Windows.Forms.Form
$form.Text = 'EduScan Launcher'
$form.ClientSize = [System.Drawing.Size]::new(516, 274)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = [System.Drawing.Font]::new('Segoe UI', 10)
$form.AutoScaleMode = 'Font'

$actions = @{
    'Start All'   = 'start'
    'Restart All' = 'restart'
    'Start API'   = 'start-api'
    'Restart API' = 'restart-api'
}
$buttons = @()
$left = 12
foreach ($label in 'Start All', 'Restart All', 'Start API', 'Restart API') {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $label
    $button.Tag = $actions[$label]
    $button.Location = [System.Drawing.Point]::new($left, 12)
    $button.Size = [System.Drawing.Size]::new(120, 36)
    $form.Controls.Add($button)
    $buttons += $button
    $left += 124
}

$output = New-Object System.Windows.Forms.TextBox
$output.Multiline = $true
$output.ReadOnly = $true
$output.ScrollBars = 'Vertical'
$output.Location = [System.Drawing.Point]::new(12, 60)
$output.Size = [System.Drawing.Size]::new(492, 154)
$output.Text = 'Start All launches the EduScan website and API.'
$form.Controls.Add($output)

$open = New-Object System.Windows.Forms.Button
$open.Text = 'Open EduScan'
$open.Location = [System.Drawing.Point]::new(12, 226)
$open.Size = [System.Drawing.Size]::new(120, 36)
$open.Add_Click({
    try { Start-Process 'http://127.0.0.1:5175/' }
    catch { $output.Text = $_.Exception.Message }
})
$form.Controls.Add($open)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 250
$script:worker = $null
$timer.Add_Tick({
    if (-not $script:worker.HasExited -or -not $script:stdout.IsCompleted -or -not $script:stderr.IsCompleted) {
        return
    }
    $timer.Stop()
    try {
        $output.Text = ($script:stdout.Result + $script:stderr.Result).Trim()
        if ($script:worker.ExitCode -ne 0 -and -not $output.Text) {
            $output.Text = "EduScan exited with code $($script:worker.ExitCode)."
        }
    } finally {
        $script:worker.Dispose()
        $script:worker = $null
        foreach ($button in $buttons) { $button.Enabled = $true }
    }
})

foreach ($button in $buttons) {
    $button.Add_Click({
        param($sender, $eventArgs)
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = Join-Path $PSHOME 'powershell.exe'
        $startInfo.Arguments = '-NoProfile -STA -ExecutionPolicy Bypass -File "' + $manager +
            '" -ShowDatabasePrompt -Action ' + $sender.Tag
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        try {
            $script:worker = [System.Diagnostics.Process]::Start($startInfo)
            $script:stdout = $script:worker.StandardOutput.ReadToEndAsync()
            $script:stderr = $script:worker.StandardError.ReadToEndAsync()
            foreach ($control in $buttons) { $control.Enabled = $false }
            $output.Text = 'Working... If asked, confirm the remote database startup to continue.'
            $timer.Start()
        } catch {
            $output.Text = $_.Exception.Message
        }
    })
}

$form.Add_FormClosing({
    param($sender, $eventArgs)
    $eventArgs.Cancel = $null -ne $script:worker
})

$created = $false
$mutex = [System.Threading.Mutex]::new($true, 'Local\EduScanLauncher', [ref]$created)
try {
    if ($created) {
        [void]$form.ShowDialog()
    } else {
        [void][System.Windows.Forms.MessageBox]::Show('EduScan Launcher is already open.', $form.Text)
    }
} finally {
    if ($created) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
    $timer.Dispose()
    $form.Dispose()
}

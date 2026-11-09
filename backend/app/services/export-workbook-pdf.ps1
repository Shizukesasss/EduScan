param(
    [Parameter(Mandatory)][string]$Source,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$Terms,
    [switch]$Draft
)

$ErrorActionPreference = 'Stop'
$excel = New-Object -ComObject Excel.Application
$book = $null
try {
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $excel.AutomationSecurity = 3  # Disable macros in uploaded templates.
    $book = $excel.Workbooks.Open($Source, 0, $true)
    if ($Terms) {
        $included = $Terms.Split(',')
        foreach ($sheet in $book.Worksheets) {
            if ($sheet.Visible -ne -1) { continue }
            $isTerm = $sheet.Name -match '^TERM\s+(\d+)\b' -and $included -contains $Matches[1]
            if (-not $isTerm -and $sheet.Name -ne 'FINAL GRADES') { continue }
            $sheet.Select()
            $pdf = Join-Path $OutputDirectory ('sheet-{0:D4}.pdf' -f [int]$sheet.Index)
            $sheet.ExportAsFixedFormat(0, $pdf, 0, $false, $false)
        }
    } else {
        if ($Draft) {
            $book.Worksheets.Item(1).PageSetup.CenterHeader = 'DRAFT PREVIEW - NOT FINAL'
        }
        $pdf = Join-Path $OutputDirectory 'sheet-0000.pdf'
        $book.ExportAsFixedFormat(0, $pdf, 0, $false, $false)
    }
} finally {
    try {
        if ($book) { $book.Close($false) }
    } finally {
        $excel.Quit()
    }
}

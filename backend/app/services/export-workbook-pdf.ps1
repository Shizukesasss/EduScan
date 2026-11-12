param(
    [Parameter(Mandatory)][string]$Source,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$Terms,
    [switch]$Draft,
    [switch]$Landscape
)

$ErrorActionPreference = 'Stop'

function Set-ClassRecordRosterPrintRows {
    param($Sheet)
    $isSummary = $Sheet.Name -eq 'FINAL GRADES'
    if ($Sheet.Name -eq 'Grade Summary' -or ($isSummary -and $Sheet.Range('A4').Value2 -eq 'Learner')) {
        $Sheet.PageSetup.PrintTitleRows = '$1:$4'
        return
    }
    $candidateRows = if ($isSummary) { @(13, 14, 16) } else { @(16, 17, 18) }
    $maleHeading = $null
    foreach ($row in $candidateRows) {
        $femaleHeading = $row + 51
        if (([string]$Sheet.Range("B$row").Value2).Trim() -eq 'MALE' -and
            ([string]$Sheet.Range("B$femaleHeading").Value2).Trim() -eq 'FEMALE') {
            $maleHeading = $row
            break
        }
    }
    if (-not $maleHeading) { return }

    $lastTitleRow = $maleHeading - 1
    $Sheet.PageSetup.PrintTitleRows = ('$1:${0}' -f $lastTitleRow)
    $nameColumn = if ($isSummary -and $maleHeading -eq 16) { 'D' } else { 'C' }
    # The fixed class record templates have two 50-row roster blocks.
    foreach ($firstRow in @(($maleHeading + 1), ($maleHeading + 52))) {
        $lastRow = $firstRow + 49
        $names = $Sheet.Range("${nameColumn}${firstRow}:${nameColumn}${lastRow}").Value2
        $lastName = $names.GetUpperBound(0)
        $firstName = $names.GetLowerBound(0)
        $column = $names.GetLowerBound(1)
        while ($lastName -ge $firstName -and [string]::IsNullOrWhiteSpace($names.GetValue($lastName, $column))) {
            $lastName--
        }
        $firstBlankRow = $firstRow + $lastName - $firstName + 1
        if ($firstBlankRow -le $lastRow) {
            $Sheet.Range("${nameColumn}${firstBlankRow}:${nameColumn}${lastRow}").EntireRow.Hidden = $true
        }
    }
}

function Set-LandscapePageFit {
    param($Sheet)
    Set-ClassRecordRosterPrintRows $Sheet
    $layout = $Sheet.PageSetup
    $layout.Orientation = 2  # xlLandscape
    $layout.Zoom = $false
    $layout.FitToPagesWide = 1
    $layout.FitToPagesTall = $false
    $layout.CenterHorizontally = $true
    if ($Sheet.Range('A10').Value2 -eq 'No.' -and
        $Sheet.Range('B11').Value2 -eq 'HIGHEST POSSIBLE SCORE' -and
        $Sheet.HPageBreaks.Count -eq 1) {
        $lastLearner = 12
        if ($Sheet.Range('A13').Value2 -eq 2) {
            $lastLearner = $Sheet.Range('A12').End(-4121).Row  # xlDown
        }
        # A conversion table can spill below an otherwise single-page roster.
        if ($Sheet.HPageBreaks.Item(1).Location.Row -gt $lastLearner -and
            $Sheet.Range("A$($lastLearner + 3)").Value2 -like 'Grade conversion*') {
            $layout.FitToPagesTall = 1
        }
    }
}

$excel = New-Object -ComObject Excel.Application
$book = $null
try {
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $excel.AutomationSecurity = 3  # Disable macros in uploaded templates.
    $book = $excel.Workbooks.Open($Source, 0, $true)
    if ($Terms) {
        $included = $Terms.Split(',')
        $termSheets = @($book.Worksheets | Where-Object {
            $_.Visible -eq -1 -and $_.Name -match '^TERM\s+(\d+)\b' -and $included -contains $Matches[1]
        })
        $includeSummary = $included.Count -gt 1 -or $termSheets.Count -gt 1
        foreach ($sheet in $book.Worksheets) {
            if ($sheet.Visible -ne -1) { continue }
            $isTerm = $sheet.Name -match '^TERM\s+(\d+)\b' -and $included -contains $Matches[1]
            if (-not $isTerm -and -not ($includeSummary -and $sheet.Name -eq 'FINAL GRADES')) { continue }
            $sheet.Select()
            if ($Landscape) { Set-LandscapePageFit $sheet }
            $pdf = Join-Path $OutputDirectory ('sheet-{0:D4}.pdf' -f [int]$sheet.Index)
            $sheet.ExportAsFixedFormat(0, $pdf, 0, $false, $false)
        }
    } else {
        if ($Landscape) {
            foreach ($sheet in $book.Worksheets) {
                if ($sheet.Visible -eq -1) { Set-LandscapePageFit $sheet }
            }
        }
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

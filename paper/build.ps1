# Build manuscript and supplementary materials with pdflatex and biber.
# Both documents are always built together, since they cross-reference each other
# via their .aux files (xr-hyper).
# Usage: .\build.ps1 [-clean] [-view]

param(
    [switch]$clean,
    [switch]$view
)

$documents = @(
    @{ Dir = "manuscript"; TexFile = "manuscript" },
    @{ Dir = "sm"; TexFile = "supplementary_materials" }
)
$pdflatex = "pdflatex"
$biber = "biber"
$root = $PSScriptRoot

function Clean-Files($doc) {
    $extensions = @("aux", "bbl", "bcf", "blg", "fdb_latexmk", "fls", "log", "out", "run.xml", "synctex.gz", "toc")
    foreach ($ext in $extensions) {
        $file = Join-Path $root "$($doc.Dir)/$($doc.TexFile).$ext"
        if (Test-Path $file) {
            Remove-Item $file -Force
        }
    }
}

function Invoke-Tool($tool, $doc) {
    Push-Location (Join-Path $root $doc.Dir)
    try {
        if ($tool -eq $biber) {
            & $biber $doc.TexFile | Out-Null
        }
        else {
            & $pdflatex -interaction=nonstopmode "$($doc.TexFile).tex" | Out-Null
        }
        return ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq 1)
    }
    finally {
        Pop-Location
    }
}

function Build-Documents {
    # Pass 1 writes .aux/.bcf files, pass 2 resolves citations and cross-document
    # references, pass 3 settles references that moved in pass 2.
    $steps = @(
        @{ Name = "First pdflatex pass"; Tool = $pdflatex },
        @{ Name = "Biber bibliography pass"; Tool = $biber },
        @{ Name = "Second pdflatex pass"; Tool = $pdflatex },
        @{ Name = "Third pdflatex pass (final references)"; Tool = $pdflatex }
    )

    $i = 1
    foreach ($step in $steps) {
        foreach ($doc in $documents) {
            Write-Host "$i. $($step.Name): $($doc.TexFile)..." -ForegroundColor Green
            if (-not (Invoke-Tool $step.Tool $doc)) {
                Write-Host "$($step.Name) failed for $($doc.TexFile)!" -ForegroundColor Red
                return $false
            }
        }
        $i++
    }
    return $true
}

function Show-Summary($doc) {
    $log = Join-Path $root "$($doc.Dir)/$($doc.TexFile).log"
    if (Test-Path $log) {
        $warnings = @(Select-String "Warning:" $log).Count
        $undefined = @(Select-String "undefined" $log).Count
        if ($warnings -gt 0 -or $undefined -gt 0) {
            Write-Host "`nCompilation Summary ($($doc.TexFile)):" -ForegroundColor Yellow
            if ($warnings -gt 0) { Write-Host "  Warnings: $warnings" }
            if ($undefined -gt 0) { Write-Host "  Undefined references: $undefined" }
        }
    }
}

# Main execution
try {
    if ($clean) {
        Write-Host "Cleaning intermediate files..." -ForegroundColor Cyan
        foreach ($doc in $documents) { Clean-Files $doc }
    }

    Write-Host "Building LaTeX documents..." -ForegroundColor Cyan
    $success = Build-Documents

    if ($success) {
        foreach ($doc in $documents) {
            Write-Host "`n[SUCCESS] PDF: $($doc.Dir)/$($doc.TexFile).pdf" -ForegroundColor Green
        }
    }
    else {
        Write-Host "`n[WARNING] Build completed (check logs for warnings)" -ForegroundColor Yellow
    }
    foreach ($doc in $documents) { Show-Summary $doc }

    if ($success -and $view) {
        Write-Host "Opening PDFs..." -ForegroundColor Cyan
        foreach ($doc in $documents) {
            Start-Process (Join-Path $root "$($doc.Dir)/$($doc.TexFile).pdf")
        }
    }
}
catch {
    Write-Host "Error: $($_)" -ForegroundColor Red
    exit 1
}

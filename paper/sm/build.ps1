# Build LaTeX document with pdflatex and biber
# Usage: .\build.ps1 [clean] [view]

param(
    [switch]$clean,
    [switch]$view
)

$texFile = "main"
$pdflatex = "pdflatex"
$biber = "biber"

function Clean-Files {
    Write-Host "Cleaning intermediate files..." -ForegroundColor Cyan
    $filesToRemove = @(
        "$texFile.aux",
        "$texFile.bbl",
        "$texFile.bcf",
        "$texFile.blg",
        "$texFile.fdb_latexmk",
        "$texFile.fls",
        "$texFile.log",
        "$texFile.out",
        "$texFile.run.xml",
        "$texFile.synctex.gz",
        "$texFile.toc"
    )

    foreach ($file in $filesToRemove) {
        if (Test-Path $file) {
            Remove-Item $file -Force
        }
    }
}

function Build-Document {
    Write-Host "Building LaTeX document..." -ForegroundColor Cyan

    # First pdflatex pass
    Write-Host "1. First pdflatex pass..." -ForegroundColor Green
    & $pdflatex -interaction=nonstopmode "$texFile.tex" | Out-Null
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
        Write-Host "First pdflatex pass failed!" -ForegroundColor Red
        return $false
    }

    # Biber pass
    Write-Host "2. Biber bibliography pass..." -ForegroundColor Green
    & $biber "$texFile" | Out-Null
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
        Write-Host "Biber pass failed!" -ForegroundColor Red
        return $false
    }

    # Second pdflatex pass
    Write-Host "3. Second pdflatex pass..." -ForegroundColor Green
    & $pdflatex -interaction=nonstopmode "$texFile.tex" | Out-Null
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
        Write-Host "Second pdflatex pass failed!" -ForegroundColor Red
        return $false
    }

    # Third pdflatex pass (ensure all references are correct)
    Write-Host "4. Third pdflatex pass (final references)..." -ForegroundColor Green
    & $pdflatex -interaction=nonstopmode "$texFile.tex" | Out-Null
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
        Write-Host "Third pdflatex pass failed!" -ForegroundColor Red
        return $false
    }

    return $true
}

function Show-Summary {
    if (Test-Path "$texFile.log") {
        $warnings = @(Select-String "Warning:" "$texFile.log").Count
        $undefined = @(Select-String "undefined" "$texFile.log").Count
        if ($warnings -gt 0 -or $undefined -gt 0) {
            Write-Host "`nCompilation Summary:" -ForegroundColor Yellow
            if ($warnings -gt 0) { Write-Host "  Warnings: $warnings" }
            if ($undefined -gt 0) { Write-Host "  Undefined references: $undefined" }
        }
    }
}

# Main execution
try {
    if ($clean) {
        Clean-Files
    }

    $success = Build-Document

    if ($success) {
        Write-Host "`n[SUCCESS] Build successful! PDF: $texFile.pdf" -ForegroundColor Green
        Show-Summary

        if ($view) {
            Write-Host "Opening PDF..." -ForegroundColor Cyan
            Start-Process "$texFile.pdf"
        }
    }
    else {
        Write-Host "`n[WARNING] Build completed (check log for warnings)" -ForegroundColor Yellow
        Show-Summary
    }
}
catch {
    Write-Host "Error: $($_)" -ForegroundColor Red
    exit 1
}

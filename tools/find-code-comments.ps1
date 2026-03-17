#!/usr/bin/env pwsh
<#
.SYNOPSIS
Finds all CODE COMMENT comments in .TcPOU files (new and in progress).

.DESCRIPTION
Searches for CODE COMMENT comments in TcPOU XML files. Identifies:
- New: (* CODE COMMENT description *)
- In Progress: (* CODE COMMENT <uuid> description *)

Outputs a table with file path, line number, UUID (if present), and description.

.EXAMPLE
.\find-code-reviews.ps1
#>

param(
    [string]$RootPath = "$PSScriptRoot\..\TcOtlp",
    [switch]$UnprocessedOnly
)

$uuid_pattern = '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
$code_review_pattern = '\(\*\s*CODE COMMENT'
$results = @()

# Find all .TcPOU files
$files = Get-ChildItem -Path $RootPath -Filter "*.TcPOU" -Recurse

foreach ($file in $files) {
    $content = Get-Content -Path $file.FullName -Raw
    
    # Split into lines for line number tracking
    $lines = $content -split "`n"
    
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        
        if ($line -match $code_review_pattern) {
            # Extract the full comment (may span multiple lines)
            $comment_start = $i
            $comment_text = $line
            
            # Check if multi-line comment
            if ($comment_text -notmatch '\*\)') {
                $j = $i + 1
                while ($j -lt $lines.Count -and $lines[$j] -notmatch '\*\)') {
                    $comment_text += "`n" + $lines[$j]
                    $j++
                }
                if ($j -lt $lines.Count) {
                    $comment_text += "`n" + $lines[$j]
                }
            }
            
            # Check if in progress (has UUID)
            $has_uuid = $comment_text -match "CODE COMMENT\s+($uuid_pattern)"
            $uuid = if ($has_uuid) { $matches[1] } else { "" }
            
            # Skip if filtering for unprocessed only
            if ($UnprocessedOnly -and $has_uuid) {
                continue
            }
            
            # Extract description
            if ($has_uuid) {
                $description = $comment_text -replace ".*?CODE COMMENT\s+$uuid\s*", ""
            } else {
                $description = $comment_text -replace ".*?CODE COMMENT\s*", ""
            }
            
            # Clean up description
            $description = $description -replace '\s*\*\)\s*', ""
            $description = $description -replace '\s+', " "
            $description = $description.Trim()
            
            $results += [PSCustomObject]@{
                File     = $file.FullName.Replace($RootPath, "").TrimStart("\")
                Line     = $comment_start + 1
                UUID     = if ($uuid) { $uuid } else { "N/A" }
                Status   = if ($uuid) { "In Progress" } else { "New" }
                Description = $description.Substring(0, [Math]::Min(80, $description.Length))
            }
        }
    }
}

if ($results.Count -eq 0) {
    Write-Host "No CODE COMMENT comments found." -ForegroundColor Green
} else {
    Write-Host "`nFound $($results.Count) CODE COMMENT comment(s):`n" -ForegroundColor Cyan
    $results | Format-Table -AutoSize
    
    $inProgress = ($results | Where-Object { $_.Status -eq "In Progress" } | Measure-Object).Count
    $new = ($results | Where-Object { $_.Status -eq "New" } | Measure-Object).Count
    
    Write-Host "`nSummary: $inProgress in progress, $new new" -ForegroundColor Yellow
}

exit 0

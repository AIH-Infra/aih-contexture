$ErrorActionPreference = "Stop"

$sessionsRoot = Join-Path $HOME ".codex\sessions"
$indexPath = Join-Path $HOME ".codex\session_index.jsonl"

function Get-FirstUserTitle {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Lines
    )

    foreach ($line in $Lines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        try {
            $entry = $line | ConvertFrom-Json -Depth 100
        } catch {
            continue
        }

        if ($entry.type -ne "response_item" -or $entry.payload.type -ne "message" -or $entry.payload.role -ne "user") {
            continue
        }

        foreach ($content in $entry.payload.content) {
            if ($content.type -ne "input_text") {
                continue
            }

            $text = [string]$content.text
            if ([string]::IsNullOrWhiteSpace($text)) {
                continue
            }

            $normalized = $text -replace '<environment_context>[\s\S]*?</environment_context>', ''
            $normalized = $normalized -replace '<turn_aborted>[\s\S]*?</turn_aborted>', ''
            $normalized = $normalized.Trim()
            if ([string]::IsNullOrWhiteSpace($normalized)) {
                continue
            }

            $lines2 = $normalized -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
            foreach ($candidate in $lines2) {
                $title = $candidate.Trim()
                if ($title -like '# AGENTS.md*') {
                    continue
                }
                if ($title.Length -gt 80) {
                    $title = $title.Substring(0, 80)
                }
                return $title
            }
        }
    }

    return "Untitled Session"
}

$records = @()
$files = Get-ChildItem -LiteralPath $sessionsRoot -Recurse -Filter *.jsonl | Sort-Object FullName

foreach ($file in $files) {
    $lines = Get-Content -LiteralPath $file.FullName
    if (-not $lines) {
        continue
    }

    $meta = $null
    $latestTimestamp = $null

    foreach ($line in $lines) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        try {
            $entry = $line | ConvertFrom-Json -Depth 100
        } catch {
            continue
        }

        if (-not $meta -and $entry.type -eq "session_meta" -and $entry.payload.id) {
            $meta = $entry.payload
        }

        if ($entry.timestamp) {
            try {
                $ts = [DateTimeOffset]::Parse($entry.timestamp)
                if (-not $latestTimestamp -or $ts -gt $latestTimestamp) {
                    $latestTimestamp = $ts
                }
            } catch {
            }
        }
    }

    if (-not $meta -or -not $meta.id) {
        continue
    }

    if (-not $latestTimestamp) {
        $latestTimestamp = [DateTimeOffset]$file.LastWriteTimeUtc
    }

    $records += [pscustomobject]@{
        id = [string]$meta.id
        thread_name = (Get-FirstUserTitle -Lines $lines)
        updated_at = $latestTimestamp.ToString("o")
    }
}

$records |
    Sort-Object updated_at |
    ForEach-Object { $_ | ConvertTo-Json -Compress } |
    Set-Content -LiteralPath $indexPath -Encoding utf8

Write-Output "Rebuilt session index: $indexPath"
Write-Output "Session count: $($records.Count)"

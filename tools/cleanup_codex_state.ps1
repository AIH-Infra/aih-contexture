$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath
)

$src = Join-Path $HOME ".codex"
$targets = @(
    "state_5.sqlite",
    "state_5.sqlite-shm",
    "state_5.sqlite-wal",
    "logs_1.sqlite",
    "logs_1.sqlite-shm",
    "logs_1.sqlite-wal"
)

$processNames = @("Code", "codex", "codex-command-runner")
$deadline = (Get-Date).AddMinutes(15)
$logPath = Join-Path $BackupPath "cleanup.log"

while ((Get-Date) -lt $deadline) {
    $active = Get-Process -Name $processNames -ErrorAction SilentlyContinue
    if (-not $active) {
        break
    }
    Start-Sleep -Seconds 2
}

"Cleanup started at $(Get-Date -Format s)" | Out-File -LiteralPath $logPath -Encoding utf8

foreach ($name in $targets) {
    $path = Join-Path $src $name
    if (Test-Path -LiteralPath $path) {
        try {
            Move-Item -LiteralPath $path -Destination (Join-Path $BackupPath $name) -Force
            "[moved] $name" | Out-File -LiteralPath $logPath -Encoding utf8 -Append
        } catch {
            "[failed] $name :: $($_.Exception.Message)" | Out-File -LiteralPath $logPath -Encoding utf8 -Append
        }
    } else {
        "[missing] $name" | Out-File -LiteralPath $logPath -Encoding utf8 -Append
    }
}

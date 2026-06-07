param(
    [string]$TargetDir = "",
    [switch]$SkipPipInstall,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host "[upgrade] $Message"
}

function Resolve-FullPath($PathValue) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PathValue)
}

$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Resolve-FullPath $SourceDir

if ([string]::IsNullOrWhiteSpace($TargetDir)) {
    $TargetDir = Join-Path (Split-Path -Parent $SourceDir) "AIH-Contexture"
}
$TargetDir = Resolve-FullPath $TargetDir

$SourcePyproject = Join-Path $SourceDir "pyproject.toml"
if (!(Test-Path $SourcePyproject)) {
    throw "Source directory is missing pyproject.toml: $SourceDir"
}

$SourcePyprojectText = Get-Content $SourcePyproject -Raw -Encoding UTF8
if ($SourcePyprojectText -notmatch 'version\s*=\s*"0\.5\.0"') {
    throw "Source directory does not look like AIH-Contexture 0.5.0: $SourceDir"
}

if (!(Test-Path $TargetDir)) {
    throw "Target directory does not exist: $TargetDir"
}

$TargetPyproject = Join-Path $TargetDir "pyproject.toml"
if (!(Test-Path $TargetPyproject)) {
    throw "Target directory is missing pyproject.toml: $TargetDir"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = Join-Path (Split-Path -Parent $TargetDir) ("AIH-Contexture-backup-before-0.5-" + $Timestamp)

$DirectoryItems = @(
    ".github",
    ".streamlit",
    "aih_contexture",
    "assets",
    "data",
    "examples",
    "signatures",
    "static",
    "tests",
    "tools"
)

$FileItems = @(
    "pyproject.toml",
    "poetry.lock",
    "requirements.txt",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "MODEL_LICENSE",
    "NOTICE",
    "CLA.md",
    "VERSION_0.5_RELEASE_REPORT.md",
    "chunk_convert.py",
    "contexture_app.py",
    "contexture_server.py",
    "convert.py",
    "convert_single.py",
    "extraction_app.py",
    "install.bat",
    "install.sh",
    "install.command",
    "start.bat",
    "start.sh",
    "start.command",
    "upgrade_from_0.1.bat",
    "upgrade_from_0.1.ps1",
    "upgrade_from_0.1.sh",
    ".pre-commit-config.yaml",
    ".gitignore",
    "pytest.ini"
)

$ProtectedItems = @(
    ".venv",
    "venv",
    ".git",
    ".claude",
    ".env",
    "configs",
    "output",
    "uploads",
    "conversion_results",
    "debug_data",
    "temp",
    ".cache"
)

Write-Step "Source: $SourceDir"
Write-Step "Target: $TargetDir"
Write-Step "Backup: $BackupRoot"
Write-Step "Protected in target: $($ProtectedItems -join ', ')"

if ($DryRun) {
    Write-Step "DryRun enabled; no files will be changed."
} else {
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
}

function Backup-TargetItem($RelativePath) {
    $TargetPath = Join-Path $TargetDir $RelativePath
    if (!(Test-Path $TargetPath)) {
        return
    }
    $BackupPath = Join-Path $BackupRoot $RelativePath
    $BackupParent = Split-Path -Parent $BackupPath
    if ($DryRun) {
        Write-Step "Would backup: $RelativePath"
        return
    }
    if ($BackupParent -and !(Test-Path $BackupParent)) {
        New-Item -ItemType Directory -Path $BackupParent -Force | Out-Null
    }
    Copy-Item -Path $TargetPath -Destination $BackupPath -Recurse -Force
}

function Replace-Directory($RelativePath) {
    $SourcePath = Join-Path $SourceDir $RelativePath
    if (!(Test-Path $SourcePath)) {
        Write-Step "Skip missing source directory: $RelativePath"
        return
    }
    $TargetPath = Join-Path $TargetDir $RelativePath
    Backup-TargetItem $RelativePath
    if ($DryRun) {
        Write-Step "Would replace directory: $RelativePath"
        return
    }
    if (Test-Path $TargetPath) {
        Remove-Item -Path $TargetPath -Recurse -Force -Confirm:$false
    }
    Copy-Item -Path $SourcePath -Destination $TargetPath -Recurse -Force
    Write-Step "Replaced directory: $RelativePath"
}

function Replace-File($RelativePath) {
    $SourcePath = Join-Path $SourceDir $RelativePath
    if (!(Test-Path $SourcePath)) {
        Write-Step "Skip missing source file: $RelativePath"
        return
    }
    $TargetPath = Join-Path $TargetDir $RelativePath
    Backup-TargetItem $RelativePath
    if ($DryRun) {
        Write-Step "Would replace file: $RelativePath"
        return
    }
    $TargetParent = Split-Path -Parent $TargetPath
    if ($TargetParent -and !(Test-Path $TargetParent)) {
        New-Item -ItemType Directory -Path $TargetParent -Force | Out-Null
    }
    Copy-Item -Path $SourcePath -Destination $TargetPath -Force
    Write-Step "Replaced file: $RelativePath"
}

foreach ($Item in $DirectoryItems) {
    Replace-Directory $Item
}

foreach ($Item in $FileItems) {
    Replace-File $Item
}

# Copy new config examples without overwriting existing user config.
$SourceConfigs = Join-Path $SourceDir "configs"
$TargetConfigs = Join-Path $TargetDir "configs"
if (Test-Path $SourceConfigs) {
    $ConfigFiles = Get-ChildItem -Path $SourceConfigs -Recurse -File
    foreach ($ConfigFile in $ConfigFiles) {
        $Rel = $ConfigFile.FullName.Substring($SourceConfigs.Length).TrimStart('\', '/')
        $TargetConfigFile = Join-Path $TargetConfigs $Rel
        if (!(Test-Path $TargetConfigFile)) {
            if ($DryRun) {
                Write-Step "Would add missing config example: configs/$Rel"
            } else {
                $Parent = Split-Path -Parent $TargetConfigFile
                if ($Parent -and !(Test-Path $Parent)) {
                    New-Item -ItemType Directory -Path $Parent -Force | Out-Null
                }
                Copy-Item -Path $ConfigFile.FullName -Destination $TargetConfigFile -Force
                Write-Step "Added missing config example: configs/$Rel"
            }
        }
    }
}

if (!$SkipPipInstall) {
    $VenvPython = Join-Path $TargetDir ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        if ($DryRun) {
            Write-Step "Would run: $VenvPython -m pip install -e $TargetDir --no-deps"
        } else {
            Write-Step "Refreshing editable install without dependencies."
            & $VenvPython -m pip install -e $TargetDir --no-deps
        }
    } else {
        Write-Step "No target .venv found; skip pip install. If needed, activate your old environment and run: python -m pip install -e `"$TargetDir`" --no-deps"
    }
}

Write-Step "Upgrade file replacement completed."
if (!$DryRun) {
    Write-Step "Backup saved at: $BackupRoot"
    Write-Step "Verify with: python -c `"import aih_contexture; print(aih_contexture.__file__)`""
    Write-Step "Then run: contexture_gui"
}

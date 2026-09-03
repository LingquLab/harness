[CmdletBinding()]
param(
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }),
    [string]$BinDirectory = $(Join-Path $env:USERPROFILE "bin"),
    [switch]$SkipPathUpdate
)

$ErrorActionPreference = "Stop"
$sourceRoot = Split-Path $PSScriptRoot -Parent
$skillRoot = Join-Path (Join-Path $CodexHome "skills") "persistent-shell"

$python = $null
$candidates = @(
    @{ Command = "py"; Arguments = @("-3") },
    @{ Command = "python3"; Arguments = @() },
    @{ Command = "python"; Arguments = @() }
)
foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
        continue
    }
    $arguments = $candidate.Arguments
    $resolved = & $candidate.Command @arguments -c "import importlib.metadata, paramiko, sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $resolved) {
        $python = $resolved.Trim()
        break
    }
}
if (-not $python) {
    throw "A compatible Python 3 interpreter with Paramiko is required. Install Paramiko with: py -3 -m pip install paramiko"
}

$sourcePath = [IO.Path]::GetFullPath($sourceRoot).TrimEnd("\")
$destinationPath = [IO.Path]::GetFullPath($skillRoot).TrimEnd("\")
if ($sourcePath -ne $destinationPath) {
    $pending = [Collections.Generic.Queue[object]]::new()
    $pending.Enqueue(@($sourceRoot, $skillRoot))
    while ($pending.Count -gt 0) {
        $pair = $pending.Dequeue()
        New-Item -ItemType Directory -Path $pair[1] -Force | Out-Null
        foreach ($item in Get-ChildItem -LiteralPath $pair[0] -Force) {
            if ($item.PSIsContainer -and $item.Name -ne "__pycache__") {
                $pending.Enqueue(@($item.FullName, (Join-Path $pair[1] $item.Name)))
            } elseif (-not $item.PSIsContainer -and $item.Extension -ne ".pyc") {
                Copy-Item -LiteralPath $item.FullName -Destination $pair[1] -Force
            }
        }
    }
}

New-Item -ItemType Directory -Path $BinDirectory -Force | Out-Null
$pshellScript = Join-Path $skillRoot "scripts\pshell.py"
$escapedPython = $python.Replace("'", "''")
$escapedScript = $pshellScript.Replace("'", "''")
$powerShellLauncher = @"
#!/usr/bin/env pwsh
& '$escapedPython' '$escapedScript' @args
exit `$LASTEXITCODE
"@
Set-Content -LiteralPath (Join-Path $BinDirectory "pshell.ps1") -Value $powerShellLauncher -Encoding utf8NoBOM

$bashPython = $python.Replace("\", "/")
$bashScript = $pshellScript.Replace("\", "/")
$gitBashLauncher = @"
#!/usr/bin/env bash
exec "$bashPython" "$bashScript" "`$@"
"@
$bashLauncherPath = Join-Path $BinDirectory "pshell"
Set-Content -LiteralPath $bashLauncherPath -Value $gitBashLauncher -Encoding utf8NoBOM

$gitBash = "C:\Program Files\Git\bin\bash.exe"
if (Test-Path -LiteralPath $gitBash) {
    $resolvedBashLauncher = [IO.Path]::GetFullPath($bashLauncherPath).Replace("\", "/")
    if ($resolvedBashLauncher -match "^([A-Za-z]):/(.*)$") {
        $resolvedBashLauncher = "/$($Matches[1].ToLower())/$($Matches[2])"
    }
    & $gitBash -lc "chmod +x '$resolvedBashLauncher'"
    if ($LASTEXITCODE -ne 0) {
        throw "Git Bash launcher was created but chmod failed."
    }
}

if (-not $SkipPathUpdate) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $entries = @($userPath -split ";" | Where-Object { $_ })
    if ($entries -notcontains $BinDirectory) {
        [Environment]::SetEnvironmentVariable("Path", (($entries + $BinDirectory) -join ";"), "User")
    }
}

Write-Output "Installed skill: $skillRoot"
Write-Output "Installed launchers: $BinDirectory"
Write-Output "Open a new shell, then run: pshell doctor"

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $rootDir ".venv\Scripts\python.exe"
$srcDir = Join-Path $rootDir "src"

if (-not (Test-Path $pythonExe)) {
    Write-Error ".venv が見つかりません。先に開発環境を作成してください。"
    exit 1
}

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcDir;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $srcDir
}

& $pythonExe -m credential_vault.cli @CliArgs
exit $LASTEXITCODE

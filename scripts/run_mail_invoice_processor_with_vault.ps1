[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("main", "url_downloader", "delivery_sender", "replay_eml")]
    [string]$Module = "url_downloader",
    [string]$MailRepoRoot = "",
    [string]$TemplatePath = "",
    [string]$RequirementSpecPath = "",
    [string]$VaultDataRoot = "",
    [string]$PythonExe = "",
    [bool]$LaunchFormIfMissing = $true,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ModuleArgs
)

$vaultRoot = Split-Path -Parent $PSScriptRoot
if (-not $MailRepoRoot) {
    $MailRepoRoot = Join-Path (Split-Path -Parent $vaultRoot) "mail-invoice-processor"
}

if (-not (Test-Path $MailRepoRoot)) {
    Write-Error "mail-invoice-processor が見つかりません: $MailRepoRoot"
    exit 1
}

if (-not $TemplatePath) {
    $mailTemplate = Join-Path $MailRepoRoot "config\local.runtime.template.yaml"
    if (Test-Path $mailTemplate) {
        $TemplatePath = $mailTemplate
    } else {
        $TemplatePath = Join-Path $vaultRoot "docs\examples\mail_invoice_processor.local.runtime.template.yaml"
    }
}

if (-not (Test-Path $TemplatePath)) {
    Write-Error "runtime template が見つかりません: $TemplatePath"
    exit 1
}

if (-not $RequirementSpecPath) {
    $mailRequirementSpec = Join-Path $MailRepoRoot "config\local.runtime.requirements.yaml"
    if (Test-Path $mailRequirementSpec) {
        $RequirementSpecPath = $mailRequirementSpec
    }
}

if (-not $PythonExe) {
    $PythonExe = Join-Path $vaultRoot ".venv\Scripts\python.exe"
}

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python 実行ファイルが見つかりません: $PythonExe"
    exit 1
}

$resolvedVaultRoot = (Resolve-Path $vaultRoot).Path
$resolvedMailRepoRoot = (Resolve-Path $MailRepoRoot).Path
$resolvedTemplatePath = (Resolve-Path $TemplatePath).Path
$resolvedPythonExe = (Resolve-Path $PythonExe).Path
$secretsScript = Join-Path $resolvedVaultRoot "secrets.ps1"
$mailSrc = Join-Path $resolvedMailRepoRoot "src"
$pathSeparator = [IO.Path]::PathSeparator

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$mailSrc$pathSeparator$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $mailSrc
}

if ($ModuleArgs.Count -gt 0 -and $ModuleArgs[0] -eq "--") {
    if ($ModuleArgs.Count -eq 1) {
        $ModuleArgs = @()
    } else {
        $ModuleArgs = $ModuleArgs[1..($ModuleArgs.Count - 1)]
    }
}

$originalVaultDataRoot = $env:CREDENTIAL_VAULT_ROOT
if ($VaultDataRoot) {
    $env:CREDENTIAL_VAULT_ROOT = (Resolve-Path $VaultDataRoot).Path
}

try {
    if ($RequirementSpecPath) {
        $resolvedRequirementSpecPath = (Resolve-Path $RequirementSpecPath).Path
        $ensureArgs = @(
            "ensure",
            "--spec",
            $resolvedRequirementSpecPath
        )
        if ($LaunchFormIfMissing) {
            $ensureArgs += "--launch-form"
        }
        & $secretsScript @ensureArgs
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    $execArgs = @(
        "exec",
        "--template",
        $resolvedTemplatePath,
        "--",
        $resolvedPythonExe,
        "-m",
        "bill_one_mail_ingest.$Module",
        "--runtime-config",
        "__CREDENTIAL_VAULT_RENDERED_TEMPLATE__"
    )

    if ($ModuleArgs) {
        $execArgs += $ModuleArgs
    }

    Push-Location $resolvedMailRepoRoot
    try {
        & $secretsScript @execArgs
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    if ($VaultDataRoot) {
        if ($null -eq $originalVaultDataRoot) {
            Remove-Item Env:CREDENTIAL_VAULT_ROOT -ErrorAction SilentlyContinue
        } else {
            $env:CREDENTIAL_VAULT_ROOT = $originalVaultDataRoot
        }
    }
}

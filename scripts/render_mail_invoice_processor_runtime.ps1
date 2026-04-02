[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$MailRepoRoot = "",
    [string]$TemplatePath = "",
    [string]$OutputPath = ""
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

if (-not $OutputPath) {
    $OutputPath = Join-Path $MailRepoRoot "runtime\local.runtime.generated.yaml"
}

$resolvedVaultRoot = (Resolve-Path $vaultRoot).Path
$resolvedTemplatePath = (Resolve-Path $TemplatePath).Path
$secretsScript = Join-Path $resolvedVaultRoot "secrets.ps1"

& $secretsScript render $resolvedTemplatePath --output $OutputPath
exit $LASTEXITCODE

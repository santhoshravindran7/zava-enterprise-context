#Requires -Version 7.2
[CmdletBinding()]
param(
    [ValidateSet('Plan', 'Apply', 'Verify')][string]$Phase = 'Plan',
    [string]$Config = (Join-Path $PSScriptRoot 'environment.template.json'),
    [Parameter(Mandatory)][string]$Bundle,
    [string]$Python = 'python',
    [string]$ApprovedPlanSha256,
    [string]$ApprovalText,
    [ValidateRange(30, 3600)][int]$MaxWaitSeconds = 1200
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Zava.psm1') -Force
if ($Phase -eq 'Plan') {
    & $Python (Join-Path $PSScriptRoot 'seed.py') --output $Bundle --config $Config
    if ($LASTEXITCODE -ne 0) { throw 'Offline generation failed. No live actions were attempted.' }
    Write-Output "Review the entire plan: $(Join-Path $Bundle 'plan.json')"
    Write-Output "Plan SHA256: $((Get-FileHash -LiteralPath (Join-Path $Bundle 'plan.json')).Hash.ToLowerInvariant())"
    return
}
Initialize-Zava $Bundle $MaxWaitSeconds
if (-not $ApprovedPlanSha256) { throw 'Apply/Verify require the exact human-reviewed plan SHA256.' }
Assert-ZavaBundle $ApprovedPlanSha256
if ($Phase -eq 'Apply') {
    $required = "APPLY $($ApprovedPlanSha256.ToLowerInvariant())"
    if (-not $ApprovalText) { $ApprovalText = Read-Host "Only after human approval of resources, scope and costs, type: $required" }
    if ($ApprovalText -cne $required) { throw 'Approval phrase mismatch; no live actions attempted.' }
}
Invoke-ZavaPreflight
if ($Phase -eq 'Apply') { Invoke-ZavaSeed }
$null = Test-ZavaNative
Write-Output "Private creation/retrieval evidence: $(Join-Path $Bundle 'readiness.private.json'). Resource creation and source-readiness checks remain separate."

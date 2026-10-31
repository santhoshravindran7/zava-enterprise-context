#Requires -Version 7.2
[CmdletBinding()]
param(
    [ValidateSet('Plan', 'Apply', 'Verify')][string]$Phase = 'Plan',
    [Parameter(Mandatory)][string]$Bundle,
    [string]$Config,
    [string]$ApprovedPlanSha256,
    [string]$ApprovalText,
    [ValidateRange(30, 3600)][int]$MaxWaitSeconds = 1200
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Zava.psm1') -Force
$Bundle = [IO.Path]::GetFullPath($Bundle)
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if ($Bundle -eq $root -or $Bundle.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Site plans and live evidence must remain outside the source repository.'
}
if ($Phase -eq 'Plan') {
    if (-not $Config) { throw 'A private configuration path is required.' }
    if (Test-Path -LiteralPath $Bundle) { throw 'Use a new site-plan directory; existing plans are never overwritten.' }
    $value = Read-ZavaJson $Config
    $blockers = [Collections.Generic.List[string]]::new()
    $tenant = [guid]::Empty
    if (-not [guid]::TryParse($value.tenantId, [ref]$tenant) -or $tenant -eq [guid]::Empty) { $blockers.Add('Resolve the approved tenant GUID') }
    foreach ($name in @('tenantDomain', 'environmentLabel', 'costApprovalReference')) {
        if (-not $value[$name]) { $blockers.Add("Resolve $name") }
    }
    foreach ($name in @('siteUrl', 'siteTitle', 'ownerUpn')) {
        if (-not $value.sharePoint.ContainsKey($name)) { $value.sharePoint[$name] = $null }
        if (-not $value.sharePoint[$name]) { $blockers.Add("Resolve sharePoint.$name") }
    }
    if ($blockers.Count -eq 0) {
        if ($value.tenantDomain -isnot [string] -or $value.tenantDomain -notmatch '^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$') {
            throw 'A verified lowercase tenant DNS domain is required.'
        }
        $site = [uri]$value.sharePoint.siteUrl
        if ($site.Scheme -ne 'https' -or $site.Host -notmatch '^[a-z0-9-]+\.sharepoint\.com$' -or
            -not $site.IsDefaultPort -or $site.UserInfo -or $site.Query -or $site.Fragment -or
            $site.AbsolutePath -notmatch '^/sites/[a-z][a-z0-9-]{2,59}$') { throw 'An exact supported HTTPS SharePoint site URL is required; other clouds/hosts require a manual lane.' }
        if ($value.sharePoint.ownerUpn -notmatch '^[^@\s]+@[^@\s]+$' -or
            -not $value.sharePoint.ownerUpn.EndsWith('@' + $value.tenantDomain, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Site owner must be in the configured verified tenant domain.'
        }
        if ($value.sharePoint.siteTitle -isnot [string] -or -not $value.sharePoint.siteTitle.Trim() -or $value.sharePoint.siteTitle.Length -gt 255) {
            throw 'Site title must be a nonempty string of at most 255 characters.'
        }
        foreach ($name in @('environmentLabel', 'costApprovalReference')) {
            if ($value[$name] -isnot [string] -or -not $value[$name].Trim()) { throw "$name must be a nonempty string." }
        }
    }
    $null = New-Item -ItemType Directory -Path $Bundle
    Save-ZavaJson (Join-Path $Bundle 'config.json') $value
    Save-ZavaJson (Join-Path $Bundle 'manifest.json') @{files = @()}
    $hashes = @{}
    foreach ($name in @('Setup-SharePointSite.ps1', 'Zava.psm1')) { $hashes[$name] = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash }
    Save-ZavaJson (Join-Path $Bundle 'plan.json') @{
        schemaVersion = 1; kind = 'SHAREPOINT_SITE'; blockers = $blockers.ToArray()
        status = if ($blockers.Count) { 'DRAFT_UNBOUND' } else { 'AWAITING_HUMAN_APPROVAL' }
        configSha256 = (Get-FileHash -LiteralPath (Join-Path $Bundle 'config.json')).Hash
        manifestSha256 = (Get-FileHash -LiteralPath (Join-Path $Bundle 'manifest.json')).Hash
        sourceHashes = $hashes
        request = @{request = @{
            Title = $value.sharePoint.siteTitle; Url = $value.sharePoint.siteUrl; Owner = $value.sharePoint.ownerUpn
            Lcid = 1033; ShareByEmailEnabled = $false; WebTemplate = 'SITEPAGEPUBLISHING#0'
            SiteDesignId = 'f6cc5403-0d63-442e-96c0-285923709ffc'
            Description = 'Synthetic Zava enterprise context test site; no real customer data.'
        }}
        action = 'Create exactly one non-group-connected communication site; poll status; read role assignments and default document-library IDs. No content upload.'
        access = 'Authenticated operator is owner; no additional members, invitations or permission edits. Tenant policies/admin access may apply; unexpected readers stop readback before seeding.'
        cost = 'Existing licensed SharePoint service; site/storage quota and tenant policy must be approved. No license/service purchase and no guaranteed zero cost.'
        prohibited = @('send', 'invite', 'grant permissions', 'create accounts', 'create group or Teams team', 'upload source content', 'delete')
    }
    Write-Output "Site plan: $Bundle"
    Write-Output "Plan SHA256: $((Get-FileHash -LiteralPath (Join-Path $Bundle 'plan.json')).Hash.ToLowerInvariant())"
    return
}
if ($Config) { throw 'Live phases use the bound private configuration; create a new Plan to change it.' }
if (-not $ApprovedPlanSha256) { throw 'The exact human-approved site plan hash is required.' }
Initialize-Zava $Bundle $MaxWaitSeconds
Assert-ZavaBundle $ApprovedPlanSha256
if ($Phase -eq 'Apply') {
    $expected = 'APPLY ' + $ApprovedPlanSha256.ToLowerInvariant()
    if (-not $ApprovalText) { $ApprovalText = Read-Host "After human approval, type $expected" }
    if ($ApprovalText -cne $expected) { throw 'Site approval phrase mismatch.' }
}
$result = Invoke-ZavaSharePointSite -VerifyOnly:($Phase -eq 'Verify')
Write-Output "Site/library readback saved privately: $Bundle\sharepoint-target.private.json"
Write-Output "Files uploaded: $($result.FilesUploaded); source indexing: $($result.SourceIndexing)"

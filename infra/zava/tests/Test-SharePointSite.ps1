#Requires -Version 7.2
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$source = Split-Path $PSScriptRoot -Parent
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('zava-site-test-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $temporary
Import-Module (Join-Path $source 'Zava.psm1') -Force
function Assert-Throws([scriptblock]$Action, [string]$Expected) {
    $failed = $false
    try { & $Action } catch {
        if ($_.Exception.Message -notmatch $Expected) { throw }
        $failed = $true
    }
    if (-not $failed) { throw "Expected rejection: $Expected" }
}
try {
    $config = Read-ZavaJson (Join-Path $source 'environment.template.json')
    $inputPath = Join-Path $temporary 'input.json'
    Save-ZavaJson $inputPath $config
    $unbound = Join-Path $temporary 'unbound'
    & (Join-Path $source 'Setup-SharePointSite.ps1') -Phase Plan -Bundle $unbound -Config $inputPath
    Initialize-Zava $unbound
    Assert-Throws { Assert-ZavaBundle (Get-FileHash (Join-Path $unbound 'plan.json')).Hash } 'Unresolved'
    $config.tenantId = '11111111-1111-1111-1111-111111111111'
    $config.tenantDomain = 'synthetic.example'
    $config.costApprovalReference = 'MOCK-NO-CLOUD'
    $config.sharePoint.siteUrl = 'https://synthetic.sharepoint.com/sites/zava-test'
    $config.sharePoint.siteTitle = 'Synthetic Zava test'
    $config.sharePoint.ownerUpn = 'operator@synthetic.example'
    Save-ZavaJson $inputPath $config
    $bundle = Join-Path $temporary 'bound'
    & (Join-Path $source 'Setup-SharePointSite.ps1') -Phase Plan -Bundle $bundle -Config $inputPath
    Initialize-Zava $bundle
    Assert-ZavaBundle (Get-FileHash (Join-Path $bundle 'plan.json')).Hash
    & (Get-Module Zava) {
        $script:Writes = 0
        $script:SiteState = 0
        $script:Owner = 'operator@synthetic.example'
        $script:ExtraReader = $false
        $script:BadCreation = $false
        $script:WrongGraphSite = $false
        $script:LibraryExtraReader = $false
        $script:SiteId = '22222222-2222-2222-2222-222222222222'
        function script:Start-Sleep { }
        function script:Invoke-ZavaRequest([string]$Uri, [string]$Audience, [string]$Method = 'GET', $Body = $null, [byte[]]$Bytes = $null, [hashtable]$ExtraHeaders = @{}) {
            $value = @{}
            if ($Method -ne 'GET') {
                $script:Writes++
                if (-not $Uri.EndsWith('/_api/SPSiteManager/create') -or $Method -ne 'POST' -or
                    $Body.request.WebTemplate -ne 'SITEPAGEPUBLISHING#0' -or $Body.request.ShareByEmailEnabled -or
                    $Body.request.Owner -ne $script:Owner -or $Body.request.Url -ne $script:Context.Config.sharePoint.siteUrl) {
                    throw 'Unexpected site write or scope.'
                }
                if ($script:BadCreation) { return @{Status = 200; Body = @{SiteStatus = 4}; Headers = @{}} }
                $script:SiteState = 1
                $value = @{SiteStatus = 1; SiteId = $script:SiteId; SiteUrl = $script:Context.Config.sharePoint.siteUrl}
            } elseif ($Uri.EndsWith('/organization')) { $value = @{value = @(@{id = $script:Context.Config.tenantId})} }
            elseif ($Uri -match '/domains/') { $value = @{id = $script:Context.Config.tenantDomain; isVerified = $true} }
            elseif ($Uri -match '/me\?') { $value = @{userPrincipalName = $script:Owner} }
            elseif ($Uri -match '/SPSiteManager/status\?') {
                if ($script:SiteState -eq 1) { $script:SiteState = 2 }
                $value = @{SiteStatus = $script:SiteState; SiteId = $script:SiteId; SiteUrl = $script:Context.Config.sharePoint.siteUrl}
            } elseif ($Uri -match '/lists\(.*\)/roleassignments\?') {
                $value = @{value = @(@{Member = @{PrincipalType = 1; Email = 'other@synthetic.example'; LoginName = 'other'}; RoleDefinitionBindings = @(@{RoleTypeKind = 2})})}
            } elseif ($Uri -match '/roleassignments\?') {
                $value = @{value = @(@{Member = @{Id = 3; PrincipalType = 8}; RoleDefinitionBindings = @(@{RoleTypeKind = 5})})}
            } elseif ($Uri -match '/sitegroups/getbyid\(3\)/users') {
                $members = @(@{Email = $script:Owner; LoginName = "i:0#.f|membership|$script:Owner"})
                if ($script:ExtraReader) { $members += @{Email = 'other@synthetic.example'; LoginName = 'other'} }
                $value = @{value = $members}
            } elseif ($Uri -match '/drive\?') {
                $value = @{id = 'fake-drive'; driveType = 'documentLibrary'; sharepointIds = @{siteId = $script:SiteId; listId = '44444444-4444-4444-4444-444444444444'}}
            } elseif ($Uri -match '/lists\(.*\)\?') { $value = @{HasUniqueRoleAssignments = $script:LibraryExtraReader} }
            elseif ($Uri -match '/sites/synthetic.sharepoint.com:') {
                $value = @{id = "synthetic.sharepoint.com,$script:SiteId,33333333-3333-3333-3333-333333333333"; webUrl = $script:Context.Config.sharePoint.siteUrl}
                if ($script:WrongGraphSite) { $value.webUrl = 'https://synthetic.sharepoint.com/sites/other' }
            } else { throw "Unhandled mock: $Uri" }
            return @{Status = 200; Body = $value; Headers = @{}}
        }
        $failed = $false
        try { Invoke-ZavaSharePointSite -VerifyOnly } catch { if ($_.Exception.Message -notmatch 'No owned') { throw }; $failed = $true }
        if (-not $failed -or $script:Writes -ne 0) { throw 'Verify created an unowned site.' }
        $script:SiteState = 4
        $failed = $false
        try { Invoke-ZavaSharePointSite } catch { if ($_.Exception.Message -notmatch 'occupied') { throw }; $failed = $true }
        if (-not $failed -or $script:Writes -ne 0) { throw 'Occupied URL was adopted.' }
        $script:SiteState = 0
        $script:Owner = 'other@synthetic.example'
        $failed = $false
        try { Invoke-ZavaSharePointSite } catch { if ($_.Exception.Message -notmatch 'authenticated operator') { throw }; $failed = $true }
        if (-not $failed -or $script:Writes -ne 0) { throw 'Another owner was accepted.' }
        $script:Owner = 'operator@synthetic.example'
        $result = Invoke-ZavaSharePointSite
        if ($script:Writes -ne 1 -or $result.DriveId -ne 'fake-drive' -or $result.FilesUploaded -ne 0) { throw 'Site creation/readback incorrect.' }
        $null = Invoke-ZavaSharePointSite
        $null = Invoke-ZavaSharePointSite -VerifyOnly
        if ($script:Writes -ne 1) { throw 'Created site was replayed.' }
        $script:Context.Ledger['sharepoint/site'].State = 'PENDING'
        $script:SiteState = 1
        $null = Invoke-ZavaSharePointSite
        if ($script:Writes -ne 1) { throw 'Known pending site operation was resubmitted.' }
        $script:ExtraReader = $true
        $failed = $false
        try { Invoke-ZavaSharePointSite -VerifyOnly } catch { if ($_.Exception.Message -notmatch 'Unexpected site reader') { throw }; $failed = $true }
        if (-not $failed) { throw 'Unexpected membership was hidden.' }
        $latest = Read-ZavaJson (Join-Path $script:Context.Bundle 'sharepoint-target.private.json')
        if ($latest.SiteStatus -ne 'NOT_VERIFIED' -or $latest.ContainsKey('DriveId')) { throw 'Failed readback left a stale verified target.' }
        $script:ExtraReader = $false
        $script:LibraryExtraReader = $true
        $failed = $false
        try { Invoke-ZavaSharePointSite -VerifyOnly } catch { if ($_.Exception.Message -notmatch 'Unexpected site reader') { throw }; $failed = $true }
        if (-not $failed) { throw 'Unique library permissions were not inspected.' }
        $script:LibraryExtraReader = $false
        $script:WrongGraphSite = $true
        $failed = $false
        try { Invoke-ZavaSharePointSite -VerifyOnly } catch { if ($_.Exception.Message -notmatch 'different site') { throw }; $failed = $true }
        if (-not $failed) { throw 'Wrong Graph site was accepted.' }
        $script:WrongGraphSite = $false
        $script:Context.Ledger.Remove('sharepoint/site')
        $script:SiteState = 0
        $script:BadCreation = $true
        $failed = $false
        try { Invoke-ZavaSharePointSite } catch { if ($_.Exception.Message -notmatch 'Unexpected site-creation') { throw }; $failed = $true }
        if (-not $failed) { throw 'Bad creation response was accepted.' }
        $before = $script:Writes
        $failed = $false
        try { Invoke-ZavaSharePointSite } catch { if ($_.Exception.Message -notmatch 'Uncertain prior') { throw }; $failed = $true }
        if (-not $failed -or $script:Writes -ne $before) { throw 'Uncertain creation was replayed.' }
    }
    $config.sharePoint.siteUrl = 'https://unapproved.example/sites/zava-test'
    Save-ZavaJson $inputPath $config
    Assert-Throws { & (Join-Path $source 'Setup-SharePointSite.ps1') -Phase Plan -Bundle (Join-Path $temporary 'bad-host') -Config $inputPath } 'exact supported HTTPS'
    Import-Module (Join-Path $source 'Zava.psm1') -Force
    Initialize-Zava $bundle
    & (Get-Module Zava) {
        $script:WrongTenant = $false
        $script:HttpCalls = 0
        function script:az {
            $claims = @{
                tid = if ($script:WrongTenant) { '55555555-5555-5555-5555-555555555555' } else { $script:Context.Config.tenantId }
                aud = '00000003-0000-0ff1-ce00-000000000000'
                exp = [DateTimeOffset]::UtcNow.AddMinutes(10).ToUnixTimeSeconds()
            }
            $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($claims | ConvertTo-Json -Compress))).TrimEnd('=').Replace('+', '-').Replace('/', '_')
            $global:LASTEXITCODE = 0
            return (@{accessToken = "header.$encoded.signature"} | ConvertTo-Json -Compress)
        }
        function script:Invoke-WebRequest {
            $script:HttpCalls++
            return @{StatusCode = 200; Content = '{}'; Headers = @{'Content-Type' = @('application/json')}}
        }
        $null = Invoke-ZavaRequest 'https://synthetic.sharepoint.com/_api/web' 'https://synthetic.sharepoint.com'
        if ($script:HttpCalls -ne 1) { throw 'SharePoint audience alias was rejected.' }
        $failed = $false
        try { Invoke-ZavaRequest 'https://other.sharepoint.com/_api/web' 'https://synthetic.sharepoint.com' } catch {
            if ($_.Exception.Message -notmatch 'unapproved host') { throw }; $failed = $true
        }
        if (-not $failed -or $script:HttpCalls -ne 1) { throw 'SharePoint token reached another host.' }
        $script:Tokens = @{}
        $script:WrongTenant = $true
        $failed = $false
        try { Invoke-ZavaRequest 'https://synthetic.sharepoint.com/_api/web' 'https://synthetic.sharepoint.com' } catch {
            if ($_.Exception.Message -notmatch 'another tenant') { throw }; $failed = $true
        }
        if (-not $failed -or $script:HttpCalls -ne 1) { throw 'Wrong-tenant SharePoint token was accepted.' }
    }
    Write-Output 'PASS: site-only plan, unbound/host/owner/collision guards, status polling, owned readback, extra-reader rejection, wrong Graph site and no blind replay. ZERO network calls.'
} finally {
    $resolved = (Resolve-Path -LiteralPath $temporary).Path
    if ([IO.Path]::GetFileName($resolved) -notmatch '^zava-site-test-[a-f0-9]{32}$') { throw 'Refusing unexpected test cleanup path.' }
    Remove-Item -LiteralPath $resolved -Recurse
}

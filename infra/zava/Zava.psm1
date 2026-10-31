#Requires -Version 7.2
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Tokens = @{}
$script:Context = $null
$script:Graph = 'https://graph.microsoft.com/v1.0'
$script:Fabric = 'https://api.fabric.microsoft.com/v1'

function Read-ZavaJson([string]$Path) {
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -AsHashtable
}

function Save-ZavaJson([string]$Path, $Value) {
    $temporary = "$Path.tmp"
    [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 100), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Initialize-Zava([string]$Bundle, [int]$MaxWaitSeconds = 1200) {
    $script:Context = @{
        Bundle = (Resolve-Path -LiteralPath $Bundle).Path
        Config = Read-ZavaJson (Join-Path $Bundle 'config.json')
        Manifest = Read-ZavaJson (Join-Path $Bundle 'manifest.json')
        LedgerPath = Join-Path $Bundle 'ledger.private.json'
        WaitSeconds = $MaxWaitSeconds
    }
    $script:Context.Ledger = if (Test-Path -LiteralPath $script:Context.LedgerPath) {
        Read-ZavaJson $script:Context.LedgerPath
    } else { @{} }
    $script:Tokens = @{}
}

function Assert-ZavaBundle([string]$ApprovedPlanSha256) {
    $bundle = $script:Context.Bundle
    $planPath = Join-Path $bundle 'plan.json'
    if ((Get-FileHash -LiteralPath $planPath).Hash -ne $ApprovedPlanSha256) {
        throw 'Approval hash does not match the exact plan.'
    }
    $plan = Read-ZavaJson $planPath
    if ($plan.blockers.Count -gt 0) { throw ('Unresolved plan: ' + ($plan.blockers -join '; ')) }
    foreach ($pair in @(@('config.json', $plan.configSha256), @('manifest.json', $plan.manifestSha256))) {
        if ((Get-FileHash -LiteralPath (Join-Path $bundle $pair[0])).Hash -ne $pair[1]) {
            throw "Plan binding changed: $($pair[0])"
        }
    }
    foreach ($name in $plan.sourceHashes.Keys) {
        if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name)).Hash -ne $plan.sourceHashes[$name]) {
            throw "Setup code changed after plan approval: $name"
        }
    }
    foreach ($file in $script:Context.Manifest.files) {
        $path = [IO.Path]::GetFullPath((Join-Path $bundle $file.path))
        if (-not $path.StartsWith($bundle + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Bundle path escapes its directory: $($file.path)"
        }
        if ((Get-FileHash -LiteralPath $path).Hash -ne $file.sha256) { throw "Bundle file changed: $($file.path)" }
    }
}

function Get-ZavaToken([string]$Audience) {
    if ($script:Tokens.ContainsKey($Audience) -and $script:Tokens[$Audience].Expires -gt [DateTimeOffset]::UtcNow.AddMinutes(2)) {
        return $script:Tokens[$Audience].Token
    }
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI is required for live operations; no automatic installation or login is performed.' }
    $tenant = $script:Context.Config.tenantId
    $tenantGuid = [guid]::Empty
    if (-not [guid]::TryParse($tenant, [ref]$tenantGuid) -or $tenantGuid -eq [guid]::Empty) { throw 'A real approved tenant GUID is required.' }
    $raw = & az account get-access-token --tenant $tenant --resource $Audience --output json --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "Token acquisition failed for $Audience. Log in to the exact approved tenant yourself." }
    $credential = ($raw -join "`n") | ConvertFrom-Json -AsHashtable
    $encoded = $credential.accessToken.Split('.')[1].Replace('-', '+').Replace('_', '/')
    $encoded = $encoded.PadRight($encoded.Length + ((4 - $encoded.Length % 4) % 4), '=')
    $claims = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded)) | ConvertFrom-Json -AsHashtable
    if ($claims.tid -ne $tenant) { throw 'STOP: token belongs to another tenant.' }
    $validAudiences = @($Audience.TrimEnd('/'))
    if ($Audience -eq 'https://graph.microsoft.com') { $validAudiences += '00000003-0000-0000-c000-000000000000' }
    if ($script:Context.Config.sharePoint.ContainsKey('siteUrl') -and $script:Context.Config.sharePoint.siteUrl) {
        $site = [uri]$script:Context.Config.sharePoint.siteUrl
        if ($site.Scheme -eq 'https' -and $site.Host -match '^[a-z0-9-]+\.sharepoint\.com$' -and
            $site.IsDefaultPort -and -not $site.UserInfo -and $Audience -eq $site.GetLeftPart([UriPartial]::Authority)) {
            $validAudiences += '00000003-0000-0ff1-ce00-000000000000'
        }
    }
    if ($claims.aud.TrimEnd('/') -notin $validAudiences) { throw 'STOP: token audience mismatch.' }
    $script:Tokens[$Audience] = @{Token = $credential.accessToken; Expires = [DateTimeOffset]::FromUnixTimeSeconds([long]$claims.exp)}
    return $credential.accessToken
}

function Invoke-ZavaRequest([string]$Uri, [string]$Audience, [string]$Method = 'GET', $Body = $null, [byte[]]$Bytes = $null, [hashtable]$ExtraHeaders = @{}) {
    $target = [uri]$Uri
    $hosts = @{
        'https://graph.microsoft.com' = 'graph.microsoft.com'
        'https://api.fabric.microsoft.com' = 'api.fabric.microsoft.com'
        'https://storage.azure.com' = 'onelake.dfs.fabric.microsoft.com'
        'https://management.azure.com' = 'management.azure.com'
    }
    if ($script:Context.Config.search.searchEndpoint) {
        $hosts['https://search.azure.com'] = ([uri]$script:Context.Config.search.searchEndpoint).Host
    }
    if ($script:Context.Config.sharePoint.ContainsKey('siteUrl') -and $script:Context.Config.sharePoint.siteUrl) {
        $site = [uri]$script:Context.Config.sharePoint.siteUrl
        if ($site.Scheme -eq 'https' -and $site.Host -match '^[a-z0-9-]+\.sharepoint\.com$' -and
            $site.IsDefaultPort -and -not $site.UserInfo) {
            $hosts[$site.GetLeftPart([UriPartial]::Authority)] = $site.Host
        }
    }
    if ($target.Scheme -ne 'https' -or $target.Host -ne $hosts[$Audience] -or -not $target.IsDefaultPort -or $target.UserInfo) {
        throw 'Refusing an unapproved host, insecure URI or token redirect.'
    }
    $headers = @{Authorization = 'Bearer ' + (Get-ZavaToken $Audience)}
    foreach ($key in $ExtraHeaders.Keys) { $headers[$key] = $ExtraHeaders[$key] }
    $parameters = @{Uri = $Uri; Method = $Method; Headers = $headers; SkipHttpErrorCheck = $true; MaximumRedirection = 0; TimeoutSec = 120}
    if ($null -ne $Bytes) { $parameters.Body = $Bytes; $parameters.ContentType = 'application/octet-stream' }
    elseif ($null -ne $Body) { $parameters.Body = $Body | ConvertTo-Json -Depth 100 -Compress; $parameters.ContentType = 'application/json' }
    for ($attempt = 0; $attempt -lt 4; $attempt++) {
        $response = Invoke-WebRequest @parameters
        if ($response.StatusCode -ne 429 -or $Method -ne 'GET' -or $attempt -eq 3) { break }
        $delay = 5
        if ($response.Headers.ContainsKey('Retry-After')) {
            $candidate = 0
            if ([int]::TryParse([string]$response.Headers['Retry-After'][0], [ref]$candidate)) { $delay = [Math]::Clamp($candidate, 1, 60) }
        }
        Start-Sleep -Seconds $delay
    }
    $value = if ($response.Content -and [string]$response.Headers['Content-Type'] -match 'json') {
        $response.Content | ConvertFrom-Json -AsHashtable
    } else { @{} }
    return @{Status = [int]$response.StatusCode; Body = $value; Headers = $response.Headers}
}

function Assert-ZavaResponse($Response, [int[]]$Allowed = @(200, 201, 202, 204)) {
    if ($Response.Status -notin $Allowed) { throw "Service request failed (HTTP $($Response.Status)); retain the private ledger and reconcile, do not blindly replay writes." }
}

function Get-ZavaPages([string]$Uri, [string]$Audience, [string]$NextKey) {
    $items = [Collections.Generic.List[object]]::new()
    do {
        $response = Invoke-ZavaRequest $Uri $Audience
        Assert-ZavaResponse $response
        foreach ($item in $response.Body.value) { $items.Add($item) }
        $Uri = if ($response.Body.ContainsKey($NextKey)) { $response.Body[$NextKey] } else { $null }
    } while ($Uri)
    return ,$items.ToArray()
}

function Assert-ZavaIdentity {
    $config = $script:Context.Config
    $organization = Invoke-ZavaRequest "$script:Graph/organization" 'https://graph.microsoft.com'
    Assert-ZavaResponse $organization
    if ($organization.Body.value.Count -ne 1 -or $organization.Body.value[0].id -ne $config.tenantId) { throw 'Approved tenant organization mismatch.' }
    $domain = Invoke-ZavaRequest "$script:Graph/domains/$($config.tenantDomain)" 'https://graph.microsoft.com'
    Assert-ZavaResponse $domain
    if (-not $domain.Body.isVerified -or $domain.Body.id -ne $config.tenantDomain) { throw 'Domain is not verified in this tenant.' }
}

function Invoke-ZavaPreflight {
    $config = $script:Context.Config
    Assert-ZavaIdentity
    if ('SharePoint' -in $config.providers) {
        $drives = Get-ZavaPages "$script:Graph/sites/$($config.sharePoint.siteId)/drives" 'https://graph.microsoft.com' '@odata.nextLink'
        if ($config.sharePoint.driveId -notin $drives.id) { throw 'Drive is not in the approved site.' }
    }
    if ('Fabric' -in $config.providers) {
        $workspace = Invoke-ZavaRequest "$script:Fabric/workspaces/$($config.fabric.workspaceId)" 'https://api.fabric.microsoft.com'
        Assert-ZavaResponse $workspace
        if ($workspace.Body.capacityId -ne $config.fabric.capacityId) { throw 'Workspace/capacity binding mismatch.' }
        $capacities = Get-ZavaPages "$script:Fabric/capacities" 'https://api.fabric.microsoft.com' 'continuationUri'
        $capacity = @($capacities | Where-Object id -eq $config.fabric.capacityId)
        if ($capacity.Count -ne 1 -or $capacity[0].state -ne 'Active') { throw 'Approved capacity is not available and active.' }
        $items = Get-ZavaPages "$script:Fabric/workspaces/$($config.fabric.workspaceId)/items" 'https://api.fabric.microsoft.com' 'continuationUri'
        $plan = Read-ZavaJson (Join-Path $script:Context.Bundle 'plan.json')
        $names = @($plan.fabricResources.displayName) + $plan.lakehouseName
        foreach ($item in $items) {
            if ($item.displayName -in $names -and $item.id -notin @($script:Context.Ledger.Values | ForEach-Object { $_.Id })) {
                throw "Name collision with a resource not owned by this ledger: $($item.displayName)"
            }
        }
    }
    if ('Search' -in $config.providers) {
        $resource = $config.search.searchResourceId
        if ($resource -notmatch '^/subscriptions/[0-9a-f-]{36}/resourceGroups/[A-Za-z0-9_.()-]+/providers/Microsoft.Search/searchServices/[a-z0-9-]+$') {
            throw 'An exact existing Azure Search ARM resource ID is required.'
        }
        $service = Invoke-ZavaRequest "https://management.azure.com${resource}?api-version=2025-05-01" 'https://management.azure.com'
        Assert-ZavaResponse $service
        $expected = "https://$($service.Body.name).search.windows.net"
        if ($config.search.searchEndpoint.TrimEnd('/') -ne $expected) { throw 'Search endpoint does not match the approved ARM service.' }
        foreach ($kb in $script:Context.Manifest.search) {
            foreach ($pair in @(@('indexes', $kb.name), @('knowledgesources', "$($kb.name)-source"), @('knowledgebases', "$($kb.name)-kb"))) {
                $key = "$($pair[0])/$($pair[1])"
                $probe = Invoke-ZavaRequest "$expected/${key}?api-version=2026-04-01" 'https://search.azure.com'
                if (-not $script:Context.Ledger.ContainsKey($key)) { Assert-ZavaResponse $probe @(404) }
            }
        }
    }
    if ($config.createOutlookDrafts -or $config.createCalendarAppointments) {
        $mailbox = Invoke-ZavaRequest "$script:Graph/users/$($config.mailboxObjectId)" 'https://graph.microsoft.com'
        Assert-ZavaResponse $mailbox
        if (-not $mailbox.Body.userPrincipalName.EndsWith('@' + $config.tenantDomain, [StringComparison]::OrdinalIgnoreCase)) { throw 'Mailbox account is outside the issued approved sandbox domain.' }
    }
    Save-ZavaJson (Join-Path $script:Context.Bundle 'preflight.private.json') @{
        Tenant = $config.tenantId; Environment = $config.environmentLabel
        CheckedAt = [DateTimeOffset]::UtcNow.ToString('o'); ScopeChecks = 'PASS'; NativeRetrieval = 'NOT_RUN'
    }
}

function Save-ZavaReceipt([string]$Key, [string]$State, [string]$Id = '', [string]$Operation = '') {
    if (-not $Operation -and $script:Context.Ledger.ContainsKey($Key)) {
        $Operation = $script:Context.Ledger[$Key].Operation
    }
    $script:Context.Ledger[$Key] = @{State = $State; Id = $Id; Operation = $Operation; At = [DateTimeOffset]::UtcNow.ToString('o')}
    Save-ZavaJson $script:Context.LedgerPath $script:Context.Ledger
}

function Assert-ZavaSharePointReaders([string]$ScopeUri, [string]$SiteUrl, [string]$Audience, [hashtable]$Headers, [string]$Owner) {
    $assignments = Invoke-ZavaRequest "$ScopeUri/roleassignments?`$expand=Member,RoleDefinitionBindings" $Audience -ExtraHeaders $Headers
    Assert-ZavaResponse $assignments @(200)
    if ($assignments.Body.ContainsKey('odata.nextLink') -or $assignments.Body.ContainsKey('@odata.nextLink')) {
        throw 'Paginated site permissions require manual review; no content is uploaded.'
    }
    $ownerFound = $false
    foreach ($assignment in $assignments.Body.value) {
        if (@($assignment.RoleDefinitionBindings | Where-Object RoleTypeKind -ne 1).Count -eq 0) { continue }
        $members = @($assignment.Member)
        if ($assignment.Member.PrincipalType -eq 8) {
            $groupId = [int]$assignment.Member.Id
            $group = Invoke-ZavaRequest "$SiteUrl/_api/web/sitegroups/getbyid($groupId)/users" $Audience -ExtraHeaders $Headers
            Assert-ZavaResponse $group @(200)
            if ($group.Body.ContainsKey('odata.nextLink') -or $group.Body.ContainsKey('@odata.nextLink')) {
                throw 'Paginated group membership requires manual review; no content is uploaded.'
            }
            $members = @($group.Body.value)
        }
        foreach ($member in $members) {
            if ($member.Email -ne $Owner -and $member.LoginName -ne "i:0#.f|membership|$Owner") {
                throw 'Unexpected site reader/member from tenant provisioning policy; inspect privately before seeding. No automatic permission changes.'
            }
            $ownerFound = $true
        }
    }
    if (-not $ownerFound) { throw 'Owner access was not present in role-assignment readback; manual review is required.' }
}

function Invoke-ZavaSharePointSite([switch]$VerifyOnly) {
    $config = $script:Context.Config
    $plan = Read-ZavaJson (Join-Path $script:Context.Bundle 'plan.json')
    if (-not $plan.ContainsKey('kind') -or $plan.kind -ne 'SHAREPOINT_SITE') { throw 'A separate approved SharePoint site plan is required.' }
    Save-ZavaJson (Join-Path $script:Context.Bundle 'sharepoint-target.private.json') @{
        Tenant = $config.tenantId; ObservedAt = [DateTimeOffset]::UtcNow.ToString('o')
        SiteStatus = 'NOT_VERIFIED'; SourceIndexing = 'NOT_RUN'; FilesUploaded = 0
    }
    Assert-ZavaIdentity
    $me = Invoke-ZavaRequest "$script:Graph/me?`$select=userPrincipalName" 'https://graph.microsoft.com'
    Assert-ZavaResponse $me @(200)
    if ($me.Body.userPrincipalName -ne $config.sharePoint.ownerUpn) { throw 'Site owner must be the authenticated operator; no creation on another person''s behalf.' }
    $site = [uri]$config.sharePoint.siteUrl
    $audience = $site.GetLeftPart([UriPartial]::Authority)
    $headers = @{Accept = 'application/json;odata.metadata=none'; 'odata-version' = '4.0'}
    $statusUri = "$audience/_api/SPSiteManager/status?url='$([uri]::EscapeDataString($site.AbsoluteUri))'"
    $key = 'sharepoint/site'
    $status = Invoke-ZavaRequest $statusUri $audience -ExtraHeaders $headers
    Assert-ZavaResponse $status @(200)
    if ($script:Context.Ledger.ContainsKey($key)) {
        $receipt = $script:Context.Ledger[$key]
        if ($receipt.State -notin @('PENDING', 'CREATED') -or -not $receipt.Id -or -not $receipt.Operation) {
            throw 'Uncertain prior site creation; reconcile the exact site and ledger before resume. No blind retry.'
        }
        if ($receipt.Operation -ne $statusUri) { throw 'Site operation does not match the approved URL.' }
    } else {
        if ($VerifyOnly) { throw 'No owned site creation receipt; Verify cannot create or adopt a site.' }
        if ($status.Body.SiteStatus -ne 0) { throw 'Site URL is occupied or provisioning; no adoption or overwrite.' }
        Save-ZavaReceipt $key 'PENDING'
        $created = Invoke-ZavaRequest "$audience/_api/SPSiteManager/create" $audience 'POST' $plan.request -ExtraHeaders $headers
        Assert-ZavaResponse $created @(200)
        $guid = [guid]::Empty
        if ($created.Body.SiteStatus -notin @(1, 2) -or $created.Body.SiteUrl -ne $site.AbsoluteUri -or
            -not [guid]::TryParse($created.Body.SiteId, [ref]$guid) -or $guid -eq [guid]::Empty) {
            throw 'Unexpected site-creation response; retain the uncertain receipt and reconcile, never replay.'
        }
        Save-ZavaReceipt $key 'PENDING' $created.Body.SiteId $statusUri
        $status = Invoke-ZavaRequest $statusUri $audience -ExtraHeaders $headers
        Assert-ZavaResponse $status @(200)
    }
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($script:Context.WaitSeconds)
    while ($true) {
        if ($status.Body.SiteStatus -notin @(1, 2) -or $status.Body.SiteId -ne $script:Context.Ledger[$key].Id -or
            $status.Body.SiteUrl -ne $site.AbsoluteUri) { throw 'Site status/identity mismatch or provisioning error; no automatic retry/delete.' }
        if ($status.Body.SiteStatus -eq 2) { break }
        if ($script:Context.Ledger[$key].State -eq 'CREATED') { throw 'Previously ready site no longer reports Ready.' }
        if ([DateTimeOffset]::UtcNow -ge $deadline) { throw 'Site provisioning exceeded the wait limit; it may continue. Resume the known status operation, not creation.' }
        Start-Sleep -Seconds 5
        $status = Invoke-ZavaRequest $statusUri $audience -ExtraHeaders $headers
        Assert-ZavaResponse $status @(200)
    }
    Save-ZavaReceipt $key 'CREATED' $status.Body.SiteId $statusUri
    Assert-ZavaSharePointReaders "$($site.AbsoluteUri)/_api/web" $site.AbsoluteUri $audience $headers $config.sharePoint.ownerUpn
    $resolved = Invoke-ZavaRequest "$script:Graph/sites/$($site.Host):$($site.AbsolutePath)" 'https://graph.microsoft.com'
    Assert-ZavaResponse $resolved @(200)
    if ($resolved.Body.webUrl -ne $site.AbsoluteUri -or
        $resolved.Body.id -notlike "$($site.Host),$($status.Body.SiteId),*") { throw 'Graph resolved a different site.' }
    $drive = Invoke-ZavaRequest "$script:Graph/sites/$($resolved.Body.id)/drive?`$select=id,driveType,sharepointIds" 'https://graph.microsoft.com'
    Assert-ZavaResponse $drive @(200)
    if ($drive.Body.driveType -ne 'documentLibrary' -or -not $drive.Body.id) { throw 'Default document library is not ready.' }
    $listId = [guid]::Empty
    if ($drive.Body.sharepointIds.siteId -ne $status.Body.SiteId -or
        -not [guid]::TryParse($drive.Body.sharepointIds.listId, [ref]$listId) -or $listId -eq [guid]::Empty) { throw 'Default library SharePoint identifiers do not match the site.' }
    $listUri = "$($site.AbsoluteUri)/_api/web/lists(guid'$listId')"
    $list = Invoke-ZavaRequest "${listUri}?`$select=HasUniqueRoleAssignments" $audience -ExtraHeaders $headers
    Assert-ZavaResponse $list @(200)
    if ($list.Body.HasUniqueRoleAssignments -isnot [bool]) { throw 'Library permission inheritance was not read back.' }
    if ($list.Body.HasUniqueRoleAssignments) {
        Assert-ZavaSharePointReaders $listUri $site.AbsoluteUri $audience $headers $config.sharePoint.ownerUpn
    }
    $result = @{
        Tenant = $config.tenantId; ObservedAt = [DateTimeOffset]::UtcNow.ToString('o')
        SiteId = $resolved.Body.id; DriveId = $drive.Body.id; SiteUrl = $site.AbsoluteUri
        SiteStatus = 'READY_READ_BACK'; ContentAccess = 'OWNER_ONLY_SITE_AND_LIBRARY_ROLE_CHECKS'
        TenantAdministratorAccess = 'IMPLICIT_NOT_CHANGED'; SourceIndexing = 'NOT_RUN'; FilesUploaded = 0
    }
    Save-ZavaJson (Join-Path $script:Context.Bundle 'sharepoint-target.private.json') $result
    return $result
}

function Wait-ZavaOperation([string]$Uri) {
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($script:Context.WaitSeconds)
    do {
        $response = Invoke-ZavaRequest $Uri 'https://api.fabric.microsoft.com'
        Assert-ZavaResponse $response
        $status = $response.Body.status
        if ($status -in @('Failed', 'Cancelled', 'Deduped')) { throw "Fabric operation ended $status; inspect the recorded operation." }
        if ($status -in @('Succeeded', 'Completed')) { return $response.Body }
        if ($status -notin @('NotStarted', 'Running', 'InProgress')) { throw "Unexpected Fabric operation state: $status" }
        Start-Sleep -Seconds 5
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "Fabric operation exceeded the wait limit. It may still run/incur costs: $Uri. No automatic cancel/delete."
}

function Invoke-ZavaWrite([string]$Key, [string]$Uri, [string]$Audience, [string]$Method, $Body, [byte[]]$Bytes = $null) {
    if ($script:Context.Ledger.ContainsKey($Key)) {
        $receipt = $script:Context.Ledger[$Key]
        if ($receipt.State -eq 'CREATED') { return $receipt.Id }
        if ($receipt.Operation) {
            $null = Wait-ZavaOperation $receipt.Operation
            $result = Invoke-ZavaRequest "$($receipt.Operation)/result" $Audience
            Assert-ZavaResponse $result
            Save-ZavaReceipt $Key 'CREATED' $result.Body.id
            return $result.Body.id
        }
        throw "Uncertain prior write: $Key. Reconcile the exact target and ledger manually before resume; no blind retry."
    }
    Save-ZavaReceipt $Key 'PENDING'
    $response = Invoke-ZavaRequest $Uri $Audience $Method $Body $Bytes
    Assert-ZavaResponse $response
    if ($response.Status -eq 202) {
        if (-not $response.Headers.ContainsKey('Location')) { throw "Missing LRO Location for $Key" }
        $operation = [string]$response.Headers['Location'][0]
        Save-ZavaReceipt $Key 'PENDING' '' $operation
        $null = Wait-ZavaOperation $operation
        $response = Invoke-ZavaRequest "$operation/result" $Audience
        Assert-ZavaResponse $response
    }
    $id = if ($response.Body.ContainsKey('id')) { [string]$response.Body.id } else { $Key }
    Save-ZavaReceipt $Key 'CREATED' $id
    return $id
}

function Expand-ZavaDefinition($Payload, [hashtable]$Bindings) {
    foreach ($part in $Payload.definition.parts) {
        $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($part.payload))
        foreach ($key in $Bindings.Keys) { $text = $text.Replace($key, [string]$Bindings[$key]) }
        if ($text -match '__[A-Z][A-Z0-9_]+__') { throw "Unresolved definition binding in $($part.path)" }
        $part.payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($text))
    }
    return $Payload
}

function New-ZavaFabricItem($Artifact, [hashtable]$Bindings) {
    $payload = Read-ZavaJson (Join-Path $script:Context.Bundle $Artifact.path)
    $payload = Expand-ZavaDefinition $payload $Bindings
    $payload.displayName = "$($script:Context.Config.resourcePrefix) - $($Artifact.name)"
    return Invoke-ZavaWrite "fabric/$($payload.displayName)" "$script:Fabric/workspaces/$($script:Context.Config.fabric.workspaceId)/items" 'https://api.fabric.microsoft.com' 'POST' $payload
}

function Invoke-ZavaSeed {
    $config = $script:Context.Config
    $manifest = $script:Context.Manifest
    $bundle = $script:Context.Bundle
    if ('SharePoint' -in $config.providers) {
        $drive = "$script:Graph/drives/$($config.sharePoint.driveId)"
        $namespace = "$($config.resourcePrefix)-$((Get-FileHash -LiteralPath (Join-Path $bundle 'manifest.json')).Hash.Substring(0, 12).ToLowerInvariant())"
        $folderKey = 'sharepoint/root'
        if (-not $script:Context.Ledger.ContainsKey($folderKey)) {
            $existing = Invoke-ZavaRequest "${drive}/root:/${namespace}" 'https://graph.microsoft.com'
            Assert-ZavaResponse $existing @(404)
        }
        $rootId = Invoke-ZavaWrite $folderKey "${drive}/root/children" 'https://graph.microsoft.com' 'POST' @{name = $namespace; folder = @{}; '@microsoft.graph.conflictBehavior' = 'fail'}
        $folders = @{'' = $rootId}
        foreach ($relative in (Read-ZavaJson (Join-Path $bundle 'uploads.json'))) {
            $parent = ''
            $segments = $relative.Split('/')
            foreach ($segment in $segments[0..($segments.Length - 2)]) {
                $next = if ($parent) { "$parent/$segment" } else { $segment }
                if (-not $folders.ContainsKey($next)) {
                    $folders[$next] = Invoke-ZavaWrite "sharepoint/folder/$next" "${drive}/items/$($folders[$parent])/children" 'https://graph.microsoft.com' 'POST' @{name = $segment; folder = @{}; '@microsoft.graph.conflictBehavior' = 'fail'}
                }
                $parent = $next
            }
            $name = [uri]::EscapeDataString($segments[-1])
            $bytes = [IO.File]::ReadAllBytes((Join-Path $bundle $relative))
            $null = Invoke-ZavaWrite "sharepoint/file/$relative" "${drive}/items/$($folders[$parent]):/${name}:/content?@microsoft.graph.conflictBehavior=fail" 'https://graph.microsoft.com' 'PUT' $null $bytes
        }
    }
    if ($config.createDisabledPeople) {
        foreach ($person in (Read-ZavaJson (Join-Path $bundle 'people.json'))) {
            $password = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(36)) + '!aA7'
            $payload = @{accountEnabled = $false; displayName = "[SYNTHETIC] $($person.displayName)"; mailNickname = "$($config.resourcePrefix)-$($person.key)"
                userPrincipalName = "$($config.resourcePrefix)-$($person.key)@$($config.tenantDomain)"
                passwordProfile = @{password = $password; forceChangePasswordNextSignIn = $true}; jobTitle = $person.role}
            $null = Invoke-ZavaWrite "person/$($person.key)" "$script:Graph/users" 'https://graph.microsoft.com' 'POST' $payload
            $payload.passwordProfile.password = ''; $password = ''
        }
    }
    foreach ($pair in @(@('createOutlookDrafts', 'outlook-drafts.json', 'messages'), @('createCalendarAppointments', 'calendar-appointments.json', 'events'))) {
        if ($config[$pair[0]]) {
            $index = 0
            foreach ($payload in (Read-ZavaJson (Join-Path $bundle $pair[1]))) {
                $null = Invoke-ZavaWrite "$($pair[2])/$index" "$script:Graph/users/$($config.mailboxObjectId)/$($pair[2])" 'https://graph.microsoft.com' 'POST' $payload
                $index++
            }
        }
    }
    if ('Fabric' -in $config.providers) {
        $workspace = $config.fabric.workspaceId
        $lakehouseName = $config.resourcePrefix.Replace('-', '_') + '_Lakehouse'
        $lakehouse = Invoke-ZavaWrite 'fabric/lakehouse' "$script:Fabric/workspaces/$workspace/lakehouses" 'https://api.fabric.microsoft.com' 'POST' @{displayName = $lakehouseName; creationPayload = @{enableSchemas = $true}}
        $storage = "https://onelake.dfs.fabric.microsoft.com/$workspace/$lakehouse/Files"
        foreach ($directory in @('zava-enterprise', 'zava-enterprise/fabric')) {
            $null = Invoke-ZavaWrite "onelake/directory/$directory" "${storage}/${directory}?resource=directory" 'https://storage.azure.com' 'PUT' $null
        }
        foreach ($table in $manifest.fabric.tables) {
            $name = $table.name
            $uri = "${storage}/zava-enterprise/fabric/${name}.csv"
            $bytes = [IO.File]::ReadAllBytes((Join-Path $bundle "canonical\fabric\$name.csv"))
            $null = Invoke-ZavaWrite "onelake/create/$name" "${uri}?resource=file" 'https://storage.azure.com' 'PUT' $null
            $null = Invoke-ZavaWrite "onelake/append/$name" "${uri}?action=append&position=0" 'https://storage.azure.com' 'PATCH' $null $bytes
            $null = Invoke-ZavaWrite "onelake/flush/$name" "${uri}?action=flush&position=$($bytes.Length)" 'https://storage.azure.com' 'PATCH' $null
        }
        $bindings = @{'__WORKSPACE_ID__' = $workspace; '__LAKEHOUSE_ID__' = $lakehouse}
        $notebook = New-ZavaFabricItem $manifest.fabric.notebook $bindings
        $jobKey = 'fabric/seed-job'
        if (-not $script:Context.Ledger.ContainsKey($jobKey)) {
            Save-ZavaReceipt $jobKey 'PENDING'
            $job = Invoke-ZavaRequest "$script:Fabric/workspaces/$workspace/items/$notebook/jobs/instances?jobType=RunNotebook" 'https://api.fabric.microsoft.com' 'POST' @{executionData = @{parameters = @{}}}
            Assert-ZavaResponse $job @(202)
            if (-not $job.Headers.ContainsKey('Location')) { throw 'Notebook job has no Location; reconcile, do not rerun.' }
            Save-ZavaReceipt $jobKey 'RUNNING' '' ([string]$job.Headers['Location'][0])
        }
        if ($script:Context.Ledger[$jobKey].State -ne 'CREATED') {
            $null = Wait-ZavaOperation $script:Context.Ledger[$jobKey].Operation
            Save-ZavaReceipt $jobKey 'CREATED' $notebook
        }
        foreach ($model in $manifest.fabric.models) {
            $id = New-ZavaFabricItem $model $bindings
            if ($model.ContainsKey('role')) {
                $role = $model.role
                if ($role -notin @('FINANCE', 'COMMERCIAL', 'OPERATIONS') -or $bindings.ContainsKey("__MODEL_${role}_ID__")) {
                    throw 'Invalid or duplicated canonical model-role binding.'
                }
                $bindings["__MODEL_${role}_ID__"] = $id
            }
        }
        foreach ($agent in $manifest.fabric.agents) { $null = New-ZavaFabricItem $agent $bindings }
        $null = New-ZavaFabricItem $manifest.fabric.ontology $bindings
    }
    if ('Search' -in $config.providers) {
        $search = $config.search.searchEndpoint.TrimEnd('/')
        foreach ($kb in $manifest.search) {
            foreach ($pair in @(@('indexes', 'index.json'), @('knowledgesources', 'knowledge-source.json'), @('knowledgebases', 'knowledge-base.json'))) {
                $payload = Read-ZavaJson (Join-Path $bundle "$($kb.path)/$($pair[1])")
                $null = Invoke-ZavaWrite "$($pair[0])/$($payload.name)" "$search/$($pair[0])/$($payload.name)?api-version=2026-04-01" 'https://search.azure.com' 'PUT' $payload
                if ($pair[0] -eq 'indexes') {
                    $key = "indexing/$($kb.name)"
                    if (-not $script:Context.Ledger.ContainsKey($key)) {
                        Save-ZavaReceipt $key 'PENDING'
                        $documents = Read-ZavaJson (Join-Path $bundle "$($kb.path)/documents.json")
                        $result = Invoke-ZavaRequest "$search/indexes/$($kb.name)/docs/index?api-version=2026-04-01" 'https://search.azure.com' 'POST' $documents
                        Assert-ZavaResponse $result @(200, 207)
                        if ($result.Body.value.Count -ne $documents.value.Count -or @($result.Body.value | Where-Object { -not $_.status }).Count) {
                            throw "Partial indexing failure in $($kb.name); reconcile the private ledger before resume."
                        }
                        Save-ZavaReceipt $key 'CREATED' $kb.name
                    } elseif ($script:Context.Ledger[$key].State -ne 'CREATED') { throw "Uncertain indexing: $key" }
                }
            }
        }
    }
}

function Test-ZavaNative {
    $config = $script:Context.Config
    $report = @{
        Tenant = $config.tenantId; ObservedAt = [DateTimeOffset]::UtcNow.ToString('o')
        Creation = @{}; KnowledgeBaseRetrieval = @{}; Microsoft365Retrieval = 'NOT_RUN'; WebRetrieval = 'NOT_RUN'
        SemanticModelQueries = 'NOT_RUN'; DataAgentQueries = 'NOT_RUN'; OntologyTraversal = 'NOT_RUN'
        SearchAgentConnection = 'NOT_RUN'; Plugins = 'MANUAL_NOT_RUN'; SourceReadiness = 'NOT_RUN'
    }
    Save-ZavaJson (Join-Path $script:Context.Bundle 'readiness.private.json') $report
    $workspace = $config.fabric.workspaceId
    $drive = "$script:Graph/drives/$($config.sharePoint.driveId)"
    foreach ($key in $script:Context.Ledger.Keys) {
        $receipt = $script:Context.Ledger[$key]
        $report.Creation[$key] = $receipt.State
        if ($receipt.State -ne 'CREATED') { continue }
        $uri = $null
        $audience = $null
        if ($key -eq 'sharepoint/root' -or $key.StartsWith('sharepoint/file/')) {
            $uri = "$drive/items/$($receipt.Id)"; $audience = 'https://graph.microsoft.com'
        } elseif ($key.StartsWith('person/')) {
            $uri = "$script:Graph/users/$($receipt.Id)"; $audience = 'https://graph.microsoft.com'
        } elseif ($key -match '^(messages|events)/') {
            $uri = "$script:Graph/users/$($config.mailboxObjectId)/$($Matches[1])/$($receipt.Id)"; $audience = 'https://graph.microsoft.com'
        } elseif ($key -eq 'fabric/seed-job') {
            $uri = $receipt.Operation; $audience = 'https://api.fabric.microsoft.com'
        } elseif ($key.StartsWith('fabric/')) {
            $uri = "$script:Fabric/workspaces/$workspace/items/$($receipt.Id)"; $audience = 'https://api.fabric.microsoft.com'
        } elseif ($key -match '^(indexes|knowledgesources|knowledgebases)/') {
            $uri = "$($config.search.searchEndpoint.TrimEnd('/'))/${key}?api-version=2026-04-01"; $audience = 'https://search.azure.com'
        }
        if ($uri) {
            $response = Invoke-ZavaRequest $uri $audience
            if ($response.Status -ne 200) {
                $report.Creation[$key] = "READBACK_HTTP_$($response.Status)"
                Save-ZavaJson (Join-Path $script:Context.Bundle 'readiness.private.json') $report
                Assert-ZavaResponse $response @(200)
            }
            if ($key.StartsWith('sharepoint/file/')) {
                $relative = $key.Substring('sharepoint/file/'.Length)
                if ($response.Body.size -ne (Get-Item -LiteralPath (Join-Path $script:Context.Bundle $relative)).Length) { throw "SharePoint size mismatch: $relative" }
            } elseif ($key.StartsWith('person/') -and $response.Body.accountEnabled) {
                throw 'A synthetic persona has been enabled outside the approved disabled-user scope.'
            } elseif ($key.StartsWith('messages/') -and (-not $response.Body.isDraft -or $response.Body.toRecipients.Count -gt 0)) {
                throw 'Synthetic mail readback is not a recipient-free draft.'
            } elseif ($key.StartsWith('events/') -and ($response.Body.attendees.Count -gt 0 -or $response.Body.isOnlineMeeting)) {
                throw 'Synthetic appointment readback contains attendees or an online meeting.'
            } elseif ($key -eq 'fabric/seed-job' -and $response.Body.status -notin @('Succeeded', 'Completed')) {
                throw 'Seed notebook no longer reports a successful job outcome.'
            }
            $report.Creation[$key] = 'EXISTS_READ_BACK'
        } elseif ($key.StartsWith('indexing/')) {
            $name = $key.Substring('indexing/'.Length)
            $stats = Invoke-ZavaRequest "$($config.search.searchEndpoint.TrimEnd('/'))/indexes/${name}/stats?api-version=2026-04-01" 'https://search.azure.com'
            Assert-ZavaResponse $stats @(200)
            $expected = @($script:Context.Manifest.search | Where-Object name -eq $name)[0].documents
            $report.Creation[$key] = if ($stats.Body.documentCount -eq $expected) { 'INDEX_COUNT_MATCH' } else { "WAITING_OR_MISMATCH_EXPECTED_${expected}_ACTUAL_$($stats.Body.documentCount)" }
        } else {
            $report.Creation[$key] = 'ACKNOWLEDGED_NOT_READ_BACK'
        }
    }
    Save-ZavaJson (Join-Path $script:Context.Bundle 'readiness.private.json') $report
    if ('Search' -in $config.providers) {
        foreach ($kb in $script:Context.Manifest.search) {
            $name = "$($kb.name)-kb"
            $result = Invoke-ZavaRequest "$($config.search.searchEndpoint.TrimEnd('/'))/knowledgebases/${name}/retrieve?api-version=2026-04-01" 'https://search.azure.com' 'POST' @{intents = @(@{type = 'semantic'; search = 'Zava synthetic evidence request current policy source version'})}
            Assert-ZavaResponse $result @(200)
            $report.KnowledgeBaseRetrieval[$name] = if ($result.Body.ContainsKey('references') -and $result.Body.references.Count -gt 0) { 'RETRIEVED_REVIEW_REQUIRED' } else { 'NO_REFERENCES_REVIEW_REQUIRED' }
            Save-ZavaJson (Join-Path $script:Context.Bundle "$name-retrieve.private.json") $result.Body
            Save-ZavaJson (Join-Path $script:Context.Bundle 'readiness.private.json') $report
        }
    }
    return $report
}

Export-ModuleMember -Function Read-ZavaJson, Save-ZavaJson, Initialize-Zava, Assert-ZavaBundle, Invoke-ZavaPreflight, Invoke-ZavaSeed, Test-ZavaNative, Expand-ZavaDefinition, Invoke-ZavaSharePointSite

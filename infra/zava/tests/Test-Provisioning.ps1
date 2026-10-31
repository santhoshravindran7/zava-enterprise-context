#Requires -Version 7.2
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$source = Split-Path $PSScriptRoot -Parent
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('zava-provisioning-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $temporary
Import-Module (Join-Path $source 'Zava.psm1') -Force
$config = Read-ZavaJson (Join-Path $source 'environment.template.json')
$config.tenantId = '11111111-1111-1111-1111-111111111111'
$config.tenantDomain = 'synthetic.example'
$config.environmentLabel = 'Mock Zava sandbox'
$config.costApprovalReference = 'TEST-ONLY-NO-CLOUD'
$config.sharePoint = @{siteId = 'fake-site'; driveId = 'fake-drive'}
$config.fabric = @{workspaceId = 'fake-workspace'; capacityId = 'fake-capacity'; ontologyAdmitted = $true; dataAgentAdmitted = $true}
$config.search.searchResourceId = '/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/fake-rg/providers/Microsoft.Search/searchServices/fake-search'
$config.search.searchEndpoint = 'https://fake-search.search.windows.net'
$config.createDisabledPeople = $true
$config.createOutlookDrafts = $true
$config.createCalendarAppointments = $true
$config.mailboxObjectId = 'fake-mailbox'
$configPath = Join-Path $temporary 'input.json'
Save-ZavaJson $configPath $config
$bundle = Join-Path $temporary 'bundle'
try {
    & python -B (Join-Path $source 'seed.py') --output $bundle --config $configPath
    if ($LASTEXITCODE -ne 0) { throw 'Mock bundle generation failed.' }
    Initialize-Zava $bundle
    Assert-ZavaBundle (Get-FileHash -LiteralPath (Join-Path $bundle 'plan.json')).Hash
    & (Get-Module Zava) {
        $script:MockWrites = [Collections.Generic.List[object]]::new()
        $script:MockCount = 0
        $script:MockTerminal = 'Succeeded'
        $script:MockObjects = @{}
        $script:MockSearch = @{}
        function script:Invoke-ZavaRequest([string]$Uri, [string]$Audience, [string]$Method = 'GET', $Body = $null, [byte[]]$Bytes = $null, [hashtable]$ExtraHeaders = @{}) {
            if ($Method -eq 'GET') {
                if ($Uri.EndsWith('/organization')) { return @{Status = 200; Body = @{value = @(@{id = $script:Context.Config.tenantId})}; Headers = @{}} }
                if ($Uri -match '/domains/') { return @{Status = 200; Body = @{id = $script:Context.Config.tenantDomain; isVerified = $true}; Headers = @{}} }
                if ($Uri -match '/sites/.+/drives$') { return @{Status = 200; Body = @{value = @(@{id = 'fake-drive'})}; Headers = @{}} }
                if ($Uri -match '/workspaces/fake-workspace$') { return @{Status = 200; Body = @{capacityId = 'fake-capacity'}; Headers = @{}} }
                if ($Uri.EndsWith('/capacities')) { return @{Status = 200; Body = @{value = @(@{id = 'fake-capacity'; state = 'Active'})}; Headers = @{}} }
                if ($Uri.EndsWith('/items')) { return @{Status = 200; Body = @{value = @()}; Headers = @{}} }
                if ($Uri -match 'management.azure.com') { return @{Status = 200; Body = @{name = 'fake-search'}; Headers = @{}} }
                if ($Uri -match '/users/fake-mailbox$') { return @{Status = 200; Body = @{userPrincipalName = 'mailbox@synthetic.example'}; Headers = @{}} }
                if ($Uri -match '/operations/[^/]+/result$') { return @{Status = 200; Body = @{id = 'fake-lro-id'}; Headers = @{}} }
                if ($Uri -match '/operations/' -or $Uri -match '/jobs/instances/fake-job') { return @{Status = 200; Body = @{status = $script:MockTerminal}; Headers = @{}} }
                if ($Uri -match '/indexes/([^/]+)/stats\?') {
                    $name = $Matches[1]
                    $count = @($script:Context.Manifest.search | Where-Object name -eq $name)[0].documents
                    return @{Status = 200; Body = @{documentCount = $count}; Headers = @{}}
                }
                if ($Uri -match '/(indexes|knowledgesources|knowledgebases)/([^/?]+)\?') {
                    $key = "$($Matches[1])/$($Matches[2])"
                    if ($script:MockSearch.ContainsKey($key)) { return @{Status = 200; Body = $script:MockSearch[$key]; Headers = @{}} }
                }
                $id = ([uri]$Uri).Segments[-1].TrimEnd('/')
                if ($script:MockObjects.ContainsKey($id)) { return @{Status = 200; Body = $script:MockObjects[$id]; Headers = @{}} }
                if ($Uri -match 'search.windows.net' -or $Uri -match '/root:/') { return @{Status = 404; Body = @{}; Headers = @{}} }
                throw "Unhandled mock GET: $Uri"
            }
            $script:MockCount++
            $script:MockWrites.Add(@{Uri = $Uri; Method = $Method; Body = $Body; ByteCount = if ($null -ne $Bytes) { $Bytes.Length } else { 0 }})
            if ($Uri -match '/jobs/instances\?') { return @{Status = 202; Body = @{}; Headers = @{Location = @('https://api.fabric.microsoft.com/v1/workspaces/fake-workspace/items/fake-notebook/jobs/instances/fake-job')}} }
            if ($Uri.EndsWith('/lakehouses')) {
                if (-not $Body.creationPayload.enableSchemas) { throw 'Managed dbo lakehouse schema not enabled.' }
                $script:MockObjects['fake-lro-id'] = @{id = 'fake-lro-id'}
                return @{Status = 202; Body = @{}; Headers = @{Location = @('https://api.fabric.microsoft.com/v1/operations/fake-lro')}}
            }
            if ($Uri -match '/docs/index\?') {
                return @{Status = 200; Body = @{value = @($Body.value | ForEach-Object { @{key = $_.id; status = $true} })}; Headers = @{}}
            }
            if ($Uri -match '/retrieve\?') { return @{Status = 200; Body = @{references = @(@{sourceData = @{sourcePath = 'canonical/work/DOC-03'}})}; Headers = @{}} }
            if ($null -ne $Body -and $Body.ContainsKey('definition')) {
                foreach ($part in $Body.definition.parts) {
                    $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($part.payload))
                    if ($text -match '__[A-Z][A-Z0-9_]+__') { throw 'Unresolved placeholder reached native creation.' }
                }
            }
            if ($Uri.EndsWith('/users') -and $Body.accountEnabled) { throw 'Synthetic user was enabled.' }
            if ($Uri.EndsWith('/messages') -and $Body.toRecipients.Count -gt 0) { throw 'Mail recipients were created.' }
            if ($Uri.EndsWith('/events') -and $Body.attendees.Count -gt 0) { throw 'Meeting attendees were created.' }
            $object = @{id = "fake-created-$script:MockCount"; size = if ($null -ne $Bytes) { $Bytes.Length } else { 0 };
                isDraft = $true; toRecipients = @(); attendees = @(); isOnlineMeeting = $false; accountEnabled = $false}
            $script:MockObjects[$object.id] = $object
            if ($Uri -match '/(indexes|knowledgesources|knowledgebases)/([^/?]+)\?') {
                $script:MockSearch["$($Matches[1])/$($Matches[2])"] = $Body
            }
            return @{Status = 201; Body = @{id = "fake-created-$script:MockCount"}; Headers = @{}}
        }
        Invoke-ZavaPreflight
        Invoke-ZavaSeed
        $first = $script:MockCount
        Invoke-ZavaSeed
        if ($script:MockCount -ne $first) { throw 'Completed provisioning replayed writes on resume.' }
        $report = Test-ZavaNative
        if ($report.KnowledgeBaseRetrieval.Count -ne 3 -or $report.Microsoft365Retrieval -ne 'NOT_RUN') { throw 'Readiness conflated native service and KB retrieval.' }
        if ($script:Context.Ledger['fabric/seed-job'].Operation -notmatch '/fake-job$' -or
            $script:Context.Ledger['fabric/lakehouse'].Operation -notmatch '/fake-lro$') { throw 'Completed receipts discarded job/LRO provenance.' }
        if (@($report.Creation.Values | Where-Object { $_ -eq 'INDEX_COUNT_MATCH' }).Count -ne 3) { throw 'Index document counts were not read back.' }
        if (@($report.Creation.Values | Where-Object { $_ -eq 'EXISTS_READ_BACK' }).Count -lt 20) { throw 'Creation verification did not read actual objects.' }
        foreach ($pair in @(@('/messages$', 120), @('/events$', 60), @('/users$', 8), @('/items$', 25), @('/knowledgebases/[^/]+\?', 3))) {
            $actual = @($script:MockWrites | Where-Object { $_.Uri -match $pair[0] }).Count
            if ($actual -ne $pair[1]) { throw "Wrong native action count for $($pair[0]): $actual" }
        }
        $script:MockTerminal = 'Failed'
        $failed = $false
        try { Wait-ZavaOperation 'https://api.fabric.microsoft.com/v1/operations/fake-failed' } catch {
            if ($_.Exception.Message -notmatch 'ended Failed') { throw }
            $failed = $true
        }
        if (-not $failed) { throw 'Failed LRO was accepted.' }
        function script:az {
            $resourceIndex = [Array]::IndexOf($args, '--resource')
            $audience = [string]$args[$resourceIndex + 1]
            $claims = @{tid = '22222222-2222-2222-2222-222222222222'; aud = $audience; exp = [DateTimeOffset]::UtcNow.AddMinutes(10).ToUnixTimeSeconds()}
            $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($claims | ConvertTo-Json -Compress))).TrimEnd('=').Replace('+', '-').Replace('/', '_')
            $global:LASTEXITCODE = 0
            return (@{accessToken = "header.$encoded.signature"} | ConvertTo-Json -Compress)
        }
        $blocked = $false
        try { Get-ZavaToken 'https://graph.microsoft.com' } catch {
            if ($_.Exception.Message -notmatch 'another tenant') { throw }
            $blocked = $true
        }
        if (-not $blocked) { throw 'Wrong tenant JWT accepted.' }
        Write-Output "PASS: all provider creation counts, CSV staging, actual-ID substitution, LRO/job polling, no-write resume, 3 KB probes, wrong-tenant rejection. Mock writes: $first; ZERO network calls."
    }
} finally {
    $resolved = (Resolve-Path -LiteralPath $temporary).Path
    if ([IO.Path]::GetFileName($resolved) -notmatch '^zava-provisioning-[a-f0-9]{32}$') { throw 'Refusing unexpected test cleanup path.' }
    Remove-Item -LiteralPath $resolved -Recurse
}

#Requires -Version 7.2
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$source = Split-Path $PSScriptRoot -Parent
Import-Module (Join-Path $source 'Zava.psm1') -Force
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('zava-safety-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $temporary
$template = Read-ZavaJson (Join-Path $source 'environment.template.json')
Save-ZavaJson (Join-Path $temporary 'config.json') $template
Save-ZavaJson (Join-Path $temporary 'manifest.json') @{files = @()}
Save-ZavaJson (Join-Path $temporary 'plan.json') @{blockers = @('tenant unresolved')}
function Assert-Throws([scriptblock]$Action, [string]$Expected) {
    $failed = $false
    try { & $Action } catch {
        if ($_.Exception.Message -notmatch $Expected) { throw }
        $failed = $true
    }
    if (-not $failed) { throw "Expected rejection: $Expected" }
}
try {
    Initialize-Zava $temporary
    Assert-Throws { Assert-ZavaBundle ('0' * 64) } 'hash'
    $hash = (Get-FileHash -LiteralPath (Join-Path $temporary 'plan.json')).Hash
    Assert-Throws { Assert-ZavaBundle $hash } 'Unresolved'
    $payload = @{definition = @{parts = @(@{path = 'definition/model.tmdl'; payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('__WORKSPACE_ID__ __LAKEHOUSE_ID__'))})}}
    Assert-Throws { Expand-ZavaDefinition $payload @{'__WORKSPACE_ID__' = 'actual-workspace'} } 'Unresolved'
    $result = Expand-ZavaDefinition $payload @{'__WORKSPACE_ID__' = 'actual-workspace'; '__LAKEHOUSE_ID__' = 'actual-lakehouse'}
    $decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($result.definition.parts[0].payload))
    if ($decoded -ne 'actual-workspace actual-lakehouse') { throw 'Definitions were not decoded/bound/re-encoded.' }
    & (Get-Module Zava) {
        function script:Get-ZavaToken { throw 'Token function must never be reached by rejected hosts.' }
        $blocked = $false
        try { Invoke-ZavaRequest 'https://unapproved.example/' 'https://graph.microsoft.com' } catch {
            if ($_.Exception.Message -notmatch 'unapproved host') { throw }
            $blocked = $true
        }
        if (-not $blocked) { throw 'Unapproved token destination accepted.' }
        $script:Context.Ledger['uncertain'] = @{State = 'PENDING'; Id = ''; Operation = ''}
        $blocked = $false
        try { Invoke-ZavaWrite 'uncertain' 'https://graph.microsoft.com/v1.0/users' 'https://graph.microsoft.com' 'POST' @{} } catch {
            if ($_.Exception.Message -notmatch 'Uncertain prior write') { throw }
            $blocked = $true
        }
        if (-not $blocked) { throw 'An uncertain POST was replayed.' }
        $script:Context.Ledger['completed'] = @{State = 'CREATED'; Id = 'known-id'; Operation = ''}
        if ((Invoke-ZavaWrite 'completed' 'https://graph.microsoft.com/v1.0/users' 'https://graph.microsoft.com' 'POST' @{}) -ne 'known-id') {
            throw 'Completed writes were not resumed without replay.'
        }
    }
    Write-Output 'PASS: exact approval, unbound rejection, definition substitution, token-host guard, uncertain POST and completed-write resume.'
} finally {
    foreach ($name in @('config.json', 'manifest.json', 'plan.json')) {
        Remove-Item -LiteralPath (Join-Path $temporary $name)
    }
    Remove-Item -LiteralPath $temporary
}

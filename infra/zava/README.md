# Setup guide

## Local generation

Prerequisites: **PowerShell 7.2+**, **Python 3.11+**. The generator uses only
Python's standard library; it does not install packages. Word files use
explicitly styled US Letter/Arial Open XML packages.

```powershell
pwsh -NoProfile -File .\infra\zava\Setup-Zava.ps1 `
  -Phase Plan -Bundle C:\ZavaPrivate\generated-001
```

Run from the repository root. The output directory must be new and outside
the repository. Output includes all synthetic assets, file hashes, directory
personas, full model/ontology/notebook payloads, Search creation/indexing
payloads, an exact resource/action plan and a reusable source ZIP.

The source ZIP contains guides, setup code, tests and canonical synthetic
fixtures. It excludes tenant configuration, live IDs, private evidence and
credentials. Extract it and run `infra\zava\Setup-Zava.ps1` the same way.

## Private environment configuration

Copy `environment.template.json` outside the repository. Resolve:

| Setting | Required target |
|---|---|
| tenantId / tenantDomain | Exact approved Entra tenant GUID and verified domain; isolate test sites/workspaces, not production data |
| environmentLabel | Operator-readable sandbox label, not an Azure resource ID |
| sharePoint.siteId / driveId | Existing approved site/library, or IDs read back by the separately approved site bootstrap below |
| sharePoint.siteUrl / siteTitle / ownerUpn | Only for the optional, separate communication-site bootstrap |
| fabric.workspaceId / capacityId | Existing workspace on an active approved capacity |
| ontologyAdmitted / dataAgentAdmitted | Explicitly confirmed service feature availability |
| search.searchResourceId / searchEndpoint | Existing Azure AI Search ARM ID and matching HTTPS endpoint |
| costApprovalReference | Human-reviewed incremental storage/compute/query cost envelope |
| mailboxObjectId | Existing licensed synthetic mailbox, only for optional draft/appointment lanes |

Providers default to `SharePoint`, `Fabric`, `Search`. Removing a provider
produces a visibly partial native setup, not an equivalent complete enterprise.
All assets are still generated offline.

Account creation, Outlook drafts and calendar appointments are off by default.
Turn on their JSON booleans only after separately reviewing the corresponding
resource/action rows. Strings such as `"false"` are rejected, not treated as
false consent.

Generate a new bound Plan:

```powershell
pwsh -NoProfile -File .\infra\zava\Setup-Zava.ps1 -Phase Plan `
  -Config C:\ZavaPrivate\environment.json -Bundle C:\ZavaPrivate\bound-001
Get-Content C:\ZavaPrivate\bound-001\plan.json -Raw
```

Read the entire plan, exact resources and its bound asset manifests. Unknown
targets produce `DRAFT_UNBOUND` and cannot be applied.

## Optional new SharePoint test site

The same setup supports an approved corporate test tenant and an isolated
training tenant. Keep separate configurations, plans and ledgers; a corporate
test is not evidence that a training tenant works. Do not hard-code an account,
tenant or SharePoint hostname into the source.

If no existing approved site is available, populate `sharePoint.siteUrl`,
`siteTitle` and `ownerUpn` in the private configuration. Use an exact
`https://<approved-host>.sharepoint.com/sites/<new-site-slug>` URL and the
authenticated operator's UPN in the verified tenant domain. Obtain site-creation
permission through the organization's existing process; this toolkit does not
grant access or bypass corporate site/lab policies.

```powershell
pwsh -NoProfile -File .\infra\zava\Setup-SharePointSite.ps1 -Phase Plan `
  -Config C:\ZavaPrivate\environment.json -Bundle C:\ZavaPrivate\site-plan-001
```

Review and approve this **separate site-only plan**, including the exact
URL/title/owner, existing SharePoint license/quota and default tenant policies.
After approved user-handled login:

```powershell
$siteBundle = 'C:\ZavaPrivate\site-plan-001'
$siteHash = (Get-FileHash (Join-Path $siteBundle 'plan.json')).Hash.ToLowerInvariant()
pwsh -NoProfile -File .\infra\zava\Setup-SharePointSite.ps1 -Phase Apply `
  -Bundle $siteBundle -ApprovedPlanSha256 $siteHash
```

The bootstrap creates one communication site without a Microsoft 365 group or
Teams team. It does not add members, invite people, edit permissions, upload
content or seed other providers. The operator must own the site. Tenant
provisioning policies can apply; unexpected content readers stop readback.
Implicit tenant-administrator access is not removed or asserted absent.
Other SharePoint clouds/hosts are a manual lane, not silently supported.

Inspect `sharepoint-target.private.json`. Copy its `SiteId` and `DriveId` into
the **private content configuration**, then generate and obtain approval for a
new `Setup-Zava.ps1` content plan. Do not reuse the site-plan hash for content
upload. Run the site bootstrap with `-Phase Verify` and the same hash for
read-only site/library verification. All live site-creation paths remain
untested; status polling and role-assignment reads are mocked regressions only.

## Approved login and deployment

After human approval of login to the exact issued tenant, sign in yourself:

```powershell
az login --tenant <APPROVED-TENANT-GUID> --allow-no-subscriptions
```

Azure CLI is required only for live operations. Authentication, consent and
permissions are operator prerequisites; no automatic installation, login,
consent or grants occur. Never paste passwords/tokens into configuration or
source control.

After separate approval of the exact resource/action/permission/cost plan:

```powershell
$bundle = 'C:\ZavaPrivate\bound-001'
$hash = (Get-FileHash (Join-Path $bundle 'plan.json')).Hash.ToLowerInvariant()
pwsh -NoProfile -File .\infra\zava\Setup-Zava.ps1 -Phase Apply `
  -Bundle $bundle -ApprovedPlanSha256 $hash
```

Type `APPLY <exact-hash>` when prompted. `-ApprovalText` exists only for an
operator acting after the same explicit human approval. A hash, configuration
flag or phrase is not itself proof of consent.

Apply validates token tenant/audience, domain, site/library, workspace/capacity
and Search ARM/endpoint before resource writes. Code/config/asset changes
invalidate the plan. The [operator guide](../../docs/operations.md) details
privileges, resource ordering, recovery and manual lanes.

## Verify

```powershell
pwsh -NoProfile -File .\infra\zava\Setup-Zava.ps1 -Phase Verify `
  -Bundle $bundle -ApprovedPlanSha256 $hash
```

Private reports separate creation receipts, actual resource readback, file
sizes, notebook job state, index document counts and three extractive
knowledge-base retrieval probes. Review actual returned passages/citations.
Native model queries, source indexing/access, data-agent publication, graph
refresh/traversal, public URL access and SaaS reads need separate checks.

**All live paths are untested in a real tenant.** Mock tests establish local
control flow only. No cold provisioning of capacity, Search services, mailboxes
or model deployments is included. The proposed 10-20 minute warm-environment
target is not guaranteed; startup, hundreds of API calls and indexing can
take longer.

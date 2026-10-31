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
| tenantId / tenantDomain | Exact approved isolated Entra tenant GUID and verified domain |
| environmentLabel | Operator-readable sandbox label, not an Azure resource ID |
| sharePoint.siteId / driveId | Existing approved site and document library |
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

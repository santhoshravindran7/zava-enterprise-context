# Operator guide

## Permission and cost boundary

Use an approved tenant, isolated synthetic-data test resources and existing
service entitlements. Before any live
write, review the exact plan, configured targets, file/resource counts, existing
privileges and incremental storage/compute/query usage with the human operator.
Configuration fields are not consent, billing limits or role grants.

| Lane | Existing access required |
|---|---|
| Identity checks | Graph organization and verified-domain read |
| SharePoint | Approved write access to the named site/library |
| Optional new SharePoint site | Existing site-creation authority, Graph self read and SharePoint site/group permission read; operator is owner |
| Fabric | Create-item/write access on approved active capacity/workspace; OneLake access |
| Search | ARM read for the exact service; Search Service Contributor and Index Data Contributor/Reader as applicable |
| Optional disabled users | Approved Graph user-creation access and administrator authority |
| Optional drafts/appointments | Existing licensed synthetic mailbox and appropriate mail/calendar write access |
| Native SaaS | Approved synthetic-data-only Salesforce, Asana and ServiceNow sandboxes |

The script does not acquire privileges, accept consent, enable/license users,
send mail, invite attendees, change capacity, create paid services or delete
resources. SaaS sandboxes are not intrinsically Entra tenant resources; approve
their target/connection separately.

## Resource ordering

1. Generate local content and read the enterprise story.
2. Resolve private configuration, feature admission and the cost envelope.
3. Generate/review a new bound plan; obtain exact human approval.
4. Log in only to the approved tenant. Preflight verifies all configured
   provider scopes before resource writes.
   If a new SharePoint site is needed, first run the separately approved
   `Setup-SharePointSite.ps1` site-only plan. Read its real site/library IDs and
   role-assignment evidence privately, then bind and approve a new content
   plan. Site approval is not source-upload approval.
5. Create an isolated SharePoint folder and upload all listed archive/document
   paths. Optional disabled users and recipient-free drafts/appointments have
   their own explicitly enabled plan rows.
6. Create a schema-enabled lakehouse; stage eleven unchanged CSVs; create/run
   the seed notebook; create twenty models, three drafts and one ontology.
7. Create three separate semantic-configured Search indexes, complete indexing
   batches, three knowledge sources and three actual knowledge bases.
8. Read private verification evidence; admit each remaining native/manual lane
   independently, preserving actual source/operation identities and timestamps.

Resource names use the environment prefix. Canonical model roles bind the
three data services; extra views cannot replace core role bindings. The seed
notebook verifies staged hashes, explicit types and row counts before writes,
and refuses incompatible existing tables.

## Required readiness checks and manual alternatives

### Microsoft 365 and directory

Read back full authoritative policies and representative new documents/email/
transcript archives under the intended source-reader identity. Establish actual
SharePoint indexing/access separately from successful upload.

Optional users are disabled and unlicensed. Initial random secrets are
memory-only and discarded; enabling, password distribution, mailbox licensing
and resource grants require new approved actions. Map fictional person keys to
actual approved directory IDs privately.

Draft owners are the configured mailbox, not the fictional source author.
Appointments do not manufacture Teams recordings, transcripts or attendance.
Native mail/meeting history requires a separately approved supported ingestion
workflow; otherwise keep the archive-only distinction.

### Web

Review the forty HTML files and two market archives. Obtain approval for the
exact public hosting destination, pages, cost and exposure before publication.
Record real HTTPS URLs and verify full reads/freshness. Local file paths and
`.example` addresses are not public citations. If no hosting exists, retain
`LOCAL_FIXTURE`, not live-web readiness.

### Microsoft Fabric

Inspect all eleven managed `dbo` tables and their counts against the manifest.
Inspect model schemas, dimensions and measures. Run real analytical queries
with consistent account/period/currency/scenario scope and record actual IDs
and results privately. Creation/readback does not establish query correctness.

Review the three data-agent drafts' selected model sources and full
instructions. Obtain approval for publication, publish through the supported
service workflow, and inspect actual query/source provenance. Source selection
and publication are manual; a direct-model query is not a data-agent run.

Confirm six entity keys and five joins before approving ontology refresh.
Wait for graph readiness and run actual traversals. A relationship does not
establish shipment cause or financial impact. Unavailable preview features are
BLOCKED rather than silently substituted.

### Azure AI Search knowledge services

Each policy, operations and commercial collection has a real index, knowledge
source and knowledge base. Three folders/indexes alone are not equivalent.
The supported GA `2026-04-01` path uses extractive `intents`, not LLM query
planning or answer synthesis.

Verify index counts and all three retrieval responses. Inspect passages,
sourcePath and version against full original source text. SourcePath is a bundle
locator, not a fabricated URL. Current-policy indexing excludes DOC-02.
Any additional client/project connection, model deployment or consent requires
its own exact approved plan and separate native readiness check.

### Salesforce, Asana and ServiceNow

Read full opportunity/task snapshots and the forty incident CSV/JSON records.
Preserve stage/amount/currency and the six tasks' unassigned/undated/open state.
Incidents have no real caller/assignee and no asserted financial cause/impact.

Before native import, approve exact sandbox/object/count/field mapping,
privileges and notification/workflow consequences. Use supported import tools
only in approved synthetic-data sandboxes. Consent/connection is a separate
approval. Read back actual records with the intended identity. If unavailable,
label each source `LOCAL_FIXTURE`/`BLOCKED`, never native PASS.

## Resume, errors and private evidence

Every write is recorded PENDING before submission. Fabric operation/job URLs
are persisted and retained after completion. Resume polls known operations
without resubmitting; completed receipts skip writes. PENDING without an
operation stops for exact-resource reconciliation. Partial indexing failures
are explicit. Do not blindly replay timed-out POSTs or edit ledger ownership.

GET throttling retries are bounded; writes have no blind retries. Tenant/
audience mismatches and unexpected hosts/redirects are refused. An operation
can continue after the wait limit and incur costs; review its recorded job
before approving any corrective action.

Private reports distinguish acknowledged writes, resource existence/file-size
readback, index counts, job state, passage retrieval and remaining unchecked
source paths. A receipt does not prove byte-level source readback or service
indexing. Do not publish config, live IDs, operations, full private retrieval
responses, secrets or tenant evidence.

The optional communication-site bootstrap uses the documented SharePoint REST
site manager. A ready site must match its owned ledger GUID and exact URL;
Graph must resolve that same site and its default document library. Existing
URLs are never adopted. Site permissions and default-library inheritance or
unique role assignments are inspected before returning seed targets.
A missing/ambiguous creation response leaves PENDING
and requires manual reconciliation. Known site-status operations can be
resumed without another creation request. If Graph/library readiness or
permission readback fails, keep the site and retry read-only Verify after
inspection; do not automatically recreate, delete or change permissions.

There is no automatic reset or prefix-based cleanup. Present an exact resource
list and obtain separate approval for cancellation/deletion.

## API contracts

- [Fabric create items](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item)
- [SharePoint modern-site creation and status](https://learn.microsoft.com/en-us/sharepoint/dev/apis/site-creation-rest)
- [Fabric lakehouse creation](https://learn.microsoft.com/en-us/rest/api/fabric/lakehouse/items/create-lakehouse)
- [Fabric data-agent definitions](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/data-agent-definition)
- [Knowledge-base creation](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-create-knowledge-base)
- [Search-index knowledge sources](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-search-index)
- [Knowledge-base retrieval](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve)

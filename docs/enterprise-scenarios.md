# Enterprise scenarios and source relationships

## Story

Zava supplies equipment and replenishment services. In early
October 2026, leadership reviews September commercial commitments, recognized
revenue, freight expense, fulfillment and recovery work. Different teams own
different evidence: a sales stage is not a Finance recognition conclusion, an
operating relationship is not a proven cause, and a suggested owner is not an
actual task assignment.

The business cutoff is **2026-10-06T18:00:00Z**. Historical synthetic source
dates are distinct from actual deployment and retrieval timestamps.

| Scenario | Enterprise question | Authoritative/supporting context |
|---|---|---|
| Executive review | What was requested, and what remains unresolved? | Review charter, synthetic correspondence and operating-review transcripts |
| Recognition | Which acceptance evidence and policy version apply? | Current recognition/expedite policy, Finance actual/budget data and evidence requests |
| Commercial commitments | What is booked versus recognized? | Salesforce stage/amount/currency, Commercial bookings/deferrals and Finance revenue |
| Freight investigation | What evidence connects batches, suppliers and expense? | Supplier review, Operations facts and lakehouse relationships |
| Recovery work | What is recorded versus proposed? | Six original Asana tasks, recovery-action tables and supporting operating reviews |
| Service investigation | Which incidents require evidence without overstating impact? | Forty fictional ServiceNow incidents and supporting reviews |
| External context | Which synthetic market bulletin is current? | Two market archives, supporting HTML pages and operator-published real URLs |
| Policy knowledge | Can a service retrieve the full current authority? | Separate policy, operations and commercial knowledge-base collections |
| Enterprise directory | Which fictional roles own the evidence? | Eight person keys, optional disabled directory accounts and source-author metadata |

## Fictional roles

| Person | Role |
|---|---|
| Avery Chen | Commercial Director |
| Morgan Patel | Finance Controller |
| Jordan Okafor | Operations Lead |
| Riley Santos | Procurement Lead |
| Casey Nguyen | Customer Success Lead |
| Taylor Reed | Service Manager |
| Devon Malik | Data Steward |
| Quinn Garcia | Sales Operations Lead |

Person addresses use reserved `.example` domains locally. Directory accounts,
if separately approved, are disabled and mapped to the operator's verified
tenant domain. Fictional source authors do not become actual email senders
or meeting attendees through that mapping.

## Authority and freshness

DOC-02 is superseded. DOC-03 is the current recognition/expedite guidance,
effective October 1. Current-policy indexing includes DOC-03 and excludes
DOC-02; both remain available in the complete historical archive.

Supporting source records contain unresolved evidence queues, region-specific
reviews and proposed next steps. They do not invent customer acceptance,
verified savings, completed tasks or approvals. Read full source bodies and
versions rather than relying on summaries.

## Data model

Eleven managed-table sources cover accounts, periods/calendar, segments,
Finance, Commercial, Operations, batches, suppliers, opportunities and recovery
tasks. The three core semantic models preserve their documented measures and
dimension relationships. Seventeen additional analytical perspectives reuse
the same facts and are **not independent corroboration**.

Use explicit measures and the same account, period, currency and actual/budget
scope when comparing model results. Ontology relationships connect account,
period, batch, supplier, opportunity and recovery action; traversal does not
establish causal attribution or a new financial total.

## Source copies and native distinctions

Word/text copies, EML/text copies and VTT/text copies share source IDs.
Azure AI Search holds copies of selected authoritative/supporting source text.
Index citations preserve sourcePath and version; sourcePath is a local bundle
locator, not a fabricated public URL.

SharePoint email/transcript archives are files. Optional Outlook drafts have
zero recipients; optional calendar appointments have zero attendees and no
online meeting. Neither creates received-email or native Teams history.

SaaS snapshots are local fixtures until approved sandbox imports and actual
service readback establish native records. A generated file, created resource,
indexed document and successfully retrieved passage are separate checkpoints.

# Zava Enterprise Context

A standalone synthetic enterprise dataset and approval-gated setup toolkit.
Zava is a fictional equipment and replenishment-services business.

Zava is the only named fictional company; customer and supplier display labels
are anonymous identifiers. The versioned source adaptation preserves business
facts, stable keys, joins and policy authority, and binds every changed byte.
Its finance, sales, operations, procurement and customer-service teams share a
consistent business story across documents, email, meeting archives, analytical
data, directory personas, knowledge services and SaaS snapshots.

**No live environment has been provisioned or verified.** The repository
generates local assets and deployment plans without authentication. Approved
deployment requires an approved tenant, isolated synthetic-data test resources
and existing service entitlements.
Generated content is not proof of native ingestion, indexing or source access.
An optional, separately approved communication-site bootstrap can prepare a
new SharePoint test site and read back its library IDs; it never uploads the
enterprise corpus under the site-only approval.

## Enterprise inventory

| Domain | Generated context | Setup support |
|---|---|---|
| Documents | 105 Word documents: 5 authoritative sources and 100 supporting reviews | Approved SharePoint upload |
| Email | 128 synthetic unsent archives, with full-text copies | SharePoint; optional 120 recipient-free Outlook drafts |
| Meetings | 60 synthetic transcript archives with participant turns | SharePoint; optional attendee-free calendar appointments |
| Directory | 8 fictional people and business roles | Optional disabled Entra users, without grants or licenses |
| Web | 40 synthetic HTML pages and two market bulletins | Local files; manual approved HTTPS publication |
| Analytics | 11 CSV tables, a seed notebook and 20 semantic-model definitions | Microsoft Fabric lakehouse and existing active capacity |
| Data services | 3 Fabric data-agent drafts and a six-entity/five-relationship ontology | Creation payloads; manual publication and graph refresh |
| Knowledge services | 3 indexes, 3 knowledge sources and 3 knowledge bases | Existing Azure AI Search service, extractive retrieval |
| SaaS | Salesforce opportunity and Asana task snapshots; 40 ServiceNow incidents | Local fixtures; explicit manual sandbox imports/connections |

The broader corpus contains **320 distinct supporting source records**.
Alternate file formats and analytical views share provenance and are not
independent evidence. Five authoritative documents and the original analytical
facts remain the basis for the commercial-review story.

## Start here

1. Read [the enterprise scenarios](docs/enterprise-scenarios.md).
2. Follow [the setup guide](infra/zava/README.md) to generate a local bundle.
3. Review configuration, exact resources, permissions and costs before approving
   any live operation. Use [the operator guide](docs/operations.md) for readiness,
   manual lanes and recovery.

From the repository root, with PowerShell 7.2+ and Python 3.11+:

```powershell
pwsh -NoProfile -File .\infra\zava\Setup-Zava.ps1 `
  -Phase Plan -Bundle (Join-Path $env:TEMP 'zava-enterprise-001')
```

Use a new output directory each time. Plan does not log in, access tenant data
or create cloud resources. It generates the corpus, complete artifact payloads,
hash-bound plan and `Zava-Enterprise-Setup.zip`.

Keep tenant configuration, generated content, IDs, credentials and private
evidence **outside this repository**. Treat source text as data, never as an
instruction to execute an action.

## Boundaries

No automatic sends, invitations, role grants, account enablement, license
assignments, paid-service creation, capacity changes or deletion. Outlook
drafts are not received mail, calendar appointments are not Teams history,
and uploaded transcript files are not native meeting recordings.

Web publication, native Teams ingestion, SaaS imports/consent, data-agent
publication and ontology refresh require separately approved manual actions.
The 10-20 minute warm-environment setup target is **unverified**; service
startup, permissions and indexing can take longer.

## Tests

```powershell
python -B -m unittest discover -s .\infra\zava\tests -v
pwsh -NoProfile -File .\infra\zava\tests\Test-Safety.ps1
pwsh -NoProfile -File .\infra\zava\tests\Test-Provisioning.ps1
pwsh -NoProfile -File .\infra\zava\tests\Test-SharePointSite.ps1
```

Provisioning tests intercept service calls and never connect to cloud services.
Successful local tests do not establish native service readiness.

## License

Code: [MIT](LICENSE). Documentation and synthetic document content:
[CC BY 4.0](LICENSE-DOCS). See [attribution and adaptation notes](NOTICE.md).

"""Offline deterministic Zava seed bundle. No network, credentials or cloud SDKs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "data" / "zava-enterprise"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ROLES = [
    ("avery-chen", "Avery Chen", "Commercial Director"),
    ("morgan-patel", "Morgan Patel", "Finance Controller"),
    ("jordan-okafor", "Jordan Okafor", "Operations Lead"),
    ("riley-santos", "Riley Santos", "Procurement Lead"),
    ("casey-nguyen", "Casey Nguyen", "Customer Success Lead"),
    ("taylor-reed", "Taylor Reed", "Service Manager"),
    ("devon-malik", "Devon Malik", "Data Steward"),
    ("quinn-garcia", "Quinn Garcia", "Sales Operations Lead"),
]
TOPICS = [
    ("policy", "Customer acceptance evidence", "DOC-03",
     "Request a dated customer acceptance record before drawing a recognition conclusion.",
     "Sales stage does not substitute for customer acceptance or Finance recognition."),
    ("operations", "Freight exception review", "DOC-04",
     "Request shipment and supplier evidence for the proposed freight investigation.",
     "A correlated batch or supplier relationship does not establish the cause of freight expense."),
    ("commercial", "Customer commitment review", "DOC-05",
     "Check the recorded opportunity stage and currency against the commercial commitment.",
     "Closed Won bookings and recognized revenue remain separate concepts."),
    ("policy", "Current expedite guidance", "DOC-03",
     "Read the full current recognition and expedite policy and record its effective date.",
     "DOC-02 is superseded; this discussion does not authorize an expedite or expenditure."),
    ("operations", "Recovery task ownership", "DOC-04",
     "Read completed, assignee and due-date fields before proposing the next recovery action.",
     "An owner named in a discussion is a proposal, not a recorded assignment."),
    ("commercial", "Executive review readiness", "DOC-01",
     "Prepare a draft review with source versions, scoped filters and unresolved evidence requests.",
     "No customer communication or leadership approval is created by this synthetic review."),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def source_text(path: Path) -> str:
    if path.suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
        return "\n".join("".join(p.itertext()) for p in root.iter(f"{{{W}}}p"))
    if path.suffix == ".eml":
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        body = message.get_body(preferencelist=("plain",))
        if body is None:
            raise ValueError(f"Missing plain email body: {path}")
        return "\n".join(f"{key}: {message.get(key, '')}" for key in
                         ("From", "To", "Date", "Subject")) + "\n\n" + body.get_content()
    return path.read_text(encoding="utf-8")


def create_docx(path: Path, title: str, paragraphs: list[str]) -> None:
    # Node is not required on approved sandbox VMs: emit a small, explicitly styled OPC package.
    body = '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>' + html.escape(title)
    body += "</w:t></w:r></w:p>"
    body += "".join('<w:p><w:r><w:t xml:space="preserve">' + html.escape(p) +
                    "</w:t></w:r></w:p>" for p in paragraphs)
    body += ('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
             '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
             'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '</Types>')
    rel_namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
    rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    parts = {
        "[Content_Types].xml": types,
        "_rels/.rels": f'<Relationships xmlns="{rel_namespace}"><Relationship Id="rId1" Type="{rel_type}/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>',
        "word/_rels/document.xml.rels": f'<Relationships xmlns="{rel_namespace}"><Relationship Id="rId1" Type="{rel_type}/styles" Target="styles.xml"/></Relationships>',
        "word/styles.xml": f'''<w:styles xmlns:w="{W}">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="24"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="240"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="000000"/><w:sz w:val="32"/></w:rPr></w:style>
</w:styles>''',
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, xml in parts.items():
            archive.writestr(zipfile.ZipInfo(name, (2026, 10, 6, 18, 0, 0)), xml.encode("utf-8"))


def validate_config(config: dict) -> None:
    for key in ("createDisabledPeople", "createOutlookDrafts", "createCalendarAppointments"):
        if type(config[key]) is not bool:
            raise ValueError(f"{key} must be a JSON boolean, not a string.")
    for key in ("ontologyAdmitted", "dataAgentAdmitted"):
        if type(config["fabric"][key]) is not bool:
            raise ValueError(f"fabric.{key} must be a JSON boolean.")
    tenant = config["tenantId"]
    if tenant is not None and (not isinstance(tenant, str) or UUID(tenant).int == 0):
        raise ValueError("tenantId must be a nonzero GUID or null.")
    profile = config["environmentLabel"]
    if profile is not None and (not isinstance(profile, str) or not profile.strip()):
        raise ValueError("environmentLabel must be a nonempty string or null.")
    domain = config["tenantDomain"]
    if domain is not None and (not isinstance(domain, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", domain)):
        raise ValueError("tenantDomain must be a lowercase DNS domain or null.")
    endpoint = config["search"]["searchEndpoint"]
    if endpoint is not None:
        uri = urlparse(endpoint)
        if uri.scheme != "https" or not re.fullmatch(r"[a-z0-9-]+\.search\.windows\.net", uri.netloc) or uri.path not in ("", "/") or uri.query or uri.fragment:
            raise ValueError("Search endpoint must be an exact HTTPS Search service origin or null.")


def build(output: Path, config_path: Path) -> dict:
    if output.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Generated bundles/configuration must remain outside the repository.")
    if output.exists():
        raise ValueError("Use a new output directory; existing bundles are never overwritten.")
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if type(config.get("schemaVersion")) is not int or config["schemaVersion"] != 1:
        raise ValueError("Unsupported configuration schema.")
    validate_config(config)
    prefix = config["resourcePrefix"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,29}", prefix):
        raise ValueError("resourcePrefix must be 3-30 lowercase ASCII letters/digits/hyphens.")
    providers = config["providers"]
    if len(set(providers)) != len(providers) or not set(providers) <= {"SharePoint", "Fabric", "Search"}:
        raise ValueError("Invalid or duplicated providers.")
    original = json.loads((CANONICAL / "manifest.json").read_text(encoding="utf-8"))
    for file in original["files"]:
        candidate = (CANONICAL / file["path"]).resolve()
        if not candidate.is_relative_to(CANONICAL.resolve()) or digest(candidate) != file["sha256"]:
            raise ValueError(f"Canonical fixture integrity failure: {file['path']}")
    output.mkdir(parents=True)
    shutil.copytree(CANONICAL, output / "canonical")
    write_json(output / "people.json", [
        {"key": key, "displayName": name, "role": role,
         "localAddress": f"{key}@zava.example", "accountEnabled": False}
        for key, name, role in ROLES])
    records, uploads, drafts, events = [], [], [], []
    canonical_bodies = {}
    for path in sorted((output / "canonical").rglob("*")):
        if path.is_file():
            text = source_text(path)
            canonical_bodies[path.relative_to(output / "canonical").as_posix()] = text
            if path.parent.name == "work":
                uploads.append(path.relative_to(output).as_posix())
                if path.suffix == ".eml":
                    archive = path.with_suffix(".md")
                    archive.write_text("Synthetic unsent email archive\n\n" + text, encoding="utf-8")
                    uploads.append(archive.relative_to(output).as_posix())
    for kind, count in (("document", 100), ("email", 120), ("meeting", 60), ("web", 40)):
        for number in range(1, count + 1):
            domain, topic, authority, request, limitation = TOPICS[(number - 1) % len(TOPICS)]
            person = ROLES[(number - 1) % len(ROLES)]
            region = ("North", "South", "East", "West", "Central")[(number - 1) % 5]
            day = datetime(2026, 9, 1, 9, tzinfo=timezone.utc) + timedelta(days=(number - 1) % 35)
            source_id = f"ZAVA-{kind.upper()}-{number:03d}"
            title = f"{region} {topic.lower()} - {source_id}"
            paragraphs = [
                "SYNTHETIC ZAVA-CONTEXT supporting context. Not an actual customer record or authorized decision.",
                f"Source ID: {source_id}. Version: 1. Recorded: {day.isoformat()}.",
                f"Fictional author: {person[1]}, {person[2]} ({person[0]}@zava.example).",
                f"Review scope: Zava, {region} operating team, September 2026; evidence queue {number:03d}.",
                f"Agenda: {topic}. {request}",
                f"Evidence request {source_id}-E1: preserve the original record, field names, account, period and currency.",
                f"Evidence request {source_id}-E2: compare the current-policy effective date with the business cutoff, 2026-10-06T18:00:00Z.",
                f"Discussion outcome: investigation remains open. {limitation}",
                f"Recommended next step: {person[2]} reviews the evidence queue; this role recommendation is not an assignment.",
                "Approval boundary: draft only. No send, invitation, purchase, task update, account grant or customer commitment.",
                f"Authority reference: {authority}; supporting review notes do not supersede that source.",
            ]
            text = title + "\n\n" + "\n\n".join(paragraphs)
            folder = output / "work" / kind
            folder.mkdir(parents=True, exist_ok=True)
            md = folder / f"{source_id}.md"
            md.write_text(text + "\n", encoding="utf-8")
            row = {"id": source_id, "title": title, "kind": kind, "domain": domain,
                   "authority": authority, "version": "1", "date": day.isoformat(),
                   "text": text, "path": md.relative_to(output).as_posix()}
            records.append(row)
            if kind != "web":
                uploads.append(row["path"])
            if kind == "document":
                doc = md.with_suffix(".docx")
                create_docx(doc, title, paragraphs)
                uploads.append(doc.relative_to(output).as_posix())
            elif kind == "email":
                message = EmailMessage()
                message["From"] = f"{person[1]} <{person[0]}@zava.example>"
                message["To"] = "Review Desk <review@zava.example>"
                message["Subject"] = "[SYNTHETIC, UNSENT] " + title
                message["Date"] = day
                message["Message-ID"] = f"<{source_id.lower()}@zava.example>"
                message.set_content(text)
                md.with_suffix(".eml").write_bytes(message.as_bytes())
                uploads.append(md.with_suffix(".eml").relative_to(output).as_posix())
                drafts.append({"subject": "[SYNTHETIC, UNSENT] " + title,
                               "body": {"contentType": "Text", "content": text},
                               "toRecipients": [], "ccRecipients": [], "bccRecipients": []})
            elif kind == "meeting":
                cues = [
                    f"{person[1]}: {request}",
                    f"{ROLES[(number + 1) % 8][1]}: {limitation}",
                    f"{ROLES[(number + 2) % 8][1]}: Evidence queue {number:03d} remains open; {authority} owns the policy.",
                    f"{person[1]}: No approval, assignment or customer communication was made.",
                ]
                vtt = "WEBVTT\n\nNOTE Synthetic transcript archive; no real Teams meeting occurred.\n\n"
                for index, cue in enumerate(cues):
                    vtt += f"{index + 1}\n00:0{index}:00.000 --> 00:0{index}:45.000\n{cue}\n\n"
                md.with_suffix(".vtt").write_text(vtt, encoding="utf-8")
                md.write_text(text + "\n\nTranscript:\n" + "\n".join(cues) + "\n", encoding="utf-8")
                row["text"] = md.read_text(encoding="utf-8")
                uploads.append(md.with_suffix(".vtt").relative_to(output).as_posix())
                events.append({"subject": "[SYNTHETIC ARCHIVE] " + title,
                               "body": {"contentType": "Text", "content": row["text"]},
                               "start": {"dateTime": day.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"},
                               "end": {"dateTime": (day + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"},
                               "attendees": [], "isReminderOn": False, "showAs": "free",
                               "isOnlineMeeting": False})
            else:
                web = output / "web" / f"{source_id}.html"
                web.parent.mkdir(parents=True, exist_ok=True)
                web.write_text("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
                               "<title>" + html.escape(title) + "</title><body><h1>" +
                               html.escape(title) + "</h1>" + "".join("<p>" + html.escape(p) +
                               "</p>" for p in paragraphs) + "</body></html>", encoding="utf-8")
    write_json(output / "records.json", records)
    write_json(output / "outlook-drafts.json", drafts)
    write_json(output / "calendar-appointments.json", events)
    incidents = [{"number": f"ZAVA-INC-{i:04d}", "short_description": f"Synthetic evidence review {i}: {TOPICS[i % 6][1]}",
                  "description": f"SYNTHETIC ZAVA-CONTEXT. Investigate queue {i}; no proven financial impact or causal attribution.",
                  "state": "1", "priority": str(2 + i % 3), "assigned_to": "", "caller_id": ""}
                 for i in range(1, 41)]
    incident_path = output / "plugins" / "servicenow-incidents.csv"
    incident_path.parent.mkdir(parents=True, exist_ok=True)
    with incident_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(incidents[0]))
        writer.writeheader()
        writer.writerows(incidents)
    write_json(output / "plugins" / "servicenow-incidents.json", incidents)
    knowledge = []
    for domain in ("policy", "operations", "commercial"):
        name = f"{prefix}-{domain}"
        fields = [{"name": "id", "type": "Edm.String", "key": True, "filterable": True},
                  {"name": "title", "type": "Edm.String", "searchable": True},
                  {"name": "content", "type": "Edm.String", "searchable": True},
                  {"name": "sourcePath", "type": "Edm.String", "retrievable": True},
                  {"name": "version", "type": "Edm.String", "filterable": True}]
        base = output / "search" / domain
        write_json(base / "index.json", {"name": name, "fields": fields, "semantic": {
            "defaultConfiguration": "zava", "configurations": [{"name": "zava", "prioritizedFields": {
                "titleField": {"fieldName": "title"}, "prioritizedContentFields": [{"fieldName": "content"}],
                "prioritizedKeywordsFields": []}}]}})
        documents = [{"@search.action": "upload", "id": row["id"], "title": row["title"],
                      "content": row["text"], "sourcePath": row["path"], "version": row["version"]}
                     for row in records if row["domain"] == domain and row["kind"] != "web"]
        authority_ids = {"policy": ("DOC-01", "DOC-03"), "operations": ("DOC-04",),
                         "commercial": ("DOC-05",)}[domain]
        for path, text in canonical_bodies.items():
            if path.startswith("work/") and any(Path(path).name.startswith(a + "-") for a in authority_ids):
                documents.append({"@search.action": "upload", "id": Path(path).stem,
                                  "title": Path(path).stem, "content": text, "sourcePath": "canonical/" + path,
                                  "version": "2" if "DOC-03" in path else "1"})
        write_json(base / "documents.json", {"value": documents})
        write_json(base / "knowledge-source.json", {
            "name": name + "-source", "kind": "searchIndex", "description": "Synthetic Zava - " + domain,
            "searchIndexParameters": {"searchIndexName": name, "semanticConfigurationName": "zava",
                                     "sourceDataFields": [{"name": field} for field in ("sourcePath", "version", "title")],
                                     "searchFields": [{"name": "content"}]}})
        write_json(base / "knowledge-base.json", {
            "name": name + "-kb", "description": "Synthetic Zava - " + domain + "; extractive, no LLM planning",
            "knowledgeSources": [{"name": name + "-source"}]})
        knowledge.append({"name": name, "path": f"search/{domain}", "documents": len(documents)})
    from fabric_artifacts import generate
    fabric = generate(output, CANONICAL)
    write_json(output / "uploads.json", sorted(uploads))
    package_paths = [ROOT / path for path in (
        "README.md", "LICENSE", "LICENSE-DOCS", "NOTICE.md", ".gitignore", ".gitattributes", "docs/enterprise-scenarios.md",
        "docs/operations.md", "infra/zava/README.md", "infra/zava/operator-runbook.md")]
    package_paths += [path for path in CANONICAL.rglob("*") if path.is_file()]
    package_paths += [path for folder in ("docs",)
                      for path in (ROOT / folder).rglob("*") if path.is_file()]
    package_paths += [path for path in Path(__file__).parent.rglob("*") if path.is_file() and
                      path.suffix in (".py", ".ps1", ".psm1") and "__pycache__" not in path.parts]
    package_paths += [Path(__file__).parent / "environment.template.json"]
    with zipfile.ZipFile(output / "Zava-Enterprise-Setup.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(package_paths)):
            name = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, (2026, 10, 6, 18, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    files = [{"path": path.relative_to(output).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size}
             for path in sorted(output.rglob("*")) if path.is_file()]
    manifest = {"schemaVersion": 1, "nativeStatus": "NOT_RUN", "canonicalFiles": len(original["files"]),
                "counts": {"wordDocuments": 105, "unsentEmails": 128, "transcriptArchives": 60,
                           "syntheticWebPages": 40, "people": 8, "semanticModels": len(fabric["models"]),
                           "dataAgentDrafts": len(fabric["agents"]), "knowledgeBases": len(knowledge),
                           "serviceNowIncidents": 40, "sharePointFiles": len(uploads)},
                "fabric": fabric, "search": knowledge, "files": files}
    write_json(output / "manifest.json", manifest)
    write_json(output / "config.json", config)
    blockers = []
    required = ["tenantId", "environmentLabel", "tenantDomain", "costApprovalReference"]
    for key in required:
        if not config.get(key):
            blockers.append("Resolve " + key)
    if "SharePoint" in providers:
        for key in ("siteId", "driveId"):
            if not config["sharePoint"].get(key):
                blockers.append("Resolve sharePoint." + key)
    if "Fabric" in providers:
        for key in ("workspaceId", "capacityId", "ontologyAdmitted", "dataAgentAdmitted"):
            if not config["fabric"].get(key):
                blockers.append("Resolve/admit fabric." + key)
    if "Search" in providers:
        for key in ("searchResourceId", "searchEndpoint"):
            if not config["search"].get(key):
                blockers.append("Resolve search." + key)
        if config["search"]["apiVersion"] != "2026-04-01":
            blockers.append("Only verified Search/Search GA 2026-04-01 is implemented")
    if (config["createOutlookDrafts"] or config["createCalendarAppointments"]) and not config["mailboxObjectId"]:
        blockers.append("Resolve mailboxObjectId")
    actions = [
        {"provider": "SharePoint", "enabled": "SharePoint" in providers,
         "target": config["sharePoint"], "action": "Create isolated library folder; upload exact uploads.json paths",
         "count": len(uploads), "permission": "Approved write access to this site/library only"},
        {"provider": "Fabric", "enabled": "Fabric" in providers, "target": config["fabric"],
         "action": "Create 1 lakehouse, upload 11 CSVs, create/run 1 seed notebook, create 20 semantic models, 3 agent drafts, 1 ontology",
         "permission": "Existing approved capacity/workspace role; no role/capacity/license changes"},
        {"provider": "Search", "enabled": "Search" in providers, "target": config["search"],
         "action": "Create 3 indexes, index listed documents, create 3 knowledge sources and 3 actual knowledge bases; run 3 extractive retrieval probes",
         "permission": "Existing Search Service Contributor and Index Data Contributor/Reader; no grants"},
        {"provider": "Entra", "enabled": config["createDisabledPeople"], "count": 8,
         "action": "Create disabled fictional users without licenses/grants; discard generated initial passwords"},
        {"provider": "Outlook", "enabled": config["createOutlookDrafts"], "count": 120,
         "target": config["mailboxObjectId"], "action": "Create synthetic drafts, zero recipients; never send"},
        {"provider": "Calendar", "enabled": config["createCalendarAppointments"], "count": 60,
         "target": config["mailboxObjectId"], "action": "Create synthetic appointments, zero attendees, no online meeting/reminders"},
    ]
    code = [path for path in Path(__file__).parent.iterdir() if path.suffix in (".py", ".ps1", ".psm1")]
    plan = {"schemaVersion": 1, "status": "DRAFT_UNBOUND" if blockers else "AWAITING_HUMAN_APPROVAL",
            "tenant": config["tenantId"], "sandboxProfile": config["environmentLabel"],
            "configSha256": digest(output / "config.json"), "manifestSha256": digest(output / "manifest.json"),
            "sourceHashes": {path.name: digest(path) for path in sorted(code)}, "blockers": blockers,
            "actions": actions, "cost": "Uses only existing approved capacity/Search service; storage, compute and query usage may incur charges. No cold service provisioning.",
            "fabricResources": [{"type": kind, "displayName": prefix + " - " + item["name"], "path": item["path"]}
                                for kind, items in (("SemanticModel", fabric["models"]), ("DataAgent", fabric["agents"]),
                                                    ("Ontology", [fabric["ontology"]]), ("Notebook", [fabric["notebook"]]))
                                for item in items],
            "lakehouseName": prefix.replace("-", "_") + "_Lakehouse",
            "manualOnly": ["Web HTTPS publication and source access", "Native Teams transcript ingestion",
                           "Data-agent publication/query", "Ontology refresh/traversal",
                           "Optional knowledge-service client connection", "Salesforce/Asana/ServiceNow sandbox import and plugin connection",
                           "Mailbox licenses and Entra grants"],
            "prohibited": ["send", "invite", "grant permissions", "enable accounts", "delete", "change capacity", "create paid services"]}
    write_json(output / "plan.json", plan)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.output.resolve(), args.config.resolve())
    print(json.dumps({"counts": result["counts"], "nativeStatus": result["nativeStatus"]}))

"""Offline Fabric create-item payloads for the immutable ZAVA-CONTEXT canonical pack.

Only the standard library is needed. No authentication, network, deployment, or
source-data writes occur here. ``generate(output, canonical)`` writes under
output/fabric and returns forward-slash locators relative to output.

Apply contract (owned by the caller):
* Parameterize dev/test/prod and obtain approval before any tenant action.
* Provision a schema-enabled lakehouse, stage the ORIGINAL eleven CSVs under
  Files/zava-enterprise/fabric/, render notebook IDs, then run the seed notebook.
* Render __WORKSPACE_ID__ and __LAKEHOUSE_ID__ in decoded definition parts.
* Create the three core models before rendering __MODEL_FINANCE_ID__,
  __MODEL_COMMERCIAL_ID__, __MODEL_OPERATIONS_ID__ in the draft agents.
* Decode/replace/re-encode ALL parts; replacement in the outer JSON is not enough.
* Check native TMDL/Direct Lake, ontology preview, connections and permissions.
  Data Agent source selection, publishing and service integration are manual.

Wire references consulted:
https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/semantic-model-definition
https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/notebook-definition
https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/data-agent-definition
https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/definition/dataSource/1.0.0/schema.json
Ontology: Fabric ontology item-definition contract.
Local checks are not live validation, RLS/CLS/OLS tests, or execution evidence.
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import hashlib
import json
import pathlib
import re
import uuid


WORKSPACE = "__WORKSPACE_ID__"
LAKEHOUSE = "__LAKEHOUSE_ID__"
MODEL_IDS = {
    "Finance": "__MODEL_FINANCE_ID__",
    "Commercial": "__MODEL_COMMERCIAL_ID__",
    "Operations": "__MODEL_OPERATIONS_ID__",
}
ONTOLOGY_NAME = "Zava Ontology"

# Explicit physical schemas. Do not infer types from sparse or empty columns.
# Int64 USD values remain integers (not floating-point currency).
SCHEMAS = {
    "accounts": [("AccountKey", "string"), ("AccountName", "string")],
    "batches": [
        ("BatchKey", "string"), ("AccountKey", "string"), ("PeriodKey", "long"),
        ("Segment", "string"), ("SupplierKey", "string"),
    ],
    "calendar": [("Date", "date"), ("PeriodKey", "long"), ("MonthLabel", "string")],
    "commercial": [
        ("AccountKey", "string"), ("Date", "date"), ("PeriodKey", "long"),
        ("Segment", "string"), ("FirmBookingsUSD", "long"), ("DeferralUSD", "long"),
    ],
    "finance": [
        ("AccountKey", "string"), ("Date", "date"), ("PeriodKey", "long"),
        ("Segment", "string"), ("Scenario", "string"), ("RevenueUSD", "long"),
        ("BaseCOGSUSD", "long"), ("FreightUSD", "long"),
    ],
    "operations": [
        ("AccountKey", "string"), ("Date", "date"), ("PeriodKey", "long"),
        ("Segment", "string"), ("EligibleOrders", "long"), ("OTIFOrders", "long"),
        ("FreightUSD", "long"), ("ExpeditedFreightUSD", "long"),
    ],
    "opportunities": [
        ("OpportunityKey", "string"), ("AccountKey", "string"), ("PeriodKey", "long"),
        ("Customer", "string"), ("Segment", "string"), ("Stage", "string"),
        ("AmountUSD", "long"),
    ],
    "periods": [("PeriodKey", "long"), ("MonthLabel", "string")],
    "recovery_tasks": [
        ("TaskKey", "string"), ("BatchKey", "string"), ("Completed", "boolean"),
        ("AssigneeKey", "string"), ("DueOn", "date"),
    ],
    "segments": [("Segment", "string")],
    "suppliers": [("SupplierKey", "string"), ("SupplierName", "string")],
}
NULLABLE = {("recovery_tasks", "AssigneeKey"), ("recovery_tasks", "DueOn")}
TABLE_FILES = {
    "Account": "accounts", "OrderBatch": "batches", "Calendar": "calendar",
    "Commercial": "commercial", "Finance": "finance", "Operations": "operations",
    "Opportunity": "opportunities", "Period": "periods",
    "RecoveryAction": "recovery_tasks", "Segments": "segments", "Supplier": "suppliers",
}
KEYS = {
    "Account": "AccountKey", "Calendar": "Date", "Segments": "Segment",
    "OrderBatch": "BatchKey", "Opportunity": "OpportunityKey", "Period": "PeriodKey",
    "RecoveryAction": "TaskKey", "Supplier": "SupplierKey",
}
ENTITY_EDGES = [
    ("OrderBatch.AccountKey", "Account.AccountKey"),
    ("OrderBatch.PeriodKey", "Period.PeriodKey"),
    ("OrderBatch.Segment", "Segments.Segment"),
    ("OrderBatch.SupplierKey", "Supplier.SupplierKey"),
    ("RecoveryAction.BatchKey", "OrderBatch.BatchKey"),
    ("RecoveryAction.DueOn", "Calendar.Date"),
    ("Opportunity.AccountKey", "Account.AccountKey"),
    ("Opportunity.PeriodKey", "Period.PeriodKey"),
    ("Opportunity.Segment", "Segments.Segment"),
]
TMDL_TYPES = {"string": "string", "long": "int64", "date": "dateTime", "boolean": "boolean"}
ONTOLOGY_TYPES = {"string": "String", "long": "BigInt", "date": "DateTime", "boolean": "Boolean"}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _part(path: str, value: object) -> dict:
    text = value if isinstance(value, str) else _json(value)
    return {
        "path": path, "payloadType": "InlineBase64",
        "payload": base64.b64encode(text.encode("utf-8")).decode("ascii"),
    }


def _body(name: str, kind: str, parts: list[dict], fmt: str | None = None) -> dict:
    definition = {"parts": parts}
    if fmt is not None:
        definition["format"] = fmt
    return {"displayName": name, "type": kind, "definition": definition}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _quote(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _endpoint(value: str) -> str:
    table, column = value.split(".")
    return f"{_quote(table)}.{_quote(column)}"


def _load(canonical: pathlib.Path) -> tuple[list[dict], dict, dict, dict]:
    """Fully read and locally validate every CSV and all three contracts."""
    contracts = {}
    for name in ("semantic-models", "ontology-intent", "providers"):
        contracts[name] = json.loads(
            (canonical / "contracts" / f"{name}.json").read_text(encoding="utf-8")
        )
    files = sorted((canonical / "fabric").glob("*.csv"))
    if {p.stem for p in files} != set(SCHEMAS):
        raise ValueError("Expected exactly the eleven canonical Fabric CSVs")
    tables, data = [], {}
    for path in files:
        raw = path.read_bytes()
        # utf-8-sig only tolerates a source BOM; source bytes are never rewritten.
        reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
        schema = SCHEMAS[path.stem]
        if reader.fieldnames != [name for name, _ in schema]:
            raise ValueError(f"{path.name}: unexpected columns")
        rows = list(reader)
        for index, row in enumerate(rows, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path.name}:{index}: malformed row")
            for column, typ in schema:
                value = row[column]
                if not value:
                    if (path.stem, column) not in NULLABLE:
                        raise ValueError(f"{path.name}:{index}: missing {column}")
                    continue
                if typ == "long":
                    if not re.fullmatch(r"-?\d+", value) or not -(2**63) <= int(value) < 2**63:
                        raise ValueError(f"{path.name}:{index}: invalid int64 {column}")
                elif typ == "date":
                    if dt.date.fromisoformat(value).isoformat() != value:
                        raise ValueError(f"{path.name}:{index}: non-ISO date")
                elif typ == "boolean" and value not in ("true", "false"):
                    raise ValueError(f"{path.name}:{index}: invalid Boolean")
        if not rows:
            raise ValueError(f"{path.name}: empty canonical table")
        data[path.stem] = rows
        tables.append({
            "name": path.stem,
            "columns": [
                {"name": name, "type": typ, "nullable": (path.stem, name) in NULLABLE}
                for name, typ in schema
            ],
            "rows": len(rows),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "file": f"fabric/{path.name}",
        })
    models = contracts["semantic-models"]["models"]
    if [m["fact_table"] for m in models] != ["Finance", "Commercial", "Operations"]:
        raise ValueError("Expected canonical Finance, Commercial and Operations models")
    for name, key in KEYS.items():
        rows = data[TABLE_FILES[name]]
        if len({row[key] for row in rows}) != len(rows):
            raise ValueError(f"{name}: non-unique key {key}")
    edges = list(ENTITY_EDGES)
    for model in models:
        fact = model["fact_table"]
        if model["file"] != f"fabric/{TABLE_FILES[fact]}.csv":
            raise ValueError(f"{fact}: unsupported canonical source")
        if model["dimensions"] != {
            "Account": "fabric/accounts.csv", "Calendar": "fabric/calendar.csv",
            "Segments": "fabric/segments.csv",
        }:
            raise ValueError(f"{fact}: unsupported dimensions")
        for rel in model["relationships"]:
            if (rel["cardinality"], rel["filter_direction"], rel["active"]) != (
                "many-to-one", "dimension-to-fact", True
            ):
                raise ValueError("Unsupported canonical relationship contract")
            edges.append((rel["from"], rel["to"]))
        grain = ["AccountKey", "Date", "Segment"] + (["Scenario"] if fact == "Finance" else [])
        fact_rows = data[TABLE_FILES[fact]]
        if len({tuple(row[c] for c in grain) for row in fact_rows}) != len(fact_rows):
            raise ValueError(f"{fact}: duplicated canonical grain")
        edges.append((f"{fact}.PeriodKey", "Period.PeriodKey"))
        for row in fact_rows:
            if row["PeriodKey"] != row["Date"][:7].replace("-", ""):
                raise ValueError(f"{fact}: Date/PeriodKey mismatch")
    for left, right in edges:
        lt, lc = left.split(".")
        rt, rc = right.split(".")
        if dict(SCHEMAS[TABLE_FILES[lt]])[lc] != dict(SCHEMAS[TABLE_FILES[rt]])[rc]:
            raise ValueError(f"Incompatible relationship types: {left} -> {right}")
        target = {row[rc] for row in data[TABLE_FILES[rt]]}
        if any(row[lc] and row[lc] not in target for row in data[TABLE_FILES[lt]]):
            raise ValueError(f"Orphan key: {left} -> {right}")
    calendar = data["calendar"]
    dates = [dt.date.fromisoformat(row["Date"]) for row in calendar]
    if dates != [dates[0] + dt.timedelta(days=i) for i in range(len(dates))]:
        raise ValueError("Calendar must be sorted, unique and continuous")
    period_labels = {row["PeriodKey"]: row["MonthLabel"] for row in data["periods"]}
    for row in calendar:
        if (
            row["PeriodKey"] != row["Date"][:7].replace("-", "")
            or period_labels.get(row["PeriodKey"]) != row["MonthLabel"]
            or row["MonthLabel"] != row["Date"][:7]
        ):
            raise ValueError("Calendar period or label mismatch")
    if {row["Scenario"] for row in data["finance"]} != {"Actual", "Budget"}:
        raise ValueError("Finance requires canonical Actual/Budget scenarios")
    providers = contracts["providers"]
    if set(providers["data_agent"]["sources"]) != {model["id"] for model in models}:
        raise ValueError("Provider/model source contract mismatch")
    return tables, data, contracts["ontology-intent"], contracts


def _closure(core: dict, requested: tuple[str, ...]) -> list[dict]:
    """Retain canonical expressions verbatim, including transitive measures."""
    available = {measure["name"]: measure for measure in core["measures"]}
    wanted = set(requested)
    while True:
        previous = set(wanted)
        for name in previous:
            if name not in available:
                raise ValueError(f"Unknown canonical measure {name}")
            wanted.update(
                ref for ref in re.findall(r"\[([^\]]+)\]", available[name]["expression"])
                if ref in available
            )
        if wanted == previous:
            return [measure for measure in core["measures"] if measure["name"] in wanted]


def _count(name: str, expression: str, description: str) -> dict:
    return {"name": name, "expression": expression, "description": description, "format": "#,##0"}


def _model_specs(models: list[dict]) -> list[dict]:
    specs = []
    for core in models:
        specs.append({
            "name": core["proposed_name"], "role": core["fact_table"].upper(),
            "tables": [core["fact_table"], *core["dimensions"]],
            "measures": {core["fact_table"]: core["measures"]},
            "relationships": [(r["from"], r["to"]) for r in core["relationships"]],
            "description": f"Synthetic canonical {core['fact_table']} model; grain {core['grain']}. "
            "No native security or live validation claim.",
        })
    # Five Finance, three Commercial, three Operations, six entity-count views.
    views = [
        ("Finance Revenue by Month", "Finance", ("Recognized Revenue",)),
        ("Finance Margin by Segment", "Finance", ("Gross Margin",)),
        ("Finance Actual Budget Comparison", "Finance", ("Budget Revenue", "Gross Profit Variance")),
        ("Finance Cost Composition", "Finance", ("Base COGS", "Freight")),
        ("Finance Freight Burden", "Finance", ("Recognized Revenue", "Freight")),
        ("Commercial Firm Bookings", "Commercial", ("Firm Bookings",)),
        ("Commercial Period Deferral", "Commercial", ("Period End Deferral",)),
        ("Commercial Bookings Reconciliation", "Commercial", ("Bookings Less Deferral (Lab)",)),
        ("Operations Service Level", "Operations", ("OTIF",)),
        ("Operations Freight Mix", "Operations", ("Operational Freight", "Expedited Freight Subset")),
        ("Operations Order Population", "Operations", ("Eligible Orders", "OTIF Orders")),
    ]
    for label, fact, names in views:
        core = next(model for model in models if model["fact_table"] == fact)
        specs.append({
            "name": f"Zava View - {label}",
            "tables": [fact, *core["dimensions"]],
            "measures": {fact: _closure(core, names)},
            "relationships": [(r["from"], r["to"]) for r in core["relationships"]],
            "description": f"Bounded analytical view: {label}. SAME canonical {fact} data, "
            "not independent corroboration. Preserve account, period, segment and scenario filters. "
            "Period snapshots must not be interpreted as order-level evidence.",
        })
    batch_tables = ["OrderBatch", "Account", "Period", "Segments", "Calendar"]
    recovery_tables = ["RecoveryAction", *batch_tables, "Supplier"]
    opportunity_tables = ["Opportunity", "Account", "Period", "Segments", "Calendar"]
    entity_views = [
        ("Batch Coverage", batch_tables, "OrderBatch", [
            _count("Batch Count", "COUNTROWS('OrderBatch')",
                   "Count canonical batch identities; not eligible-order or causal evidence."),
        ]),
        ("Supplier Batch Coverage", [*batch_tables, "Supplier"], "OrderBatch", [
            _count("Supplied Batch Count", "COUNTROWS('OrderBatch')",
                   "Count batches by linked supplier; supplies is not proof of cause."),
        ]),
        ("Recovery Completion Status", recovery_tables, "RecoveryAction", [
            _count("Recovery Action Count", "COUNTROWS('RecoveryAction')",
                   "Count proposed investigation tasks, not completed remediation benefits."),
            _count("Completed Action Count",
                   "CALCULATE(COUNTROWS('RecoveryAction'), KEEPFILTERS('RecoveryAction'[Completed] = TRUE()))",
                   "Count task status true within the current linked batch population."),
            _count("Incomplete Action Count",
                   "CALCULATE(COUNTROWS('RecoveryAction'), KEEPFILTERS('RecoveryAction'[Completed] = FALSE()))",
                   "Count task status false; incomplete does not establish a root cause."),
        ]),
        ("Recovery Assignment Readiness", recovery_tables, "RecoveryAction", [
            _count("Unassigned Action Count",
                   "COUNTROWS(FILTER('RecoveryAction', ISBLANK('RecoveryAction'[AssigneeKey])))",
                   "Count missing assignee keys; does not assign people or change tasks."),
            _count("Undated Action Count",
                   "COUNTROWS(FILTER('RecoveryAction', ISBLANK('RecoveryAction'[DueOn])))",
                   "Count missing due dates; no invented deadlines."),
        ]),
        ("Opportunity Stage Population", opportunity_tables, "Opportunity", [
            _count("Opportunity Count", "COUNTROWS('Opportunity')",
                   "Count CRM opportunity identities; not recognized revenue or accepted orders."),
            _count("Closed Won Opportunity Count",
                   'CALCULATE(COUNTROWS(\'Opportunity\'), KEEPFILTERS(\'Opportunity\'[Stage] = "Closed Won"))',
                   "Count stage Closed Won, not an order-level acceptance link."),
            _count("Open Pipeline Opportunity Count",
                   'CALCULATE(COUNTROWS(\'Opportunity\'), KEEPFILTERS(\'Opportunity\'[Stage] = "Open Pipeline"))',
                   "Count open opportunities; do not add pipeline amounts to firm bookings."),
        ]),
        ("Customer Opportunity Coverage", opportunity_tables, "Opportunity", [
            _count("Customers with Opportunities", "DISTINCTCOUNT('Opportunity'[Customer])",
                   "Distinct customer labels in the filtered opportunity population; "
                   "non-additive across segments or periods."),
        ]),
    ]
    for label, tables, host, measures in entity_views:
        specs.append({
            "name": f"Zava View - {label}", "tables": tables,
            "measures": {host: measures},
            "relationships": [
                (left, right) for left, right in ENTITY_EDGES
                if left.split(".")[0] in tables and right.split(".")[0] in tables
            ],
            "description": f"Bounded analytical view: {label}. SAME canonical entity tables, "
            "not independent corroboration. Counts/status only; no unsupported additive USD totals. "
            "Use Period for monthly populations; Calendar is a reference date utility "
            "except where explicitly linked to a task DueOn.",
        })
    if len(specs) != 20 or len({spec["name"] for spec in specs}) != 20:
        raise ValueError("Exactly twenty uniquely named model specifications required")
    return specs


def _model(spec: dict) -> dict:
    parts = [
        _part("definition.pbism", {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "5.0", "settings": {"qnaEnabled": False},
        }),
        _part("definition/database.tmdl",
              f"database {_quote(spec['name'])}\n\tcompatibilityLevel: 1702\n\tcompatibilityMode: powerBI\n"),
    ]
    model_text = (
        f"/// {spec['description']}\nmodel Model\n\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tsourceQueryCulture: en-US\n"
        "\tdiscourageImplicitMeasures\n\n"
    )
    model_text += "".join(f"ref table {_quote(table)}\n" for table in spec["tables"])
    model_text += "\nref expression DL_Lakehouse\n"
    model_text += "".join(
        f"ref relationship {_quote(left + ' to ' + right)}\n"
        for left, right in spec["relationships"]
    )
    parts.append(_part("definition/model.tmdl", model_text))
    parts.append(_part("definition/expressions.tmdl",
                       "/// Shared canonical managed OneLake source; render IDs before apply.\n"
                       "expression DL_Lakehouse =\n"
                       "\t\tlet\n"
                       f'\t\t\tSource = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/{WORKSPACE}/{LAKEHOUSE}", [HierarchicalNavigation=true])\n'
                       "\t\tin\n\t\t\tSource\n"))
    relationships = ""
    foreign_keys = set()
    for left, right in spec["relationships"]:
        foreign_keys.add(left)
        relationships += (
            f"/// Canonical single-direction many-to-one link {left} to {right}.\n"
            f"relationship {_quote(left + ' to ' + right)}\n"
            f"\tfromColumn: {_endpoint(left)}\n\ttoColumn: {_endpoint(right)}\n"
            "\tfromCardinality: many\n\ttoCardinality: one\n"
            "\tcrossFilteringBehavior: oneDirection\n\tisActive: true\n\n"
        )
    parts.append(_part("definition/relationships.tmdl", relationships))
    for table in spec["tables"]:
        managed = TABLE_FILES[table]
        text = f"/// {spec['description']} Source dbo.{managed}.\ntable {_quote(table)}\n"
        if table == "Calendar":
            text += "\tdataCategory: Time\n"
        text += "\n"
        for measure in spec["measures"].get(table, []):
            text += (
                f"\t/// {measure['description']}\n"
                f"\tmeasure {_quote(measure['name'])} = {measure['expression']}\n"
                f"\t\tformatString: {measure['format']}\n"
                "\t\tdisplayFolder: Explicit measures\n\n"
            )
        for column, typ in SCHEMAS[managed]:
            text += (
                f"\t/// Canonical {managed}.{column}"
                + (" in integer USD; use explicit measures." if column.endswith("USD") else ".")
                + f"\n\tcolumn {_quote(column)}\n"
                f"\t\tdataType: {TMDL_TYPES[typ]}\n"
                f"\t\tsourceColumn: {column}\n\t\tsummarizeBy: none\n"
            )
            if KEYS.get(table) == column:
                text += "\t\tisKey\n"
            if (
                f"{table}.{column}" in foreign_keys or column.endswith("Key")
                or column.endswith("USD") or column in ("EligibleOrders", "OTIFOrders")
            ):
                text += "\t\tisHidden\n"
            if typ == "long":
                text += "\t\tformatString: " + ("$#,0;($#,0);$0" if column.endswith("USD") else "0") + "\n"
            elif typ == "date":
                text += "\t\tformatString: yyyy-MM-dd\n"
            if table == "Calendar" and column == "MonthLabel":
                text += "\t\tsortByColumn: 'PeriodKey'\n"
            text += "\n"
        text += (
            f"\tpartition {_quote(table)} = entity\n\t\tmode: directLake\n"
            f"\t\tsource\n\t\t\tentityName: {managed}\n\t\t\tschemaName: dbo\n"
            "\t\t\texpressionSource: DL_Lakehouse\n"
        )
        parts.append(_part(f"definition/tables/{table}.tmdl", text))
    return _body(spec["name"], "SemanticModel", parts, "TMDL")


def _ontology(intent: dict) -> tuple[dict, dict]:
    # Stable concept-derived int64 IDs, stored as strings to avoid JS precision loss.
    # Collision detection is scoped across entities, properties AND relationships.
    assigned = set()

    def integer(concept: str) -> str:
        value = str(1 + int.from_bytes(hashlib.sha256(("zava:zava:" + concept).encode()).digest()[:8],
                                       "big") % (2**63 - 1))
        if value in assigned:
            raise ValueError(f"Ontology ID collision for {concept}")
        assigned.add(value)
        return value

    def guid(concept: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "urn:zava:zava:" + concept))

    def source(table: str) -> dict:
        return {
            "sourceType": "LakehouseTable", "workspaceId": WORKSPACE,
            "itemId": LAKEHOUSE, "sourceTableName": table, "sourceSchema": "dbo",
        }

    if len(intent["entities"]) != 6 or len(intent["relationships"]) != 5:
        raise ValueError("Expected six canonical entities and five relationships")
    ids = {"ontologyName": ONTOLOGY_NAME, "entityTypes": {}, "relationshipTypes": {}, "bindings": {}}
    parts = [
        _part("definition.json", "{}"),
        _part(".platform", {"metadata": {"type": "Ontology", "displayName": ONTOLOGY_NAME}}),
    ]
    entities = {entity["name"]: entity for entity in intent["entities"]}
    expected = {"Account", "Period", "OrderBatch", "Supplier", "RecoveryAction", "Opportunity"}
    if set(entities) != expected:
        raise ValueError("Unsupported canonical ontology entities")
    for name, entity in entities.items():
        table = TABLE_FILES[name]
        if entity["source"] != f"fabric/{table}.csv" or entity["key"] != KEYS[name]:
            raise ValueError(f"{name}: ontology source/key mismatch")
        et_id = integer("entity:" + name)
        properties = {column: integer(f"property:{name}:{column}") for column, _ in SCHEMAS[table]}
        ids["entityTypes"][name] = {"id": et_id, "properties": properties}
        definition = {
            "id": et_id, "namespace": "usertypes", "name": name, "namespaceType": "Custom",
            "visibility": "Visible", "entityIdParts": [properties[entity["key"]]],
            "displayNamePropertyId": properties.get(name + "Name", properties[entity["key"]]),
            "properties": [
                {"id": properties[column], "name": column, "valueType": ONTOLOGY_TYPES[typ]}
                for column, typ in SCHEMAS[table]
            ],
            "timeseriesProperties": [],
        }
        parts.append(_part(f"EntityTypes/{et_id}/definition.json", definition))
        binding_id = guid("binding:" + name)
        ids["bindings"][name + "_static"] = binding_id
        parts.append(_part(f"EntityTypes/{et_id}/DataBindings/{binding_id}.json", {
            "id": binding_id, "dataBindingConfiguration": {
                "dataBindingType": "NonTimeSeries", "sourceTableProperties": source(table),
                "propertyBindings": [
                    {"sourceColumnName": column, "targetPropertyId": properties[column]}
                    for column, _ in SCHEMAS[table]
                ],
            },
        }))
    for rel in intent["relationships"]:
        left, right = rel["from"], rel["to"]
        if left not in entities or right not in entities or left == right:
            raise ValueError("Unsupported ontology relationship endpoint")
        link = TABLE_FILES[right]  # canonical child contains both FK and its own PK
        left_key, right_key = entities[left]["key"], entities[right]["key"]
        if rel["join_key"] != left_key or not {left_key, right_key} <= dict(SCHEMAS[link]).keys():
            raise ValueError("Canonical child table must contain both relationship keys")
        rel_name = left + "To" + right
        rel_id, context_id = integer("relationship:" + rel_name), guid("context:" + rel_name)
        ids["relationshipTypes"][rel_name] = {"id": rel_id, "meaning": rel["meaning"]}
        ids["bindings"][rel_name + "_context"] = context_id
        parts.append(_part(f"RelationshipTypes/{rel_id}/definition.json", {
            "id": rel_id, "namespace": "usertypes", "namespaceType": "Custom", "name": rel_name,
            "source": {"entityTypeId": ids["entityTypes"][left]["id"]},
            "target": {"entityTypeId": ids["entityTypes"][right]["id"]},
        }))
        parts.append(_part(f"RelationshipTypes/{rel_id}/Contextualizations/{context_id}.json", {
            "id": context_id, "dataBindingTable": source(link),
            "sourceKeyRefBindings": [{
                "sourceColumnName": left_key,
                "targetPropertyId": ids["entityTypes"][left]["properties"][left_key],
            }],
            "targetKeyRefBindings": [{
                "sourceColumnName": right_key,
                "targetPropertyId": ids["entityTypes"][right]["properties"][right_key],
            }],
        }))
    return _body(ONTOLOGY_NAME, "Ontology", parts), ids


def _agents(models: list[dict], providers: dict) -> list[dict]:
    instructions = providers["data_agent"]["instructions"]
    results = []
    for core in models:
        fact = core["fact_table"]
        scope = (
            f"This draft is scoped to {core['proposed_name']} only. "
            "Other models, Microsoft 365 documents, Azure AI Search retrieval, web pages and plugins "
            "are not connected here. Cross-source questions require separately admitted sources. "
            "Analytical views share canonical data and are not independent corroboration. "
            "No access-control or live-execution success claim. "
            "For Actual versus Budget comparison, evaluate each without an incompatible "
            "Scenario slicer; canonical KEEPFILTERS deliberately respects scenario filters. "
            "Use Calendar.MonthLabel/PeriodKey, Account and Segments for matching populations. "
            "Do not infer order-level acceptance, supplier causation, or add expedited freight "
            "on top of operational freight (it is a subset)."
        )
        datasource = {
            "$schema": "1.0.0", "artifactId": MODEL_IDS[fact], "workspaceId": WORKSPACE,
            "displayName": core["proposed_name"], "type": "semantic_model",
            "dataSourceInstructions": instructions + " " + scope,
        }
        # elements is OPTIONAL in the official JSON schema. Native table/measure
        # IDs are unknown; do not invent UUIDs, and do not promise selection works.
        parts = [
            _part("Files/Config/data_agent.json", {"$schema": "2.1.0"}),
            _part("Files/Config/draft/stage_config.json", {
                "$schema": "1.0.0", "aiInstructions": instructions + " " + scope,
            }),
            _part(f"Files/Config/draft/semantic_model-{core['proposed_name']}/datasource.json", datasource),
        ]
        results.append(_body(f"Zava - {fact} Data Agent", "DataAgent", parts, "JSON"))
    return results


def _notebook(tables: list[dict]) -> dict:
    # A single Python code cell gives a preflight barrier for ALL tables before
    # any writes. Pure Python parse checks are possible without importing Spark.
    code = '''import hashlib
import pathlib
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, LongType, DateType, BooleanType

# Set the deployment lane explicitly before running; IDs belong in metadata.
environment = "dev"
if environment not in ("dev", "test", "prod"):
    raise ValueError("Set environment to dev, test or prod")
SPECS = __SPECS__
TYPES = {"string": StringType(), "long": LongType(), "date": DateType(), "boolean": BooleanType()}
pending = []
frames = []
try:
    for spec in SPECS:
        relative = "Files/zava-enterprise/" + spec["file"]
        mounted = pathlib.Path("/lakehouse/default") / relative
        raw = mounted.read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
            raise ValueError("Staged canonical CSV bytes differ: " + relative)
        schema = StructType([StructField(c["name"], TYPES[c["type"]], True) for c in spec["columns"]])
        df = (spark.read.format("csv").option("header", "true")
              .option("mode", "FAILFAST").option("enforceSchema", "false")
              .option("dateFormat", "yyyy-MM-dd").schema(schema).load(relative).cache())
        frames.append(df)
        if df.count() != spec["rows"]:
            raise ValueError("Unexpected row count: " + spec["name"])
        for col in spec["columns"]:
            if not col["nullable"] and df.filter(F.col(col["name"]).isNull()).limit(1).count():
                raise ValueError("Required value is null: " + spec["name"] + "." + col["name"])
        qualified = "dbo." + spec["name"]
        if spark.catalog.tableExists(qualified):
            if spark.catalog.getTable(qualified).tableType != "MANAGED":
                raise ValueError("Existing table must be managed: " + qualified)
            detail = spark.sql("DESCRIBE DETAIL " + qualified).first().asDict()
            if detail["format"] != "delta" or detail["properties"].get("delta.columnMapping.mode", "none") != "none":
                raise ValueError("Existing table is not compatible un-mapped Delta: " + qualified)
            existing = spark.table(qualified)
            actual = [(f.name, f.dataType.simpleString()) for f in existing.schema.fields]
            expected = [(c["name"], TYPES[c["type"]].simpleString()) for c in spec["columns"]]
            if actual != expected:
                raise ValueError("Existing schema is incompatible: " + qualified)
            if existing.exceptAll(df).limit(1).count() or df.exceptAll(existing).limit(1).count():
                raise ValueError("Existing data differs; never overwrite: " + qualified)
        else:
            pending.append((qualified, df))
    # No upstream mutations above. This lab seed never appends or overwrites.
    # Managed Delta saveAsTable WITHOUT a path avoids external-table bindings.
    spark.sql("CREATE SCHEMA IF NOT EXISTS dbo")
    for qualified, df in pending:
        df.write.format("delta").option("delta.columnMapping.mode", "none").mode("errorifexists").saveAsTable(qualified)
    for spec in SPECS:
        if spark.table("dbo." + spec["name"]).count() != spec["rows"]:
            raise ValueError("Post-write count check failed: " + spec["name"])
    print("Synthetic canonical tables seeded or verified; environment=" + environment)
finally:
    for df in frames:
        df.unpersist()
'''
    code = code.replace("__SPECS__", repr(tables))
    content = {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {
            "language_info": {"name": "python"},
            "kernel_info": {"name": "synapse_pyspark"},
            "dependencies": {"lakehouse": {
                "default_lakehouse": LAKEHOUSE,
                "default_lakehouse_workspace_id": WORKSPACE,
                "lakehouses": [{"id": LAKEHOUSE}],
            }},
        },
        "cells": [{
            "id": "seed-canonical", "cell_type": "code",
            "execution_count": None, "outputs": [],
            "metadata": {"language": "python", "language_group": "synapse_pyspark"},
            "source": [line + "\n" for line in code.splitlines()],
        }],
    }
    return _body("Zava Seed Canonical Tables", "Notebook",
                 [_part("notebook-content.ipynb", content)], "ipynb")


def generate(output: pathlib.Path, canonical: pathlib.Path) -> dict:
    """Generate exactly 20 models, 3 draft agents, one ontology and seed notebook.

    Input is the zava-commercial PACK ROOT (contracts/ and fabric/), not fabric/.
    The only filesystem changes are create.json/ids.json/seed-notebook.json
    below output/fabric. No CSVs, manifests, instructor answers or oracles are
    copied/generated. On an unchanged input, every output byte is deterministic.
    Core model inventory rows additionally carry role FINANCE, COMMERCIAL or
    OPERATIONS from the canonical fact contract; additional views have no role.
    ValueError fails closed on incompatible source schemas, keys or contracts.
    """
    output, canonical = pathlib.Path(output).resolve(), pathlib.Path(canonical).resolve()
    fabric = (output / "fabric").resolve()
    if fabric == canonical or canonical in fabric.parents or fabric in canonical.parents:
        raise ValueError("Artifact output must not overlap the canonical pack")
    tables, _data, intent, contracts = _load(canonical)
    models = contracts["semantic-models"]["models"]
    model_specs = _model_specs(models)
    model_bodies = [_model(spec) for spec in model_specs]
    ontology, ids = _ontology(intent)
    agent_bodies = _agents(models, contracts["providers"])
    notebook = _notebook(tables)
    writes = []

    def locator(relative: str, body: dict, role: str | None = None) -> dict:
        writes.append((relative, body))
        item = {"name": body["displayName"], "path": relative}
        if role is not None:
            item["role"] = role
        return item

    result = {
        "models": [
            locator(f"fabric/models/{_slug(body['displayName'])}/create.json", body, spec.get("role"))
            for spec, body in zip(model_specs, model_bodies)
        ],
        "agents": [
            locator(f"fabric/agents/{_slug(body['displayName'])}/create.json", body)
            for body in agent_bodies
        ],
        "ontology": locator("fabric/ontology/create.json", ontology),
        "notebook": locator("fabric/seed-notebook.json", notebook),
        "tables": [{key: table[key] for key in ("name", "columns", "rows")} for table in tables],
    }
    writes.append(("fabric/ontology/ids.json", ids))
    # Check ALL paths before creating anything, including symlink/junction cases.
    for relative, _ in writes:
        destination = (output / pathlib.Path(relative)).resolve()
        if output not in destination.parents:
            raise ValueError("Artifact destination escapes output")
        if destination == canonical or canonical in destination.parents:
            raise ValueError("Artifact destination overlaps canonical source")
    for relative, body in writes:
        destination = output / pathlib.Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(_json(body), encoding="utf-8", newline="\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate offline Zava Fabric create payloads")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--canonical", type=pathlib.Path, required=True, help="zava-commercial pack root")
    args = parser.parse_args()
    print(_json(generate(args.output, args.canonical)), end="")


if __name__ == "__main__":
    main()

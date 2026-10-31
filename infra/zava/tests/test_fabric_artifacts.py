"""Standard-library local contract checks, NOT a Fabric/TOM execution test."""

import ast
import base64
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import re
import shutil
import tempfile
import types
import unittest
import uuid
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "infra" / "zava" / "fabric_artifacts.py"
SPEC = importlib.util.spec_from_file_location("zava_fabric_artifacts", MODULE_PATH)
artifacts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artifacts)
CANONICAL = ROOT / "data" / "zava-enterprise"


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file()
    }


def decode(body):
    return {
        part["path"]: base64.b64decode(part["payload"], validate=True).decode("utf-8")
        for part in body["definition"]["parts"]
    }


def rows(name):
    with (CANONICAL / "fabric" / (name + ".csv")).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class FabricArtifactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = snapshot(CANONICAL)
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = pathlib.Path(cls.temp.name) / "output"
        cls.inventory = artifacts.generate(cls.output, CANONICAL)
        cls.contracts = json.loads((CANONICAL / "contracts" / "semantic-models.json").read_text())
        cls.model_bodies = {
            item["name"]: json.loads((cls.output / item["path"]).read_text(encoding="utf-8"))
            for item in cls.inventory["models"]
        }

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exact_inventory_and_complete_create_envelopes(self):
        self.assertEqual(set(self.inventory), {"models", "agents", "ontology", "notebook", "tables"})
        self.assertEqual(len(self.inventory["models"]), 20)
        self.assertEqual(len(self.inventory["agents"]), 3)
        self.assertEqual(len(self.inventory["tables"]), 11)
        self.assertEqual(
            [item["name"] for item in self.inventory["models"][:3]],
            [core["proposed_name"] for core in self.contracts["models"]],
        )
        self.assertEqual(len(self.model_bodies), 20)
        self.assertEqual(len(list(self.output.rglob("*.json"))), 26)
        self.assertFalse(list(self.output.rglob("*.csv")))
        for group, kind in (("models", "SemanticModel"), ("agents", "DataAgent")):
            for item in self.inventory[group]:
                self.assertNotIn("\\", item["path"])
                self.assertFalse(pathlib.PurePosixPath(item["path"]).is_absolute())
                body = json.loads((self.output / item["path"]).read_text())
                self.assertEqual(body["type"], kind)
                self.assertEqual(body["displayName"], item["name"])
                self.assertEqual(set(body), {"type", "displayName", "definition"})
                parts = body["definition"]["parts"]
                self.assertEqual(len({part["path"] for part in parts}), len(parts))
                for part in parts:
                    self.assertEqual(part["payloadType"], "InlineBase64")
                    self.assertNotIn("\\", part["path"])
                    self.assertFalse(base64.b64decode(part["payload"]).startswith(b"\xef\xbb\xbf"))
        for path in self.output.rglob("*.json"):
            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            json.loads(path.read_text(encoding="utf-8"))

    def test_explicit_core_roles_only_on_inventory_rows(self):
        core_rows = self.inventory["models"][:3]
        self.assertEqual([row["role"] for row in core_rows], ["FINANCE", "COMMERCIAL", "OPERATIONS"])
        self.assertEqual(
            {row["role"]: row["name"] for row in core_rows},
            {
                "FINANCE": "Zava Finance",
                "COMMERCIAL": "Zava - Commercial",
                "OPERATIONS": "Zava Operations",
            },
        )
        self.assertTrue(all(set(row) == {"name", "path", "role"} for row in core_rows))
        self.assertTrue(all(set(row) == {"name", "path"} for row in self.inventory["models"][3:]))
        self.assertTrue(all("role" not in body for body in self.model_bodies.values()))
        self.assertTrue(all("role" not in row for row in self.inventory["agents"]))

    def test_canonical_measure_expression_format_and_relationship_completeness(self):
        total = 0
        for core in self.contracts["models"]:
            body = self.model_bodies[core["proposed_name"]]
            parts = decode(body)
            self.assertEqual(body["definition"]["format"], "TMDL")
            self.assertIn("definition.pbism", parts)
            self.assertEqual(json.loads(parts["definition.pbism"])["version"], "5.0")
            self.assertIn("\tcompatibilityLevel: 1702\n", parts["definition/database.tmdl"])
            self.assertTrue(parts["definition/database.tmdl"].startswith("database "))
            fact = parts[f"definition/tables/{core['fact_table']}.tmdl"]
            for measure in core["measures"]:
                self.assertIn(
                    f"\tmeasure {artifacts._quote(measure['name'])} = {measure['expression']}\n",
                    fact,
                )
                self.assertIn(f"\t\tformatString: {measure['format']}\n", fact)
                self.assertIn(f"\t/// {measure['description']}\n", fact)
                total += 1
            relationship = parts["definition/relationships.tmdl"]
            self.assertEqual(relationship.count("\nrelationship "), len(core["relationships"]))
            for rel in core["relationships"]:
                self.assertIn("\tfromColumn: " + artifacts._endpoint(rel["from"]) + "\n", relationship)
                self.assertIn("\ttoColumn: " + artifacts._endpoint(rel["to"]) + "\n", relationship)
                self.assertIn(
                    "ref relationship " + artifacts._quote(rel["from"] + " to " + rel["to"]) + "\n",
                    parts["definition/model.tmdl"],
                )
            self.assertEqual(relationship.count("\tisActive: true"), 3)
            self.assertEqual(relationship.count("\tcrossFilteringBehavior: oneDirection"), 3)
            self.assertNotIn("bothDirections", relationship)
        self.assertEqual(total, 16)
        finance = decode(self.model_bodies["Zava Finance"])["definition/tables/Finance.tmdl"]
        self.assertIn('KEEPFILTERS(Finance[Scenario] = "Actual")', finance)
        self.assertIn('KEEPFILTERS(Finance[Scenario] = "Budget")', finance)
        self.assertIn("IF(NOT ISBLANK([Recognized Revenue]) && NOT ISBLANK([Budget Gross Profit])", finance)

    def test_all_direct_lake_partitions_and_physical_types(self):
        for body in self.model_bodies.values():
            parts = decode(body)
            model = parts["definition/model.tmdl"]
            self.assertIn("\tdiscourageImplicitMeasures\n", model)
            self.assertIn("ref expression DL_Lakehouse\n", model)
            expression = parts["definition/expressions.tmdl"]
            self.assertIn("AzureStorage.DataLake(", expression)
            self.assertIn("__WORKSPACE_ID__/__LAKEHOUSE_ID__", expression)
            self.assertIn("[HierarchicalNavigation=true]", expression)
            self.assertNotIn("Sql.Database", expression)
            for path, text in parts.items():
                if not path.startswith("definition/tables/"):
                    continue
                table = pathlib.PurePosixPath(path).stem
                self.assertIn("ref table " + artifacts._quote(table) + "\n", model)
                self.assertEqual(text.count("\tpartition "), 1)
                self.assertIn(" = entity\n\t\tmode: directLake\n", text)
                self.assertIn("\t\t\tschemaName: dbo\n", text)
                self.assertIn("\t\t\texpressionSource: DL_Lakehouse\n", text)
                physical = artifacts.TABLE_FILES[table]
                self.assertIn("\t\t\tentityName: " + physical + "\n", text)
                for column, typ in artifacts.SCHEMAS[physical]:
                    self.assertIn(
                        f"\tcolumn '{column}'\n\t\tdataType: {artifacts.TMDL_TYPES[typ]}\n",
                        text,
                    )
                    self.assertIn(f"\t\tsourceColumn: {column}\n\t\tsummarizeBy: none\n", text)
                self.assertNotIn("mode: import", text)
            calendar = parts["definition/tables/Calendar.tmdl"]
            self.assertIn("\tdataCategory: Time\n", calendar)
            self.assertIn("\tcolumn 'Date'\n\t\tdataType: dateTime\n", calendar)
            self.assertIn("\t\tisKey\n", calendar)
            self.assertIn("\t\tsortByColumn: 'PeriodKey'\n", calendar)
            self.assertNotIn("LocalDateTable", "\n".join(parts.values()))
        dates = [dt.date.fromisoformat(row["Date"]) for row in rows("calendar")]
        self.assertEqual(len(dates), 61)
        self.assertEqual(dates, [dates[0] + dt.timedelta(days=i) for i in range(61)])

    def test_views_are_bounded_dependency_closed_and_not_independent_evidence(self):
        specs = artifacts._model_specs(self.contracts["models"])
        self.assertEqual(len(specs[3:]), 17)
        core_by_fact = {core["fact_table"]: core for core in self.contracts["models"]}
        for spec in specs[3:]:
            self.assertTrue(spec["name"].startswith("Zava View - "))
            self.assertIn("SAME canonical", spec["description"])
            self.assertIn("not independent corroboration", spec["description"])
            for host, measures in spec["measures"].items():
                names = {measure["name"] for measure in measures}
                for measure in measures:
                    dax = measure["expression"]
                    for table, column in re.findall(r"([A-Za-z]+)\[([^\]]+)\]", dax):
                        self.assertIn(table, spec["tables"])
                        self.assertIn(column, dict(artifacts.SCHEMAS[artifacts.TABLE_FILES[table]]))
                    if host in core_by_fact:
                        available = {m["name"]: m for m in core_by_fact[host]["measures"]}
                        self.assertEqual(measure, available[measure["name"]])
                        for ref in re.findall(r"\[([^\]]+)\]", dax):
                            if ref in available:
                                self.assertIn(ref, names)
                    else:
                        self.assertNotIn("SUM(", dax)
                        self.assertNotIn("AmountUSD", dax)
                        self.assertTrue("COUNTROWS" in dax or "DISTINCTCOUNT" in dax)
            for left, right in spec["relationships"]:
                lt, lc = left.split(".")
                rt, rc = right.split(".")
                self.assertIn(lt, spec["tables"])
                self.assertIn(rt, spec["tables"])
                self.assertEqual(
                    dict(artifacts.SCHEMAS[artifacts.TABLE_FILES[lt]])[lc],
                    dict(artifacts.SCHEMAS[artifacts.TABLE_FILES[rt]])[rc],
                )

    def test_ontology_ids_bindings_types_and_keys(self):
        body = json.loads((self.output / self.inventory["ontology"]["path"]).read_text())
        self.assertEqual(body["type"], "Ontology")
        decoded = decode(body)
        self.assertEqual(decoded["definition.json"], "{}")
        parts = {path: json.loads(text) for path, text in decoded.items()}
        ids = json.loads((self.output / "fabric/ontology/ids.json").read_text())
        self.assertEqual(len(ids["entityTypes"]), 6)
        self.assertEqual(len(ids["relationshipTypes"]), 5)
        all_ids = []
        names_to_types = {}
        entity_by_id = {}
        for name, assigned in ids["entityTypes"].items():
            entity_id = assigned["id"]
            all_ids.append(entity_id)
            entity = parts[f"EntityTypes/{entity_id}/definition.json"]
            entity_by_id[entity_id] = entity
            self.assertEqual(entity["name"], name)
            self.assertEqual(entity["namespace"], "usertypes")
            self.assertEqual(entity["namespaceType"], "Custom")
            self.assertEqual(entity["timeseriesProperties"], [])
            property_by_id = {prop["id"]: prop for prop in entity["properties"]}
            all_ids.extend(property_by_id)
            self.assertIn(entity["displayNamePropertyId"], property_by_id)
            self.assertEqual(entity["entityIdParts"], [assigned["properties"][artifacts.KEYS[name]]])
            for key in entity["entityIdParts"]:
                self.assertIn(property_by_id[key]["valueType"], ("String", "BigInt"))
            binding_id = ids["bindings"][name + "_static"]
            uuid.UUID(binding_id)
            config = parts[f"EntityTypes/{entity_id}/DataBindings/{binding_id}.json"]["dataBindingConfiguration"]
            self.assertEqual(config["dataBindingType"], "NonTimeSeries")
            source = config["sourceTableProperties"]
            self.assertEqual(source["sourceType"], "LakehouseTable")
            self.assertEqual(source["sourceSchema"], "dbo")
            self.assertEqual(source["workspaceId"], "__WORKSPACE_ID__")
            self.assertEqual(source["itemId"], "__LAKEHOUSE_ID__")
            schema = dict(artifacts.SCHEMAS[source["sourceTableName"]])
            self.assertEqual({p["sourceColumnName"] for p in config["propertyBindings"]}, set(schema))
            self.assertEqual({p["targetPropertyId"] for p in config["propertyBindings"]}, set(property_by_id))
            for binding in config["propertyBindings"]:
                prop = property_by_id[binding["targetPropertyId"]]
                self.assertEqual(prop["name"], binding["sourceColumnName"])
                self.assertEqual(prop["valueType"], artifacts.ONTOLOGY_TYPES[schema[prop["name"]]])
                if prop["name"] in names_to_types:
                    self.assertEqual(prop["valueType"], names_to_types[prop["name"]])
                names_to_types[prop["name"]] = prop["valueType"]
        for name, assigned in ids["relationshipTypes"].items():
            relationship_id = assigned["id"]
            all_ids.append(relationship_id)
            relationship = parts[f"RelationshipTypes/{relationship_id}/definition.json"]
            source = entity_by_id[relationship["source"]["entityTypeId"]]
            target = entity_by_id[relationship["target"]["entityTypeId"]]
            self.assertNotEqual(source["id"], target["id"])
            context_id = ids["bindings"][name + "_context"]
            uuid.UUID(context_id)
            context = parts[f"RelationshipTypes/{relationship_id}/Contextualizations/{context_id}.json"]
            table = context["dataBindingTable"]
            self.assertEqual(table["sourceSchema"], "dbo")
            self.assertEqual(table["sourceTableName"], artifacts.TABLE_FILES[target["name"]])
            link_rows = rows(table["sourceTableName"])
            schema = dict(artifacts.SCHEMAS[table["sourceTableName"]])
            for end, entity in (("source", source), ("target", target)):
                bindings = context[end + "KeyRefBindings"]
                self.assertEqual([p["targetPropertyId"] for p in bindings], entity["entityIdParts"])
                column = bindings[0]["sourceColumnName"]
                self.assertIn(column, schema)
                allowed = {row[artifacts.KEYS[entity["name"]]] for row in rows(artifacts.TABLE_FILES[entity["name"]])}
                self.assertTrue(all(row[column] in allowed for row in link_rows))
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertTrue(all(0 < int(identifier) < 2**63 for identifier in all_ids))
        self.assertEqual(len(ids["bindings"]), len(set(ids["bindings"].values())))
        self.assertEqual(len(parts), 24)
        self.assertIn("not proof of cause", json.dumps(ids))
        self.assertNotIn("CONCEPTUAL_INTENT", json.dumps(body))

    def test_data_agent_official_draft_parts_and_placeholders(self):
        provider = json.loads((CANONICAL / "contracts/providers.json").read_text())["data_agent"]
        seen = set()
        for item in self.inventory["agents"]:
            body = json.loads((self.output / item["path"]).read_text())
            self.assertEqual(body["definition"]["format"], "JSON")
            decoded = decode(body)
            self.assertEqual(len(decoded), 3)
            parts = {path: json.loads(text) for path, text in decoded.items()}
            self.assertEqual(parts["Files/Config/data_agent.json"], {"$schema": "2.1.0"})
            stage = parts["Files/Config/draft/stage_config.json"]
            self.assertEqual(stage["$schema"], "1.0.0")
            self.assertIn(provider["instructions"], stage["aiInstructions"])
            datasource_path = next(path for path in parts if path.endswith("/datasource.json"))
            datasource = parts[datasource_path]
            self.assertEqual(datasource["$schema"], "1.0.0")
            self.assertEqual(datasource["type"], "semantic_model")
            self.assertEqual(datasource["workspaceId"], "__WORKSPACE_ID__")
            self.assertIn(datasource["artifactId"], artifacts.MODEL_IDS.values())
            seen.add(datasource["artifactId"])
            fact = next(f for f, placeholder in artifacts.MODEL_IDS.items() if placeholder == datasource["artifactId"])
            display_name = "Zava - Commercial" if fact == "Commercial" else "Zava " + fact
            self.assertEqual(datasource["displayName"], display_name)
            self.assertEqual(datasource_path, f"Files/Config/draft/semantic_model-{display_name}/datasource.json")
            self.assertIn(provider["instructions"], datasource["dataSourceInstructions"])
            self.assertNotIn("elements", datasource)  # optional; no fabricated native IDs
            self.assertNotIn("published", json.dumps(parts))
            self.assertFalse(any("fewshots" in path for path in parts))
        self.assertEqual(seen, set(artifacts.MODEL_IDS.values()))

    def test_notebook_parse_explicit_schema_hashes_and_preflight(self):
        body = json.loads((self.output / self.inventory["notebook"]["path"]).read_text())
        self.assertEqual(body["type"], "Notebook")
        self.assertEqual(body["definition"]["format"], "ipynb")
        notebook = json.loads(decode(body)["notebook-content.ipynb"])
        lakehouse = notebook["metadata"]["dependencies"]["lakehouse"]
        self.assertEqual(lakehouse["default_lakehouse"], "__LAKEHOUSE_ID__")
        self.assertEqual(lakehouse["default_lakehouse_workspace_id"], "__WORKSPACE_ID__")
        self.assertEqual(notebook["nbformat"], 4)
        all_code = ""
        for cell in notebook["cells"]:
            self.assertEqual(cell["cell_type"], "code")
            self.assertIsNone(cell["execution_count"])
            self.assertEqual(cell["outputs"], [])
            self.assertTrue(all(line.endswith("\n") for line in cell["source"]))
            code = "".join(cell["source"])
            ast.parse(code)
            compile(code, "<generated-seed>", "exec")
            all_code += code
        tree = ast.parse(all_code)
        specs = next(
            ast.literal_eval(node.value) for node in tree.body
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SPECS" for t in node.targets)
        )
        self.assertEqual(len(specs), 11)
        for spec in specs:
            self.assertEqual(spec["file"], f"fabric/{spec['name']}.csv")
            self.assertEqual(spec["rows"], len(rows(spec["name"])))
            self.assertEqual(spec["sha256"], self.before["fabric/" + spec["name"] + ".csv"])
            self.assertEqual([(c["name"], c["type"]) for c in spec["columns"]], artifacts.SCHEMAS[spec["name"]])
        recovery = next(spec for spec in specs if spec["name"] == "recovery_tasks")
        self.assertEqual([(c["name"], c["type"]) for c in recovery["columns"]][-3:], [
            ("Completed", "boolean"), ("AssigneeKey", "string"), ("DueOn", "date"),
        ])
        self.assertIn('"Files/zava-enterprise/" + spec["file"]', all_code)
        self.assertIn('qualified = "dbo." + spec["name"]', all_code)
        self.assertIn('StructType([StructField(c["name"], TYPES[c["type"]], True)', all_code)
        self.assertIn('.option("mode", "FAILFAST")', all_code)
        self.assertIn('.option("enforceSchema", "false")', all_code)
        self.assertIn('tableType != "MANAGED"', all_code)
        self.assertIn('existing.exceptAll(df)', all_code)
        self.assertIn('df.exceptAll(existing)', all_code)
        self.assertIn('.mode("errorifexists").saveAsTable(qualified)', all_code)
        self.assertNotIn('.mode("overwrite")', all_code)
        self.assertNotIn('.mode("append")', all_code)
        self.assertLess(all_code.index("Existing schema is incompatible"), all_code.index("df.write.format"))
        self.assertIn('environment not in ("dev", "test", "prod")', all_code)
        self.assertIn("finally:", all_code)
        self.assertIn("df.unpersist()", all_code)

    def test_notebook_runtime_refuses_incompatible_existing_tables(self):
        """Execute generated Python control flow with fake Spark, not a tenant."""
        body = json.loads((self.output / self.inventory["notebook"]["path"]).read_text())
        notebook = json.loads(decode(body)["notebook-content.ipynb"])
        code = "".join(notebook["cells"][0]["source"])
        type_module = types.ModuleType("pyspark.sql.types")
        for name, simple_name in (
            ("StringType", "string"), ("LongType", "bigint"),
            ("DateType", "date"), ("BooleanType", "boolean"),
        ):
            setattr(type_module, name, lambda s=simple_name: types.SimpleNamespace(simpleString=lambda: s))
        type_module.StructType = lambda fields: fields
        type_module.StructField = lambda name, datatype, nullable: types.SimpleNamespace(
            name=name, dataType=datatype, nullable=nullable,
        )
        sql_module = types.ModuleType("pyspark.sql")
        sql_module.functions = mock.MagicMock()
        modules = {
            "pyspark": types.ModuleType("pyspark"),
            "pyspark.sql": sql_module,
            "pyspark.sql.types": type_module,
        }
        for failure, message in (
            ("external", "must be managed"),
            ("schema", "schema is incompatible"),
            ("data", "Existing data differs"),
        ):
            with self.subTest(failure=failure):
                spark = mock.MagicMock()
                df = mock.MagicMock()
                df.cache.return_value = df
                df.count.return_value = 1  # accounts is first in the notebook
                df.filter.return_value.limit.return_value.count.return_value = 0
                reader = spark.read.format.return_value
                reader.option.return_value = reader
                reader.schema.return_value = reader
                reader.load.return_value = df
                spark.catalog.tableExists.return_value = True
                spark.catalog.getTable.return_value.tableType = "EXTERNAL" if failure == "external" else "MANAGED"
                spark.sql.return_value.first.return_value.asDict.return_value = {
                    "format": "delta", "properties": {},
                }
                existing = spark.table.return_value
                existing.schema.fields = [] if failure == "schema" else [
                    type_module.StructField(column, type_module.StringType(), True)
                    for column, _ in artifacts.SCHEMAS["accounts"]
                ]
                existing.exceptAll.return_value.limit.return_value.count.return_value = 1
                with mock.patch.dict("sys.modules", modules), \
                     mock.patch.object(pathlib.Path, "read_bytes",
                                       return_value=(CANONICAL / "fabric/accounts.csv").read_bytes()):
                    with self.assertRaisesRegex(ValueError, message):
                        exec(compile(code, "<mocked-seed>", "exec"), {"spark": spark})
                df.write.format.assert_not_called()
                self.assertFalse(any(
                    call.args and "CREATE" in call.args[0] for call in spark.sql.call_args_list
                ))
                df.unpersist.assert_called_once()

    def test_pack_byte_preservation_determinism_and_no_oracle_assets(self):
        generated_before = snapshot(self.output)
        again = artifacts.generate(self.output, CANONICAL)
        self.assertEqual(self.inventory, again)
        self.assertEqual(generated_before, snapshot(self.output))
        self.assertEqual(self.before, snapshot(CANONICAL))
        output_text = "\n".join(
            "\n".join(decode(body).values())
            for body in self.model_bodies.values()
        )
        for forbidden in ("instructor oracle", "expected_answer", "answer_key", "oracle.json", "RLS success"):
            self.assertNotIn(forbidden.lower(), output_text.lower())
        self.assertFalse(any("oracle" in name.lower() for name in generated_before))

    def test_reject_source_output_overlap_without_writes(self):
        for output in (CANONICAL, CANONICAL / "generated", CANONICAL / "fabric"):
            with self.subTest(output=output):
                with self.assertRaisesRegex(ValueError, "overlap"):
                    artifacts.generate(output, CANONICAL)
        self.assertEqual(self.before, snapshot(CANONICAL))

    def test_fail_closed_bad_headers_orphan_keys_and_calendar_gaps(self):
        mutations = {
            "headers": ("finance.csv", "RevenueUSD", "RevenueTotalUSD"),
            "orphan": ("batches.csv", "SUP-01", "SUP-MISSING"),
            "calendar": ("calendar.csv", "2026-08-02,202608,2026-08\n", ""),
        }
        for label, (filename, old, new) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                fixture = pathlib.Path(directory) / "canonical"
                shutil.copytree(CANONICAL, fixture)
                target = fixture / "fabric" / filename
                target.write_text(target.read_text().replace(old, new), encoding="utf-8")
                output = pathlib.Path(directory) / "output"
                with self.assertRaises(ValueError):
                    artifacts.generate(output, fixture)
                self.assertFalse(output.exists())

    def test_generation_never_uses_network_or_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("socket.socket", side_effect=AssertionError("network prohibited")), \
                 mock.patch("subprocess.Popen", side_effect=AssertionError("process prohibited")):
                generated = artifacts.generate(pathlib.Path(directory), CANONICAL)
            self.assertEqual(len(generated["models"]), 20)


if __name__ == "__main__":
    unittest.main()

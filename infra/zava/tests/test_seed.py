import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seed


class SeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.output = cls.base / "bundle"
        cls.manifest = seed.build(cls.output, Path(seed.__file__).with_name("environment.template.json"))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exact_inventory_and_complete_unique_context(self):
        counts = self.manifest["counts"]
        self.assertEqual((105, 128, 60, 40, 20, 3, 3, 8),
                         tuple(counts[key] for key in ("wordDocuments", "unsentEmails", "transcriptArchives",
                               "syntheticWebPages", "semanticModels", "dataAgentDrafts", "knowledgeBases", "people")))
        records = json.loads((self.output / "records.json").read_text())
        self.assertEqual(320, len(records))
        self.assertEqual(320, len({row["text"] for row in records}))
        self.assertTrue(all(len(row["text"]) > 1000 for row in records))
        self.assertEqual(105, len(list(self.output.rglob("*.docx"))))
        self.assertEqual(128, len(list(self.output.rglob("*.eml"))))
        self.assertEqual(60, len(list(self.output.rglob("*.vtt"))))
        self.assertTrue(all("Transcript:" in row["text"] for row in records if row["kind"] == "meeting"))

    def test_manifest_binds_every_canonical_byte_and_generated_asset(self):
        for file in self.manifest["files"]:
            self.assertEqual(file["sha256"], seed.digest(self.output / file["path"]))
        original = json.loads((seed.CANONICAL / "manifest.json").read_text())
        for file in original["files"]:
            self.assertEqual(file["sha256"], seed.digest(self.output / "canonical" / file["path"]))
        self.assertEqual("NOT_RUN", self.manifest["nativeStatus"])

    def test_docx_packages_are_parseable_and_preserve_full_content(self):
        for path in (self.output / "work" / "document").glob("*.docx"):
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                for name in archive.namelist():
                    ET.fromstring(archive.read(name))
            text = seed.source_text(path)
            source = path.with_suffix(".md").read_text()
            self.assertTrue(all(paragraph in text for paragraph in source.strip().split("\n\n")))

    def test_current_authority_is_full_body_and_superseded_policy_excluded(self):
        indexed = []
        for domain in ("policy", "operations", "commercial"):
            folder = self.output / "search" / domain
            index = json.loads((folder / "index.json").read_text())
            source = json.loads((folder / "knowledge-source.json").read_text())
            kb = json.loads((folder / "knowledge-base.json").read_text())
            documents = json.loads((folder / "documents.json").read_text())["value"]
            self.assertEqual(index["name"], source["searchIndexParameters"]["searchIndexName"])
            self.assertEqual(source["name"], kb["knowledgeSources"][0]["name"])
            self.assertEqual("zava", source["searchIndexParameters"]["semanticConfigurationName"])
            self.assertNotIn("models", kb)
            indexed.extend(documents)
        self.assertTrue(all("DOC-02" not in row["id"] for row in indexed))
        policy = next(row for row in indexed if row["id"].startswith("DOC-03"))
        self.assertEqual(seed.source_text(seed.CANONICAL / "work" / (policy["id"] + ".docx")), policy["content"])
        self.assertEqual("2", policy["version"])

    def test_native_drafts_and_appointments_have_no_recipients_or_invites(self):
        drafts = json.loads((self.output / "outlook-drafts.json").read_text())
        events = json.loads((self.output / "calendar-appointments.json").read_text())
        self.assertEqual(120, len(drafts))
        self.assertEqual(60, len(events))
        self.assertTrue(all(row["toRecipients"] == row["ccRecipients"] == row["bccRecipients"] == [] for row in drafts))
        self.assertTrue(all(row["attendees"] == [] and not row["isOnlineMeeting"] and not row["isReminderOn"] for row in events))

    def test_packaging_excludes_private_configuration_and_includes_entrypoint(self):
        with zipfile.ZipFile(self.output / "Zava-Enterprise-Setup.zip") as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertIn("infra/zava/Setup-Zava.ps1", names)
            self.assertIn("infra/zava/environment.template.json", names)
            self.assertIn("docs/enterprise-scenarios.md", names)
            self.assertFalse(any("private" in name or name.endswith("/config.json") or name.endswith("/plan.json") for name in names))
            self.assertNotIn("data/zava-enterprise/../instructor", names)

    def test_deterministic_generation_and_explicit_unbound_plan(self):
        second = self.base / "second"
        result = seed.build(second, Path(seed.__file__).with_name("environment.template.json"))
        self.assertEqual(self.manifest, result)
        self.assertEqual(seed.digest(self.output / "plan.json"), seed.digest(second / "plan.json"))
        plan = json.loads((second / "plan.json").read_text())
        self.assertEqual("DRAFT_UNBOUND", plan["status"])
        self.assertGreater(len(plan["blockers"]), 0)
        self.assertEqual(25, len(plan["fabricResources"]))
        self.assertTrue(all(not row["enabled"] for row in plan["actions"] if row["provider"] in ("Entra", "Outlook", "Calendar")))

    def test_refuse_existing_output_and_repository_output(self):
        with self.assertRaisesRegex(ValueError, "existing"):
            seed.build(self.output, Path(seed.__file__).with_name("environment.template.json"))
        with self.assertRaisesRegex(ValueError, "outside"):
            seed.build(seed.ROOT / "generated-not-allowed", Path(seed.__file__).with_name("environment.template.json"))

    def test_upload_paths_and_core_role_binding(self):
        uploads = json.loads((self.output / "uploads.json").read_text())
        self.assertEqual(len(set(uploads)), len(uploads))
        self.assertEqual(self.manifest["counts"]["sharePointFiles"], len(uploads))
        self.assertTrue(all((self.output / path).is_file() for path in uploads))
        self.assertFalse(any("config" in path or "private" in path or "instructor" in path for path in uploads))
        roles = {row["role"] for row in self.manifest["fabric"]["models"] if "role" in row}
        self.assertEqual({"FINANCE", "COMMERCIAL", "OPERATIONS"}, roles)

    def test_configuration_flags_cannot_turn_false_strings_into_account_writes(self):
        config = json.loads(Path(seed.__file__).with_name("environment.template.json").read_text())
        config["createDisabledPeople"] = "false"
        with self.assertRaisesRegex(ValueError, "JSON boolean"):
            seed.validate_config(config)
        config["createDisabledPeople"] = False
        config["environmentLabel"] = 42
        with self.assertRaisesRegex(ValueError, "nonempty string"):
            seed.validate_config(config)
        config["environmentLabel"] = "Synthetic enterprise sandbox"
        config["search"]["searchEndpoint"] = "https://evil.example/"
        with self.assertRaisesRegex(ValueError, "exact HTTPS"):
            seed.validate_config(config)


if __name__ == "__main__":
    unittest.main()

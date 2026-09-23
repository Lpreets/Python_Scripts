import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sms_export


FIXTURE = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<smses count="3" backup_set="test" backup_date="0" type="full">
  <sms protocol="0" address="+4711111111" date="1693569484281" type="1"
       body="Hei æøå 😊" contact_name="Ola Nordmann" />
  <sms protocol="0" address="+4711111111" date="1693571039454" type="2"
       body="Linje 1&#10;Linje 2" contact_name="Ola Nordmann" />
  <mms address="+4722222222" date="1693572000123" msg_box="1"
       contact_name="Kari Nordmann">
    <parts>
      <part seq="0" ct="application/smil" text="&lt;smil/&gt;" />
      <part seq="1" ct="text/plain" text="Her er bildet." />
      <part seq="2" ct="image/jpeg" data="BASE64DATA" />
    </parts>
    <addrs><addr address="+4722222222" type="137" /></addrs>
  </mms>
</smses>
"""


class SmsExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "fixture.xml"
        self.source.write_text(FIXTURE, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_preserves_text_direction_and_milliseconds(self):
        messages = sms_export.parse_backup(self.source)

        self.assertEqual(3, len(messages))
        self.assertEqual("received", messages[0].direction)
        self.assertEqual("Hei æøå 😊", messages[0].body)
        self.assertEqual("2023-09-01T13:58:04.281+02:00", messages[0].timestamp)
        self.assertEqual("sent", messages[1].direction)
        self.assertEqual("Linje 1\nLinje 2", messages[1].body)

    def test_mms_keeps_text_and_reports_binary_attachment(self):
        message = sms_export.parse_backup(self.source)[2]

        self.assertEqual("mms", message.kind)
        self.assertEqual("Her er bildet.", message.body)
        self.assertEqual(1, message.attachments_omitted)
        self.assertEqual(("image/jpeg",), message.attachment_types)

    def test_write_exports_one_jsonl_and_markdown_pair_per_contact(self):
        messages = sms_export.parse_backup(self.source)
        output_dir = self.root / "out"
        result = sms_export.write_exports(messages, output_dir, self.source)

        self.assertEqual(2, len(result))
        ola_jsonl = output_dir / "01_ola_nordmann.jsonl"
        ola_markdown = output_dir / "01_ola_nordmann.md"
        self.assertTrue(ola_jsonl.exists())
        self.assertTrue(ola_markdown.exists())

        records = [json.loads(line) for line in ola_jsonl.read_text(encoding="utf-8").splitlines()]
        self.assertEqual("Hei æøå 😊", records[0]["body"])
        markdown = ola_markdown.read_text(encoding="utf-8")
        self.assertIn("OLA NORDMANN → ME", markdown)
        self.assertIn("ME → OLA NORDMANN", markdown)

        kari_markdown = (output_dir / "02_kari_nordmann.md").read_text(encoding="utf-8")
        self.assertIn("[MMS image omitted]", kari_markdown)

    def test_interactive_run_uses_a_separate_directory_for_the_source(self):
        dated_source = self.root / "sms-20230901135804.xml"
        self.source.rename(dated_source)
        with mock.patch.object(sms_export.sys, "argv", ["sms_export.py"]), \
             mock.patch.object(sms_export.sys, "stdin") as stdin, \
             mock.patch("builtins.input", side_effect=[str(self.root), "", ""]):
            stdin.isatty.return_value = True
            sms_export.main()

        output_dir = self.root / "extracted_conversations" / "2023-09-01"
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(str(dated_source), manifest["source"])
        self.assertFalse(manifest["sibling_comparison_performed"])
        self.assertIn("Sibling backups were not compared", (output_dir / "validation_report.md").read_text())

    def test_folder_selection_accepts_a_filename(self):
        dated_source = self.root / "sms-20260923181143.xml"
        self.source.rename(dated_source)
        with mock.patch("builtins.input", return_value=dated_source.name):
            self.assertEqual(dated_source, sms_export.choose_backup(self.root))
        self.assertEqual("2026-09-23", sms_export.backup_date_folder(dated_source))

    def test_sibling_report_counts_differing_records(self):
        source = self.root / "sms-1.xml"
        source.write_text(FIXTURE, encoding="utf-8")
        sibling = self.root / "sms-2.xml"
        sibling.write_text(FIXTURE.replace("Hei æøå 😊", "Different message"), encoding="utf-8")
        output_dir = self.root / "out"
        messages = sms_export.parse_backup(source)
        summaries = sms_export.write_exports(messages, output_dir, source)
        sms_export.write_validation_files(source, output_dir, messages, summaries, compare_siblings=True)

        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        matches = {item["file"]: item["same_records_as_source"] for item in manifest["sibling_backups"]}
        self.assertEqual({"sms-1.xml": True, "sms-2.xml": False}, matches)
        self.assertIn("1 have identical message records", (output_dir / "validation_report.md").read_text())


if __name__ == "__main__":
    unittest.main()

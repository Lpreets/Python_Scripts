import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import filter_conversation


class FilterConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "01_example.jsonl"
        dates = ("2025-12-31", "2026-01-01", "2026-12-31", "2027-01-01")
        with self.source.open("w", encoding="utf-8") as handle:
            for index, day in enumerate(dates, start=1):
                handle.write(json.dumps({
                    "timestamp_epoch_ms": index,
                    "timestamp": f"{day}T12:00:00.000+01:00",
                    "direction": "received",
                    "address": "+4711111111",
                    "contact": "Example",
                    "body": f"Message {index}",
                    "kind": "sms",
                    "attachments_omitted": 0,
                    "attachment_types": [],
                    "source_record_index": index,
                }) + "\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_year_includes_both_endpoints_and_excludes_other_years(self):
        start, end, label = filter_conversation.date_bounds(2026, None, None)
        contact, messages = filter_conversation.filter_jsonl(self.source, start, end)
        self.assertEqual("Example", contact)
        self.assertEqual("2026", label)
        self.assertEqual(["Message 2", "Message 3"], [message.body for message in messages])

    def test_custom_date_range_is_inclusive(self):
        start, end, _ = filter_conversation.date_bounds(None, "2026-12-31", "2027-01-01")
        _, messages = filter_conversation.filter_jsonl(self.source, start, end)
        self.assertEqual(["Message 3", "Message 4"], [message.body for message in messages])

    def test_reversed_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "start date is after end date"):
            filter_conversation.date_bounds(None, "2026-12-31", "2026-01-01")

    def test_interactive_folder_year_and_default_output(self):
        with mock.patch.object(filter_conversation.sys, "argv", ["filter_conversation.py"]), \
             mock.patch.object(filter_conversation.sys, "stdin") as stdin, \
             mock.patch("builtins.input", side_effect=[str(self.root), "1", "2026", ""]):
            stdin.isatty.return_value = True
            filter_conversation.main()

        output = self.root / "filtered" / "01_example_2026.md"
        content = output.read_text(encoding="utf-8")
        self.assertIn("Messages: 2", content)
        self.assertIn("Message 2", content)
        self.assertNotIn("Message 1", content)


if __name__ == "__main__":
    unittest.main()

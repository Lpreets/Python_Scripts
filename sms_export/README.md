# SMS conversation export

Export a SyncTech `sms-*.xml` backup into readable Markdown conversations and
one-record-per-line JSON files. Python 3.10+ and its standard library are the
only requirements. The original XML is read, not changed.

## Interactive use

Run from any directory:

```bash
python /home/lpreet/Python_Scripts/sms_export/sms_export.py
```

Paste the full path to a backup XML file **or its containing folder** at the
first prompt. If you enter a folder, select a numbered backup from the list or
press Enter for the newest filename. Paste the whole path on one line; quotes
around a path are accepted. At the output prompt, enter a **base folder** or
press Enter for `<backup folder>/extracted_conversations`. The script appends
the backup date from its filename, so `sms-20260923181143.xml` goes into
`extracted_conversations/2026-09-23`. For unusual filenames, it uses the
filename stem instead of a date.

For the current phone backups, enter this folder at the first prompt:

```text
/home/lpreet/GoogleDrive/gdrive_lpreet/S25 Ultra SMS Backups/
```

Then press Enter to choose the newest backup and again to accept the default
output base folder. The source XML is never selected from the existing
`extracted_conversations` directory.

## Command-line use

```bash
python /home/lpreet/Python_Scripts/sms_export/sms_export.py \
  "/home/lpreet/GoogleDrive/gdrive_lpreet/S25 Ultra SMS Backups/sms-20260923181143.xml" \
  --output-dir "/home/lpreet/GoogleDrive/gdrive_lpreet/S25 Ultra SMS Backups/extracted_conversations/2026-09-23"
```

`--output-dir` is an exact final directory in command-line use. The date is
appended automatically only in interactive use.

## Give a date-limited conversation to an LLM

Run the filter interactively:

```bash
python /home/lpreet/Python_Scripts/sms_export/filter_conversation.py
```

Enter the path to an exported date folder, such as
`.../extracted_conversations/2026-09-23`. Choose one conversation from its
numbered JSONL list. Enter a year such as `2026`, or press Enter and give a
start and end date in `YYYY-MM-DD` form. The dates are inclusive. Press Enter
at the final prompt to save a Markdown file in that folder's `filtered/`
subdirectory. Give that smaller `.md` file to the LLM.

For command-line use with one conversation:

```bash
python /home/lpreet/Python_Scripts/sms_export/filter_conversation.py \
  "/path/to/01_contact.jsonl" --year 2026

python /home/lpreet/Python_Scripts/sms_export/filter_conversation.py \
  "/path/to/01_contact.jsonl" --from-date 2026-03-01 --to-date 2026-06-30
```

The filter uses each message's Europe/Oslo calendar date recorded by the
exporter. It does not change the full export. If no messages match, it tells
you and creates no file.

Use `--compare-siblings` if you want to compare every `sms-*.xml` in the same
backup folder. This may take a while with many backups. The report states
whether comparison was performed and how many backups have identical records.

## Files and limits

- One `.md` and one `.jsonl` file are produced for each contact name found in
  the selected XML. All conversations in that backup are exported.
- `manifest.json` records the source path, hashes, counts, and generated files.
  `validation_report.md` summarizes the export.
- The script refuses to put an export into a nonempty directory without a
  manifest, or one whose manifest points to another backup. Repeating a run
  against the same backup updates its files.
- MMS text is included, but binary attachments are omitted and marked. RCS or
  other messages absent from the XML cannot be recovered by this script.
- Conversations are grouped by contact name. If two people share the same
  contact name, their records will be grouped together; check the listed phone
  numbers when that matters.

Run the tests with:

```bash
cd /home/lpreet/Python_Scripts/sms_export
python -m unittest -v
```

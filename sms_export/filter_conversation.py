#!/usr/bin/env python3
"""Make a date-limited Markdown conversation from an SMS export JSONL file."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from sms_export import Message, _markdown


def select_jsonl(folder: Path) -> Path:
    files = sorted(folder.glob("*.jsonl"))
    if not files:
        raise ValueError(f"no conversation .jsonl files found in {folder}")
    print("Available conversations:")
    for number, path in enumerate(files, start=1):
        print(f"  {number}. {path.name}")
    choice = input("Choose conversation number or filename: ").strip().strip('"').strip("'")
    if choice.isdecimal():
        number = int(choice)
        if 1 <= number <= len(files):
            return files[number - 1]
        raise ValueError(f"conversation number must be between 1 and {len(files)}")
    selected = folder / choice
    if selected in files:
        return selected
    raise ValueError(f"conversation file not found: {selected}")


def date_bounds(year: int | None, from_date: str | None, to_date: str | None) -> tuple[date, date, str]:
    if year is not None:
        if from_date or to_date:
            raise ValueError("use either a year or a date range")
        if not 1 <= year <= 9999:
            raise ValueError("year must be between 1 and 9999")
        return date(year, 1, 1), date(year, 12, 31), str(year)
    if not from_date and not to_date:
        raise ValueError("enter a year, a start date, or an end date")
    try:
        start = date.fromisoformat(from_date) if from_date else date.min
        end = date.fromisoformat(to_date) if to_date else date.max
    except ValueError as exc:
        raise ValueError("dates must use YYYY-MM-DD and be valid calendar dates") from exc
    if start > end:
        raise ValueError("start date is after end date")
    label = f"{from_date or 'beginning'}_to_{to_date or 'end'}"
    return start, end, label


def filter_jsonl(source: Path, start: date, end: date) -> tuple[str, list[Message]]:
    messages: list[Message] = []
    contact: str | None = None
    with source.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                record["attachment_types"] = tuple(record["attachment_types"])
                message = Message(**record)
                message_date = date.fromisoformat(message.timestamp[:10])
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError(f"invalid export record at line {line_number} in {source}") from exc
            if contact is None:
                contact = message.contact
            elif message.contact != contact:
                raise ValueError(f"multiple contacts found in {source}; select one conversation JSONL")
            if start <= message_date <= end:
                messages.append(message)
    if contact is None:
        raise ValueError(f"no messages found in {source}")
    messages.sort(key=lambda message: (message.timestamp_epoch_ms, message.source_record_index))
    return contact, messages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, help="Conversation JSONL file or export folder")
    parser.add_argument("--year", type=int, help="Select all messages in this calendar year")
    parser.add_argument("--from-date", help="Inclusive start date, YYYY-MM-DD")
    parser.add_argument("--to-date", help="Inclusive end date, YYYY-MM-DD")
    parser.add_argument("--output", type=Path, help="Markdown file to create")
    args = parser.parse_args()

    if args.source is None:
        if not sys.stdin.isatty():
            parser.error("source is required when input is not interactive")
        entered = input("Conversation JSONL file or export folder: ").strip().strip('"').strip("'")
        args.source = Path(entered).expanduser()
    source = args.source.expanduser().resolve()
    if source.is_dir():
        if not sys.stdin.isatty():
            parser.error("an export folder requires interactive conversation selection")
        try:
            source = select_jsonl(source).resolve()
        except ValueError as exc:
            parser.error(str(exc))
    if not source.is_file() or source.suffix.lower() != ".jsonl":
        parser.error(f"conversation JSONL file does not exist: {source}")

    if args.year is None and not args.from_date and not args.to_date:
        if not sys.stdin.isatty():
            parser.error("a year or date range is required when input is not interactive")
        entered_year = input("Year (YYYY), or Enter for a date range: ").strip()
        if entered_year:
            if not entered_year.isdecimal():
                parser.error("year must use YYYY")
            args.year = int(entered_year)
        else:
            args.from_date = input("From date (YYYY-MM-DD, inclusive): ").strip() or None
            args.to_date = input("Through date (YYYY-MM-DD, inclusive): ").strip() or None
    try:
        start, end, label = date_bounds(args.year, args.from_date, args.to_date)
        contact, messages = filter_jsonl(source, start, end)
    except ValueError as exc:
        parser.error(str(exc))
    if not messages:
        print(f"No messages found in the selected date range for {contact}. No file created.")
        return

    suggested = source.parent / "filtered" / f"{source.stem}_{label}.md"
    if args.output is None and sys.stdin.isatty():
        entered = input(f"Output Markdown file [{suggested}]: ").strip().strip('"').strip("'")
        args.output = Path(entered).expanduser() if entered else suggested
    output = (args.output or suggested).expanduser().resolve()
    if output == source:
        parser.error("output cannot be the source JSONL file")
    output.parent.mkdir(parents=True, exist_ok=True)
    header = f"Date range: {start.isoformat()} through {end.isoformat()} (inclusive)\nSource: {source.name}\n\n"
    output.write_text(header + _markdown(contact, messages), encoding="utf-8", newline="\n")
    print(f"Wrote {len(messages)} messages for {contact}: {output}")


if __name__ == "__main__":
    main()

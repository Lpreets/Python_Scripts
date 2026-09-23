#!/usr/bin/env python3
"""Create readable and structured per-contact exports from SyncTech XML."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


OSLO = ZoneInfo("Europe/Oslo")
DIRECTION = {"1": "received", "2": "sent"}


@dataclass(frozen=True)
class Message:
    timestamp_epoch_ms: int
    timestamp: str
    direction: str
    address: str
    contact: str
    body: str
    kind: str
    attachments_omitted: int
    attachment_types: tuple[str, ...]
    source_record_index: int

    def json_record(self) -> dict[str, object]:
        record = asdict(self)
        record["attachment_types"] = list(self.attachment_types)
        return record


def _timestamp(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, OSLO).isoformat(timespec="milliseconds")


def _direction(code: str | None, kind: str, index: int) -> str:
    try:
        return DIRECTION[code or ""]
    except KeyError as exc:
        raise ValueError(f"Unsupported {kind} direction code {code!r} at record {index}") from exc


def _mms_content(element: ET.Element) -> tuple[str, tuple[str, ...]]:
    text_parts: list[tuple[int, str]] = []
    attachment_types: list[str] = []
    parts = element.find("parts")
    if parts is None:
        return "", ()

    for position, part in enumerate(parts):
        content_type = part.attrib.get("ct", "application/octet-stream").lower()
        if content_type == "text/plain":
            sequence = part.attrib.get("seq", str(position))
            try:
                sort_key = int(sequence)
            except ValueError:
                sort_key = position
            text_parts.append((sort_key, part.attrib.get("text", "")))
        elif content_type != "application/smil":
            attachment_types.append(content_type)

    text_parts.sort(key=lambda item: item[0])
    body = "\n".join(text for _, text in text_parts if text)
    return body, tuple(attachment_types)


def parse_backup(source: Path) -> list[Message]:
    messages: list[Message] = []
    declared_count: int | None = None

    root_seen = False
    for event, element in ET.iterparse(source, events=("start", "end")):
        if event == "start" and element.tag == "smses" and declared_count is None:
            root_seen = True
            raw_count = element.attrib.get("count")
            declared_count = int(raw_count) if raw_count is not None else None
            continue
        if event != "end" or element.tag not in {"sms", "mms"}:
            continue

        index = len(messages) + 1
        raw_date = element.attrib.get("date")
        if raw_date is None:
            raise ValueError(f"Missing date at record {index}")
        epoch_ms = int(raw_date)
        contact = element.attrib.get("contact_name") or "Unknown contact"
        address = element.attrib.get("address") or "Unknown address"

        if element.tag == "sms":
            direction = _direction(element.attrib.get("type"), "SMS", index)
            body = element.attrib.get("body", "")
            attachment_types: tuple[str, ...] = ()
        else:
            direction = _direction(element.attrib.get("msg_box"), "MMS", index)
            body, attachment_types = _mms_content(element)

        messages.append(
            Message(
                timestamp_epoch_ms=epoch_ms,
                timestamp=_timestamp(epoch_ms),
                direction=direction,
                address=address,
                contact=contact,
                body=body,
                kind=element.tag,
                attachments_omitted=len(attachment_types),
                attachment_types=attachment_types,
                source_record_index=index,
            )
        )
        element.clear()

    if not root_seen:
        raise ValueError("Expected a SyncTech <smses> XML backup")
    if declared_count is not None and declared_count != len(messages):
        raise ValueError(
            f"XML declares {declared_count} records but parser found {len(messages)}"
        )
    return messages


def slugify(value: str) -> str:
    value = value.translate(str.maketrans({"æ": "ae", "ø": "o", "å": "a", "Æ": "Ae", "Ø": "O", "Å": "A"}))
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "unknown_contact"


def _attachment_marker(message: Message) -> str | None:
    if not message.attachments_omitted:
        return None
    if all(kind.startswith("image/") for kind in message.attachment_types):
        if message.attachments_omitted == 1:
            return "[MMS image omitted]"
        return f"[{message.attachments_omitted} MMS images omitted]"
    types = ", ".join(message.attachment_types)
    return f"[MMS attachment omitted: {types}]"


def _markdown(contact: str, messages: list[Message]) -> str:
    addresses = list(dict.fromkeys(message.address for message in messages))
    phone_label = "Phone" if len(addresses) == 1 else "Phones"
    lines = [
        f"# Conversation: {contact}",
        "",
        f"{phone_label}: {', '.join(addresses)}",
        "Timezone: Europe/Oslo",
        f"Messages: {len(messages)}",
        "",
        "=" * 60,
        "",
    ]
    participant = contact.upper()
    for message in messages:
        display_time = message.timestamp.replace("T", " ", 1)
        speaker = f"{participant} → ME" if message.direction == "received" else f"ME → {participant}"
        content: list[str] = []
        if message.body:
            content.append(message.body)
        marker = _attachment_marker(message)
        if marker:
            content.append(marker)
        if not content:
            content.append(f"[Empty {message.kind.upper()} message]")
        lines.extend(
            [
                display_time,
                speaker,
                "",
                "\n\n".join(content),
                "",
                "-" * 60,
                "",
            ]
        )
    return "\n".join(lines)


def write_exports(
    messages: list[Message], output_dir: Path, source: Path
) -> list[dict[str, object]]:
    del source  # Kept in the API to make export provenance explicit at call sites.
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped: OrderedDict[str, list[Message]] = OrderedDict()
    for message in messages:
        grouped.setdefault(message.contact, []).append(message)

    summaries: list[dict[str, object]] = []
    used_stems: set[str] = set()
    for number, (contact, contact_messages) in enumerate(grouped.items(), start=1):
        contact_messages.sort(key=lambda message: (message.timestamp_epoch_ms, message.source_record_index))
        stem = f"{number:02d}_{slugify(contact)}"
        while stem in used_stems:
            stem += "_2"
        used_stems.add(stem)
        jsonl_path = output_dir / f"{stem}.jsonl"
        markdown_path = output_dir / f"{stem}.md"

        with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
            for message in contact_messages:
                json.dump(message.json_record(), handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")
        markdown_path.write_text(_markdown(contact, contact_messages), encoding="utf-8", newline="\n")

        summaries.append(
            {
                "contact": contact,
                "messages": len(contact_messages),
                "received": sum(message.direction == "received" for message in contact_messages),
                "sent": sum(message.direction == "sent" for message in contact_messages),
                "sms": sum(message.kind == "sms" for message in contact_messages),
                "mms": sum(message.kind == "mms" for message in contact_messages),
                "attachments_omitted": sum(message.attachments_omitted for message in contact_messages),
                "oldest": contact_messages[0].timestamp,
                "newest": contact_messages[-1].timestamp,
                "jsonl": jsonl_path.name,
                "markdown": markdown_path.name,
            }
        )
    return summaries


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def child_records_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    root = ET.parse(path).getroot()
    for child in root:
        digest.update(ET.tostring(child, encoding="utf-8"))
    return digest.hexdigest()


def write_validation_files(
    source: Path,
    output_dir: Path,
    messages: list[Message],
    summaries: list[dict[str, object]],
    compare_siblings: bool = False,
) -> None:
    source_record_hash = child_records_sha256(source) if compare_siblings else None
    sibling_backups = []
    if compare_siblings:
        for candidate in sorted(source.parent.glob("sms-*.xml")):
            candidate_record_hash = child_records_sha256(candidate)
            sibling_backups.append(
                {
                    "file": candidate.name,
                    "sha256": sha256_file(candidate),
                    "child_records_sha256": candidate_record_hash,
                    "same_records_as_source": candidate_record_hash == source_record_hash,
                }
            )

    generated_files = []
    for summary in summaries:
        for key in ("jsonl", "markdown"):
            path = output_dir / str(summary[key])
            generated_files.append({"file": path.name, "sha256": sha256_file(path)})

    manifest = {
        "source": str(source.resolve()),
        "source_sha256": sha256_file(source),
        "source_child_records_sha256": source_record_hash,
        "timezone": "Europe/Oslo",
        "parsed_messages": len(messages),
        "sms": sum(message.kind == "sms" for message in messages),
        "mms": sum(message.kind == "mms" for message in messages),
        "conversations": summaries,
        "sibling_backups": sibling_backups,
        "sibling_comparison_performed": compare_siblings,
        "generated_files": generated_files,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    report = [
        "# Extraction validation",
        "",
        f"Source: `{source.name}`",
        f"Source SHA-256: `{manifest['source_sha256']}`",
        f"Parsed records: {len(messages)} ({manifest['sms']} SMS, {manifest['mms']} MMS)",
        "Timezone: Europe/Oslo",
        "",
        "The XML-declared count was checked when present. "
        + (
            f"Compared {len(sibling_backups)} sibling SMS backups; "
            f"{sum(item['same_records_as_source'] for item in sibling_backups)} have identical message records."
            if compare_siblings
            else "Sibling backups were not compared."
        ),
        "",
        "| Conversation | Records | Received | Sent | Oldest | Newest | Omitted attachments |",
        "|---|---:|---:|---:|---|---|---:|",
    ]
    for item in summaries:
        report.append(
            f"| {item['contact']} | {item['messages']} | {item['received']} | {item['sent']} | "
            f"{item['oldest']} | {item['newest']} | {item['attachments_omitted']} |"
        )
    report.extend(
        [
            "",
            "## Remaining phone-side check",
            "",
            "Compare each conversation's oldest/newest timestamp and approximate message count with "
            "the phone. This export proves internal XML completeness, but only that phone-side comparison "
            "can reveal RCS/chat messages omitted before the XML was created.",
            "",
        ]
    )
    (output_dir / "validation_report.md").write_text("\n".join(report), encoding="utf-8", newline="\n")


def backup_date_folder(source: Path) -> str:
    """Use the date encoded in a SyncTech backup filename."""
    match = re.fullmatch(r"sms-(\d{8})\d{6}\.xml", source.name)
    if not match:
        return source.stem
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date().isoformat()
    except ValueError:
        return source.stem


def choose_backup(folder: Path) -> Path:
    backups = sorted(folder.glob("sms-*.xml"), reverse=True)
    if not backups:
        raise ValueError(f"no sms-*.xml backups found in {folder}")
    print("Available SMS backups (newest filename first):")
    for number, backup in enumerate(backups, start=1):
        print(f"  {number:2d}. {backup.name}")
    choice = input("Choose backup number or filename [1 = newest]: ").strip().strip('"').strip("'")
    if not choice:
        return backups[0]
    if choice.isdecimal():
        number = int(choice)
        if not 1 <= number <= len(backups):
            raise ValueError(f"backup number must be between 1 and {len(backups)}")
        return backups[number - 1]
    selected = folder / choice
    if not selected.is_file() or selected.suffix.lower() != ".xml":
        raise ValueError(f"backup file does not exist: {selected}")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, help="SyncTech sms-*.xml backup")
    parser.add_argument("--output-dir", type=Path, help="Directory for the exported conversations")
    parser.add_argument("--compare-siblings", action="store_true", help="Compare all sms-*.xml files beside the source (can be slow)")
    args = parser.parse_args()

    def entered_path(prompt: str) -> Path:
        return Path(input(prompt).strip().strip('"').strip("'")).expanduser()

    if args.source is None:
        if not sys.stdin.isatty():
            parser.error("source is required when input is not interactive")
        args.source = entered_path("SMS backup XML file or folder: ")
    source = args.source.expanduser().resolve()
    if source.is_dir():
        if not sys.stdin.isatty():
            parser.error("a backup folder requires interactive selection; supply an XML file")
        try:
            source = choose_backup(source).resolve()
        except ValueError as exc:
            parser.error(str(exc))
    if not source.is_file():
        parser.error(f"source file does not exist: {source}")
    if source.suffix.lower() != ".xml":
        parser.error(f"source must be an XML file: {source}")

    if args.output_dir is None:
        if not sys.stdin.isatty():
            parser.error("--output-dir is required when input is not interactive")
        suggested_base = source.parent / "extracted_conversations"
        entered = input(f"Output base folder [{suggested_base}]: ").strip().strip('"').strip("'")
        base = Path(entered).expanduser() if entered else suggested_base
        args.output_dir = base / backup_date_folder(source)
    output_dir = args.output_dir.expanduser().resolve()
    print(f"Selected backup: {source.name}")
    print(f"Output directory: {output_dir}")
    if output_dir.exists() and not output_dir.is_dir():
        parser.error(f"output path is not a directory: {output_dir}")
    manifest_path = output_dir / "manifest.json"
    if output_dir.exists() and any(output_dir.iterdir()) and not manifest_path.exists():
        parser.error(f"output directory is not empty and has no export manifest: {output_dir}")
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous.get("source") != str(source) or previous.get("source_sha256") != sha256_file(source):
            parser.error(f"output directory contains an export from a different backup: {output_dir}")

    messages = parse_backup(source)
    summaries = write_exports(messages, output_dir, source)
    write_validation_files(source, output_dir, messages, summaries, args.compare_siblings)
    print(f"Exported {len(messages)} records into {len(summaries)} conversations: {output_dir}")


if __name__ == "__main__":
    main()

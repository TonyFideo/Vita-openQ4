#!/usr/bin/env python3
"""Extract the last Vita3K launch and create a small, self-contained report.

The compact view is intentionally lossy: expected ENOENT probes and low-level
traffic are counted instead of repeated. The ZIP ALWAYS retains the complete
last launch byte-for-byte, including its final partial line. Originals are never
modified. No network or third-party packages are used.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

BOOT = re.compile(rb"\[\d{2}:\d{2}:\d{2}\.\d+\]\s*\|I\|\s*\[load_app_impl\]: CPU Optimisation state:")
EVENT = re.compile(r"(?m)^\[\d{2}:\d{2}:\d{2}\.\d+\]\s*\|([A-Z])\|\s*\[([^\]]+)\]:")


def split_latest(data: bytes) -> tuple[bytes, int, int]:
    """Search anywhere: some previous crashes end without a newline."""
    launches = list(BOOT.finditer(data))
    offset = launches[-1].start() if launches else 0
    return data[offset:], len(launches), offset


def noise_category(severity: str, function: str, event: str) -> str | None:
    # Never classify an arbitrary error by a word in its text alone.
    if function in {"stat_file", "open_file"} and "Missing file at " in event:
        return "expected_missing_path"
    if function == "io_error_impl" and re.search(r"returned 0x80010002\b", event):
        return "expected_enoent_return"
    if function == "export_sceIoOpen":
        if "FAILED" in event:
            return "expected_open_miss" if "FAILED 0x80010002" in event else None
        return "successful_open_trace" if "Opening file:" in event else None
    if severity in {"T", "D"}:
        return "trace_debug"
    return None


def compact_view(latest: bytes, tail_lines: int = 120) -> tuple[str, dict]:
    if tail_lines < 0:
        raise ValueError("tail_lines must be nonnegative")
    text = latest.decode("utf-8", errors="replace")
    # Keep the tail verbatim in the text view as well as in the lossless ZIP.
    lines = text.splitlines(keepends=True)
    tail_start = sum(len(line) for line in lines[:-tail_lines]) if tail_lines else len(text)
    head, tail = text[:tail_start], text[tail_start:]
    starts = list(EVENT.finditer(head))
    kept = [head[:starts[0].start()]] if starts else [head]
    suppressed: Counter[str] = Counter()
    kept_events = 0
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(head)
        event = head[match.start():end]
        category = noise_category(match[1], match[2], event)
        if category is not None:
            suppressed[category] += 1
        else:
            kept.append(event)
            kept_events += 1
    stats = {"last_launch_bytes": len(latest), "events_retained_before_tail": kept_events,
             "suppressed_events": dict(suppressed), "unfiltered_tail_lines": min(tail_lines, len(lines))}
    header = ("Vita3K compact diagnostic view (NOT the original log)\n"
              "Expected missing-file probes and trace/debug traffic are summarized.\n"
              "Other warnings/errors, engine messages and multiline details are retained.\n"
              "The ZIP contains latest_boot.full.log, byte-for-byte, without filtering.\n"
              + json.dumps(stats, ensure_ascii=True, indent=2) + "\n\n--- TIMELINE ---\n")
    return header + "".join(kept) + "\n--- UNFILTERED FINAL TAIL ---\n" + tail, stats


def build_report(source: Path, destination: Path, attachments: list[Path],
                 tail_lines: int = 120, overwrite: bool = False) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    raw = source.read_bytes()
    latest, launches, offset = split_latest(raw)
    compact, stats = compact_view(latest, tail_lines)
    stats.update(source_name=source.name, source_bytes=len(raw), launches_detected=launches,
                 selected_offset=offset, last_launch_sha256=hashlib.sha256(latest).hexdigest(),
                 source_sha256=hashlib.sha256(raw).hexdigest())
    outputs = [destination / "latest_boot.compact.log", destination / "diagnostics.zip"]
    inputs = {source, *(p.resolve() for p in attachments)}
    if any(path in inputs for path in outputs):
        raise ValueError("Output would overwrite an input file")
    if not overwrite and any(path.exists() for path in outputs):
        raise FileExistsError("Report exists; choose another --output-dir or pass --overwrite")
    # Validate before creating any output files.
    for path in attachments:
        if not path.is_file():
            raise FileNotFoundError(path)
    destination.mkdir(parents=True, exist_ok=True)
    compact_bytes = compact.encode("utf-8")
    stats["compact_bytes"] = len(compact_bytes)
    outputs[0].write_bytes(compact_bytes)
    with zipfile.ZipFile(outputs[1], "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("latest_boot.full.log", latest)
        archive.writestr("latest_boot.compact.log", compact_bytes)
        archive.writestr("summary.json", json.dumps(stats, indent=2) + "\n")
        for index, path in enumerate(attachments, 1):
            archive.write(path, f"attachments/{index:02d}_{path.name}")
    stats["zip_bytes"] = outputs[1].stat().st_size
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="Vita3K log to inspect (never modified)")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--attach", type=Path, action="append", default=[], help="Include e.g. loading.log or errors.log")
    parser.add_argument("--tail-lines", type=int, default=120, help="Unfiltered final lines in compact view")
    parser.add_argument("--overwrite", action="store_true", help="Replace a previously generated report, not inputs")
    args = parser.parse_args(argv)
    if args.tail_lines < 0:
        parser.error("--tail-lines must be nonnegative")
    destination = args.output_dir or args.log.parent / (args.log.stem + "-diagnostics")
    try:
        stats = build_report(args.log, destination, args.attach, args.tail_lines, args.overwrite)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(stats, indent=2))
    print(f"Report: {destination.resolve() / 'diagnostics.zip'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

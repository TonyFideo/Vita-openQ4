#!/usr/bin/env python3
"""Summarize Vita runtime observations without treating missing data as success.

Reads the emulator log or native errors.log as a stream. A matching clear only
qualifies the sampled points in that frame; readback may change GPU timing.
Heap free bytes are not the largest free allocation. Allocation traffic is not
live memory usage. No third-party dependencies or game assets are required.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable

POINTS = ('L', 'C', 'R', 'TL', 'BR')
FIELDS = re.compile(r'([A-Za-z][A-Za-z0-9]*)=([^\s]+)')
LIMIT = 256


def vector(text: str | None, kind=float):
    try:
        values = [kind(x) for x in (text or '').split(',')]
        if len(values) != 4 or not all(math.isfinite(v) for v in values):
            return None
        return values
    except (ValueError, OverflowError):
        return None


def number(fields: dict[str, str], key: str):
    try:
        return int(fields[key], 0)
    except (KeyError, ValueError):
        return None


def analyze(lines: Iterable[str]) -> dict:
    result = {
        'builds': [], 'memory_records': 0, 'failed_reservations': [],
        'failed_reservation_count': 0, 'peak_heap_used': None,
        'minimum_heap_free': None, 'clear_samples': [], 'fatal_count': 0,
        'warnings': [], 'truncated': False,
    }
    samples: dict[tuple[int, int], dict] = {}
    session = 0
    for line_number, line in enumerate(lines, 1):
        if 'build action=' in line and '[VOQ4]' in line:
            session += 1
            if len(result['builds']) < LIMIT:
                result['builds'].append({'line': line_number, **dict(FIELDS.findall(line))})
            else:
                result['truncated'] = True
        if 'FATAL: Out of memory' in line:
            result['fatal_count'] += 1
        if '[VOQ4][memory]' in line:
            result['memory_records'] += 1
            fields = dict(FIELDS.findall(line))
            used, free = number(fields, 'heapUsed'), number(fields, 'heapFree')
            if used is not None:
                previous = result['peak_heap_used']
                result['peak_heap_used'] = used if previous is None else max(previous, used)
            if free is not None:
                previous = result['minimum_heap_free']
                result['minimum_heap_free'] = free if previous is None else min(previous, free)
            if fields.get('failed') == '1':
                result['failed_reservation_count'] += 1
                count, size = number(fields, 'count'), number(fields, 'size')
                requested = None if count is None or size is None else count * size
                record = {'line': line_number, 'session': session,
                          'requested_bytes_mathematical': requested, 'fields': fields}
                if len(result['failed_reservations']) < LIMIT:
                    result['failed_reservations'].append(record)
                else:
                    result['truncated'] = True
        if '[VOQ4][clear-audit]' not in line:
            continue
        fields = dict(FIELDS.findall(line))
        index = number(fields, 'sample')
        if index is None:
            continue
        key = (session, index)
        if key not in samples:
            if len(samples) >= LIMIT:
                result['truncated'] = True
                continue
            samples[key] = {'session': session, 'sample': index, 'line': line_number}
        sample = samples[key]
        phase = fields.get('phase')
        if phase in ('before', 'after', 'present'):
            sample[phase] = {p: vector(fields.get(p), int) for p in POINTS}
        elif phase is None:
            sample['state'] = fields

    for sample in samples.values():
        state = sample.get('state', {})
        expected = vector(state.get('rgba'))
        mask = number(state, 'mask')
        eligible = (number(state, 'drawFbo') == 0 and mask is not None and
                    mask & 0x4000 and state.get('writes') == '1111' and
                    state.get('scissor') == '0' and expected is not None)
        sample['clear_observation'] = 'insufficient_state_or_pixels'
        pixels = sample.get('after', {})
        if eligible and all(pixels.get(p) is not None for p in POINTS):
            target = [round(max(0.0, min(1.0, c)) * 255) for c in expected]
            # Values outside the byte range cannot be valid RGBA8 readbacks.
            valid = all(0 <= c <= 255 for p in POINTS for c in pixels[p])
            if valid:
                mismatches = [p for p in POINTS if any(
                    abs(a - b) > 2 for a, b in zip(pixels[p], target))]
                sample['clear_observation'] = ('differs_from_requested' if mismatches
                    else 'matches_requested_at_sampled_points')
                sample['different_points'] = mismatches
        result['clear_samples'].append(sample)
    if not result['memory_records']:
        result['warnings'].append('No allocation audit records; failing size/caller remain unknown.')
    if not result['clear_samples']:
        result['warnings'].append('No clear audit records; brightness cause remains unmeasured.')
    if result['fatal_count'] and not result['failed_reservation_count']:
        result['warnings'].append('OOM is present without a captured failing allocation; do not infer a size or allocator.')
    result['warnings'].append('Clear observations qualify only sampled points/frames, not visual correctness or unsampled GPU timing.')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--output', type=Path, help='JSON report path; otherwise stdout')
    args = parser.parse_args()
    try:
        with args.log.open(encoding='utf-8-sig', errors='replace') as stream:
            report = analyze(stream)
        text = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
        if args.output:
            args.output.write_text(text, encoding='utf-8')
        else:
            sys.stdout.write(text)
    except OSError as exc:
        parser.exit(2, f'Cannot process runtime audit: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

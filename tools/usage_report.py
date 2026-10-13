"""Summarize server stdout or Cloud Logging JSON/JSONL by UTC day and host.

Usage: python tools/usage_report.py logs.json (or pipe logs to stdin; '-' also reads stdin).
Export the last 14 days first:
    gcloud logging read 'resource.type="cloud_run_revision" AND jsonPayload.event=("draft_analysis" OR "draft_from_notes" OR "render_analysis" OR "read_pdf" OR "correct_bars" OR "limit" OR "download")' --project=sheet-music-analysis --freshness=14d --format=json > logs.json

Accepts the JSON array from gcloud logging read --format=json, JSONL entries,
or raw server JSON lines. No cloud calls are made. Counts are successful calls;
piano is a subset of renders, checks a subset of drafts. Part-writing counts
reports generated, not user acceptance. PDF reads/pages include cached calls;
uncached pages count reader work. Fresh/cached drafts split successful draft calls;
older missing cache flags are unknown. Corrections count successful correct_bars
calls, including calls with no changes.
Exports count generated files; downloads count successful HTTP file requests
(including inline PNGs), not confirmed saves. Browser downloads usually appear
under Other, so their host attribution is not reliable. Views/ranges include
refused requests when logged. Errors count log entries, including optional export failures.
Older missing check/part-writing/export fields are shown
as unknown, never inferred.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

EVENTS = {'draft_analysis', 'draft_from_notes', 'render_analysis', 'read_pdf',
          'correct_bars', 'limit', 'download'}
HOSTS = {'claude': 'Claude', 'chatgpt': 'ChatGPT', 'other': 'Other'}


def read_logs(raw: str) -> list[dict]:
    if not raw.strip():
        return []
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        entries = []
        for number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f'Invalid JSON on line {number}: {error.msg}') from error
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError('Expected JSON objects or an array of log entries')
    return entries


def summarize(entries: list[dict]) -> str:
    rows = defaultdict(Counter)
    views, ranges, exports, downloads = (defaultdict(Counter) for _ in range(4))
    for entry in entries:
        data = entry.get('jsonPayload', entry)
        if 'textPayload' in entry:
            try:
                data = json.loads(entry['textPayload'])
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(data, dict) or data.get('event') not in EVENTS:
            continue
        timestamp = entry.get('timestamp') or data.get('timestamp')
        day = 'unknown'
        if timestamp:
            try:
                moment = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                day = moment.astimezone(timezone.utc).date().isoformat() if moment.tzinfo else 'unknown'
            except (ValueError, TypeError, AttributeError):
                pass
        source = data.get('platform')
        key = (day, HOSTS.get(source, source or 'Unknown'))
        counts = rows[key]
        event = data['event']
        failed = any(field in data for field in ('error', 'problems', 'export_error'))
        failed = failed or (event == 'download' and data.get('status', 200) >= 400)
        if failed:
            counts['errors'] += 1
        if data.get('clarification'):
            counts['questions'] += 1
        if 'view' in data:
            views[key][str(data['view'])] += 1
        if 'measure_range' in data:
            ranges[key][str(data['measure_range'])] += 1
        if event == 'limit':
            counts['limits'] += 1
        elif not failed:
            if event in ('draft_analysis', 'draft_from_notes'):
                counts['drafts'] += 1
                if 'cached' not in data:
                    counts['unknown draft cache'] += 1
                else:
                    counts['cached drafts' if data['cached'] else 'fresh drafts'] += 1
                for field, label in [('mode', 'checks'), ('part_writing', 'part-writing')]:
                    if field not in data:
                        counts[f'unknown {label}'] += 1
                    elif data[field] == ('check' if field == 'mode' else True):
                        counts[label] += 1
            elif event == 'render_analysis':
                counts['renders'] += 1
                counts['piano'] += bool(data.get('piano'))
                if 'exports' not in data:
                    counts['unknown exports'] += 1
            elif event == 'read_pdf':
                if data.get('busy'):
                    counts['busy'] += 1
                else:
                    counts['pdf reads'] += 1
                    counts['pages'] += data.get('pages', 0)
                    counts['cached'] += bool(data.get('cached'))
                    if not data.get('cached'):
                        counts['uncached pages'] += data.get('pages', 0)
            elif event == 'download':
                counts['downloads'] += 1
                downloads[key][data.get('extension', 'unknown')] += 1
            elif event == 'correct_bars':
                counts['corrections'] += 1
        # Publishing files precedes downloading them, including correction previews.
        if not failed:
            for extension in data.get('exports', []):
                counts['exports'] += 1
                exports[key][extension] += 1
            if event == 'read_pdf' and not data.get('busy') and 'exports' not in data:
                counts['unknown exports'] += 1
            if event == 'correct_bars' and data.get('changed') and 'exports' not in data:
                counts['unknown exports'] += 1
    lines = []
    labels = ('drafts', 'fresh drafts', 'cached drafts', 'renders', 'piano', 'corrections',
              'pdf reads', 'pages', 'cached', 'busy', 'uncached pages',
              'checks', 'part-writing', 'exports', 'downloads', 'limits', 'errors', 'questions')
    for key in sorted(rows):
        counts = rows[key]
        line = f'{key[0]}  {key[1]}  ' + '  '.join(f'{label} {counts[label]}' for label in labels)
        for label, values in [('views', views[key]), ('ranges', ranges[key]),
                              ('export formats', exports[key]), ('download formats', downloads[key])]:
            line += f'  {label} [' + ', '.join(f'{name} x{count}' for name, count in sorted(values.items())) + ']'
        line += '  unknown checks {0}  part-writing {1}  exports {2}'.format(
            counts['unknown checks'], counts['unknown part-writing'], counts['unknown exports'])
        line += f"  unknown draft cache {counts['unknown draft cache']}"
        lines.append(line)
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', default='-', help='JSON/JSONL log file, or - for stdin')
    args = parser.parse_args()
    try:
        raw = sys.stdin.read() if args.path == '-' else Path(args.path).read_text()
        report = summarize(read_logs(raw))
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')
    if report:
        print(report)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Validate and print the source-grounded evaluation matrix."""

from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
VALID_DISPOSITIONS = {'ADOPT', 'ADAPT', 'DEFER', 'REJECT'}


def fail(message):
    print('ERROR: %s' % message, file=sys.stderr)
    return 1


def main():
    data = json.loads((ROOT / 'evaluation.json').read_text(encoding='utf-8'))
    items = data.get('items', [])
    if not items:
        return fail('evaluation contains no items')

    errors = []
    seen = set()
    for item in items:
        item_id = item.get('id')
        if not item_id or item_id in seen:
            errors.append('missing or duplicate id: %r' % item_id)
        seen.add(item_id)
        if item.get('disposition') not in VALID_DISPOSITIONS:
            errors.append('%s has invalid disposition' % item_id)
        if not item.get('reason'):
            errors.append('%s has no reason' % item_id)
        evidence = item.get('evidence', [])
        if not evidence:
            errors.append('%s has no evidence' % item_id)
        for reference in evidence:
            path = (ROOT / reference['path']).resolve()
            try:
                text = path.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError) as exc:
                errors.append('%s cannot read %s: %s' % (item_id, path, exc))
                continue
            anchor = reference['contains']
            if anchor not in text:
                errors.append('%s missing anchor %r in %s' % (item_id, anchor, path))

    if errors:
        for error in errors:
            print('ERROR: %s' % error, file=sys.stderr)
        return 1

    print(data['question'])
    print()
    print('%-26s %-7s %s' % ('CAPABILITY', 'RESULT', 'PLAN SECTION'))
    print('%-26s %-7s %s' % ('-' * 26, '-' * 7, '-' * 40))
    for item in items:
        print('%-26s %-7s %s' % (item['id'], item['disposition'], item['plan_section']))

    counts = Counter(item['disposition'] for item in items)
    print()
    print(
        'Summary: %s'
        % ', '.join(
            '%s=%d' % (name, counts.get(name, 0)) for name in ('ADOPT', 'ADAPT', 'DEFER', 'REJECT')
        )
    )
    print('Evidence anchors: verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""
Append-only records: diagnostics, mutations, and proposal fingerprints.

Nothing written here may contain a prompt, a response, tool output, or a
credential; callers hand over already-classified values.
"""

import json
import os
import time

from . import paths

DIAGNOSTICS = 'diagnostics.jsonl'
MUTATIONS = 'mutations.jsonl'
FINGERPRINTS = 'fingerprints.json'


def _append(filename, record):
    path = paths.state_path(filename)
    line = json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n'
    # O_APPEND writes under the size of a pipe buffer are atomic, so concurrent
    # sessions cannot interleave partial lines.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, paths.FILE_MODE)
    try:
        os.write(fd, line.encode('utf-8'))
    finally:
        os.close(fd)
    return path


def diagnostic(stage, error_class, **fields):
    """
    Record that something failed, and in which bounded category.

    Called from every failure path. The exception message is never included;
    callers pass a class from :func:`redact.error_class`.
    """
    record = {'ts': int(time.time()), 'stage': stage, 'error_class': error_class}
    record.update(fields)
    return _append(DIAGNOSTICS, record)


def mutation(record):
    """Record a verified mutation or rollback (spec section 9 step 9)."""
    return _append(MUTATIONS, record)


def read_mutations():
    path = os.path.join(paths.state_root(), MUTATIONS)
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                # A truncated final line from an interrupted write should not
                # make the whole journal unreadable.
                continue
    return records


def find_mutation(mutation_id):
    for record in reversed(read_mutations()):
        if record.get('mutation_id') == mutation_id:
            return record
    return None


def _read_fingerprints():
    path = os.path.join(paths.state_root(), FINGERPRINTS)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def known_fingerprints():
    """Every fingerprint seen before, for reviewer-side deduplication."""
    return sorted(_read_fingerprints())


def fingerprint_status(fingerprint):
    """Return ``"accepted"``, ``"rejected"``, or ``None`` if unseen."""
    entry = _read_fingerprints().get(fingerprint)
    return entry.get('status') if isinstance(entry, dict) else None


def record_fingerprint(fingerprint, status, reason_category=None):
    """
    Remember a proposal outcome so the same lesson is not offered twice.

    Only the fingerprint and a category are kept. A rejection reason is stored
    as a category, never as the user's own words.
    """
    data = _read_fingerprints()
    data[fingerprint] = {'status': status, 'ts': int(time.time())}
    if reason_category:
        data[fingerprint]['reason_category'] = reason_category
    paths.atomic_write(
        paths.state_path(FINGERPRINTS),
        json.dumps(data, sort_keys=True, indent=2) + '\n',
    )
    return data[fingerprint]

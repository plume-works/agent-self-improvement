"""
Expiring JSON records: turns, candidates, proposals, authorizations.

All four state classes in spec section 10.1 share the same shape — a JSON
document with an ``expires_at`` — so they share one implementation. Expiry is
enforced on read as well as by the sweep, because a record that outlived its
lifetime must not be usable just because no sweep has run yet.
"""

import json
import os
import time

from . import paths

TURNS = 'turns'
CANDIDATES = 'candidates'
PROPOSALS = 'proposals'
AUTHORIZATIONS = 'authorizations'


def write_record(kind, record_id, payload, ttl, subdir=None):
    """Store ``payload`` under ``kind`` with an absolute expiry."""
    payload = dict(payload)
    now = int(time.time())
    payload.setdefault('created_at', now)
    payload['expires_at'] = now + ttl
    parts = [kind] + ([subdir] if subdir else []) + ['%s.json' % record_id]
    path = paths.state_path(*parts)
    paths.atomic_write(path, json.dumps(payload, sort_keys=True, indent=2) + '\n')
    return path


def read_record(kind, record_id, subdir=None, allow_expired=False):
    """Load a record, or ``None`` when it is missing, unreadable, or expired."""
    parts = [kind] + ([subdir] if subdir else []) + ['%s.json' % record_id]
    path = os.path.join(paths.state_root(), *parts)
    return read_path(path, allow_expired=allow_expired)


def read_path(path, allow_expired=False):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as handle:
            record = json.load(handle)
    except (ValueError, OSError):
        return None
    if not isinstance(record, dict):
        return None
    if not allow_expired and is_expired(record):
        return None
    return record


def is_expired(record, now=None):
    expires_at = record.get('expires_at')
    if expires_at is None:
        return False
    return (now if now is not None else time.time()) >= expires_at


def delete_record(kind, record_id, subdir=None):
    parts = [kind] + ([subdir] if subdir else []) + ['%s.json' % record_id]
    path = os.path.join(paths.state_root(), *parts)
    try:
        os.unlink(path)
        return True
    except OSError:
        return False


def list_records(kind, subdir=None, allow_expired=False):
    """Every live record under ``kind``, newest first."""
    parts = [kind] + ([subdir] if subdir else [])
    directory = os.path.join(paths.state_root(), *parts)
    if not os.path.isdir(directory):
        return []
    records = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith('.json'):
            continue
        record = read_path(os.path.join(directory, name), allow_expired=allow_expired)
        if record is not None:
            records.append(record)
    records.sort(key=lambda item: item.get('created_at', 0), reverse=True)
    return records


def sweep(now=None):
    """
    Delete every expired record. Returns how many were removed.

    Run from ``SessionEnd`` and before any operation that must not act on stale
    state. Failure to unlink one file must not abandon the rest of the sweep.
    """
    now = now if now is not None else time.time()
    removed = 0
    root = paths.state_root()
    for kind in (TURNS, CANDIDATES, PROPOSALS, AUTHORIZATIONS):
        base = os.path.join(root, kind)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                if not name.endswith('.json'):
                    continue
                path = os.path.join(dirpath, name)
                record = read_path(path, allow_expired=True)
                if record is None or is_expired(record, now):
                    try:
                        os.unlink(path)
                        removed += 1
                    except OSError:
                        continue
    _prune_empty_dirs(os.path.join(root, TURNS))
    return removed


def _prune_empty_dirs(base):
    if not os.path.isdir(base):
        return
    for name in os.listdir(base):
        path = os.path.join(base, name)
        if os.path.isdir(path) and not os.listdir(path):
            try:
                os.rmdir(path)
            except OSError:
                continue

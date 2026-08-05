"""
Bounded event capture (spec sections 5.1, 5.3, 5.4).

Everything recorded here is already normalized and redacted. The turn file is
ephemeral: it holds the current turn's events, is mode 0600, expires within the
hour, and is deleted once review has run.

Capture is deterministic and cheap. No model is consulted, no transcript is
read, and every failure path is silent — a capture bug must not cost the user
their completed work.
"""

import time

from . import config, markers, redact, store

TOOL_FAILURE = 'tool_failure'
TOOL_SUCCESS = 'tool_success'
PROMPT = 'prompt'


FALLBACK_TURN = 'session-turn'


def turn_id(event):
    """
    Identify the turn a hook event belongs to.

    ``prompt_id`` is the documented identifier and requires Claude Code 2.1.196.
    Older versions omit it, so a single rolling turn is used rather than losing
    capture entirely.
    """
    return event.get('prompt_id') or FALLBACK_TURN


def session_id(event):
    return event.get('session_id') or 'unknown-session'


def load_turn(event):
    """
    The turn this event belongs to, or the session's most recent one.

    Callers that were not handed a ``prompt_id`` fall back to the newest turn
    recorded for the session. The manual review path is the case that matters:
    it is invoked from a skill, which knows the session but not the identifier
    Claude Code assigned to the prompt, and without this it would review an
    empty bundle and conclude there was nothing to learn.
    """
    identifier = turn_id(event)
    record = store.read_record(store.TURNS, identifier, subdir=session_id(event))
    if record is not None:
        return record
    if event.get('prompt_id'):
        return {}
    latest = _latest_turn(session_id(event))
    return latest or {}


def _latest_turn(session):
    records = store.list_records(store.TURNS, subdir=session)
    return records[0] if records else None


def _save(event, record):
    store.write_record(
        store.TURNS, turn_id(event), record, ttl=config.TURN_TTL, subdir=session_id(event)
    )
    return record


def discard_turn(event, turn=None):
    """
    Delete the ephemeral turn file (spec section 10).

    ``turn`` is the record :func:`load_turn` returned. Passing it matters when
    that lookup fell back to the session's latest turn, since deleting by the
    event's own identifier would leave the file, and its prompt, on disk.
    """
    identifier = (turn or {}).get('turn_id') or turn_id(event)
    session = (turn or {}).get('session_id') or session_id(event)
    return store.delete_record(store.TURNS, identifier, subdir=session)


def record_prompt(event):
    """
    Start a turn and note which markers its prompt contains.

    The prompt text is stored only when a correction or retention marker fired,
    which is the narrow case section 5.1 permits. Otherwise only the categories
    survive.
    """
    prompt = event.get('prompt')
    found = markers.detect(prompt)
    record = load_turn(event)
    record.update(
        {
            'session_id': session_id(event),
            'turn_id': turn_id(event),
            'cwd': event.get('cwd'),
            'markers': found,
            'started_at': record.get('started_at', int(time.time())),
        }
    )
    if markers.justifies_keeping_prompt(found):
        record['prompt'] = redact.scrub(prompt, limit=1500)
    else:
        record.pop('prompt', None)
    record.setdefault('events', [])
    record['events'] = _append(
        record['events'],
        {
            'kind': PROMPT,
            'ts': int(time.time()),
            'markers': found,
        },
    )
    return _save(event, record)


def record_tool_failure(event):
    """
    Record bounded failure metadata (spec section 5.3).

    No raw tool output, no command arguments, no environment values: a tool
    category, a normalized signature, and an error class.
    """
    if event.get('is_interrupt'):
        # A user interrupt is not evidence of anything about the approach.
        return None

    record = load_turn(event)
    signature = redact.tool_signature(
        event.get('tool_name'), event.get('tool_input'), cwd=event.get('cwd')
    )
    record.setdefault('events', [])
    record['events'] = _append(
        record['events'],
        {
            'kind': TOOL_FAILURE,
            'ts': int(time.time()),
            'tool': event.get('tool_name'),
            'signature': signature,
            'error_class': redact.error_class(event.get('error')),
        },
    )
    return _save(event, record)


def record_tool_success(event):
    """
    Pair a success with a prior compatible failure (spec section 5.4).

    This is what creates a ``failed_then_succeeded`` signal without asking a
    model to infer success from a transcript. A success with no matching prior
    failure is not recorded at all: most successes are unremarkable, and storing
    them would swamp the evidence bundle.
    """
    record = load_turn(event)
    events = record.get('events', [])
    signature = redact.tool_signature(
        event.get('tool_name'), event.get('tool_input'), cwd=event.get('cwd')
    )

    prior = [
        item
        for item in events
        if item.get('kind') == TOOL_FAILURE
        and item.get('signature') == signature
        and not item.get('resolved')
    ]
    if not prior:
        return None

    for item in prior:
        item['resolved'] = True

    record['events'] = _append(
        events,
        {
            'kind': TOOL_SUCCESS,
            'ts': int(time.time()),
            'tool': event.get('tool_name'),
            'signature': signature,
            'after_failure': True,
            'prior_error_class': prior[-1].get('error_class'),
            'failures_before_success': len(prior),
        },
    )
    return _save(event, record)


def _append(events, item):
    """Append within the per-turn cap, keeping the most recent activity."""
    events = list(events)
    events.append(item)
    if len(events) > config.MAX_EVENTS_PER_TURN:
        events = events[-config.MAX_EVENTS_PER_TURN :]
    return events

"""Assembly of the reviewer's input bundle (spec section 7.2).

The reviewer sees only what is listed here. Everything is already redacted by
the time it arrives, and the bundle is capped so a long turn cannot push an
unbounded payload into a model call.
"""

from . import config, redact

MAX_EVENTS_IN_BUNDLE = 40
MAX_OWNERS_IN_BUNDLE = 25


def build(turn, signal, owners=None, last_assistant_message=None, fingerprints=None, focus=None):
    """Compose the bundle for one completed turn.

    ``turn`` is the ephemeral record; ``signal`` is what the deterministic gate
    found. The prompt is included only when the gate detected a correction or a
    retention request, which is the narrow case section 5.1 allows.
    """
    events = (turn or {}).get("events", [])[-MAX_EVENTS_IN_BUNDLE:]
    bundle = {
        "signal": {
            "type": signal.get("type"),
            "detail": signal.get("detail"),
        },
        "events": [_summarize_event(event) for event in events],
        "transitions": transitions(events),
        "last_assistant_message": redact.scrub(last_assistant_message, limit=1500),
        "candidate_owners": (owners or [])[:MAX_OWNERS_IN_BUNDLE],
        "known_fingerprints": sorted(fingerprints or [])[:50],
    }

    if signal.get("include_prompt"):
        bundle["user_prompt"] = redact.scrub((turn or {}).get("prompt"), limit=1500)
    if focus:
        bundle["focus"] = redact.scrub(focus, limit=300)
    return bundle


def _summarize_event(event):
    """Keep only the bounded fields; drop anything a capture hook left behind."""
    summary = {
        "kind": event.get("kind"),
        "signature": event.get("signature"),
        "ts": event.get("ts"),
    }
    for optional in ("error_class", "tool", "markers", "count"):
        if event.get(optional) is not None:
            summary[optional] = event[optional]
    return summary


def transitions(events):
    """Verified failure-to-success transitions, as section 7.2 requires.

    Reported as a signature plus the error class that preceded the success, so
    the reviewer learns that a retry worked without seeing either command.
    """
    found = []
    for event in events or []:
        if event.get("kind") != "tool_success":
            continue
        if not event.get("after_failure"):
            continue
        found.append(
            {
                "signature": event.get("signature"),
                "prior_error_class": event.get("prior_error_class"),
                "failures_before_success": event.get("failures_before_success", 1),
            }
        )
    return found


def friction_counts(events):
    """How many times each signature failed, for the repeated-friction signal."""
    counts = {}
    for event in events:
        if event.get("kind") != "tool_failure":
            continue
        signature = event.get("signature")
        if signature:
            counts[signature] = counts.get(signature, 0) + 1
    return counts


def exceeds_friction_threshold(events, threshold=None):
    threshold = threshold or config.REPEATED_FRICTION_THRESHOLD
    return any(count >= threshold for count in friction_counts(events).values())

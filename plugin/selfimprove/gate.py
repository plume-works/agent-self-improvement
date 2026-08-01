"""The deterministic meaningful-event gate (spec section 6).

Nothing here consults a model. The gate decides whether a turn is worth paying
for a review, and its default answer is no. Suppressors are checked before
signals, because a reason not to review is always decisive.

A signal is permission to reflect, not proof that a durable lesson exists. The
reviewer may and often should still return nothing.
"""

import json
import time

from . import capture, config, evidence, markers, paths, store

COUNTERS = "counters.json"

# Signal types, in the order section 6 lists them.
EXPLICIT_RETENTION = "explicit_retention"
EXPLICIT_CORRECTION = "explicit_correction"
VERIFIED_WORKAROUND = "verified_workaround"
REPEATED_FRICTION = "repeated_friction"
CONFIRMED_TECHNIQUE = "confirmed_technique"
REUSABLE_COMPLETION = "reusable_completion"
MANUAL_FORCE = "manual_force"

# A completed multi-step procedure worth remembering leaves traces in the final
# message. Deliberately conservative: this is the weakest signal in section 6,
# and the one most likely to fire on ordinary work.
COMPLETION_MINIMUM_EVENTS = 6

# The suppressors that bound spending rather than protect correctness. Everything
# else in `suppressed` is a safety guard and is decisive for every caller.
RATE_LIMITS = ("cooldown", "daily_limit_reached")


def _counters_path():
    return paths.state_path(COUNTERS)


def _read_counters():
    record = store.read_path(_counters_path(), allow_expired=True)
    return record if isinstance(record, dict) else {}


def _write_counters(data):
    paths.atomic_write(_counters_path(),
                       json.dumps(data, sort_keys=True, indent=2) + "\n")


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def note_review(now=None):
    """Record that a review ran, for the cooldown and the daily cap."""
    now = now if now is not None else time.time()
    data = _read_counters()
    if data.get("day") != _today():
        data = {"day": _today(), "count": 0}
    data["count"] = data.get("count", 0) + 1
    data["last_review_at"] = int(now)
    _write_counters(data)
    return data


def note_awaiting_presentation(session, candidate_id):
    """Mark a session as holding an unpresented candidate.

    This is the real recursion guard for the asyncRewake path. Waking the
    session produces another turn, and therefore another Stop event;
    ``stop_hook_active`` is documented for the blocking continuation case and is
    not guaranteed here, so the flag is tracked explicitly.
    """
    data = _read_counters()
    data.setdefault("awaiting", {})[session or "unknown"] = candidate_id
    _write_counters(data)


def clear_awaiting_presentation(session):
    data = _read_counters()
    if data.get("awaiting", {}).pop(session or "unknown", None) is not None:
        _write_counters(data)


def _awaiting(session):
    return _read_counters().get("awaiting", {}).get(session or "unknown")


def suppressed(event, now=None):
    """Why this turn must not be reviewed, or ``None``.

    Checked before any signal: a reason not to review is decisive, and this is
    the cheap half of the gate.
    """
    now = now if now is not None else time.time()

    if config.disabled():
        return "disabled"
    if config.in_reviewer_session():
        # Spec section 5.5 step 4: never reflect inside a reviewer's own session.
        return "reviewer_session"
    if event.get("stop_hook_active"):
        return "stop_hook_active"
    if event.get("background_tasks"):
        return "background_work_in_flight"
    if event.get("session_crons"):
        return "scheduled_wakeup_pending"

    candidate = _awaiting(event.get("session_id"))
    if candidate is not None:
        if store.read_record(store.CANDIDATES, candidate) is None:
            # The candidate expired or was presented; the flag is stale.
            clear_awaiting_presentation(event.get("session_id"))
        else:
            return "candidate_awaiting_presentation"

    counters = _read_counters()
    if counters.get("day") == _today() and \
            counters.get("count", 0) >= config.DAILY_REVIEW_LIMIT:
        return "daily_limit_reached"
    last = counters.get("last_review_at")
    if last is not None and now - last < config.COOLDOWN_SECONDS:
        return "cooldown"
    return None


def evaluate(event, turn=None, forced=False, focus=None, now=None):
    """Decide whether to review this turn, and on what grounds.

    Returns a signal mapping when review is warranted, otherwise ``None``. The
    ``include_prompt`` flag on the result is what permits the prompt into the
    evidence bundle.
    """
    reason = suppressed(event, now=now)
    if reason is not None and reason not in RATE_LIMITS:
        # A safety guard is decisive for everyone, including a direct request.
        return None

    # Read before the rate limits are applied, because whether a cooldown may be
    # passed depends on what the user said, and that cannot be known without
    # looking. This is the one file read the gate was always allowed; it now
    # happens on cooldown turns too, which is the price of not dropping a
    # directive that arrives moments after unrelated work.
    turn = turn if turn is not None else capture.load_turn(event)
    events = turn.get("events", [])
    found = turn.get("markers", [])

    if forced:
        # A direct request overrides both rate limits.
        return _signal(MANUAL_FORCE, include_prompt=True, focus=focus)

    if reason == "daily_limit_reached":
        # The real spending ceiling, and nothing automatic passes it.
        return None

    if reason == "cooldown" and not markers.justifies_keeping_prompt(found):
        # Signals 1 and 2 are the user's own words. The cooldown exists so a
        # burst of ordinary work cannot bill a review per turn, and the weaker
        # signals are inferred from that work — but a stated directive is not
        # inferred from anything, and it does not come round again.
        #
        # This is the failure it was written for: `pytest` failed, a retry
        # succeeded, and that verified transition — a true signal about ordinary
        # work — spent the review. The correction that followed ten seconds
        # later, "always use `make test` in this repo", was dropped unreviewed.
        # The cheaper reading of the turn won over the one the user typed.
        return None

    if markers.has_retention(found):
        return _signal(EXPLICIT_RETENTION, include_prompt=True)

    if markers.has_correction(found):
        return _signal(EXPLICIT_CORRECTION, include_prompt=True)

    verified = evidence.transitions(events)
    if verified:
        return _signal(VERIFIED_WORKAROUND,
                       detail="%d verified transition(s)" % len(verified))

    if evidence.exceeds_friction_threshold(events):
        return _signal(REPEATED_FRICTION)

    if markers.has_confirmation(found) and _has_tool_activity(events):
        return _signal(CONFIRMED_TECHNIQUE, include_prompt=True)

    if _looks_like_a_completed_procedure(event, events):
        return _signal(REUSABLE_COMPLETION)

    return None


def _signal(signal_type, include_prompt=False, detail=None, focus=None):
    signal = {"type": signal_type, "include_prompt": include_prompt}
    if detail:
        signal["detail"] = detail
    if focus:
        signal["focus"] = focus
    return signal


def _has_tool_activity(events):
    return any(item.get("kind") in (capture.TOOL_FAILURE, capture.TOOL_SUCCESS)
               for item in events)


def _looks_like_a_completed_procedure(event, events):
    """The weakest signal in section 6, so held to the highest bar.

    Requires both a substantial amount of tool activity and a final message
    that reports a verified outcome. Ordinary task completion is the common
    case and must not trigger a review.
    """
    if len(events) < COMPLETION_MINIMUM_EVENTS:
        return False
    if not _has_tool_activity(events):
        return False
    message = (event.get("last_assistant_message") or "").lower()
    if not message:
        return False
    return ("passing" in message or "all tests pass" in message
            or "verified" in message or "now works" in message)

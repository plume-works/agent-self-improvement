"""The Stop-hook orchestration (spec section 5.5).

Runs in the background under ``asyncRewake``, so the user's response is never
delayed by it. The exit code is the whole interface: 0 means stay silent, 2
means wake the session with the message on stderr.

Every step is allowed to decide nothing happens. Most turns end at the gate,
having cost one file read.
"""

import json
import time
import uuid

from . import (
    capture,
    config,
    evidence,
    gate,
    journal,
    owners,
    paths,
    proposals,
    reviewer,
    schema,
    store,
)

PENDING = "pending.json"


def run(event, forced=False, focus=None):
    """Review one completed turn. Returns a result mapping describing what happened.

    The caller translates this into an exit code. Keeping the decision separate
    from the exit makes the whole path testable without spawning a process.
    """
    turn = capture.load_turn(event)

    signal = gate.evaluate(event, turn=turn, forced=forced, focus=focus)
    if signal is None:
        # Section 3.1: no signal means delete the ephemeral turn data and stay
        # silent. The turn taught nothing; there is no reason to keep it.
        capture.discard_turn(event, turn)
        return {"outcome": "no_signal"}

    gate.note_review()

    bundle = evidence.build(
        turn,
        signal,
        owners=_owner_summaries(event),
        last_assistant_message=event.get("last_assistant_message"),
        fingerprints=_known_fingerprints(),
        focus=signal.get("focus"),
    )

    result = reviewer.review(bundle)
    if result.get("decision") != schema.PROPOSE:
        reason = result.get("discard_reason", "reviewer_discarded")
        # A clean decline used to leave no trace anywhere: the turn was deleted,
        # nothing was journaled, and the only evidence a review had happened at
        # all was the counter it incremented. That makes "the reviewer declined"
        # indistinguishable after the fact from "the reviewer was never reached",
        # which is expensive to tell apart when the run costs a real model call.
        # The category is bounded and carries no model prose, so the diagnostics
        # file stays shareable without a transcript.
        #
        # This fires for a transport or schema failure too, which those paths
        # have already recorded under their own stage. The duplication is the
        # point: every review that ended without a candidate says so under one
        # stage, so the journal can be read for what happened rather than for
        # what is missing from it. A review that produced a candidate needs no
        # such record — the candidate is the record.
        #
        # The signal goes with it, for the same cost and the same reason: a
        # decline reads completely differently depending on which turn was
        # reviewed, and without this the journal cannot say. It is one of the
        # gate's own bounded labels, never anything the user or the model wrote.
        journal.diagnostic("review_outcome", "no_lesson", reason=reason, signal=signal.get("type"))
        capture.discard_turn(event, turn)
        return {"outcome": "no_lesson", "reason": reason}

    fingerprint = proposals.fingerprint(result["lesson"], result["destination_scope"], result["destination_kind"])
    status = journal.fingerprint_status(fingerprint)
    if status is not None:
        # Section 11: a duplicate candidate is suppressed, whether the user
        # accepted this lesson before or declined it. Silent from the outside
        # and identical in state to a decline, so it is journaled for the same
        # reason.
        journal.diagnostic("review_outcome", "duplicate", reason=status)
        capture.discard_turn(event, turn)
        return {"outcome": "duplicate", "status": status}

    candidate = _store_candidate(event, signal, result, fingerprint)
    capture.discard_turn(event, turn)
    gate.note_awaiting_presentation(event.get("session_id"), candidate["candidate_id"])
    return {"outcome": "candidate", "candidate": candidate, "message": wake_message(candidate)}


def _store_candidate(event, signal, result, fingerprint):
    candidate_id = "cand-%s" % uuid.uuid4().hex[:12]
    record = dict(result)
    record.update(
        {
            "candidate_id": candidate_id,
            "fingerprint": fingerprint,
            "session_id": event.get("session_id"),
            "cwd": event.get("cwd"),
            "signal": signal.get("type"),
            "detected_at": int(time.time()),
        }
    )
    record.pop("decision", None)
    store.write_record(store.CANDIDATES, candidate_id, record, ttl=config.CANDIDATE_TTL)
    _add_pending(record)
    return record


def _add_pending(record):
    """Queue the candidate before waking, not after.

    A wake that never lands — the session exited, the message was lost — must
    still leave something for the next SessionStart to surface. Writing this
    first is what makes section 11's session-unavailable case recoverable.
    """
    path = paths.state_path(PENDING)
    existing = store.read_path(path, allow_expired=True) or {}
    entries = existing.get("candidates", [])
    entries = [entry for entry in entries if entry.get("candidate_id") != record["candidate_id"]]
    entries.append(
        {
            "candidate_id": record["candidate_id"],
            "cwd": record.get("cwd"),
            "lesson": record.get("lesson"),
            "expires_at": int(time.time()) + config.CANDIDATE_TTL,
        }
    )
    paths.atomic_write(path, json.dumps({"candidates": entries[-25:]}, sort_keys=True, indent=2) + "\n")
    return path


def pending_candidates(cwd=None, now=None):
    """Live queued candidates, optionally limited to one working directory."""
    now = now if now is not None else time.time()
    record = store.read_path(paths.state_path(PENDING), allow_expired=True) or {}
    entries = []
    for entry in record.get("candidates", []):
        if entry.get("expires_at", 0) <= now:
            continue
        if store.read_record(store.CANDIDATES, entry["candidate_id"]) is None:
            continue
        if cwd and entry.get("cwd") and entry["cwd"] != cwd:
            continue
        entries.append(entry)
    return entries


def drop_pending(candidate_id):
    path = paths.state_path(PENDING)
    record = store.read_path(path, allow_expired=True) or {}
    entries = [entry for entry in record.get("candidates", []) if entry.get("candidate_id") != candidate_id]
    paths.atomic_write(path, json.dumps({"candidates": entries}, sort_keys=True, indent=2) + "\n")


def _owner_summaries(event):
    try:
        return owners.search("", project_dir=event.get("cwd"))
    except OSError:
        return []


def _known_fingerprints():
    return journal.known_fingerprints()


def wake_message(candidate):
    """What Claude sees when the session is woken.

    Written as an instruction rather than a finding: the foreground turn has to
    route the lesson and stage a proposal, and must not edit anything itself.
    """
    return (
        "self-improve: this turn may have produced a reusable lesson.\n"
        "Candidate %s (signal: %s, confidence: %s).\n"
        "Lesson under consideration: %s\n\n"
        "Run the self-improve improve skill with this candidate id to find the "
        "artifact that should own it and stage one exact proposal for the user "
        "to approve. Present the staged proposal verbatim. Do not edit any file "
        "yourself, and do not apply anything: only a command the user types can "
        "authorize a change."
        % (candidate["candidate_id"], candidate.get("signal"), candidate.get("confidence"), candidate.get("lesson"))
    )

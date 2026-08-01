"""The deterministic gate (spec section 6).

The gate's default answer is no. Suppressors are tested first because a reason
not to review is decisive, and the recursion guards are what keep a woken
session from waking itself forever.
"""

import time

import pytest

from selfimprove import capture, config, gate, store

STOP = {"hook_event_name": "Stop", "session_id": "s1", "prompt_id": "t1",
        "cwd": "/project", "last_assistant_message": "Done."}


def turn(events=None, markers=None, prompt=None):
    record = {"events": events or [], "markers": markers or []}
    if prompt:
        record["prompt"] = prompt
    return record


def failure(signature="Bash:pytest", error_class="nonzero_exit"):
    return {"kind": capture.TOOL_FAILURE, "signature": signature,
            "error_class": error_class, "ts": 1}


def success(signature="Bash:pytest", failures=1):
    return {"kind": capture.TOOL_SUCCESS, "signature": signature, "ts": 2,
            "after_failure": True, "prior_error_class": "nonzero_exit",
            "failures_before_success": failures}


# Suppressors.

def test_stop_hook_active_suppresses(state_root):
    assert gate.suppressed(dict(STOP, stop_hook_active=True)) == "stop_hook_active"


def test_background_work_suppresses(state_root):
    """Section 5.5 step 3: a paused session is not a finished one."""
    event = dict(STOP, background_tasks=[{"id": "t", "type": "shell",
                                          "status": "running"}])
    assert gate.suppressed(event) == "background_work_in_flight"


def test_a_scheduled_wakeup_suppresses(state_root):
    event = dict(STOP, session_crons=[{"id": "c", "schedule": "* * * * *"}])
    assert gate.suppressed(event) == "scheduled_wakeup_pending"


def test_a_reviewer_session_suppresses(state_root, monkeypatch):
    """The recursion guard: the reviewer must never review itself."""
    monkeypatch.setenv("SELF_IMPROVE_REVIEWER", "1")
    assert gate.suppressed(STOP) == "reviewer_session"


def test_the_disable_switch_suppresses(state_root, monkeypatch):
    monkeypatch.setenv("SELF_IMPROVE_DISABLE", "1")
    assert gate.suppressed(STOP) == "disabled"


def test_an_unpresented_candidate_suppresses(state_root):
    """The real recursion guard for asyncRewake.

    Waking the session produces another turn and another Stop event, and
    stop_hook_active is not guaranteed to be set for that path.
    """
    store.write_record(store.CANDIDATES, "cand-1", {"lesson": "x"}, ttl=3600)
    gate.note_awaiting_presentation("s1", "cand-1")
    assert gate.suppressed(STOP) == "candidate_awaiting_presentation"


def test_the_awaiting_flag_lifts_when_the_candidate_is_gone(state_root):
    gate.note_awaiting_presentation("s1", "cand-expired")
    assert gate.suppressed(STOP) is None


def test_the_awaiting_flag_is_scoped_to_its_session(state_root):
    store.write_record(store.CANDIDATES, "cand-1", {"lesson": "x"}, ttl=3600)
    gate.note_awaiting_presentation("s1", "cand-1")
    assert gate.suppressed(dict(STOP, session_id="s2")) is None


def test_cooldown_suppresses(state_root):
    gate.note_review()
    assert gate.suppressed(STOP) == "cooldown"


def test_cooldown_expires(state_root):
    gate.note_review(now=time.time() - config.COOLDOWN_SECONDS - 1)
    assert gate.suppressed(STOP) is None


def test_the_daily_limit_suppresses(state_root):
    for _ in range(config.DAILY_REVIEW_LIMIT):
        gate.note_review(now=time.time() - config.COOLDOWN_SECONDS - 1)
    assert gate.suppressed(STOP) == "daily_limit_reached"


def test_no_suppressor_on_a_clean_turn(state_root):
    assert gate.suppressed(STOP) is None


# Signals.

def test_a_retention_request_is_a_signal(state_root):
    signal = gate.evaluate(STOP, turn=turn(markers=["retention"]))
    assert signal["type"] == gate.EXPLICIT_RETENTION
    assert signal["include_prompt"] is True


def test_a_correction_is_a_signal(state_root):
    signal = gate.evaluate(STOP, turn=turn(markers=["correction"]))
    assert signal["type"] == gate.EXPLICIT_CORRECTION
    assert signal["include_prompt"] is True


def test_a_verified_transition_is_a_signal(state_root):
    signal = gate.evaluate(STOP, turn=turn(events=[failure(), success()]))
    assert signal["type"] == gate.VERIFIED_WORKAROUND
    assert signal["include_prompt"] is False


def test_repeated_friction_is_a_signal(state_root):
    events = [failure() for _ in range(config.REPEATED_FRICTION_THRESHOLD)]
    assert gate.evaluate(STOP, turn=turn(events=events))["type"] == \
        gate.REPEATED_FRICTION


def test_friction_below_the_threshold_is_not_a_signal(state_root):
    events = [failure() for _ in range(config.REPEATED_FRICTION_THRESHOLD - 1)]
    assert gate.evaluate(STOP, turn=turn(events=events)) is None


def test_a_confirmation_needs_tool_activity_to_count(state_root):
    """"That worked" about nothing in particular is not evidence."""
    assert gate.evaluate(STOP, turn=turn(markers=["confirmation"])) is None
    signal = gate.evaluate(STOP, turn=turn(markers=["confirmation"],
                                           events=[failure()]))
    assert signal["type"] == gate.CONFIRMED_TECHNIQUE


def test_manual_force_is_always_a_signal(state_root):
    signal = gate.evaluate(STOP, turn=turn(), forced=True, focus="the deploy step")
    assert signal["type"] == gate.MANUAL_FORCE
    assert signal["focus"] == "the deploy step"


def test_manual_force_overrides_rate_limiting_but_not_safety(state_root):
    gate.note_review()
    assert gate.evaluate(STOP, turn=turn(), forced=True) is not None
    assert gate.evaluate(dict(STOP, stop_hook_active=True), turn=turn(),
                         forced=True) is None


# What a rate limit may and may not drop.
#
# A cooldown bounds spending; it is not a reason to stop reading what the user
# typed. These pin the precedence, because getting it wrong is silent: the turn
# is discarded, nothing is journaled, and the only trace is a review that went
# to something else.

@pytest.mark.parametrize("marker", ["correction", "retention"])
def test_a_stated_directive_passes_a_cooldown(state_root, marker):
    """The live wake failure of 2026-07-31.

    Turn 1 was "run the tests with pytest": pytest failed, a retry succeeded,
    and that verified transition is a true signal about ordinary work. It spent
    the review and armed the cooldown. Ten seconds later the user typed "no,
    always use `make test` in this repo, not pytest directly" — and the gate
    dropped it unreviewed, so the reviewer never saw the one thing the whole
    check exists to observe.

    The weaker signals are inferred from work Claude did. A directive is
    inferred from nothing, and it does not come round again.
    """
    gate.note_review()
    assert gate.suppressed(STOP) == "cooldown"

    signal = gate.evaluate(STOP, turn=turn(markers=[marker]))
    assert signal is not None
    assert signal["include_prompt"] is True


@pytest.mark.parametrize("weak", [
    {"events": [failure(), success()]},
    {"events": [failure() for _ in range(config.REPEATED_FRICTION_THRESHOLD)]},
    {"markers": ["confirmation"], "events": [failure()]},
])
def test_an_inferred_signal_does_not_pass_a_cooldown(state_root, weak):
    """The exemption is for the user's own words, not for a strong-looking turn.

    Without this the cooldown would stop bounding anything: these are the
    signals that fire on ordinary work, which is most turns.
    """
    gate.note_review()
    assert gate.evaluate(STOP, turn=turn(**weak)) is None


def test_nothing_automatic_passes_the_daily_limit(state_root):
    """The cooldown paces spending; the daily cap is the ceiling.

    A directive may arrive at any time, so exempting it from the cooldown puts
    no bound on the day. This is the bound.
    """
    for _ in range(config.DAILY_REVIEW_LIMIT):
        gate.note_review(now=time.time() - config.COOLDOWN_SECONDS - 1)
    assert gate.suppressed(STOP) == "daily_limit_reached"
    assert gate.evaluate(STOP, turn=turn(markers=["correction"])) is None
    assert gate.evaluate(STOP, turn=turn(markers=["retention"])) is None


@pytest.mark.parametrize("suppressor", [
    {"stop_hook_active": True},
    {"background_tasks": [{"id": "x"}]},
    {"session_crons": [{"id": "x"}]},
])
def test_a_safety_guard_still_outranks_a_stated_directive(state_root, suppressor):
    """Only the rate limits were relaxed.

    These guards are what stop a woken session waking itself, and a correction
    is exactly the kind of turn that would recur if they were passable.
    """
    event = dict(STOP, **suppressor)
    assert gate.evaluate(event, turn=turn(markers=["correction"])) is None


# The default answer.

def test_an_ordinary_turn_produces_no_signal(state_root):
    assert gate.evaluate(STOP, turn=turn()) is None


def test_ordinary_tool_use_produces_no_signal(state_root):
    events = [{"kind": capture.PROMPT, "ts": 1},
              {"kind": capture.TOOL_FAILURE, "signature": "Bash:ls",
               "error_class": "other", "ts": 2}]
    assert gate.evaluate(STOP, turn=turn(events=events)) is None


def test_a_completed_procedure_needs_both_substance_and_verification(state_root):
    """The weakest signal in section 6, held to the highest bar."""
    events = [failure("Bash:make"), success("Bash:make"),
              failure("Bash:npm"), success("Bash:npm"),
              {"kind": capture.PROMPT, "ts": 5}, {"kind": capture.PROMPT, "ts": 6}]

    quiet = gate.evaluate(dict(STOP, last_assistant_message="Done."),
                          turn=turn(events=[{"kind": capture.PROMPT, "ts": 1}]))
    assert quiet is None

    # Enough activity, but the message claims nothing verified. The transition
    # signal fires first here, which is the correct, more specific answer.
    verified = gate.evaluate(
        dict(STOP, last_assistant_message="All tests pass now."),
        turn=turn(events=events))
    assert verified["type"] in {gate.VERIFIED_WORKAROUND, gate.REUSABLE_COMPLETION}


def test_reusable_completion_fires_without_a_transition(state_root):
    events = [{"kind": capture.TOOL_FAILURE, "signature": "Bash:a",
               "error_class": "other", "ts": index} for index in range(6)]
    signal = gate.evaluate(
        dict(STOP, last_assistant_message="The pipeline is verified end to end."),
        turn=turn(events=events))
    # Six failures of the same signature is repeated friction, which is more
    # specific and therefore correct to report first.
    assert signal["type"] == gate.REPEATED_FRICTION


@pytest.mark.parametrize("suppressor", [
    {"stop_hook_active": True},
    {"background_tasks": [{"id": "x"}]},
    {"session_crons": [{"id": "x"}]},
])
def test_a_suppressed_turn_yields_no_signal_however_strong(state_root, suppressor):
    event = dict(STOP, **suppressor)
    assert gate.evaluate(event, turn=turn(markers=["retention", "correction"],
                                          events=[failure(), success()])) is None


def test_counters_reset_on_a_new_day(state_root, monkeypatch):
    gate._write_counters({"day": "1999-01-01", "count": 99})
    gate.note_review(now=time.time() - config.COOLDOWN_SECONDS - 1)
    assert gate.suppressed({**STOP}) is None

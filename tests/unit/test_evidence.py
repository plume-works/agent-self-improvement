"""The reviewer's input bundle (spec section 7.2).

The bundle is the boundary between captured state and a model call, so what it
may and may not carry is worth pinning down explicitly.
"""

from selfimprove import evidence

EVENTS = [
    {"kind": "tool_failure", "signature": "Bash:pytest", "ts": 1,
     "error_class": "assertion_failed", "tool": "Bash"},
    {"kind": "tool_failure", "signature": "Bash:pytest", "ts": 2,
     "error_class": "assertion_failed", "tool": "Bash"},
    {"kind": "tool_success", "signature": "Bash:pytest", "ts": 3,
     "after_failure": True, "prior_error_class": "assertion_failed",
     "failures_before_success": 2, "tool": "Bash"},
]


def test_bundle_reports_verified_transitions():
    bundle = evidence.build({"events": EVENTS}, {"type": "verified_workaround"})
    assert bundle["transitions"] == [{
        "signature": "Bash:pytest",
        "prior_error_class": "assertion_failed",
        "failures_before_success": 2,
    }]


def test_bundle_omits_the_prompt_unless_the_signal_requires_it():
    """Section 5.1 permits the prompt only for a correction or retention ask."""
    turn = {"events": EVENTS, "prompt": "no, use make test instead"}
    without = evidence.build(turn, {"type": "verified_workaround"})
    assert "user_prompt" not in without

    with_prompt = evidence.build(
        turn, {"type": "explicit_correction", "include_prompt": True})
    assert with_prompt["user_prompt"] == "no, use make test instead"


def test_bundle_scrubs_the_prompt_it_does_include():
    turn = {"events": [], "prompt": "use API_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123"}
    bundle = evidence.build(
        turn, {"type": "explicit_retention", "include_prompt": True})
    assert "ghp_" not in bundle["user_prompt"]


def test_bundle_scrubs_the_final_assistant_message():
    bundle = evidence.build(
        {"events": []}, {"type": "reusable_completion"},
        last_assistant_message="done, the key was sk-abcdefghijklmnopqrstuvwxyz01")
    assert "sk-" not in bundle["last_assistant_message"]


def test_event_summaries_drop_unexpected_fields():
    """A capture bug must not leak a raw payload into a model call."""
    events = [{"kind": "tool_failure", "signature": "Bash:x", "ts": 1,
               "raw_output": "SECRET", "tool_input": {"command": "curl ..."}}]
    bundle = evidence.build({"events": events}, {"type": "repeated_friction"})
    summary = bundle["events"][0]
    assert set(summary) <= {"kind", "signature", "ts", "error_class", "tool",
                            "markers", "count"}
    assert "SECRET" not in str(bundle)


def test_bundle_is_capped():
    events = [{"kind": "tool_failure", "signature": "Bash:x", "ts": index}
              for index in range(500)]
    bundle = evidence.build({"events": events}, {"type": "repeated_friction"})
    assert len(bundle["events"]) == evidence.MAX_EVENTS_IN_BUNDLE
    # The cap keeps the most recent activity, which is what the turn is about.
    assert bundle["events"][-1]["ts"] == 499


def test_owners_are_capped():
    owners = [{"path": "CLAUDE.md"}] * 100
    bundle = evidence.build({"events": []}, {"type": "manual_force"}, owners=owners)
    assert len(bundle["candidate_owners"]) == evidence.MAX_OWNERS_IN_BUNDLE


def test_friction_counts_group_by_signature():
    counts = evidence.friction_counts(EVENTS)
    assert counts == {"Bash:pytest": 2}


def test_friction_threshold():
    assert not evidence.exceeds_friction_threshold(EVENTS, threshold=3)
    assert evidence.exceeds_friction_threshold(EVENTS, threshold=2)


def test_bundle_handles_an_empty_turn():
    bundle = evidence.build(None, {"type": "manual_force"})
    assert bundle["events"] == []
    assert bundle["transitions"] == []

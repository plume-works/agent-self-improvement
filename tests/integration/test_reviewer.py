"""The reviewer subprocess: isolation, envelope handling, and failure modes.

These run the real code path against a stand-in binary, so the argument vector
and environment are the ones a real review would use.
"""

import json
import os

from selfimprove import journal, paths, reviewer, schema

BUNDLE = {
    "signal": {"type": "explicit_correction"},
    "events": [{"kind": "tool_failure", "signature": "Bash:pytest"}],
}


def test_proposal_round_trips(state_root, fake_reviewer):
    fake_reviewer.mode("propose")
    result = reviewer.review(BUNDLE)
    assert result["decision"] == schema.PROPOSE
    assert result["destination_kind"] == "CLAUDE.md"


def test_discard_round_trips(state_root, fake_reviewer):
    fake_reviewer.mode("discard")
    assert reviewer.review(BUNDLE)["decision"] == schema.DISCARD


def test_fenced_output_is_recovered(state_root, fake_reviewer):
    fake_reviewer.mode("fenced")
    assert reviewer.review(BUNDLE)["decision"] == schema.PROPOSE


def test_prose_wrapped_output_is_recovered(state_root, fake_reviewer):
    fake_reviewer.mode("chatty")
    assert reviewer.review(BUNDLE)["decision"] == schema.PROPOSE


def test_malformed_output_becomes_a_discard(state_root, fake_reviewer):
    fake_reviewer.mode("malformed")
    result = reviewer.review(BUNDLE)
    assert result["decision"] == schema.DISCARD
    assert result["discard_reason"] == "not_json"


def test_unknown_field_becomes_a_discard(state_root, fake_reviewer):
    fake_reviewer.mode("unknown_field")
    assert reviewer.review(BUNDLE)["discard_reason"] == "unknown_field"


def test_low_confidence_becomes_a_discard(state_root, fake_reviewer):
    fake_reviewer.mode("low_confidence")
    assert reviewer.review(BUNDLE)["discard_reason"] == "low_confidence"


def test_timeout_becomes_a_silent_discard(state_root, fake_reviewer):
    fake_reviewer.mode("timeout")
    result = reviewer.review(BUNDLE, timeout=1)
    assert result["decision"] == schema.DISCARD
    assert result["discard_reason"] == "timeout"


def test_crash_becomes_a_silent_discard(state_root, fake_reviewer):
    fake_reviewer.mode("crash")
    assert reviewer.review(BUNDLE)["decision"] == schema.DISCARD


def test_authentication_failure_is_classified(state_root, fake_reviewer):
    """Section 11 names authentication failure as its own silent case."""
    fake_reviewer.mode("unauthorized")
    assert reviewer.review(BUNDLE)["discard_reason"] == "unauthenticated"


def test_provider_failures_are_classified_apart_from_a_declined_review(state_root, fake_reviewer):
    """A review that never happened must not look like one that said no.

    Section 11 keeps every one of these silent, but the recorded class is the
    only thing a later investigation has, and "the provider was busy" and "the
    reviewer found no lesson" call for opposite responses.
    """
    for mode, expected in (
        ("rate_limited", "rate_limited"),
        ("overloaded", "overloaded"),
        ("provider_error", "provider_error"),
        ("bad_model", "model_unavailable"),
    ):
        fake_reviewer.mode(mode)
        result = reviewer.review(BUNDLE)
        assert result["decision"] == schema.DISCARD
        assert result["discard_reason"] == expected, mode


def test_empty_output_becomes_a_discard(state_root, fake_reviewer):
    fake_reviewer.mode("empty")
    assert reviewer.review(BUNDLE)["discard_reason"] == "empty_output"


def test_missing_binary_becomes_a_discard(state_root, monkeypatch):
    monkeypatch.setenv("SELF_IMPROVE_REVIEWER_CMD", "/nonexistent/claude")
    assert reviewer.review(BUNDLE)["discard_reason"] == "cli_not_found"


def test_every_failure_is_recorded_as_a_bounded_class(state_root, fake_reviewer):
    fake_reviewer.mode("crash")
    reviewer.review(BUNDLE)
    with open(os.path.join(paths.state_root(), journal.DIAGNOSTICS), encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    assert records
    for record in records:
        assert set(record) <= {"ts", "stage", "error_class", "exception"}
        assert "exploded" not in json.dumps(record)


def test_reviewer_is_invoked_with_no_tools(state_root, fake_reviewer):
    """Spec section 7.3: the reviewer must hold no capability to act."""
    fake_reviewer.mode("discard")
    reviewer.review(BUNDLE)
    argv = fake_reviewer.recorded_argv()

    assert "-p" in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--disallowedTools") + 1] == "*"
    assert "--strict-mcp-config" in argv
    assert json.loads(argv[argv.index("--settings") + 1]) == {"disableAllHooks": True}
    assert argv[argv.index("--max-turns") + 1] == "1"
    assert argv[argv.index("--output-format") + 1] == "json"


def test_reviewer_uses_the_configured_model(state_root, fake_reviewer, monkeypatch):
    fake_reviewer.mode("discard")
    reviewer.review(BUNDLE)
    assert fake_reviewer.recorded_argv()[fake_reviewer.recorded_argv().index("--model") + 1] == "sonnet"

    monkeypatch.setenv("SELF_IMPROVE_REVIEW_MODEL", "haiku")
    reviewer.review(BUNDLE)
    argv = fake_reviewer.recorded_argv()
    assert argv[argv.index("--model") + 1] == "haiku"


def test_reviewer_system_prompt_is_the_committed_file(state_root, fake_reviewer):
    fake_reviewer.mode("discard")
    reviewer.review(BUNDLE)
    argv = fake_reviewer.recorded_argv()
    prompt = argv[argv.index("--system-prompt-file") + 1]
    assert prompt.endswith("reviewer/prompt.md")
    assert os.path.exists(prompt)


def test_bundle_reaches_the_reviewer_on_stdin(state_root, fake_reviewer):
    """The reviewer needs no filesystem access because the evidence comes in."""
    fake_reviewer.mode("discard")
    reviewer.review(BUNDLE)
    assert fake_reviewer.recorded_bundle() == BUNDLE


def test_reviewer_environment_marks_the_child_and_hides_state(state_root):
    environment = reviewer.build_environment()
    assert environment["SELF_IMPROVE_REVIEWER"] == "1"
    assert "SELF_IMPROVE_STATE_DIR" not in environment
    assert "CLAUDE_PLUGIN_DATA" not in environment


def test_reviewer_runs_at_the_configured_effort(state_root, monkeypatch):
    """Medium by default, and carried by the environment rather than a flag.

    The flag is the tempting shape, and it is the wrong one: review failure is
    silent, so a CLI too old to know `--effort` would abort every review with
    nothing on screen to explain it. An unknown variable is ignored, and the
    review still happens at the default level.
    """
    monkeypatch.delenv("SELF_IMPROVE_REVIEW_EFFORT", raising=False)
    assert reviewer.build_environment()["CLAUDE_CODE_EFFORT_LEVEL"] == "medium"
    assert "--effort" not in reviewer.build_command("/tmp/prompt.md")

    monkeypatch.setenv("SELF_IMPROVE_REVIEW_EFFORT", "high")
    assert reviewer.build_environment()["CLAUDE_CODE_EFFORT_LEVEL"] == "high"


def test_an_empty_reviewer_effort_leaves_the_cli_to_decide(state_root, monkeypatch):
    monkeypatch.setenv("SELF_IMPROVE_REVIEW_EFFORT", "")
    monkeypatch.delenv("CLAUDE_CODE_EFFORT_LEVEL", raising=False)
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in reviewer.build_environment()


def test_an_empty_reviewer_effort_also_drops_an_inherited_level(state_root, monkeypatch):
    """The escape hatch has to survive a session that already set the variable.

    The reviewer inherits the environment of the session it reflects on, so a
    parent that exported `CLAUDE_CODE_EFFORT_LEVEL` would otherwise hand the
    reviewer that level even though the user asked for the CLI default.
    """
    monkeypatch.setenv("SELF_IMPROVE_REVIEW_EFFORT", "")
    monkeypatch.setenv("CLAUDE_CODE_EFFORT_LEVEL", "high")
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in reviewer.build_environment()


def test_reviewer_prompt_forbids_tool_use_in_its_own_text():
    """The prompt should not invite behavior the flags already prevent."""
    with open(os.path.join(paths.plugin_root(), "reviewer", "prompt.md"), encoding="utf-8") as handle:
        text = handle.read()
    assert "You have no tools" in text
    assert "discard" in text

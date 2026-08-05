"""How the smoke harness reads a session that went wrong.

The smoke checks spend real model usage, so their reliability rests on telling
three outcomes apart: the plugin misbehaved, the provider was unavailable, and
the session never answered at all. Getting that wrong once already turned a
provider outage into three "failures" pointing at innocent code, so the
classification is checked here, offline, where it costs nothing.
"""

from tests.smoke.conftest import Session


def session(events, returncode=0, stderr=""):
    return Session("/tmp/project", events, returncode, stderr, 1.0)


def assistant(text, **extra):
    event = {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}
    event.update(extra)
    return event


def result(**fields):
    return dict({"type": "result", "subtype": "success", "is_error": False}, **fields)


HEALTHY = [assistant("ready"), result(result="ready")]


def test_a_completed_turn_is_neither_a_provider_failure_nor_a_failure():
    healthy = session(HEALTHY)
    assert healthy.provider_failure() is None
    assert healthy.failure() is None


def test_an_api_error_message_is_recognized_even_though_the_session_exits_zero():
    """The failure mode that made the suite lie.

    A rate-limited turn still emits an assistant message and still exits zero.
    The message is the error text, so the only thing distinguishing it from a
    real answer is the flag.
    """
    limited = session(
        [
            assistant("API Error: 429 rate_limit_error", is_api_error_message=True, error="rate_limit_error"),
            result(is_error=True, terminal_reason="api_error", api_error_status=429),
        ]
    )
    assert limited.provider_failure() == "rate_limit_error"


def test_a_status_only_provider_failure_is_named_from_the_status():
    overloaded = session(
        [
            result(is_error=True, terminal_reason="api_error", api_error_status=529, result="please try again"),
        ]
    )
    assert overloaded.provider_failure() == "overloaded"


def test_a_session_that_never_started_is_a_provider_failure_only_when_it_says_so():
    unauthenticated = session([], returncode=1, stderr="Invalid API key. Please run /login.")
    assert unauthenticated.provider_failure() == "invalid api key"

    broken = session([], returncode=1, stderr="cannot find module ./cli.js")
    assert broken.provider_failure() is None
    assert "exited 1" in broken.failure()


def test_durations_that_look_like_statuses_are_not_read_as_failures():
    """Envelope numbers collide with status codes; only the status field counts."""
    healthy = session([assistant("ready"), result(result="ready", duration_ms=429, num_turns=503)])
    assert healthy.provider_failure() is None
    assert healthy.failure() is None


def test_an_exhausted_turn_fails_rather_than_skipping():
    exhausted = session([assistant("working on it"), result(subtype="error_max_turns", is_error=True)])
    assert exhausted.provider_failure() is None
    assert "error_max_turns" in exhausted.failure()


def test_a_session_with_no_reply_fails_rather_than_passing_vacuously():
    silent = session([result(result="")])
    assert silent.provider_failure() is None
    assert silent.failure() == "the session produced no assistant message"

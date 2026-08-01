"""Which model, and how much effort, the smoke and wake driving sessions use.

Neither can be observed without spending model usage, so what is checked here is
the argument vector: that a driving session is pinned rather than inheriting
whatever the developer's CLI prefers, and that the escape hatch back to that
default still exists. The reviewer's own dials are separate and are covered by
tests/integration/test_reviewer.py.
"""

from tests.smoke import conftest


def test_the_driving_session_is_pinned_by_default(monkeypatch):
    """Nothing set: sonnet at low effort, not the CLI default of high.

    This is the whole point of the knobs — an unconfigured `make smoke` should
    not quietly bill Opus usage at high effort for checks that do not depend on
    either.
    """
    monkeypatch.delenv("SMOKE_MODEL", raising=False)
    monkeypatch.delenv("SMOKE_EFFORT", raising=False)
    assert conftest.smoke_model() == "sonnet"
    assert conftest.smoke_effort() == "low"
    assert conftest.session_args() == ["--model", "sonnet", "--effort", "low"]


def test_overrides_are_honored(monkeypatch):
    monkeypatch.setenv("SMOKE_MODEL", "haiku")
    monkeypatch.setenv("SMOKE_EFFORT", "high")
    assert conftest.session_args() == ["--model", "haiku", "--effort", "high"]


def test_an_empty_override_restores_the_cli_default(monkeypatch):
    """A model- or effort-specific failure has to be reproducible against the
    real default, so passing no flag at all must remain reachable."""
    monkeypatch.setenv("SMOKE_MODEL", "")
    monkeypatch.setenv("SMOKE_EFFORT", "")
    assert conftest.smoke_model() is None
    assert conftest.smoke_effort() is None
    assert conftest.session_args() == []

    monkeypatch.setenv("SMOKE_MODEL", "   ")
    monkeypatch.setenv("SMOKE_EFFORT", "   ")
    assert conftest.session_args() == []


def test_effort_is_a_flag_and_never_an_inherited_variable(monkeypatch):
    """The harness must not export CLAUDE_CODE_EFFORT_LEVEL.

    That variable is inherited, so it would reach the reviewer subprocess
    running inside the driving session and override the reviewer's own level —
    silently making the component under test cheaper than it ships.
    """
    monkeypatch.delenv("SMOKE_EFFORT", raising=False)
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in conftest.session_args()
    assert conftest.effort_args() == ["--effort", "low"]

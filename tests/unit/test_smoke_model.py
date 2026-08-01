"""Which model, and how much effort, the smoke and wake driving sessions use.

Neither can be observed without spending model usage, so what is checked here is
the argument vector: that a driving session is pinned rather than inheriting
whatever the developer's CLI prefers, and that the escape hatch back to that
default still exists. The reviewer's own dials are separate and are covered by
tests/integration/test_reviewer.py.
"""

import pytest

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


def test_auto_memory_is_off_by_default(monkeypatch):
    """Claude Code's own auto memory records the lesson during the turn.

    It gets there before this plugin's Stop hook runs, so the reviewer is handed
    a turn whose lesson is already owned and correctly declines. The wake check
    is not a race between two learning systems, so it does not enter one.
    """
    monkeypatch.delenv("SMOKE_AUTO_MEMORY", raising=False)
    assert conftest.auto_memory_enabled() is False
    assert conftest.with_auto_memory({})["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_auto_memory_can_be_turned_back_on(monkeypatch, value):
    monkeypatch.setenv("SMOKE_AUTO_MEMORY", value)
    assert conftest.auto_memory_enabled() is True
    assert conftest.with_auto_memory({})["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "0"


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "  "])
def test_falsey_values_leave_auto_memory_off(monkeypatch, value):
    monkeypatch.setenv("SMOKE_AUTO_MEMORY", value)
    assert conftest.auto_memory_enabled() is False


def test_an_explicit_argument_outranks_the_environment(monkeypatch):
    """The paired checks choose per test, not per run.

    `make wake` and `make wake-memory` must observe what they say they observe
    whatever the developer exported.
    """
    monkeypatch.setenv("SMOKE_AUTO_MEMORY", "1")
    assert conftest.with_auto_memory({}, False)["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    monkeypatch.setenv("SMOKE_AUTO_MEMORY", "0")
    assert conftest.with_auto_memory({}, True)["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "0"


def test_auto_memory_is_never_left_to_the_developers_settings(monkeypatch):
    """Always set, either way — never inherited.

    `autoMemoryEnabled` is a user setting, so an unset variable means the check
    behaves differently for different people. That is exactly the failure this
    dial exists to prevent: a decline that reproduces for one person and not
    another, on a check that costs a live run to observe.
    """
    monkeypatch.delenv("SMOKE_AUTO_MEMORY", raising=False)
    for enabled in (None, True, False):
        assert "CLAUDE_CODE_DISABLE_AUTO_MEMORY" in conftest.with_auto_memory({}, enabled)
    assert conftest.runner_environment()["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"


def test_effort_is_a_flag_and_never_an_inherited_variable(monkeypatch):
    """The harness must not export CLAUDE_CODE_EFFORT_LEVEL.

    That variable is inherited, so it would reach the reviewer subprocess
    running inside the driving session and override the reviewer's own level —
    silently making the component under test cheaper than it ships.
    """
    monkeypatch.delenv("SMOKE_EFFORT", raising=False)
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in conftest.session_args()
    assert conftest.effort_args() == ["--effort", "low"]

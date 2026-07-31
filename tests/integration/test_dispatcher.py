"""The dispatcher as a hook actually invokes it: through ``scripts/si``."""

import json
import os
import subprocess

from selfimprove import paths, store
from tests.conftest import PLUGIN_ROOT, SI


def test_entry_point_is_executable():
    assert os.access(SI, os.X_OK), "scripts/si must be executable to run as a hook"


def test_shim_ignores_a_stale_python3_on_path(run_si, tmp_path):
    """The failure this shim exists to prevent.

    A developer machine can easily have an old virtualenv first on PATH; the
    machine this plugin was written on resolves ``python3`` to a 2019 build of
    3.6.5. Discovery must find a real interpreter anyway.
    """
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    stale = fake_bin / "python3"
    stale.write_text("#!/bin/sh\nexit 47\n")
    stale.chmod(0o755)

    result = run_si("self-test", env={"PATH": "%s:%s" % (fake_bin, os.environ["PATH"])})
    assert result.returncode == 0, result.stderr


def test_self_test_reports_ok(run_si):
    result = run_si("self-test")
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_self_test_fails_when_state_root_is_unwritable(run_si, tmp_path):
    blocked = tmp_path / "blocked"
    blocked.mkdir(mode=0o500)
    try:
        result = run_si("self-test", env={"SELF_IMPROVE_STATE_DIR": str(blocked / "s")})
        assert result.returncode == 1
        assert "state root" in result.stderr
    finally:
        blocked.chmod(0o700)


def test_status_reports_json(run_si):
    result = run_si("status")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["candidates"] == 0
    assert report["review_model"] == "sonnet"


def test_unknown_subcommand_is_a_usage_error(run_si):
    result = run_si("no-such-subcommand")
    assert result.returncode == 2
    assert "invalid choice" in result.stderr


def test_disable_switch_short_circuits_every_subcommand(run_si):
    result = run_si("status", env={"SELF_IMPROVE_DISABLE": "1"})
    assert result.returncode == 0
    assert result.stdout == ""


def test_session_end_sweeps_expired_state(run_si, state_root, monkeypatch):
    monkeypatch.setenv("SELF_IMPROVE_STATE_DIR", str(state_root))
    store.write_record(store.TURNS, "t1", {}, ttl=-1, subdir="s1")
    store.write_record(store.CANDIDATES, "c1", {}, ttl=3600)

    event = json.dumps({"hook_event_name": "SessionEnd", "session_id": "s1"})
    result = run_si("session-end", stdin=event)

    assert result.returncode == 0, result.stderr
    assert not os.path.exists(
        os.path.join(paths.state_root(), store.TURNS, "s1", "t1.json")
    )
    assert store.read_record(store.CANDIDATES, "c1") is not None


def test_session_end_is_silent(run_si):
    result = run_si("session-end", stdin='{"hook_event_name":"SessionEnd"}')
    assert result.stdout == ""


def test_hook_handlers_fail_open(run_si, state_root, monkeypatch):
    """Spec section 11: a capture failure must not disturb the completed task."""
    result = run_si("session-end", stdin="{not json at all")
    assert result.returncode == 0


def test_hooks_manifest_is_valid_and_uses_the_plugin_root_placeholder():
    with open(os.path.join(PLUGIN_ROOT, "hooks", "hooks.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    for entries in manifest["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert hook["command"].startswith("${CLAUDE_PLUGIN_ROOT}/")
                assert isinstance(hook["args"], list) and hook["args"]
                assert hook["timeout"] >= 1


def test_plugin_manifest_declares_the_expected_name():
    manifest_path = os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    # The name namespaces the skills as /self-improve:<skill>.
    assert manifest["name"] == "self-improve"


def test_runtime_imports_under_the_oldest_supported_interpreter():
    """Import the package under 3.9 when that interpreter is available.

    The AST guard proves nothing outside the standard library is imported; this
    proves the code actually parses and loads on the version being targeted.
    """
    system_python = "/usr/bin/python3"
    if not os.path.exists(system_python):
        return
    probe = (
        "import sys; sys.path.insert(0, %r);"
        "import selfimprove.commands, selfimprove.paths, selfimprove.redact,"
        "selfimprove.store, selfimprove.journal, selfimprove.locking,"
        "selfimprove.hookio, selfimprove.config;"
        "print(sys.version_info[:2])" % PLUGIN_ROOT
    )
    result = subprocess.run([system_python, "-c", probe],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
